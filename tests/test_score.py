from score import (LABEL_BREAKING, LABEL_DOC_DRIFT, LABEL_RISK, business_risk,
                   doc_drift, score, verification_score)
from score import test_gaps as find_test_gaps

EMPTY = {"claims": [], "docs": [], "impact": [], "callers_outside_diff": [],
         "contracts": [], "tests": [], "threads": [], "unresolved_questions": []}


def _claim(status, evidence):
    return {"id": "C1", "status": status, "evidence": evidence, "note": "",
            "confidence": 1.0}


def test_verification_score_needs_real_evidence():
    assert verification_score({"claims": [_claim("PASS", ["src/a.py:12"])]}) == 1.0
    # a PASS with no line reference is not proof
    assert verification_score({"claims": [_claim("PASS", [])]}) == 0.0
    assert verification_score({"claims": [_claim("PASS", ["src/a.py"])]}) == 0.0
    assert verification_score({"claims": [_claim("FAIL", ["src/a.py:1"])]}) == 0.0


def test_verification_score_is_a_ratio():
    findings = {"claims": [_claim("PASS", ["a.py:1"]), _claim("FAIL", ["a.py:2"]),
                           _claim("PASS", ["a.py:3"]), _claim("UNVERIFIED", [])]}
    assert verification_score(findings) == 0.5


def test_verification_score_of_a_claimless_pr():
    assert verification_score(EMPTY) == 1.0


def test_doc_drift_only_counts_core_docs():
    findings = {"docs": [{"path": "docs/api.md", "status": "WRONG", "what": ""},
                         {"path": "notes/scratch.md", "status": "STALE", "what": ""},
                         {"path": "README.md", "status": "MATCH", "what": ""}]}
    assert [d["path"] for d in doc_drift(findings, ["README.md", "docs/**"])] == ["docs/api.md"]


def test_business_risk_high_on_breaking_contract():
    findings = {**EMPTY, "contracts": [
        {"kind": "API", "path": "openapi.yml", "status": "BREAKING_API_CHANGE",
         "detail": "removed field"}]}
    level, reasons = business_risk(findings, [])
    assert level == "high"
    assert "BREAKING_API_CHANGE" in reasons[0]


def test_business_risk_high_on_broken_sensitive_area():
    findings = {**EMPTY, "impact": [
        {"requirement": "Charge card", "impact": "BROKEN", "area": "payment",
         "paths": ["src/payment/charge.py"], "detail": "refund path removed"}]}
    assert business_risk(findings, ["**/payment*/**"])[0] == "high"


def test_business_risk_medium_when_area_is_not_sensitive():
    findings = {**EMPTY, "impact": [
        {"requirement": "Tooltip copy", "impact": "BROKEN", "area": "other",
         "paths": ["src/ui/tooltip.tsx"], "detail": ""}]}
    assert business_risk(findings, ["**/payment*/**"])[0] == "medium"


def test_business_risk_high_on_broken_caller():
    findings = {**EMPTY, "callers_outside_diff": [
        {"symbol": "charge()", "defined_at": "a.py:1", "callers": ["b.py:9"],
         "risk": "BROKEN", "note": ""}]}
    assert business_risk(findings, [])[0] == "high"


def test_business_risk_none_when_clean():
    assert business_risk(EMPTY, [])[0] == "none"


def test_weak_and_missing_tests_are_gaps():
    findings = {"tests": [{"target": "a:f", "assertion_quality": "STRONG"},
                          {"target": "b:g", "assertion_quality": "WEAK"},
                          {"target": "c:h", "assertion_quality": "MISSING"}]}
    assert [t["target"] for t in find_test_gaps(findings)] == ["b:g", "c:h"]


def test_score_passes_a_clean_pr():
    findings = {**EMPTY, "claims": [_claim("PASS", ["src/a.py:1"])]}
    result = score(findings)
    assert result["gate"] == "pass"
    assert result["labels"] == []
    assert result["reasons"] == []


