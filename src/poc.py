"""Turn "this is BROKEN" into a test the author can run.

A reviewer reading "the retry only fires once" has to take it on faith. A
failing test with concrete inputs is the same claim, checkable in ten seconds.
This is the same move remediate.py makes for documentation: a second read-only
agent pass, gated so it costs nothing on a clean review, returning structured
output that a deterministic module renders.

Two rules it must keep. The framework is detected from the workspace, never
guessed by the model — a model that picks jest for a pytest repo produces a test
nobody can run. And every generated test is labelled as not executed: the agent
has no way to run it, so under the project's own standard it is an unverified
claim and has to say so.
"""
import json
from pathlib import Path

import untrusted
from agent import READ_ONLY_TOOLS, record_usage
from agent import run_structured as _default_runner

POC_SCHEMA = {
    "type": "object",
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "file the test covers"},
                    "framework": {"type": "string"},
                    "test_code": {"type": "string",
                                  "description": "a complete, runnable failing test"},
                    "why_it_fails": {"type": "string",
                                     "description": "the concrete input and the wrong output"},
                },
                "required": ["target", "framework", "test_code", "why_it_fails"],
            },
        },
    },
    "required": ["tests"],
}

SYSTEM_PROMPT = (
    "You write the smallest failing test that demonstrates a specific broken "
    "behaviour. You read the real code first and use the project's existing test "
    "conventions, imports and helpers. The test must fail against the current "
    "code for the stated reason — never write a test that passes."
    + untrusted.SYSTEM_CLAUSE
)


def detect_framework(workspace: Path) -> str:
    """The repo's test runner, read off disk. 'unknown' when nothing matches."""
    if (workspace / "conftest.py").exists() or (workspace / "pytest.ini").exists():
        return "pytest"
    package = workspace / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text())
        except (OSError, json.JSONDecodeError):
            return "unknown"
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        for name in ("vitest", "jest", "mocha"):
            if name in deps:
                return name
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        try:
            if "pytest" in pyproject.read_text():
                return "pytest"
        except OSError:
            pass
    if (workspace / "go.mod").exists():
        return "go test"
    if (workspace / "Cargo.toml").exists():
        return "cargo test"
    return "unknown"


def broken(findings: dict) -> list[dict]:
    """Behaviours a review called broken, as `{what, where}` pairs."""
    out = []
    for impact in findings.get("impact") or []:
        if impact.get("impact") == "BROKEN":
            out.append({"what": f"{impact.get('requirement', '?')} — "
                                f"{impact.get('detail', '')}",
                        "where": ", ".join(impact.get("paths") or []) or "?"})
    for caller in findings.get("callers_outside_diff") or []:
        if caller.get("risk") == "BROKEN":
            out.append({"what": f"`{caller.get('symbol', '?')}` — "
                                f"{caller.get('note', '')}",
                        "where": caller.get("defined_at", "?")})
    return out


def build_prompt(items: list[dict], framework: str, language: str = "en",
                 found: list[str] | None = None) -> str:
    listed = untrusted.block(
        "Broken behaviours",
        "\n".join(f"- {b['what']} (in {b['where']})" for b in items),
        found=found)
    tongue = "" if language == "en" else (
        "\n\nWrite `why_it_fails` and every comment inside the test in "
        f"{'Vietnamese' if language == 'vi' else language}.")
    return f"""
A review found these behaviours broken:

{listed}

This repository's test framework is: {framework}

For each one, write the smallest test that FAILS against the current code and
demonstrates the break. Read the real code and the existing tests first, and
match their conventions, imports and helpers so the author can paste the test in
and run it. State in `why_it_fails` the concrete input and the wrong output it
produces. If you cannot write a test that genuinely fails, skip that item rather
than inventing one.
""".strip() + tongue


def draft_pocs(findings: dict, cfg: dict, workspace: Path, session_dir: Path,
               runner=_default_runner) -> list[dict]:
    """One failing test per broken behaviour. Writes poc.json, returns the list."""
    items = broken(findings)
    if not items:
        return []
    found: list[str] = []
    result = runner(
        build_prompt(items, detect_framework(Path(workspace)),
                     language=cfg.get("language", "en"), found=found),
        schema=POC_SCHEMA,
        cwd=workspace,
        tools=READ_ONLY_TOOLS,
        model=cfg.get("model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=cfg.get("max_turns", 30),
        effort=cfg.get("effort"),
        provider=cfg.get("provider"),
    )
    pocs = [p for p in result.data.get("tests") or []
            if p.get("test_code") and p.get("target")]

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "poc.json").write_text(json.dumps(pocs, indent=2))
    record_usage(session_dir, "poc", result)
    untrusted.record_neutralized(session_dir, "poc", found)
    return pocs


def comment_section(pocs: list[dict]) -> str:
    """The generated tests, folded into the review comment and the report."""
    if not pocs:
        return ""
    blocks = "\n\n".join(
        f"**`{p['target']}`** — {p.get('why_it_fails', '')}\n\n"
        f"```{p.get('framework', '')}\n{p['test_code']}\n```" for p in pocs)
    return ("<details>\n\n<summary>Failing tests that reproduce the broken behaviour "
            f"({len(pocs)})</summary>\n\nThese tests were generated from the review and "
            "have **not been executed** — run them locally to confirm the break.\n\n"
            f"{blocks}\n\n</details>")
