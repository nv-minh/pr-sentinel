"""Phase 3: clone the PR head into a disposable workspace and deep-dive it.

The agent only reads: it reports everything through the JSON schema below, and
this module writes findings.json itself. Nothing depends on the agent
remembering to call a write tool.
"""
import json
import subprocess
import sys
from pathlib import Path

from agent import BASH_TOOLS, READ_ONLY_TOOLS, record_usage
from agent import run_structured as _default_runner
import untrusted

CLAIM_STATUS = ["PASS", "FAIL", "PARTIAL", "UNVERIFIED"]
DOC_STATUS = ["MATCH", "STALE", "WRONG", "FABRICATED"]
IMPACT_STATUS = ["CHANGED", "BROKEN", "UNAFFECTED", "RISK"]
CALLER_RISK = ["SAFE", "NEEDS_UPDATE", "BROKEN"]
CONTRACT_KIND = ["API", "SCHEMA", "TYPE", "PROTO"]
CONTRACT_STATUS = ["COMPATIBLE", "BREAKING_API_CHANGE", "SCHEMA_MIGRATION_RISK"]
ASSERTION_QUALITY = ["STRONG", "WEAK", "MISSING"]
THREAD_STATUS = ["RESOLVED", "STILL_VALID", "FIXED", "OUTDATED"]
CROSS_PR_STATUS = ["NO_CONFLICT", "SEMANTIC_CONFLICT", "DUPLICATE_WORK",
                   "MERGE_ORDER_RISK"]
AREAS = ["payment", "auth", "data", "infra", "other"]

LANGUAGES = {"en": "English", "vi": "Vietnamese"}


def _array(item_props: dict, required: list[str]) -> dict:
    return {"type": "array",
            "items": {"type": "object", "properties": item_props,
                      "required": required}}


def _strings() -> dict:
    return {"type": "array", "items": {"type": "string"}}


FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": _array({
            "id": {"type": "string"},
            "status": {"type": "string", "enum": CLAIM_STATUS},
            "evidence": {**_strings(), "description": "file:line references proving the verdict"},
            "note": {"type": "string"},
            "confidence": {"type": "number", "description": "0.0-1.0"},
        }, ["id", "status", "evidence", "note", "confidence"]),
        "docs": _array({
            "path": {"type": "string"},
            "status": {"type": "string", "enum": DOC_STATUS},
            "what": {"type": "string", "description": "the concrete difference vs the code"},
        }, ["path", "status", "what"]),
        "impact": _array({
            "requirement": {"type": "string"},
            "requirement_source": {
                "type": "string",
                "description": "where the requirement came from: a ticket key, "
                               "'PR description', or 'inferred from code'",
            },
            "impact": {"type": "string", "enum": IMPACT_STATUS},
            "area": {"type": "string", "enum": AREAS},
            "paths": {**_strings(), "description": "repo paths this requirement lives in"},
            "detail": {"type": "string"},
        }, ["requirement", "requirement_source", "impact", "area", "paths", "detail"]),
        "callers_outside_diff": _array({
            "symbol": {"type": "string", "description": "function/class/endpoint that changed"},
            "defined_at": {"type": "string", "description": "file:line"},
            "callers": {**_strings(), "description": "file:line of callers NOT in this PR"},
            "risk": {"type": "string", "enum": CALLER_RISK},
            "note": {"type": "string"},
        }, ["symbol", "defined_at", "callers", "risk", "note"]),
        "contracts": _array({
            "kind": {"type": "string", "enum": CONTRACT_KIND},
            "path": {"type": "string"},
            "status": {"type": "string", "enum": CONTRACT_STATUS},
            "detail": {"type": "string"},
        }, ["kind", "path", "status", "detail"]),
        "tests": _array({
            "target": {"type": "string", "description": "file:function the test covers"},
            "assertion_quality": {"type": "string", "enum": ASSERTION_QUALITY},
            "uncovered_edge_cases": _array({
                "case": {"type": "string"},
                "where": {"type": "string", "description": "file:function to add it to"},
            }, ["case", "where"]),
            "note": {"type": "string"},
        }, ["target", "assertion_quality", "uncovered_edge_cases", "note"]),
        "threads": _array({
            "text": {"type": "string"},
            "status": {"type": "string", "enum": THREAD_STATUS},
            "note": {"type": "string"},
        }, ["text", "status", "note"]),
        "cross_pr": _array({
            "pr": {"type": "integer", "description": "the other open PR's number"},
            "status": {"type": "string", "enum": CROSS_PR_STATUS},
            "symbol": {"type": "string",
                       "description": "function/endpoint/column at stake, '' if none"},
            "paths": _strings(),
            "evidence": {**_strings(),
                         "description": "file:line in THIS checkout — you cannot "
                                        "cite lines of the other PR"},
            "detail": {"type": "string"},
            "confidence": {"type": "number", "description": "0.0-1.0"},
        }, ["pr", "status", "symbol", "paths", "evidence", "detail", "confidence"]),
        "unresolved_questions": {
            **_strings(),
            "description": "questions for the human, each at most 20 words",
        },
    },
    "required": ["claims", "docs", "impact", "callers_outside_diff", "contracts",
                 "tests", "threads", "cross_pr", "unresolved_questions"],
}

