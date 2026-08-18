"""Read sessions/ data into PR and repo metric records. Pure logic, no HTTP."""
import json
import sys
from datetime import datetime
from pathlib import Path

from describe import MIN_BODY_CHARS
from poc import broken
from remediate import fixable_docs
from synthesize import _overall_verdict

VERDICTS = ("ACCURATE", "PARTIAL", "MISLEADING", "NO_CLAIMS")
GATES = ("pass", "warn", "fail", "unknown")
REQUIRED_FILES = ("snapshot.json", "findings.json")


def _warn(msg: str) -> None:
    print(f"[metrics] {msg}", file=sys.stderr)


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        _warn(f"skipping corrupt file: {path}")
        return None


def _read_json_list(path: Path) -> list:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        _warn(f"skipping corrupt file: {path}")
        return []


def _verdict_key(verdict: str) -> str:
    """Normalize verdict names to safe dict keys (NO CLAIMS -> NO_CLAIMS)."""
    return verdict.replace(" ", "_")


def _session_dirs(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        d for d in root.glob("*/*/pr-*")
        if d.is_dir() and all((d / f).exists() for f in REQUIRED_FILES))


def _session_updated(session_dir: Path) -> str:
    try:
        return datetime.fromtimestamp(session_dir.stat().st_mtime).strftime(
            "%Y-%m-%d %H:%M")
    except OSError:
        return ""


def list_repos(session_root: Path) -> list[tuple[str, str]]:
    """Return sorted [(owner, repo)] pairs with review data."""
    pairs = sorted({(d.parent.parent.name, d.parent.name)
                    for d in _session_dirs(session_root)})
    return pairs


def _read_rounds(session_dir: Path) -> int:
    """Rounds from rounds.txt; fallback 1 for legacy sessions; garbage → 1."""
    path = session_dir / "rounds.txt"
    if not path.exists():
        return 1
    try:
        return max(1, int(path.read_text().strip()))
    except (OSError, ValueError):
        return 1


def pr_record(session_root: Path, owner: str, repo: str, n: int) -> dict | None:
    """Build one PR metric record. None if missing/corrupt data."""
    session_dir = session_root / owner / repo / f"pr-{n}"
    if not session_dir.is_dir():
        return None
    snapshot = _read_json(session_dir / "snapshot.json")
    findings = _read_json(session_dir / "findings.json")
    if snapshot is None or findings is None:
        return None

    answers = _read_json_list(session_dir / "answers.json")

    report = session_dir / "report.md"
    failed = report.exists() and report.read_text(
        errors="replace").startswith("# Review FAILED")

    claims = findings.get("claims", [])
    docs = findings.get("docs", [])
    impact = findings.get("impact", [])
    contracts = findings.get("contracts", [])
    tests = findings.get("tests", [])
    callers = findings.get("callers_outside_diff", [])

    scores = _read_json(session_dir / "score.json") or {}
    usage = _read_json_list(session_dir / "usage.json")

    return {
        "pr": n,
        "title": snapshot.get("title", ""),
        "author": snapshot.get("author", ""),
        "base": snapshot.get("base", ""),
        "head": snapshot.get("head", ""),
        "verdict": _verdict_key(_overall_verdict(findings)),
        "gate": scores.get("gate", ""),
        "verification_score": scores.get("verification_score"),
        "business_risk": scores.get("business_risk", ""),
        "gate_reasons": scores.get("reasons", []),
        "cost_usd": round(sum(e.get("cost_usd") or 0.0 for e in usage
                              if isinstance(e, dict)), 4),
        "breaking": sum(1 for c in contracts if c.get("status") in
                        ("BREAKING_API_CHANGE", "SCHEMA_MIGRATION_RISK")),
        "test_gaps": sum(1 for t in tests
                         if t.get("assertion_quality") in ("WEAK", "MISSING")),
        "callers_at_risk": sum(1 for c in callers
                               if c.get("risk") in ("NEEDS_UPDATE", "BROKEN")),
        "cross_pr": sum(1 for c in findings.get("cross_pr") or []
                        if c.get("status") not in (None, "NO_CONFLICT")),
        "claims_total": len(claims),
        "bugs": sum(1 for c in claims
                    if c.get("status") in ("FAIL", "PARTIAL"))
                + sum(1 for i in impact
                      if i.get("impact") in ("BROKEN", "RISK")),
        "bug_breakdown": {
            "claims_fail": sum(1 for c in claims if c.get("status") == "FAIL"),
            "claims_partial": sum(1 for c in claims
                                  if c.get("status") == "PARTIAL"),
            "impact_broken": sum(1 for i in impact
                                 if i.get("impact") == "BROKEN"),
            "impact_risk": sum(1 for i in impact if i.get("impact") == "RISK"),
        },
        "doc_errors": sum(1 for d in docs
                          if d.get("status") in ("WRONG", "FABRICATED", "STALE")),
        "doc_breakdown": {
            "wrong": sum(1 for d in docs if d.get("status") == "WRONG"),
            "fabricated": sum(1 for d in docs
                              if d.get("status") == "FABRICATED"),
            "stale": sum(1 for d in docs if d.get("status") == "STALE"),
        },
        "open_questions": sum(1 for a in answers
                              if a.get("answer") in ("SKIPPED", "")),
        "rounds": _read_rounds(session_dir),
        "updated_at": _session_updated(session_dir),
        "failed": failed,
    }


