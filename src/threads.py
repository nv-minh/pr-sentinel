"""The conversation loop: react to what the author replies on the PR.

When someone answers the bot ("already refactored, see the new commit"), a full
re-review is wasteful. This module collects the replies and re-runs the verify
agent by *resuming its previous session*, so it only pays for the delta.
"""
import json
from pathlib import Path

import untrusted
from agent import BASH_TOOLS, READ_ONLY_TOOLS, record_usage
from agent import run_structured as _default_runner
from gh import run_gh
from session_store import FileSessionStore
from synthesize import MARKER
from verify import FINDINGS_SCHEMA, SYSTEM_PROMPT, validate_findings


def _bot_comment(comments: list) -> dict | None:
    for c in comments:
        if MARKER in (c.get("body") or ""):
            return c
    return None


def fetch_replies(owner: str, repo: str, n: int, *, gh=run_gh) -> list[dict]:
    """Comments written after the bot's review comment, by anyone else.

    Covers both conversation comments and inline review replies; the bot's own
    comments are excluded so it never answers itself.

    The floor is the bot comment's `created_at`, never its `updated_at`: the
    bot PATCHes its comment in place at the end of every run, which advances
    `updated_at` past any reply that landed while that run was in flight —
    such a reply would otherwise be invisible forever. Stale results are
    filtered out by `unseen()` against `replies.json` instead.
    """
    issue_comments = gh(["api", f"repos/{owner}/{repo}/issues/{n}/comments", "--paginate"])
    bot = _bot_comment(issue_comments)
    if bot is None:
        return []
    since = bot.get("created_at") or bot.get("updated_at") or ""
    bot_login = (bot.get("user") or {}).get("login", "")

    replies: list[dict] = []
    for c in issue_comments:
        if (c.get("created_at") or "") > since and (c.get("user") or {}).get("login") != bot_login:
            replies.append({"id": c.get("id"), "source": "conversation",
                            "author": (c.get("user") or {}).get("login", ""),
                            "created_at": c.get("created_at", ""),
                            "body": c.get("body", ""), "path": None})

    try:
        review_comments = gh(["api", f"repos/{owner}/{repo}/pulls/{n}/comments", "--paginate"])
    except RuntimeError:
        review_comments = []
    for c in review_comments:
        if (c.get("created_at") or "") > since and (c.get("user") or {}).get("login") != bot_login:
            replies.append({"id": c.get("id"), "source": "review",
                            "author": (c.get("user") or {}).get("login", ""),
                            "created_at": c.get("created_at", ""),
                            "body": c.get("body", ""), "path": c.get("path")})

    replies.sort(key=lambda r: r.get("created_at") or "")
    return replies


def unseen(session_dir: Path, replies: list[dict]) -> list[dict]:
    """Replies this session has not answered yet."""
    path = session_dir / "replies.json"
    try:
        seen = {r.get("id") for r in json.loads(path.read_text())
                if isinstance(r, dict)}
    except (OSError, json.JSONDecodeError):
        seen = set()
    return [r for r in replies if r.get("id") not in seen]


def save_replies(session_dir: Path, replies: list[dict]) -> None:
    """Record replies as answered. Merges by id — the set only grows.

    The caller passes only what this run actually answered, never a fresh
    fetch of everything: a reply that landed mid-run must stay unseen so the
    next run answers it. And because fetch_replies re-returns every reply
    since the bot's first comment, overwriting would resurrect earlier
    rounds' replies as unseen.
    """
    path = session_dir / "replies.json"
    try:
        answered = json.loads(path.read_text())
        merged = {r.get("id"): r for r in answered if isinstance(r, dict)}
    except (OSError, json.JSONDecodeError):
        merged = {}
    for r in replies:
        merged[r.get("id")] = r
    session_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(merged.values()), indent=2))


def previous_session(session_dir: Path) -> str:
    try:
        return json.loads((session_dir / "verify-meta.json").read_text()).get("session_id", "")
    except (OSError, json.JSONDecodeError):
        return ""


def load_previous_findings(session_dir: Path) -> dict | None:
    """The findings of the last review, or None if they did not survive."""
    try:
        return json.loads((session_dir / "findings.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def can_resume(session_dir: Path, session_id: str) -> bool:
    """True when the transcript for `session_id` is on disk next to the findings.

    A session id whose transcript is gone is worse than no session id: the SDK
    would fail the resume mid-run instead of taking the cheaper stateless path.
    """
    if not session_id:
        return False
    return FileSessionStore(session_dir).path_for({"session_id": session_id}).exists()


def build_followup_prompt(replies: list[dict], new_commits: list[dict],
                          previous_findings: dict | None = None,
                          found: list[str] | None = None) -> str:
    quoted = "\n\n".join(
        f"[{r['source']}] {r['author']}"
        + (f" on {r['path']}" if r.get("path") else "") + ":\n"
        + untrusted.block(f"Reply {i}", r["body"], found=found)
        for i, r in enumerate(replies, 1))
    commits = "\n".join(f"- {c['sha'][:8]} {c['message'].splitlines()[0]}"
                        for c in new_commits if c.get("message")) or "- (no new commits)"
    carried = ""
    if previous_findings is not None:
        carried = ("\nPrevious findings — your own verdicts from the earlier "
                   "review, carried over because the session could not be "
                   "resumed. Treat them as your prior conclusions, re-check the "
                   "ones these replies and commits affect, and keep the rest:\n"
                   + untrusted.block("Previous findings",
                                     json.dumps(previous_findings, indent=2),
                                     found=found) + "\n")
    return f"""
The author replied to your review. The workspace is now at the latest commit.

New commits since your review:
{commits}

Replies:
{quoted}
{carried}
Re-check only what these replies and commits affect: read the current code for
those parts, then return the COMPLETE findings object again — carry over the
verdicts that did not change, update the ones that did, and drop questions the
author has now answered. Evidence must still be real `file:line` references from
the current code.
""".strip()


def run_followup(cfg: dict, workspace: Path, session_dir: Path, snapshot: dict,
                 replies: list[dict], new_commits: list[dict],
                 runner=_default_runner) -> dict:
    """Resume the verify session to answer replies cheaply.

    Raises RuntimeError when the session cannot be resumed — the caller then
    falls back to a full `run_verify`.
    """
    session_id = previous_session(session_dir)
    resuming = can_resume(session_dir, session_id)
    carried = None if resuming else load_previous_findings(session_dir)
    if not resuming and carried is None:
        raise RuntimeError("no previous verify session to resume")
    mode = (f"resuming {session_id}" if resuming
            else "stateless (transcript gone, carrying previous findings)")
    print(f"[threads] follow-up: {mode}")

    tools = BASH_TOOLS if cfg.get("allow_bash") else READ_ONLY_TOOLS
    found: list[str] = []
    result = runner(
        build_followup_prompt(replies, new_commits, previous_findings=carried,
                              found=found),
        schema=FINDINGS_SCHEMA,
        cwd=workspace,
        tools=tools,
        model=cfg.get("model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=cfg.get("max_turns", 40),
        max_budget_usd=cfg.get("max_budget_usd"),
        resume=session_id if resuming else None,
        session_dir=session_dir,
        provider=cfg.get("provider"),
    )
    findings = validate_findings(result.data)

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "findings.json").write_text(json.dumps(findings, indent=2))
    (session_dir / "verify-meta.json").write_text(json.dumps(
        {"session_id": result.session_id, "head_sha": snapshot.get("head_sha", "")}, indent=2))
    record_usage(session_dir, "followup", result)
    untrusted.record_neutralized(session_dir, "followup", found)
    return findings