SYSTEM_PROMPT = (
    "You are a meticulous code reviewer working inside a checkout of a pull "
    "request. You read the real code before judging anything. You never guess: "
    "a conclusion you cannot back with a file:line reference is UNVERIFIED, and "
    "becomes a question for the human instead." + untrusted.SYSTEM_CLAUSE
)


def _run_git(args: list[str], cwd: Path) -> None:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")


def setup_workspace(owner: str, repo: str, n: int, workspace: Path,
                    remote_url: str | None = None) -> None:
    """Clone the repo (first time) and check out the PR head branch.

    The path must resolve to an absolute one: a relative target plus subprocess
    cwd would nest the clone in the wrong place.
    """
    workspace = workspace.resolve()
    if not workspace.exists():
        url = remote_url or f"https://github.com/{owner}/{repo}.git"
        _run_git(["clone", "--no-checkout", url, str(workspace)], workspace.parent)
    branch = f"pr-{n}"
    # Fetch into FETCH_HEAD (a refspec ending in :branch is refused when that
    # branch is checked out, which happens on every re-review); checkout -B
    # then force-resets the branch.
    _run_git(["fetch", "origin", f"pull/{n}/head"], workspace)
    _run_git(["checkout", "-B", branch, "FETCH_HEAD"], workspace)


def _requirement_section(ticket: dict | None,
                         found: list[str] | None = None) -> str:
    """The ticket text wrapped as untrusted, or a line saying why there is none.

    Returns "" when no lookup happened at all, so a caller that never had a
    ticket produces exactly the prompt it produced before this feature existed.
    """
    if ticket is None:
        return ""
    if not ticket.get("tickets"):
        return ("\nRequirement: none available — "
                + (ticket.get("skipped") or "no ticket was looked up")
                + ". Judge `impact` against the PR description and set "
                "requirement_source accordingly.\n")
    parts = []
    for issue in ticket["tickets"]:
        role = "PRIMARY requirement" if issue["key"] == ticket.get("primary") else "related ticket"
        body = (f"{issue['key']} — {issue['summary']}\n"
                f"status: {issue['status']} | type: {issue['type']} | "
                f"priority: {issue['priority']}\n{issue['url']}\n\n"
                f"{issue['description']}")
        parts.append(f"{role}:\n"
                     + untrusted.block(f"Jira {issue['key']}", body, found=found))
    return "\n" + "\n\n".join(parts) + "\n"


def build_verify_prompt(snapshot: dict, claims: list[dict],
                        ticket: dict | None = None,
                        found: list[str] | None = None,
                        language: str = "en") -> str:
    """Instruct the agent to verify the PR from inside the workspace."""
    files = [f"- {f['filename']} (+{f.get('additions', 0)}/-{f.get('deletions', 0)})"
             for f in snapshot["files"]]
    threads = [f"- (resolved={t['resolved']}) {t.get('author')}:\n"
               + untrusted.block(f"Thread {i}", (t.get("body") or "")[:200], found=found)
               for i, t in enumerate(snapshot.get("threads", []), 1)]
    pruned = [f"- {p['filename']} ({p['reason']})" for p in snapshot.get("pruned", [])]
    prompt = f"""
You are in a checkout of PR #{snapshot['pr']} of {snapshot['owner']}/{snapshot['repo']}.

PR title:
{untrusted.block("PR title", snapshot['title'], found=found)}
PR body:
{untrusted.block("PR body", snapshot['body'] or '(empty)', found=found)}
Base: {snapshot['base']} → Head: {snapshot['head']}

Files changed:
{chr(10).join(files) if files else '- (none)'}

Excluded from this summary (generated/oversized — read them from disk if a
verdict depends on them):
{chr(10).join(pruned) if pruned else '- (none)'}

Review threads:
{chr(10).join(threads) if threads else '- (none)'}

{_requirement_section(ticket, found=found)}

Claims to verify — read the actual code, do not trust the description:
{json.dumps(claims, indent=2)}

Produce, in the required schema:

1. claims — PASS (the code does what is described) / FAIL (the description is
   wrong) / PARTIAL / UNVERIFIED. Every non-UNVERIFIED verdict needs at least
   one `file:line` in evidence. Set confidence 0.0-1.0.
2. docs — for every documentation file related to the changed code, compare the
   doc against the real code: MATCH / STALE (outdated) / WRONG (contradicts the
   code) / FABRICATED (describes something that does not exist). Say concretely
   what differs.
3. impact — which requirement or business behaviour this change touches:
   CHANGED / BROKEN / UNAFFECTED / RISK, with the repo paths involved and the
   area it belongs to. Judge against the requirement above when one is present,
   and set requirement_source to that ticket's key; otherwise set it to
   "PR description" or "inferred from code".
4. callers_outside_diff — for each function, class, endpoint or exported symbol
   whose behaviour or signature changed, search the whole repository for callers
   that this PR does NOT touch. Report them with file:line and whether they still
   work (SAFE), need updating (NEEDS_UPDATE) or are now broken (BROKEN). This is
   the most valuable part of the review: a five-line diff can break ten files.
5. contracts — inspect API specs, database migrations, protobuf definitions and
   exported types touched by this PR. Flag BREAKING_API_CHANGE (removed or
   renamed field/endpoint/parameter, narrowed type, new required field) and
   SCHEMA_MIGRATION_RISK (destructive or non-reversible migration, missing
   default, index built on a large table without CONCURRENTLY).
6. tests — judge whether the tests in this PR actually assert the new branch
   logic, or only execute it for coverage. assertion_quality: STRONG (asserts
   the new behaviour and its failure modes), WEAK (executes the code but asserts
   little), MISSING (new logic with no test). List 2-3 concrete uncovered edge
   cases and the file:function each belongs in.
7. threads — do the unresolved review comments still hold against the current code?
8. unresolved_questions — anything you could not verify, phrased as a question of
   at most 20 words, in {LANGUAGES.get(language, "English")}.

Do not guess. Anything unproven is UNVERIFIED plus a question.
""".strip()
    if language not in ("", "en"):
        name = LANGUAGES.get(language, language)
        prompt += (f"\n\nWrite every note, detail and question in {name}.")
    return prompt