def repo_record(session_root: Path, owner: str, repo: str) -> dict | None:
    """Build one repo aggregate record. None if repo has no review data."""
    dirs = [d for d in _session_dirs(session_root)
            if d.parent.parent.name == owner and d.parent.name == repo]
    if not dirs:
        return None
    prs = []
    for d in dirs:
        n = int(d.name.split("-")[1])
        rec = pr_record(session_root, owner, repo, n)
        if rec is not None:
            prs.append(rec)
    prs.sort(key=lambda r: r["updated_at"], reverse=True)
    verdict_count = {v: 0 for v in VERDICTS}
    gate_count = {g: 0 for g in GATES}
    for r in prs:
        if not r["failed"]:
            verdict_count[r["verdict"]] += 1
            gate_count[r["gate"] or "unknown"] = gate_count.get(r["gate"] or "unknown", 0) + 1
    scored = [r["verification_score"] for r in prs if r["verification_score"] is not None]
    return {
        "owner": owner,
        "repo": repo,
        "prs_total": len(prs),
        "bugs_total": sum(r["bugs"] for r in prs),
        "doc_errors_total": sum(r["doc_errors"] for r in prs),
        "breaking_total": sum(r["breaking"] for r in prs),
        "test_gaps_total": sum(r["test_gaps"] for r in prs),
        "cost_total": round(sum(r["cost_usd"] for r in prs), 4),
        "avg_verification_score": round(sum(scored) / len(scored), 3) if scored else None,
        "verdict_count": verdict_count,
        "gate_count": gate_count,
        "prs": prs,
    }


def pr_detail(session_root: Path, owner: str, repo: str, n: int) -> dict | None:
    """Full data for the PR detail page (claims merged with claim text)."""
    rec = pr_record(session_root, owner, repo, n)
    if rec is None:
        return None
    session_dir = session_root / owner / repo / f"pr-{n}"
    snapshot = _read_json(session_dir / "snapshot.json")
    findings = _read_json(session_dir / "findings.json")
    claims_json = _read_json_list(session_dir / "claims.json")
    by_id = {c.get("id"): c for c in claims_json if isinstance(c, dict)}

    claims = []
    for fc in findings.get("claims", []):
        base = by_id.get(fc.get("id"), {})
        claims.append({
            "id": fc.get("id", ""),
            "text": base.get("text", ""),
            "category": base.get("category", ""),
            "status": fc.get("status", ""),
            "evidence": fc.get("evidence", []),
            "note": fc.get("note", ""),
        })

    answers = _read_json_list(session_dir / "answers.json")

    return {
        "pr": rec,
        "title": snapshot.get("title", ""),
        "body": snapshot.get("body", ""),
        "claims": claims,
        "docs": findings.get("docs", []),
        "impact": findings.get("impact", []),
        "callers": findings.get("callers_outside_diff", []),
        "contracts": findings.get("contracts", []),
        "cross_pr": findings.get("cross_pr", []),
        "siblings": _read_json(session_dir / "siblings.json") or {},
        "tests": findings.get("tests", []),
        "threads": findings.get("threads", []),
        "questions": findings.get("unresolved_questions", []),
        "answers": answers,
        "pruned": snapshot.get("pruned", []),
        "score": _read_json(session_dir / "score.json") or {},
        "usage": _read_json_list(session_dir / "usage.json"),
        "replies": _read_json_list(session_dir / "replies.json"),
    }


