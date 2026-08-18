from annotations import MAX_INLINE, candidates, diff_lines, parse_ref, split

PATCH = ("@@ -1,3 +1,4 @@\n"
         " unchanged\n"
         "-old_line()\n"
         "+new_line()\n"
         "+another()\n"
         " tail\n")

SNAPSHOT = {"files": [
    {"filename": "src/a.py", "patch": PATCH},
    {"filename": "src/b.py", "patch": ""},
]}

FINDINGS = {
    "claims": [
        {"id": "C1", "status": "FAIL", "evidence": ["src/a.py:2"], "note": "not wired"},
        {"id": "C2", "status": "PASS", "evidence": ["src/a.py:3"], "note": ""},
        {"id": "C3", "status": "PARTIAL", "evidence": ["src/a.py:99"], "note": "half"},
    ],
    "callers_outside_diff": [
        {"symbol": "charge", "defined_at": "src/a.py:3", "callers": ["src/z.py:9"],
         "risk": "BROKEN", "note": "signature changed"},
        {"symbol": "ok", "defined_at": "src/a.py:2", "callers": [], "risk": "SAFE",
         "note": ""},
    ],
    "contracts": [
        {"kind": "API", "path": "src/a.py", "status": "BREAKING_API_CHANGE",
         "detail": "removed field"},
        {"kind": "API", "path": "src/a.py", "status": "COMPATIBLE", "detail": ""},
    ],
    "tests": [
        {"target": "src/a.py:test_charge", "assertion_quality": "MISSING",
         "uncovered_edge_cases": [], "note": "no test"},
        {"target": "src/a.py:test_ok", "assertion_quality": "STRONG",
         "uncovered_edge_cases": [], "note": ""},
    ],
}


def test_diff_lines_counts_added_and_context_lines():
    assert diff_lines(SNAPSHOT) == {"src/a.py": {1, 2, 3, 4}}


def test_a_file_without_a_patch_is_absent_from_the_index():
    assert "src/b.py" not in diff_lines(SNAPSHOT)


def test_diff_lines_handles_several_hunks():
    patch = "@@ -1,1 +1,1 @@\n+a\n@@ -10,1 +20,2 @@\n+b\n+c\n"
    assert diff_lines({"files": [{"filename": "x", "patch": patch}]}) == {"x": {1, 20, 21}}


def test_diff_lines_ignores_file_headers():
    patch = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n+a\n"
    assert diff_lines({"files": [{"filename": "x", "patch": patch}]}) == {"x": {1}}


def test_parse_ref_splits_a_file_and_line():
    assert parse_ref("src/a.py:42") == ("src/a.py", 42)


def test_parse_ref_takes_the_last_colon():
    assert parse_ref("C:/win/a.py:7") == ("C:/win/a.py", 7)


def test_parse_ref_rejects_a_non_numeric_suffix():
    assert parse_ref("src/a.py:test_charge") is None
    assert parse_ref("src/a.py") is None
    assert parse_ref("") is None


def test_candidates_cover_a_failed_claim():
    got = [c for c in candidates(FINDINGS) if "C1" in c["body"]]
    assert got == [{"path": "src/a.py", "line": 2,
                    "body": got[0]["body"]}]
    assert "not wired" in got[0]["body"]


def test_candidates_skip_a_passing_claim():
    assert not any("C2" in c["body"] for c in candidates(FINDINGS))


def test_candidates_cover_a_broken_caller_at_its_definition():
    got = [c for c in candidates(FINDINGS) if "charge" in c["body"]]
    assert got[0]["path"] == "src/a.py" and got[0]["line"] == 3
    assert "src/z.py:9" in got[0]["body"]


def test_candidates_skip_a_safe_caller():
    assert not any("`ok`" in c["body"] for c in candidates(FINDINGS))


def test_a_contract_candidate_has_no_line():
    got = [c for c in candidates(FINDINGS) if "BREAKING_API_CHANGE" in c["body"]]
    assert got[0] == {"path": "src/a.py", "line": None, "body": got[0]["body"]}


def test_a_compatible_contract_is_not_a_candidate():
    assert not any("COMPATIBLE" in c["body"] for c in candidates(FINDINGS))


def test_a_weak_test_candidate_uses_the_file_part_of_target():
    got = [c for c in candidates(FINDINGS) if "MISSING" in c["body"]]
    assert got[0]["path"] == "src/a.py" and got[0]["line"] is None


def test_split_keeps_a_candidate_on_a_diff_line():
    index = diff_lines(SNAPSHOT)
    inline, leftover = split([{"path": "src/a.py", "line": 2, "body": "x"}], index)
    assert inline == [{"path": "src/a.py", "line": 2, "body": "x"}]
    assert leftover == []


def test_split_rejects_a_line_outside_the_diff():
    index = diff_lines(SNAPSHOT)
    inline, leftover = split([{"path": "src/a.py", "line": 99, "body": "x"}], index)
    assert inline == []
    assert leftover[0]["line"] == 99


def test_split_rejects_a_file_outside_the_diff():
    index = diff_lines(SNAPSHOT)
    inline, leftover = split([{"path": "src/gone.py", "line": 1, "body": "x"}], index)
    assert inline == [] and len(leftover) == 1


