"""Turn findings into a merge decision.

Pure functions over the findings dict: no I/O, no LLM. `score()` is what CI
turns into an exit code and what the dashboard turns into a badge.
"""
import re
from fnmatch import fnmatch

DEFAULT_GATE = {
    "verification_score_min": 0.8,
    "sensitive_areas": ["**/payment*/**", "**/billing/**", "**/auth*/**",
                        "**/migrations/**", "**/checkout/**"],
    "core_docs": ["README.md", "docs/**", "**/openapi*.y*ml", "**/openapi*.json",
                  "**/*.proto", "API.md"],
}

# "src/app.py:42" — evidence must point at a line, not just name a file.
EVIDENCE_RE = re.compile(r"\S+:\d+")

DOC_DRIFT_STATUSES = ("STALE", "WRONG", "FABRICATED")
LABEL_DOC_DRIFT = "needs-doc-update"
LABEL_BREAKING = "breaking-change"
LABEL_RISK = "review-risk-high"
LABEL_CROSS_PR = "cross-pr-collision"
# Below this, a collision is reported but does not move the gate: a half-sure
# guess about a branch that may never merge is not worth an amber CI run.
CROSS_PR_MIN_CONFIDENCE = 0.5
RISKY_CROSS_PR = ("SEMANTIC_CONFLICT", "MERGE_ORDER_RISK")
REAL_CROSS_PR = RISKY_CROSS_PR + ("DUPLICATE_WORK",)


def _matches(path: str, patterns: list[str]) -> bool:
    """Glob match tolerant of a leading `**/` (fnmatch's `*` already spans `/`)."""
    path = (path or "").lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if fnmatch(path, pattern):
            return True
        if pattern.startswith("**/") and fnmatch(path, pattern[3:]):
            return True
    return False


def verification_score(findings: dict) -> float:
    """Share of claims that are PASS *and* backed by a real file:line reference.

    A PASS with no evidence counts as unproven — that is the whole point of the
    metric. Returns 1.0 when a PR makes no claims (nothing to get wrong).
    """
    claims = findings.get("claims") or []
    if not claims:
        return 1.0
    proven = sum(
        1 for c in claims
        if c.get("status") == "PASS"
        and any(EVIDENCE_RE.search(str(e)) for e in (c.get("evidence") or []))
    )
    return round(proven / len(claims), 3)


def doc_drift(findings: dict, core_docs: list[str]) -> list[dict]:
    """Core documentation that no longer matches the code."""
    return [d for d in findings.get("docs") or []
            if d.get("status") in DOC_DRIFT_STATUSES and _matches(d.get("path", ""), core_docs)]


def business_risk(findings: dict, sensitive_areas: list[str]) -> tuple[str, list[str]]:
    """Highest business risk in the findings, with the reasons that produced it."""
    high: list[str] = []
    medium: list[str] = []

    for c in findings.get("contracts") or []:
        status = c.get("status")
        if status in ("BREAKING_API_CHANGE", "SCHEMA_MIGRATION_RISK"):
            high.append(f"{status} in {c.get('path', '?')}: {c.get('detail', '')}".strip())

    for i in findings.get("impact") or []:
        sensitive = _matches(" ".join(i.get("paths") or []), sensitive_areas) or any(
            _matches(p, sensitive_areas) for p in i.get("paths") or [])
        sensitive = sensitive or i.get("area") in ("payment", "auth")
        if i.get("impact") == "BROKEN":
            (high if sensitive else medium).append(
                f"BROKEN: {i.get('requirement', '?')} — {i.get('detail', '')}".strip())
        elif i.get("impact") == "RISK" and sensitive:
            medium.append(f"RISK: {i.get('requirement', '?')} — {i.get('detail', '')}".strip())

    for c in findings.get("callers_outside_diff") or []:
        if c.get("risk") == "BROKEN":
            high.append(f"caller broken: {c.get('symbol', '?')} used at "
                        f"{', '.join(c.get('callers') or []) or '?'}")
        elif c.get("risk") == "NEEDS_UPDATE":
            medium.append(f"caller needs update: {c.get('symbol', '?')}")

    if high:
        return "high", high
    if medium:
        return "medium", medium
    return "none", []


def test_gaps(findings: dict) -> list[dict]:
    """Tests that execute new logic without asserting it, or are missing entirely."""
    return [t for t in findings.get("tests") or []
            if t.get("assertion_quality") in ("WEAK", "MISSING")]


def cross_pr(findings: dict) -> tuple[list[dict], list[dict]]:
    """(collisions that raise risk to medium, collisions only reported).

    Deliberately outside `business_risk`: that function answers "how risky is
    this PR as it stands", and a sibling branch is not part of what this PR
    stands on. A collision is a claim about code that may never merge, so it can
    move the gate to warn and never to fail.
    """
    bumping: list[dict] = []
    noted: list[dict] = []
    for c in findings.get("cross_pr") or []:
        if c.get("status") not in REAL_CROSS_PR:
            continue
        try:
            confidence = float(c.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        risky = (c["status"] in RISKY_CROSS_PR
                 and confidence >= CROSS_PR_MIN_CONFIDENCE)
        (bumping if risky else noted).append(c)
    return bumping, noted


def score(findings: dict, gate: dict | None = None) -> dict:
    """Full risk matrix + the merge decision (pass / warn / fail)."""
    cfg = {**DEFAULT_GATE, **(gate or {})}
    minimum = float(cfg["verification_score_min"])

    score_value = verification_score(findings)
    drifted = doc_drift(findings, cfg["core_docs"])
    risk, risk_reasons = business_risk(findings, cfg["sensitive_areas"])
    gaps = test_gaps(findings)
    bumping, noted = cross_pr(findings)
    # Raises the floor, never sets the ceiling: `high` stays a statement about
    # this PR's own code.
    if bumping and risk == "none":
        risk = "medium"

    reasons: list[str] = []
    labels: list[str] = []
    if score_value < minimum:
        reasons.append(f"verification score {score_value:.0%} below {minimum:.0%}")
    if drifted:
        reasons.append(f"{len(drifted)} core doc(s) out of sync: "
                       + ", ".join(d.get("path", "?") for d in drifted))
        labels.append(LABEL_DOC_DRIFT)
    reasons.extend(risk_reasons)
    reasons.extend(f"cross-PR {c['status']} with #{c.get('pr', '?')}: "
                   f"{c.get('detail', '')}".strip() for c in bumping + noted)
    if bumping or noted:
        labels.append(LABEL_CROSS_PR)
    if any(c.get("status") == "BREAKING_API_CHANGE" for c in findings.get("contracts") or []):
        labels.append(LABEL_BREAKING)

    decision = "pass"
    if score_value < minimum or drifted or risk == "medium":
        decision = "warn"
    if risk == "high":
        decision = "fail"
        labels.append(LABEL_RISK)

    return {
        "verification_score": score_value,
        "doc_drift": [d.get("path", "?") for d in drifted],
        "business_risk": risk,
        "test_gaps": [t.get("target", "?") for t in gaps],
        "cross_pr": [f"#{c.get('pr', '?')} {c.get('status', '')}"
                     for c in bumping + noted],
        "gate": decision,
        "labels": sorted(set(labels)),
        "reasons": reasons,
    }