def open_prs(session_root: Path, owner: str, repo: str, gh=None) -> list[dict]:
    """Merge GitHub open PRs with session state.

    Returns rows: {pr, title, draft, status, rounds, bugs, doc_errors,
    unavailable} sorted by pr desc. status: reviewed | reviewing | not_reviewed.
    gh failure → rows for reviewed sessions only, unavailable=True.
    """
    if gh is None:
        from gh import run_gh
        gh = run_gh
    rows = []
    unavailable = False
    try:
        prs = gh(["api", f"repos/{owner}/{repo}/pulls?state=open", "--paginate"])
    except (RuntimeError, OSError):
        prs = []
        unavailable = True

    session_dir = session_root / owner / repo
    seen = set()
    for p in prs:
        n = int(p["number"])
        seen.add(n)
        d = session_dir / f"pr-{n}"
        info = review_process_info(d)
        if info:  # lock sống → đang review/re-review (kể cả khi đã có findings)
            rec = pr_record(session_root, owner, repo, n) if (d / "findings.json").exists() else None
            rows.append({
                "pr": n, "title": p.get("title", ""),
                "draft": bool(p.get("draft")),
                "status": "reviewing", "rounds": None,
                "pid": info["pid"],
                "started_at": info["started_at"],
                "bugs": rec["bugs"] if rec else None,
                "doc_errors": rec["doc_errors"] if rec else None,
                "unavailable": unavailable,
            })
        elif (d / "findings.json").exists():
            rec = pr_record(session_root, owner, repo, n)
            rows.append({
                "pr": n, "title": p.get("title", ""),
                "draft": bool(p.get("draft")),
                "status": "reviewed",
                "rounds": _read_rounds(d),
                "bugs": rec["bugs"] if rec else 0,
                "doc_errors": rec["doc_errors"] if rec else 0,
                "unavailable": unavailable,
            })
        elif d.exists():
            info = review_process_info(d)
            rows.append({
                "pr": n, "title": p.get("title", ""),
                "draft": bool(p.get("draft")),
                "status": "reviewing", "rounds": None,
                "pid": info["pid"] if info else None,
                "started_at": info["started_at"] if info else None,
                "bugs": None, "doc_errors": None,
                "unavailable": unavailable,
            })
        else:
            rows.append({
                "pr": n, "title": p.get("title", ""),
                "draft": bool(p.get("draft")),
                "status": "not_reviewed", "rounds": None,
                "bugs": None, "doc_errors": None,
                "unavailable": unavailable,
            })

    if unavailable:
        # gh lỗi → fallback: PR đã review từ sessions
        for d in sorted((session_root / owner / repo).glob("pr-*")):
            n = int(d.name.split("-")[1])
            if n in seen:
                continue
            if (d / "findings.json").exists():
                rec = pr_record(session_root, owner, repo, n)
                rows.append({
                    "pr": n, "title": "", "draft": False,
                    "status": "reviewed",
                    "rounds": _read_rounds(d),
                    "bugs": rec["bugs"] if rec else 0,
                    "doc_errors": rec["doc_errors"] if rec else 0,
                    "unavailable": True,
                })

    rows.sort(key=lambda r: r["pr"], reverse=True)
    return rows


def review_process_info(session_dir: Path) -> dict | None:
    """PID + started_at of a running review, or None if not running/stale.

    Reads session_dir/review.lock (JSON {pid, started_at}); lock without a
    live PID is treated as stale (not running).
    """
    lock = session_dir / "review.lock"
    if not lock.exists():
        return None
    try:
        import json as _json

        meta = _json.loads(lock.read_text())
        pid = int(meta.get("pid", 0))
        started_at = meta.get("started_at", "")
    except (ValueError, OSError, _json.JSONDecodeError):
        return None
    if pid <= 0:
        return None
    try:
        import os as _os

        _os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    return {"pid": pid, "started_at": started_at}


# The pipeline, as the dashboard draws it. `optional` phases do not run on every
# review — a good PR body skips Describe, no fixable docs skips Doc fixes, and
# the reply loop only runs under `--reply`.
PHASES = (
    {"id": "snapshot", "label": "Snapshot", "artifact": "snapshot.json"},
    {"id": "siblings", "label": "Sibling scan", "artifact": "siblings.json"},
    {"id": "describe", "label": "Describe", "artifact": "description.json"},
    {"id": "claims", "label": "Claims", "artifact": "claims.json"},
    {"id": "followup", "label": "Replies", "artifact": "replies.json"},
    {"id": "verify", "label": "Verify", "artifact": "findings.json"},
    {"id": "remediate", "label": "Doc fixes", "artifact": "patches.json"},
    {"id": "poc", "label": "PoC tests", "artifact": "poc.json"},
    {"id": "score", "label": "Score", "artifact": "score.json"},
    {"id": "ask", "label": "Confirm", "artifact": "answers.json"},
    {"id": "report", "label": "Report", "artifact": "report.md"},
)

EDGES = (
    ("snapshot", "describe"), ("snapshot", "siblings"), ("siblings", "verify"),
    ("describe", "claims"), ("claims", "verify"),
    ("followup", "verify"), ("verify", "score"), ("verify", "remediate"),
    ("verify", "poc"), ("score", "ask"), ("ask", "report"),
    ("remediate", "report"), ("poc", "report"),
)

# The path a run actually walks, used to decide which node is the live one.
ORDER = ("snapshot", "siblings", "describe", "claims", "verify", "score", "ask",
         "remediate", "poc", "report")


