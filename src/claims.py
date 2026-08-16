"""Phase 2: split the PR description into verifiable claims."""
import json
from pathlib import Path

import untrusted
from agent import record_usage
from agent import run_structured as _default_runner

CATEGORIES = ["feature", "bugfix", "refactor", "perf", "ux", "docs"]

CLAIMS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "C1, C2, ..."},
                    "text": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "files": {"type": "array", "items": {"type": "string"}},
                    "docs": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["id", "text", "category", "files", "docs"],
            },
        },
    },
    "required": ["claims"],
}

SYSTEM_PROMPT = (
    "You split pull request descriptions into claims that can be checked "
    "against source code. A claim is verifiable when reading the diff or the "
    "repository can prove or disprove it. Skip pleasantries, TODOs and open "
    "questions. Return an empty list when the description claims nothing."
    + untrusted.SYSTEM_CLAUSE
)


def _validate(data: dict) -> list[dict]:
    claims = data.get("claims")
    if not isinstance(claims, list):
        raise RuntimeError("invalid claims response: missing 'claims' list")
    for c in claims:
        if not isinstance(c, dict) or not c.get("id"):
            raise RuntimeError(f"claim has invalid schema (missing id): {c}")
        if not c.get("text") or c.get("category") not in CATEGORIES:
            raise RuntimeError(f"claim has invalid schema: {c}")
    return claims


def build_prompt(snapshot: dict, found: list[str] | None = None) -> str:
    files = [f["filename"] for f in snapshot.get("files", [])]
    listed = "\n".join(f"- {f}" for f in files) or "- (none)"
    return (
        "Title:\n" + untrusted.block("PR title", snapshot["title"], found=found) + "\n\n"
        "Description:\n"
        + untrusted.block("PR description", snapshot["body"] or "(empty)", found=found)
        + f"\n\nFiles changed:\n{listed}"
    )


def extract_claims(snapshot: dict, cfg: dict, session_dir: Path,
                   runner=_default_runner) -> list[dict]:
    """Extract claims from the PR description. Writes claims.json, returns the list."""
    found: list[str] = []
    result = runner(
        build_prompt(snapshot, found=found),
        schema=CLAIMS_SCHEMA,
        model=cfg.get("claims_model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=2,
        provider=cfg.get("provider"),
    )
    claims = _validate(result.data)

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "claims.json").write_text(json.dumps(claims, indent=2))
    record_usage(session_dir, "claims", result)
    untrusted.record_neutralized(session_dir, "claims", found)
    return claims