def validate_findings(data: dict, sibling_numbers: set[int] | None = None) -> dict:
    """Defence in depth: the schema is enforced by the SDK, this catches the rest.

    `cross_pr` is required of the model but tolerated as absent here: a
    findings.json written before the sibling scan existed must still validate,
    score and render.
    """
    if not isinstance(data, dict):
        raise RuntimeError("invalid findings: must be a JSON object")
    data.setdefault("cross_pr", [])
    for key in FINDINGS_SCHEMA["required"]:
        if not isinstance(data.get(key), list):
            raise RuntimeError(f"invalid findings: missing key {key} (must be a list)")
    for c in data["claims"]:
        if not c.get("id") or c.get("status") not in CLAIM_STATUS:
            raise RuntimeError(f"invalid findings: claim has invalid schema: {c}")
    for d in data["docs"]:
        if d.get("status") not in DOC_STATUS:
            raise RuntimeError(f"invalid findings: doc has invalid schema: {d}")
    for c in data["contracts"]:
        if c.get("status") not in CONTRACT_STATUS:
            raise RuntimeError(f"invalid findings: contract has invalid schema: {c}")
    for c in data["cross_pr"]:
        if c.get("status") not in CROSS_PR_STATUS:
            raise RuntimeError(f"invalid findings: cross_pr has invalid schema: {c}")
    if sibling_numbers is not None:
        kept = []
        for c in data["cross_pr"]:
            if c.get("pr") in sibling_numbers:
                kept.append(c)
            else:
                # An invented PR number is a hallucination, not a schema break:
                # drop it, say so, and let the rest of the review stand.
                print(f"[verify] dropped cross_pr entry citing unknown PR "
                      f"#{c.get('pr')}", file=sys.stderr)
        data["cross_pr"] = kept
    return data


def run_verify(cfg: dict, workspace: Path, session_dir: Path, snapshot: dict,
               claims: list[dict], ticket: dict | None = None,
               runner=_default_runner) -> dict:
    """Run the deep-dive agent and persist findings.json. Returns the findings."""
    session_dir.mkdir(parents=True, exist_ok=True)
    tools = BASH_TOOLS if cfg.get("allow_bash") else READ_ONLY_TOOLS
    found: list[str] = []
    prompt = build_verify_prompt(snapshot, claims, ticket, found=found,
                                 language=cfg.get("language", "en"))
    result = runner(
        prompt,
        schema=FINDINGS_SCHEMA,
        cwd=workspace,
        tools=tools,
        model=cfg.get("model"),
        effort=cfg.get("effort"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=cfg.get("max_turns", 60),
        max_budget_usd=cfg.get("max_budget_usd"),
        session_dir=session_dir,
        provider=cfg.get("provider"),
    )
    findings = validate_findings(result.data)

    (session_dir / "findings.json").write_text(json.dumps(findings, indent=2))
    (session_dir / "verify-meta.json").write_text(json.dumps(
        {"session_id": result.session_id, "head_sha": snapshot.get("head_sha", "")},
        indent=2))
    record_usage(session_dir, "verify", result)
    untrusted.record_neutralized(session_dir, "verify", found)
    return findings
