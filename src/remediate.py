"""Turn "this doc is wrong" into an actual fix the author can accept.

Two delivery paths, because GitHub only accepts a ```suggestion block on lines
that are part of the diff:

- doc file IS in the diff  → inline review comment with a suggestion block
- doc file is NOT in the diff → optional follow-up branch + PR (`docs_fix_pr`),
  otherwise the patch is folded into the summary comment as a plain diff.
"""
import base64
import json
from pathlib import Path

import untrusted
from agent import READ_ONLY_TOOLS, record_usage
from agent import run_structured as _default_runner
from gh import run_gh
from verify import LANGUAGES

FIXABLE_STATUSES = ("STALE", "WRONG", "FABRICATED")
BRANCH_PREFIX = "pr-sentinel/docs"

PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_snippet": {"type": "string",
                                    "description": "exact text to replace, copied from the file"},
                    "new_snippet": {"type": "string", "description": "replacement text"},
                    "line_hint": {"type": "integer",
                                  "description": "1-based line where old_snippet starts"},
                    "why": {"type": "string", "description": "what the code actually does"},
                },
                "required": ["path", "old_snippet", "new_snippet", "line_hint", "why"],
            },
        },
    },
    "required": ["patches"],
}

SYSTEM_PROMPT = (
    "You correct documentation so it matches the code. You copy `old_snippet` "
    "verbatim from the file — byte for byte, including indentation — so it can be "
    "replaced mechanically. You change only what is factually wrong."
    + untrusted.SYSTEM_CLAUSE
)


def fixable_docs(findings: dict) -> list[dict]:
    return [d for d in findings.get("docs") or []
            if d.get("status") in FIXABLE_STATUSES and d.get("path")]


def build_prompt(docs: list[dict], found: list[str] | None = None,
                 language: str = "en") -> str:
    # `what` is the review agent's account of a doc, written from repository
    # content — second-hand, but the same provenance as the text it describes.
    listed = untrusted.block(
        "Doc findings",
        "\n".join(f"- {d['path']} ({d['status']}): {d.get('what', '')}" for d in docs),
        found=found)
    prompt = f"""
A review found these documentation files out of sync with the code:

{listed}

For each one: read the file, read the code it describes, and produce the minimal
text replacement that makes the doc true. Copy `old_snippet` exactly as it
appears in the file so it can be replaced programmatically — if you cannot
reproduce it exactly, skip that file rather than guessing.
""".strip()
    if language not in ("", "en"):
        name = LANGUAGES.get(language, language)
        # Deliberately split: `new_snippet` is pasted into the file through a
        # GitHub suggestion block, so translating it would rewrite the document
        # in a language its readers did not choose.
        prompt += (f"\n\nWrite `why` in {name}. Write `old_snippet` and "
                   f"`new_snippet` in the same language as the document itself — "
                   f"never translate the documentation text you are replacing.")
    return prompt


def draft_patches(findings: dict, cfg: dict, workspace: Path, session_dir: Path,
                  runner=_default_runner) -> list[dict]:
    """Ask the agent for concrete doc patches. Writes patches.json, returns them."""
    docs = fixable_docs(findings)
    if not docs:
        return []
    found: list[str] = []
    result = runner(
        build_prompt(docs, found=found, language=cfg.get("language", "en")),
        schema=PATCH_SCHEMA,
        cwd=workspace,
        tools=READ_ONLY_TOOLS,
        model=cfg.get("model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=cfg.get("max_turns", 30),
        effort=cfg.get("effort"),
        provider=cfg.get("provider"),
    )
    patches = [p for p in result.data.get("patches") or []
               if p.get("path") and p.get("old_snippet") and p.get("new_snippet")]

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "patches.json").write_text(json.dumps(patches, indent=2))
    record_usage(session_dir, "remediate", result)
    untrusted.record_neutralized(session_dir, "remediate", found)
    return patches


def suggestion_body(patch: dict) -> str:
    """A GitHub suggestion block GitHub can apply with one click."""
    return (f"**Docs out of sync** — {patch.get('why', '')}\n\n"
            f"```suggestion\n{patch['new_snippet']}\n```")