def test_split_resolves_a_lineless_candidate_to_the_first_diff_line():
    index = diff_lines(SNAPSHOT)
    inline, _ = split([{"path": "src/a.py", "line": None, "body": "x"}], index)
    assert inline[0]["line"] == 1


def test_split_caps_the_number_of_inline_comments():
    index = {"x": set(range(1, 100))}
    cands = [{"path": "x", "line": i, "body": "b"} for i in range(1, 40)]
    inline, leftover = split(cands, index, cap=5)
    assert len(inline) == 5
    assert len(leftover) == 34


def test_the_default_cap_is_exported():
    assert isinstance(MAX_INLINE, int) and MAX_INLINE > 0


def test_a_failed_claim_without_a_line_anchors_to_the_files_first_diff_line():
    """Evidence naming a file but no line is still placeable, like a contract is."""
    findings = {"claims": [{"id": "C9", "status": "FAIL", "evidence": ["src/a.py"],
                            "note": "no line number"}]}
    cands = candidates(findings)
    assert len(cands) == 1 and cands[0]["line"] is None
    inline, leftover = split(cands, diff_lines(SNAPSHOT))
    assert inline[0]["line"] == 1 and "C9" in inline[0]["body"]
    assert leftover == []


def test_a_failed_claim_naming_a_file_outside_the_diff_reaches_leftover():
    """Unanchorable is not the same as uninteresting — it belongs in the summary."""
    findings = {"claims": [{"id": "C7", "status": "FAIL", "evidence": ["gone.py"],
                            "note": "not in this diff"}]}
    inline, leftover = split(candidates(findings), diff_lines(SNAPSHOT))
    assert inline == [] and "C7" in leftover[0]["body"]


def test_a_failed_claim_with_no_evidence_at_all_still_reaches_leftover():
    findings = {"claims": [{"id": "C8", "status": "FAIL", "evidence": [],
                            "note": "nothing to cite"}]}
    inline, leftover = split(candidates(findings), diff_lines(SNAPSHOT))
    assert inline == [] and "C8" in leftover[0]["body"]


def test_a_broken_caller_without_a_line_still_reaches_leftover():
    findings = {"callers_outside_diff": [
        {"symbol": "charge", "defined_at": "src/pay.py", "callers": [], "risk": "BROKEN",
         "note": "moved"}]}
    inline, leftover = split(candidates(findings), diff_lines(SNAPSHOT))
    assert inline == [] and "charge" in leftover[0]["body"]


def test_the_cap_is_filled_in_list_order():
    """run.py relies on this: whichever source it concatenates first wins the cap."""
    index = {"src/a.py": {1, 2}}
    first = {"path": "src/a.py", "line": 1, "body": "first"}
    second = {"path": "src/a.py", "line": 2, "body": "second"}
    inline, leftover = split([first, second], index, cap=1)
    assert inline[0]["body"] == "first"
    assert leftover[0]["body"] == "second"


def _collision(status="SEMANTIC_CONFLICT", evidence=("src/payment/invoice.py:42",)):
    return {"pr": 456, "status": status, "symbol": "createInvoice",
            "paths": ["src/payment/invoice.py"], "evidence": list(evidence),
            "detail": "PR #456 renames the parameter this call passes",
            "confidence": 0.9}


def test_a_collision_anchors_on_its_evidence_line():
    out = candidates({"cross_pr": [_collision()]})
    assert len(out) == 1
    assert out[0]["path"] == "src/payment/invoice.py"
    assert out[0]["line"] == 42
    assert "cross-PR collision" in out[0]["body"]
    assert "#456" in out[0]["body"]
    assert "createInvoice" in out[0]["body"]


def test_a_collision_without_a_line_still_reaches_the_summary():
    out = candidates({"cross_pr": [_collision(evidence=("src/payment/invoice.py",))]})
    assert out[0]["path"] == "src/payment/invoice.py"
    assert out[0]["line"] is None


def test_a_no_conflict_verdict_is_not_annotated():
    assert candidates({"cross_pr": [_collision(status="NO_CONFLICT")]}) == []


def test_collisions_are_annotated_after_contracts_and_before_tests():
    findings = {
        "cross_pr": [_collision()],
        "contracts": [{"kind": "API", "path": "openapi.yml",
                       "status": "BREAKING_API_CHANGE", "detail": "d"}],
        "tests": [{"target": "tests/test_a.py:test_x", "assertion_quality": "WEAK",
                   "uncovered_edge_cases": [], "note": "n"}],
    }
    bodies = [c["body"] for c in candidates(findings)]
    assert "BREAKING_API_CHANGE" in bodies[0]
    assert "cross-PR collision" in bodies[1]
    assert "Test coverage" in bodies[2]


def test_parse_ref_accepts_a_line_range():
    assert parse_ref("src/a.py:12-34") == ("src/a.py", 12)


def test_parse_ref_accepts_trailing_words():
    assert parse_ref("src/a.py:7 test_name") == ("src/a.py", 7)
    assert parse_ref("src/repo_ref.py:1-36 (module with parse_repo)") == ("src/repo_ref.py", 1)


def test_parse_ref_rejects_digits_glued_to_text():
    assert parse_ref("src/a.py:12abc") is None