def test_score_warns_on_low_verification_and_doc_drift():
    findings = {**EMPTY,
                "claims": [_claim("PASS", []), _claim("PASS", ["a.py:1"])],
                "docs": [{"path": "docs/api.md", "status": "WRONG", "what": "x"}]}
    result = score(findings)
    assert result["gate"] == "warn"
    assert result["verification_score"] == 0.5
    assert LABEL_DOC_DRIFT in result["labels"]
    assert len(result["reasons"]) == 2


def test_score_fails_and_labels_on_breaking_change():
    findings = {**EMPTY,
                "claims": [_claim("PASS", ["a.py:1"])],
                "contracts": [{"kind": "SCHEMA", "path": "db/migrations/1.sql",
                               "status": "BREAKING_API_CHANGE", "detail": "drop column"}]}
    result = score(findings)
    assert result["gate"] == "fail"
    assert LABEL_BREAKING in result["labels"]
    assert LABEL_RISK in result["labels"]


def test_score_honours_a_custom_threshold():
    findings = {**EMPTY, "claims": [_claim("PASS", []), _claim("PASS", ["a.py:1"])]}
    assert score(findings, {"verification_score_min": 0.4})["gate"] == "pass"


from score import CROSS_PR_MIN_CONFIDENCE, LABEL_CROSS_PR, cross_pr


def _collision(status="SEMANTIC_CONFLICT", confidence=0.9, pr=456):
    return {"pr": pr, "status": status, "symbol": "createInvoice",
            "paths": ["src/payment/invoice.py"],
            "evidence": ["src/payment/invoice.py:42"],
            "detail": "renames a symbol this PR calls", "confidence": confidence}


def test_a_confident_semantic_conflict_bumps_and_is_reported():
    bumping, noted = cross_pr({"cross_pr": [_collision()]})
    assert len(bumping) == 1 and noted == []


def test_a_merge_order_risk_also_bumps():
    bumping, _ = cross_pr({"cross_pr": [_collision(status="MERGE_ORDER_RISK")]})
    assert len(bumping) == 1


def test_an_unsure_collision_is_reported_without_bumping():
    bumping, noted = cross_pr({"cross_pr": [_collision(confidence=0.3)]})
    assert bumping == [] and len(noted) == 1


def test_duplicate_work_is_reported_without_bumping():
    bumping, noted = cross_pr({"cross_pr": [_collision(status="DUPLICATE_WORK")]})
    assert bumping == [] and len(noted) == 1


def test_no_conflict_is_neither():
    assert cross_pr({"cross_pr": [_collision(status="NO_CONFLICT")]}) == ([], [])


def test_a_missing_cross_pr_key_is_fine():
    assert cross_pr(EMPTY) == ([], [])


def test_a_collision_warns_labels_and_never_fails():
    scores = score({**EMPTY, "cross_pr": [_collision()]})
    assert scores["gate"] == "warn"
    assert scores["business_risk"] == "medium"
    assert LABEL_CROSS_PR in scores["labels"]
    assert scores["cross_pr"] == ["#456 SEMANTIC_CONFLICT"]
    assert any("cross-PR" in r for r in scores["reasons"])


def test_an_unsure_collision_does_not_move_the_gate():
    scores = score({**EMPTY, "cross_pr": [_collision(confidence=0.2)]})
    assert scores["gate"] == "pass"
    assert scores["business_risk"] == "none"
    assert LABEL_CROSS_PR in scores["labels"]
    assert any("cross-PR" in r for r in scores["reasons"])


def test_a_collision_never_lowers_a_high_risk():
    broken = {**EMPTY, "cross_pr": [_collision()],
              "callers_outside_diff": [{"symbol": "f", "defined_at": "a.py:1",
                                        "callers": ["b.py:2"], "risk": "BROKEN",
                                        "note": ""}]}
    scores = score(broken)
    assert scores["business_risk"] == "high" and scores["gate"] == "fail"


def test_the_confidence_threshold_is_documented_as_a_constant():
    assert CROSS_PR_MIN_CONFIDENCE == 0.5


def test_a_non_numeric_confidence_is_treated_as_unsure():
    bumping, noted = cross_pr({"cross_pr": [_collision(confidence="high")]})
    assert bumping == [] and len(noted) == 1
