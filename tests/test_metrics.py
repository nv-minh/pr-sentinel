# tests/test_metrics.py
import json
import os

from web import metrics

EMPTY_FINDINGS = {"claims": [], "docs": [], "impact": [], "threads": [],
                  "unresolved_questions": []}

SNAPSHOT = {"pr": 7, "title": "Add checkout", "author": "dev1",
            "base": "main", "head": "x", "files": [], "commits": [], "threads": []}


def _write_session(root, owner, repo, pr, snapshot=None, findings=None,
                   answers=None, report=None):
    d = root / owner / repo / f"pr-{pr}"
    d.mkdir(parents=True, exist_ok=True)
    if snapshot is not None:
        (d / "snapshot.json").write_text(json.dumps(snapshot))
    if findings is not None:
        (d / "findings.json").write_text(json.dumps(findings))
    if answers is not None:
        (d / "answers.json").write_text(json.dumps(answers))
    if report is not None:
        (d / "report.md").write_text(report)


def test_list_repos_empty(tmp_path):
    assert metrics.list_repos(tmp_path) == []


def test_list_repos_finds_pairs(tmp_path):
    _write_session(tmp_path, "sample-org", "sample-app", 7,
                   snapshot=SNAPSHOT, findings=EMPTY_FINDINGS)
    _write_session(tmp_path, "sample-org", "sample-api", 3,
                   snapshot=SNAPSHOT, findings=EMPTY_FINDINGS)
    assert metrics.list_repos(tmp_path) == [("sample-org", "sample-api"),
                                            ("sample-org", "sample-app")]


def test_pr_record_counts(tmp_path):
    findings = {
        "claims": [{"id": "C1", "status": "FAIL", "evidence": [], "note": ""},
                   {"id": "C2", "status": "PASS", "evidence": [], "note": ""}],
        "docs": [{"path": "a.md", "status": "WRONG", "what": ""},
                 {"path": "b.md", "status": "FABRICATED", "what": ""},
                 {"path": "c.md", "status": "MATCH", "what": ""}],
        "impact": [{"requirement": "R1", "impact": "BROKEN", "detail": ""}],
        "threads": [],
        "unresolved_questions": [],
    }
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=findings,
                   answers=[{"question": "q1", "kind": "doc", "answer": "SKIPPED"},
                            {"question": "q2", "kind": "claim", "answer": "y"}])
    rec = metrics.pr_record(tmp_path, "o", "r", 7)
    assert rec["verdict"] == "MISLEADING"
    assert rec["bugs"] == 2            # 1 FAIL claim + 1 BROKEN impact
    assert rec["doc_errors"] == 2      # WRONG + FABRICATED
    assert rec["open_questions"] == 1  # only SKIPPED counted
    assert rec["claims_total"] == 2
    assert rec["failed"] is False


def test_pr_record_failed_phase(tmp_path):
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS,
                   report="# Review FAILED\n\n- Lỗi: boom\n")
    rec = metrics.pr_record(tmp_path, "o", "r", 7)
    assert rec["failed"] is True


def test_pr_record_missing_files_returns_none(tmp_path):
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT)  # no findings
    assert metrics.pr_record(tmp_path, "o", "r", 7) is None


def test_pr_record_corrupt_json_skipped(tmp_path):
    d = tmp_path / "o" / "r" / "pr-7"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text("garbage")
    (d / "findings.json").write_text("garbage")
    assert metrics.pr_record(tmp_path, "o", "r", 7) is None


def test_repo_record_aggregates(tmp_path):
    findings = {
        "claims": [{"id": "C1", "status": "FAIL", "evidence": [], "note": ""}],
        "docs": [], "impact": [], "threads": [], "unresolved_questions": [],
    }
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT, findings=EMPTY_FINDINGS)
    _write_session(tmp_path, "o", "r", 8, snapshot=SNAPSHOT, findings=findings)
    rec = metrics.repo_record(tmp_path, "o", "r")
    assert rec["prs_total"] == 2
    assert rec["bugs_total"] == 1
    assert rec["doc_errors_total"] == 0
    assert rec["verdict_count"] == {"ACCURATE": 0, "PARTIAL": 0,
                                    "MISLEADING": 1, "NO_CLAIMS": 1}
    assert len(rec["prs"]) == 2


def test_repo_record_missing_returns_none(tmp_path):
    assert metrics.repo_record(tmp_path, "o", "nope") is None