def _phase_skipped(phase_id: str, snapshot: dict, findings: dict) -> bool:
    """Whether a missing artifact means 'not applicable' rather than 'not yet'."""
    if phase_id == "describe":
        return len((snapshot.get("body") or "").strip()) >= MIN_BODY_CHARS
    if phase_id == "remediate":
        return not fixable_docs(findings)
    if phase_id == "poc":
        return not broken(findings)
    if phase_id == "followup":
        return True  # only ever runs on --reply; its artifact is the only proof
    if phase_id == "siblings":
        # No artifact means the scan is off or the session predates it, never
        # "not yet": the phase runs before anything the graph shows after it.
        return True
    return False


def _phase_metrics(phase_id: str, session_dir: Path, snapshot: dict,
                   findings: dict, scores: dict) -> list[dict]:
    """The two or three numbers worth putting on the node itself."""
    if phase_id == "snapshot":
        return [{"label": "files", "value": len(snapshot.get("files") or [])},
                {"label": "commits", "value": len(snapshot.get("commits") or [])},
                {"label": "pruned", "value": len(snapshot.get("pruned") or [])}]
    if phase_id == "siblings":
        data = _read_json(session_dir / "siblings.json") or {}
        return [{"label": "scanned", "value": data.get("scanned", 0)},
                {"label": "overlapping",
                 "value": len(data.get("siblings") or [])}]
    if phase_id == "claims":
        return [{"label": "claims",
                 "value": len(_read_json_list(session_dir / "claims.json"))}]
    if phase_id == "verify":
        return [{"label": "claims", "value": len(findings.get("claims") or [])},
                {"label": "docs", "value": len(findings.get("docs") or [])},
                {"label": "callers",
                 "value": len(findings.get("callers_outside_diff") or [])},
                {"label": "contracts", "value": len(findings.get("contracts") or [])}]
    if phase_id == "score":
        value = scores.get("verification_score")
        return [{"label": "gate", "value": scores.get("gate") or "—"},
                {"label": "verified",
                 "value": f"{round(value * 100)}%" if value is not None else "—"}]
    if phase_id == "ask":
        answers = _read_json_list(session_dir / "answers.json")
        return [{"label": "answered",
                 "value": sum(1 for a in answers
                              if a.get("answer") not in ("SKIPPED", ""))},
                {"label": "open",
                 "value": sum(1 for a in answers
                              if a.get("answer") in ("SKIPPED", ""))}]
    if phase_id == "remediate":
        return [{"label": "patches",
                 "value": len(_read_json_list(session_dir / "patches.json"))}]
    if phase_id == "poc":
        return [{"label": "tests",
                 "value": len(_read_json_list(session_dir / "poc.json"))}]
    if phase_id == "followup":
        return [{"label": "replies",
                 "value": len(_read_json_list(session_dir / "replies.json"))}]
    return []


def pipeline_graph(session_root: Path, owner: str, repo: str, n: int) -> dict | None:
    """The review pipeline for one PR, derived only from artifacts on disk.

    There is no run state to store: a phase is done because its file exists, and
    the live phase is the first one that has neither run nor been skipped.
    """
    session_dir = session_root / owner / repo / f"pr-{n}"
    if not session_dir.is_dir():
        return None
    snapshot = _read_json(session_dir / "snapshot.json") or {}
    findings = _read_json(session_dir / "findings.json") or {}
    scores = _read_json(session_dir / "score.json") or {}
    usage = {e.get("phase"): e
             for e in _read_json_list(session_dir / "usage.json")
             if isinstance(e, dict)}
    report = session_dir / "report.md"
    failed = report.exists() and report.read_text(
        errors="replace").startswith("# Review FAILED")
    running = review_process_info(session_dir) is not None

    nodes = []
    for phase in PHASES:
        phase_id = phase["id"]
        if (session_dir / phase["artifact"]).exists():
            status = "failed" if (phase_id == "report" and failed) else "done"
        elif _phase_skipped(phase_id, snapshot, findings):
            status = "skipped"
        else:
            status = "pending"
        spent = usage.get(phase_id) or {}
        nodes.append({
            "id": phase_id,
            "label": phase["label"],
            "status": status,
            "artifact": phase["artifact"],
            "cost_usd": spent.get("cost_usd"),
            "duration_ms": spent.get("duration_ms"),
            "model": spent.get("model", ""),
            "metrics": _phase_metrics(phase_id, session_dir, snapshot,
                                      findings, scores),
        })

    if running:
        by_id = {node["id"]: node for node in nodes}
        for phase_id in ORDER:
            if by_id[phase_id]["status"] == "pending":
                by_id[phase_id]["status"] = "running"
                break

    return {"nodes": nodes,
            "edges": [{"source": s, "target": t} for s, t in EDGES],
            "running": running}
