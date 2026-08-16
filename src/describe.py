"""Draft a PR description when the author did not write a usable one.

The draft is only ever *proposed* in the review comment unless `auto_describe`
is switched on in prsentinel.yml — rewriting someone's PR body without asking is
the kind of thing a bot should need permission for.
"""
import json
from pathlib import Path

from agent import record_usage
from agent import run_structured as _default_runner

MIN_BODY_CHARS = 120

DESCRIPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "description": {"type": "string", "description": "markdown PR description"},
        "summary": {"type": "string", "description": "one line, what this PR does"},
    },
    "required": ["description", "summary"],
}

SYSTEM_PROMPT = (
    "You write pull request descriptions from the actual diff. You describe only "
    "what the code shows — no speculation about intent, no invented ticket "
    "numbers, no praise. Plain, specific engineering prose."
)

TEMPLATE = """## What
<what changed, 1-3 sentences>

## Why
<the problem this solves, or "not stated in the diff">

## How
- <key implementation points>

## Impact
- <APIs, schemas, behaviour, or docs affected>

## Testing
- <tests added or changed; say "none" when there are none>"""


def needs_description(snapshot: dict, min_chars: int = MIN_BODY_CHARS) -> bool:
    """True when the PR body is empty or too thin to carry any claim."""
    body = (snapshot.get("body") or "").strip()
    return len(body) < min_chars


def build_prompt(snapshot: dict) -> str:
    files = [f"- {f['filename']} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
             for f in snapshot.get("files", [])]
    commits = [f"- {c['message'].splitlines()[0]}" for c in snapshot.get("commits", [])
               if c.get("message")]
    patches = []
    for f in snapshot.get("files", [])[:20]:
        if f.get("patch"):
            patches.append(f"### {f['filename']}\n```diff\n{f['patch']}\n```")
    return f"""
Write a pull request description for this change.

Title: {snapshot.get('title', '')}
Existing body: {snapshot.get('body') or '(empty)'}

Commits:
{chr(10).join(commits) if commits else '- (none)'}

Files changed:
{chr(10).join(files) if files else '- (none)'}

Diff:
{chr(10).join(patches) if patches else '(no textual diff available)'}

Follow this template exactly:

{TEMPLATE}
""".strip()


def draft_description(snapshot: dict, cfg: dict, session_dir: Path,
                      runner=_default_runner) -> dict:
    """Generate a description draft. Writes description.json, returns it."""
    result = runner(
        build_prompt(snapshot),
        schema=DESCRIPTION_SCHEMA,
        model=cfg.get("claims_model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=2,
    )
    draft = result.data
    if not isinstance(draft, dict) or not draft.get("description"):
        raise RuntimeError("invalid description response: missing 'description'")

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "description.json").write_text(json.dumps(draft, indent=2))
    record_usage(session_dir, "describe", result)
    return draft


def comment_section(draft: dict) -> str:
    """The proposed description, folded into the review comment."""
    return ("<details>\n\n<summary>Proposed PR description (the current one is "
            f"empty or too short)</summary>\n\n{draft['description']}\n\n</details>")