def test_pr_detail_merges_claims(tmp_path):
    claims = [{"id": "C1", "text": "Adds checkout", "category": "feature",
               "files": [], "docs": []}]
    findings = {
        "claims": [{"id": "C1", "status": "PASS", "evidence": ["a.py:1"],
                    "note": ""}],
        "docs": [], "impact": [], "threads": [], "unresolved_questions": [],
    }
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT, findings=findings)
    (tmp_path / "o" / "r" / "pr-7" / "claims.json").write_text(
        json.dumps(claims))
    detail = metrics.pr_detail(tmp_path, "o", "r", 7)
    assert detail["claims"][0]["text"] == "Adds checkout"
    assert detail["claims"][0]["status"] == "PASS"
    assert detail["claims"][0]["category"] == "feature"


def test_pr_record_wider_metrics(tmp_path):
    findings = {
        "claims": [{"id": "C1", "status": "FAIL", "evidence": [], "note": ""},
                   {"id": "C2", "status": "PARTIAL", "evidence": [], "note": ""},
                   {"id": "C3", "status": "PASS", "evidence": [], "note": ""}],
        "docs": [{"path": "a.md", "status": "WRONG", "what": ""},
                 {"path": "b.md", "status": "STALE", "what": ""},
                 {"path": "c.md", "status": "FABRICATED", "what": ""},
                 {"path": "d.md", "status": "MATCH", "what": ""}],
        "impact": [{"requirement": "R1", "impact": "BROKEN", "detail": ""},
                   {"requirement": "R2", "impact": "RISK", "detail": ""},
                   {"requirement": "R3", "impact": "CHANGED", "detail": ""}],
        "threads": [],
        "unresolved_questions": [],
    }
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT, findings=findings)
    rec = metrics.pr_record(tmp_path, "o", "r", 7)
    assert rec["bugs"] == 4          # FAIL + PARTIAL + BROKEN + RISK
    assert rec["doc_errors"] == 3    # WRONG + FABRICATED + STALE


def test_pr_record_rounds(tmp_path):
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS)
    (tmp_path / "o" / "r" / "pr-7" / "rounds.txt").write_text("3")
    rec = metrics.pr_record(tmp_path, "o", "r", 7)
    assert rec["rounds"] == 3


def test_pr_record_rounds_fallback(tmp_path):
    # không có rounds.txt → 1
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS)
    assert metrics.pr_record(tmp_path, "o", "r", 7)["rounds"] == 1


def test_pr_record_rounds_garbage(tmp_path):
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS)
    (tmp_path / "o" / "r" / "pr-7" / "rounds.txt").write_text("abc")
    assert metrics.pr_record(tmp_path, "o", "r", 7)["rounds"] == 1


def test_open_prs_merge(tmp_path):
    root = tmp_path / "sessions"
    _write_session(root, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS)
    (root / "o" / "r" / "pr-7" / "rounds.txt").write_text("2")
    # pr-8: session dir có snapshot nhưng chưa có findings → Reviewing…
    d8 = root / "o" / "r" / "pr-8"
    d8.mkdir(parents=True)
    (d8 / "snapshot.json").write_text(json.dumps(SNAPSHOT))

    open_prs = [
        {"number": 7, "title": "T7", "draft": False},
        {"number": 8, "title": "T8", "draft": True},
        {"number": 9, "title": "T9", "draft": False},
    ]

    def fake_gh(args, **kw):
        assert "pulls" in args[1]
        return open_prs

    rows = metrics.open_prs(root, "o", "r", gh=fake_gh)
    by_num = {r["pr"]: r for r in rows}
    assert by_num[7]["status"] == "reviewed"
    assert by_num[7]["rounds"] == 2
    assert by_num[7]["draft"] is False
    assert by_num[8]["status"] == "reviewing"
    assert by_num[9]["status"] == "not_reviewed"
    # sort theo number desc
    assert [r["pr"] for r in rows] == [9, 8, 7]


def test_open_prs_gh_failure(tmp_path):
    root = tmp_path / "sessions"
    _write_session(root, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS)

    def fake_gh(args, **kw):
        raise RuntimeError("rate limited")

    rows = metrics.open_prs(root, "o", "r", gh=fake_gh)
    # gh lỗi → trả PR đã review từ sessions, đánh dấu unavailable
    assert rows[0]["pr"] == 7
    assert rows[0]["unavailable"] is True