def diff_block(patch: dict) -> str:
    """A plain diff for docs that cannot carry a suggestion block."""
    old = "\n".join(f"-{line}" for line in patch["old_snippet"].splitlines())
    new = "\n".join(f"+{line}" for line in patch["new_snippet"].splitlines())
    return (f"**{patch['path']}** (line ~{patch.get('line_hint', '?')}) — "
            f"{patch.get('why', '')}\n\n```diff\n{old}\n{new}\n```")


def suggestion_comments(patches: list[dict], snapshot: dict) -> tuple[list[dict], list[dict]]:
    """Doc patches that can carry a ```suggestion block, as review comments.

    Returns `(comments, leftover)`. A comment is the `{path, line, body}` shape
    annotations.py uses, so both sources go out in one review. GitHub only
    accepts a suggestion on a line inside the diff, which is what leftover means.
    """
    in_diff = {f["filename"] for f in snapshot.get("files", [])}
    head_sha = snapshot.get("head_sha", "")
    comments, leftover = [], []
    for patch in patches:
        line = patch.get("line_hint")
        if (patch["path"] not in in_diff or not head_sha
                or not isinstance(line, int) or line < 1):
            leftover.append(patch)
            continue
        comments.append({"path": patch["path"], "line": line,
                         "body": suggestion_body(patch)})
    return comments, leftover


def comment_section(patches: list[dict]) -> str:
    """Leftover patches, folded into the summary comment."""
    if not patches:
        return ""
    blocks = "\n\n".join(diff_block(p) for p in patches)
    return ("<details>\n\n<summary>Suggested documentation fixes "
            f"({len(patches)})</summary>\n\n{blocks}\n\n</details>")


def apply_to_workspace(patches: list[dict], workspace: Path) -> tuple[list[dict], list[dict]]:
    """Apply patches to files on disk. Returns (applied, rejected)."""
    applied, rejected = [], []
    for patch in patches:
        target = (workspace / patch["path"]).resolve()
        if not str(target).startswith(str(workspace.resolve())) or not target.exists():
            rejected.append({**patch, "reason": "file not found in workspace"})
            continue
        text = target.read_text()
        if patch["old_snippet"] not in text:
            rejected.append({**patch, "reason": "old_snippet did not match the file"})
            continue
        target.write_text(text.replace(patch["old_snippet"], patch["new_snippet"], 1))
        applied.append(patch)
    return applied, rejected


def create_docs_fix_pr(owner: str, repo: str, n: int, patches: list[dict],
                       snapshot: dict, workspace: Path, *, gh=run_gh) -> str | None:
    """Open a follow-up PR against the PR's own head branch. Opt-in (`docs_fix_pr`).

    Uses the GitHub contents API rather than `git push` so it needs no local push
    credentials. Returns the PR URL, or None when nothing could be applied.
    """
    applied, _ = apply_to_workspace(patches, workspace)
    if not applied:
        return None

    branch = f"{BRANCH_PREFIX}-{n}"
    head_sha = snapshot.get("head_sha", "")
    try:
        gh(["api", f"repos/{owner}/{repo}/git/refs", "-f", f"ref=refs/heads/{branch}",
            "-f", f"sha={head_sha}"])
    except RuntimeError as e:
        print(f"[remediate] branch {branch} not created (may already exist): {e}")

    changed = sorted({p["path"] for p in applied})
    for path in changed:
        content = base64.b64encode((workspace / path).read_bytes()).decode()
        args = ["api", f"repos/{owner}/{repo}/contents/{path}", "-X", "PUT",
                "-f", f"message=docs: sync {path} with the code",
                "-f", f"content={content}", "-f", f"branch={branch}"]
        try:
            existing = gh(["api", f"repos/{owner}/{repo}/contents/{path}?ref={branch}"])
            if isinstance(existing, dict) and existing.get("sha"):
                args += ["-f", f"sha={existing['sha']}"]
        except RuntimeError:
            pass
        gh(args)

    body = ("Documentation fixes for #{n}, generated by PR Sentinel.\n\n"
            + "\n".join(f"- `{p}`" for p in changed)).format(n=n)
    result = gh(["api", f"repos/{owner}/{repo}/pulls",
                 "-f", f"title=docs: sync docs with code (#{n})",
                 "-f", f"head={branch}", "-f", f"base={snapshot['head']}",
                 "-f", f"body={body}"])
    return result.get("html_url") if isinstance(result, dict) else None
