import jira_client
import jira_report
from jira_report import MARKER, build_body, post_result

CFG = jira_client.JiraConfig(base_url="https://x.atlassian.net", email="e", token="t")

SNAPSHOT = {"owner": "acme", "repo": "app", "pr": 7, "title": "Add retries"}

SCORES = {"gate": "fail", "verification_score": 0.5, "business_risk": "high",
          "reasons": ["1 breaking contract change", "verification score 50% below 80%"],
          "labels": []}

FINDINGS = {
    "claims": [
        {"id": "C1", "status": "FAIL", "evidence": ["a.py:1"],
         "note": "the retry is not wired up", "confidence": 0.9},
        {"id": "C2", "status": "PASS", "evidence": ["b.py:2"], "note": "", "confidence": 1.0},
    ],
    "unresolved_questions": ["Should a 429 count as retryable?"],
}


def test_body_states_the_gate_and_the_score():
    body = build_body(SNAPSHOT, FINDINGS, SCORES)
    assert "fail" in body.lower()
    assert "50%" in body
    assert "high" in body


def test_body_links_the_pull_request():
    assert "https://github.com/acme/app/pull/7" in build_body(SNAPSHOT, FINDINGS, SCORES)


def test_body_lists_failed_claims_only():
    body = build_body(SNAPSHOT, FINDINGS, SCORES)
    assert "the retry is not wired up" in body
    assert "C2" not in body


def test_body_reports_open_questions():
    assert "Should a 429 count as retryable?" in build_body(SNAPSHOT, FINDINGS, SCORES)


def test_body_ends_with_the_marker():
    assert build_body(SNAPSHOT, FINDINGS, SCORES).rstrip().endswith(MARKER)


def test_the_marker_is_not_an_html_comment():
    assert "<!--" not in MARKER


def test_a_clean_review_says_so():
    clean = {"claims": [{"id": "C1", "status": "PASS", "evidence": ["a.py:1"],
                         "note": "", "confidence": 1.0}], "unresolved_questions": []}
    body = build_body(SNAPSHOT, clean, {**SCORES, "gate": "pass", "reasons": []})
    assert "No failed claims" in body


def test_post_creates_a_comment_when_none_exists(monkeypatch):
    calls = {}
    monkeypatch.setattr(jira_client, "list_comments", lambda *a, **kw: [])

    def fake_add(cfg, key, body, **kw):
        calls.setdefault("add", (key, body))
        return True

    def fake_update(*a, **kw):
        calls.setdefault("update", True)
        return True

    monkeypatch.setattr(jira_client, "add_comment", fake_add)
    monkeypatch.setattr(jira_client, "update_comment", fake_update)
    assert post_result(CFG, "ABC-1", "body " + MARKER) is True
    assert calls["add"] == ("ABC-1", "body " + MARKER)
    assert "update" not in calls


def test_post_updates_the_existing_marked_comment(monkeypatch):
    calls = {}
    monkeypatch.setattr(jira_client, "list_comments", lambda *a, **kw: [
        {"id": "10", "body": "unrelated human comment"},
        {"id": "11", "body": "older report\n" + MARKER},
    ])

    def fake_add(*a, **kw):
        calls.setdefault("add", True)
        return True

    def fake_update(cfg, key, cid, body, **kw):
        calls.setdefault("update", (key, cid))
        return True

    monkeypatch.setattr(jira_client, "add_comment", fake_add)
    monkeypatch.setattr(jira_client, "update_comment", fake_update)
    assert post_result(CFG, "ABC-1", "new " + MARKER) is True
    assert calls["update"] == ("ABC-1", "11")
    assert "add" not in calls


def test_post_never_touches_an_unmarked_comment(monkeypatch):
    monkeypatch.setattr(jira_client, "list_comments", lambda *a, **kw: [
        {"id": "10", "body": "a human wrote this"}])
    monkeypatch.setattr(jira_client, "add_comment", lambda *a, **kw: True)

    def fail_update(*a, **kw):
        raise AssertionError("must not update a comment without the marker")

    monkeypatch.setattr(jira_client, "update_comment", fail_update)
    assert post_result(CFG, "ABC-1", "new " + MARKER) is True


def test_post_returns_false_without_a_key(monkeypatch):
    monkeypatch.setattr(jira_client, "list_comments", lambda *a, **kw: [])
    assert post_result(CFG, "", "body") is False


def test_post_returns_false_when_the_write_fails(monkeypatch):
    monkeypatch.setattr(jira_client, "list_comments", lambda *a, **kw: [])
    monkeypatch.setattr(jira_client, "add_comment", lambda *a, **kw: False)
    assert post_result(CFG, "ABC-1", "body") is False