def test_open_prs_reviewing_with_existing_findings(tmp_path):
    # PR đã review nhưng lock sống (re-review đang chạy) → vẫn hiện reviewing
    root = tmp_path / "sessions"
    _write_session(root, "o", "r", 7, snapshot=SNAPSHOT,
                   findings=EMPTY_FINDINGS)
    lock = root / "o" / "r" / "pr-7" / "review.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    import os
    lock.write_text('{"pid": %d, "started_at": "2026-08-16T10:00:00"}'
                    % os.getpid())

    rows = metrics.open_prs(
        root, "o", "r",
        gh=lambda args, **kw: [{"number": 7, "title": "T7", "draft": False}])
    assert rows[0]["status"] == "reviewing"
    assert rows[0]["pid"] == os.getpid()


# ------------------------------------------------------------------- pipeline graph

def _session(tmp_path, **files):
    d = tmp_path / "demo" / "app" / "pr-8"
    d.mkdir(parents=True)
    for name, body in files.items():
        name = name.replace("__", ".")
        (d / name).write_text(body if isinstance(body, str) else json.dumps(body))
    return d


def _by_id(graph):
    return {n["id"]: n for n in graph["nodes"]}


def test_graph_is_none_without_a_session(tmp_path):
    assert metrics.pipeline_graph(tmp_path, "demo", "app", 8) is None


def test_a_fresh_session_has_only_snapshot_done(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200, "files": [{"filename": "a.py"}]})
    nodes = _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))
    assert nodes["snapshot"]["status"] == "done"
    assert nodes["claims"]["status"] == "pending"
    assert nodes["snapshot"]["metrics"][0] == {"label": "files", "value": 1}


def test_a_long_pr_body_skips_describe(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["describe"]["status"] == "skipped"


def test_a_thin_pr_body_leaves_describe_pending(tmp_path):
    _session(tmp_path, snapshot__json={"body": "too short"})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["describe"]["status"] == "pending"


def test_remediate_is_skipped_when_no_doc_is_fixable(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"docs": [{"path": "README.md", "status": "MATCH"}]})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["remediate"]["status"] == "skipped"


def test_remediate_is_pending_when_a_doc_is_stale(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"docs": [{"path": "README.md", "status": "STALE"}]})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["remediate"]["status"] == "pending"


def test_the_reply_loop_is_skipped_until_it_runs(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["followup"]["status"] == "skipped"


def test_poc_is_skipped_when_nothing_is_broken(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"impact": [], "callers_outside_diff": []})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["poc"]["status"] == "skipped"


def test_poc_is_pending_when_something_is_broken(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"impact": [{"requirement": "R1", "impact": "BROKEN",
                                         "detail": "", "paths": []}]})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["poc"]["status"] == "pending"


def test_poc_is_done_when_its_artifact_exists(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"impact": [{"requirement": "R1", "impact": "BROKEN",
                                         "detail": "", "paths": []}]},
             poc__json=[{"target": "a.py", "framework": "pytest",
                        "test_code": "...", "why_it_fails": "..."}])
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["poc"]["status"] == "done"


def test_usage_lands_on_the_phase_that_spent_it(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"claims": [{"id": "C1"}], "docs": []},
             usage__json=[{"phase": "verify", "cost_usd": 0.34, "duration_ms": 9100,
                           "model": "claude-sonnet-5", "num_turns": 12}])
    verify = _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["verify"]
    assert verify["status"] == "done"
    assert verify["cost_usd"] == 0.34
    assert verify["model"] == "claude-sonnet-5"
    assert {"label": "claims", "value": 1} in verify["metrics"]


def test_a_failed_report_is_marked_failed(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200},
             report__md="# Review FAILED\n\n- Error: boom\n")
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["report"]["status"] == "failed"


def test_a_live_lock_marks_the_first_unfinished_phase_running(tmp_path, monkeypatch):
    d = _session(tmp_path, snapshot__json={"body": "x" * 200},
                 claims__json=[{"id": "C1"}])
    (d / "review.lock").write_text(json.dumps({"pid": os.getpid(),
                                               "started_at": "2026-08-16T10:00:00"}))
    graph = metrics.pipeline_graph(tmp_path, "demo", "app", 8)
    assert graph["running"] is True
    assert _by_id(graph)["verify"]["status"] == "running"


def test_a_live_lock_during_doc_remediation_marks_remediate_running(tmp_path):
    # Regression for ORDER omitting "remediate": once score.json and
    # answers.json exist and a doc is fixable, remediate — not report — is
    # the phase actually running.
    d = _session(tmp_path,
                 snapshot__json={"body": "x" * 200},
                 claims__json=[{"id": "C1"}],
                 findings__json={"docs": [{"path": "README.md", "status": "STALE"}]},
                 score__json={"gate": "pass", "verification_score": 0.9},
                 answers__json=[])
    (d / "review.lock").write_text(json.dumps({"pid": os.getpid(),
                                               "started_at": "2026-08-16T10:00:00"}))
    graph = metrics.pipeline_graph(tmp_path, "demo", "app", 8)
    nodes = _by_id(graph)
    assert nodes["remediate"]["status"] == "running"
    assert nodes["report"]["status"] == "pending"


def test_a_live_lock_during_poc_drafting_marks_poc_running(tmp_path):
    # Regression for ORDER omitting "poc": once remediate has finished (no
    # fixable doc here, so it is skipped) and something was found broken,
    # poc — not report — is the phase actually running.
    d = _session(tmp_path,
                 snapshot__json={"body": "x" * 200},
                 claims__json=[{"id": "C1"}],
                 findings__json={"impact": [{"requirement": "R1", "impact": "BROKEN",
                                             "detail": "", "paths": []}]},
                 score__json={"gate": "fail", "verification_score": 0.5},
                 answers__json=[])
    (d / "review.lock").write_text(json.dumps({"pid": os.getpid(),
                                               "started_at": "2026-08-16T10:00:00"}))
    graph = metrics.pipeline_graph(tmp_path, "demo", "app", 8)
    nodes = _by_id(graph)
    assert nodes["poc"]["status"] == "running"
    assert nodes["report"]["status"] == "pending"


def test_edges_form_the_documented_dag(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    edges = {(e["source"], e["target"])
             for e in metrics.pipeline_graph(tmp_path, "demo", "app", 8)["edges"]}
    assert ("verify", "remediate") in edges     # doc-fix branch
    assert ("followup", "verify") in edges      # reply loop
    assert ("remediate", "report") in edges
    assert ("verify", "poc") in edges           # PoC-test branch
    assert ("poc", "report") in edges


# ---------------------------------------------------------------- sibling scan

SIBLINGS_JSON = {"scanned": 12, "truncated": False, "skipped": "",
                 "siblings": [{"pr": 456, "title": "t", "author": "dev_b",
                               "url": "u", "base": "main", "head": "h",
                               "updated_at": "2026-08-16T09:00:00Z",
                               "overlap": "file", "overlap_paths": ["a.py"],
                               "files": [], "pruned": []}]}

COLLISION = {"pr": 456, "status": "SEMANTIC_CONFLICT", "symbol": "createInvoice",
             "paths": ["a.py"], "evidence": ["a.py:42"], "detail": "d",
             "confidence": 0.9}


def test_the_sibling_scan_is_a_pipeline_phase(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200},
             siblings__json=SIBLINGS_JSON)
    node = _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))["siblings"]
    assert node["status"] == "done"
    assert {"label": "scanned", "value": 12} in node["metrics"]
    assert {"label": "overlapping", "value": 1} in node["metrics"]


def test_a_session_without_a_sibling_scan_shows_the_phase_skipped(tmp_path):
    # every session written before this feature, sessions/demo/app included
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    assert _by_id(metrics.pipeline_graph(tmp_path, "demo", "app", 8))[
        "siblings"]["status"] == "skipped"


def test_the_sibling_phase_sits_between_snapshot_and_verify(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    edges = {(e["source"], e["target"])
             for e in metrics.pipeline_graph(tmp_path, "demo", "app", 8)["edges"]}
    assert ("snapshot", "siblings") in edges
    assert ("siblings", "verify") in edges


def test_the_pr_detail_carries_collisions_and_the_scan(tmp_path):
    findings = {"claims": [], "docs": [], "impact": [],
                "callers_outside_diff": [], "contracts": [], "tests": [],
                "threads": [], "cross_pr": [COLLISION],
                "unresolved_questions": []}
    _write_session(tmp_path, "o", "r", 7, snapshot=SNAPSHOT, findings=findings)
    (tmp_path / "o" / "r" / "pr-7" / "siblings.json").write_text(
        json.dumps(SIBLINGS_JSON))
    detail = metrics.pr_detail(tmp_path, "o", "r", 7)
    assert detail["cross_pr"][0]["pr"] == 456
    assert detail["siblings"]["scanned"] == 12
    assert detail["pr"]["cross_pr"] == 1
