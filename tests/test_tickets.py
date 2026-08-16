import json

import jira_client
from tickets import fetch_tickets, find_keys


def _snap(*, title="", body="", head=""):
    return {"title": title, "body": body, "head": head}


PROJECTS = ["ABC", "PRJ"]


def test_a_browse_link_in_the_body_is_found():
    snap = _snap(body="Context: https://acme.atlassian.net/browse/ABC-123 thanks")
    assert find_keys(snap, PROJECTS) == ["ABC-123"]


def test_a_browse_link_needs_no_allowlist():
    snap = _snap(body="https://acme.atlassian.net/browse/ZZZ-9")
    assert find_keys(snap, PROJECTS) == ["ZZZ-9"]


def test_a_title_prefix_is_found():
    assert find_keys(_snap(title="ABC-123: add retries"), PROJECTS) == ["ABC-123"]


def test_a_title_prefix_outside_the_allowlist_is_ignored():
    assert find_keys(_snap(title="XYZ-1: add retries"), PROJECTS) == []


def test_a_branch_name_key_is_found():
    assert find_keys(_snap(head="feature/ABC-123-add-retries"), PROJECTS) == ["ABC-123"]


def test_utf_8_in_a_title_prefix_is_not_a_ticket():
    assert find_keys(_snap(title="UTF-8: fix encoding"), PROJECTS) == []


def test_a_cve_in_a_title_prefix_is_not_a_ticket():
    assert find_keys(_snap(title="CVE-2024-1234: bump the parser"), PROJECTS) == []


def test_the_browse_link_wins_over_the_title_and_branch():
    snap = _snap(title="PRJ-2: work", body="see https://x.atlassian.net/browse/ABC-1",
                 head="feature/PRJ-3-work")
    assert find_keys(snap, PROJECTS)[0] == "ABC-1"


def test_every_source_contributes_after_the_primary():
    snap = _snap(title="PRJ-2: work", body="https://x.atlassian.net/browse/ABC-1",
                 head="feature/PRJ-3-work")
    assert find_keys(snap, PROJECTS) == ["ABC-1", "PRJ-2", "PRJ-3"]


def test_duplicate_keys_across_sources_appear_once():
    snap = _snap(title="ABC-1: work", body="https://x.atlassian.net/browse/ABC-1",
                 head="feature/ABC-1-work")
    assert find_keys(snap, PROJECTS) == ["ABC-1"]


def test_at_most_three_tickets_are_returned():
    body = " ".join(f"https://x.atlassian.net/browse/ABC-{i}" for i in range(1, 8))
    assert len(find_keys(_snap(body=body), PROJECTS)) == 3


def test_a_lowercase_browse_key_is_normalised():
    snap = _snap(body="https://x.atlassian.net/browse/abc-7")
    assert find_keys(snap, PROJECTS) == ["ABC-7"]


def test_the_allowlist_is_matched_case_insensitively():
    assert find_keys(_snap(title="abc-9: work"), PROJECTS) == ["ABC-9"]


def test_a_bare_key_in_the_body_is_not_a_source():
    assert find_keys(_snap(body="relates to ABC-5 somehow"), PROJECTS) == []


def test_no_sources_yields_nothing():
    assert find_keys(_snap(title="fix things", head="fix-things"), PROJECTS) == []


def test_an_empty_allowlist_still_honours_browse_links():
    snap = _snap(title="ABC-1: work", body="https://x.atlassian.net/browse/ABC-2")
    assert find_keys(snap, []) == ["ABC-2"]


JIRA_CFG = {"projects": ["ABC"], "comment_result": False}
CONFIGURED = jira_client.JiraConfig(base_url="https://x.atlassian.net", email="e", token="t")
UNCONFIGURED = jira_client.JiraConfig(base_url="", email="", token="")


def _issue(key):
    return {"key": key, "summary": f"summary {key}", "description": "req text",
            "status": "In Progress", "type": "Story", "priority": "High",
            "labels": [], "url": f"https://x.atlassian.net/browse/{key}"}


def _fetcher(available, calls=None):
    def get_issue(cfg, key, *, opener=None):
        if calls is not None:
            calls.append(key)
        return _issue(key) if key in available else None
    return get_issue


def test_fetch_writes_the_ticket_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(jira_client, "get_issue", _fetcher({"ABC-1"}))
    snap = {"title": "ABC-1: work", "body": "", "head": ""}
    result = fetch_tickets(snap, tmp_path, JIRA_CFG, config=CONFIGURED)
    assert result["primary"] == "ABC-1"
    assert result["tickets"][0]["summary"] == "summary ABC-1"
    assert result["skipped"] == ""
    assert json.loads((tmp_path / "ticket.json").read_text()) == result


def test_fetch_without_jira_configured_is_skipped(tmp_path):
    snap = {"title": "ABC-1: work", "body": "", "head": ""}
    result = fetch_tickets(snap, tmp_path, JIRA_CFG, config=UNCONFIGURED)
    assert result == {"primary": "", "tickets": [],
                      "skipped": "Jira is not configured (JIRA_BASE_URL, "
                                 "JIRA_EMAIL, JIRA_API_TOKEN)"}


def test_fetch_without_any_key_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(jira_client, "get_issue", _fetcher(set()))
    snap = {"title": "just work", "body": "", "head": "fix"}
    result = fetch_tickets(snap, tmp_path, JIRA_CFG, config=CONFIGURED)
    assert result["tickets"] == []
    assert "no ticket key" in result["skipped"]


def test_an_unreachable_ticket_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(jira_client, "get_issue", _fetcher(set()))
    snap = {"title": "ABC-9: work", "body": "", "head": ""}
    result = fetch_tickets(snap, tmp_path, JIRA_CFG, config=CONFIGURED)
    assert result["tickets"] == []
    assert "ABC-9" in result["skipped"]


def test_the_primary_is_the_first_key_that_actually_resolved(tmp_path, monkeypatch):
    monkeypatch.setattr(jira_client, "get_issue", _fetcher({"ABC-2"}))
    snap = {"title": "", "head": "",
            "body": "https://x.atlassian.net/browse/ABC-1 "
                    "https://x.atlassian.net/browse/ABC-2"}
    result = fetch_tickets(snap, tmp_path, JIRA_CFG, config=CONFIGURED)
    assert result["primary"] == "ABC-2"
    assert result["skipped"] == ""


def test_at_most_three_tickets_are_fetched(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(jira_client, "get_issue", _fetcher({f"ABC-{i}" for i in range(1, 8)}, calls))
    body = " ".join(f"https://x.atlassian.net/browse/ABC-{i}" for i in range(1, 8))
    fetch_tickets({"title": "", "body": body, "head": ""}, tmp_path, JIRA_CFG,
                  config=CONFIGURED)
    assert len(calls) == 3


def test_fetch_uses_the_configured_project_allowlist(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(jira_client, "get_issue", _fetcher({"ZZZ-1"}, calls))
    snap = {"title": "ZZZ-1: work", "body": "", "head": ""}
    fetch_tickets(snap, tmp_path, {"projects": ["ZZZ"]}, config=CONFIGURED)
    assert calls == ["ZZZ-1"]


def test_a_lookup_that_raises_is_recorded_not_propagated(tmp_path, monkeypatch):
    def boom(cfg, key, **kw):
        raise RuntimeError("jira exploded")

    monkeypatch.setattr(jira_client, "get_issue", boom)
    snap = {"title": "ABC-9: work", "body": "", "head": ""}
    result = fetch_tickets(snap, tmp_path, JIRA_CFG, config=CONFIGURED)
    assert result["tickets"] == []
    assert "ABC-9" in result["skipped"]
    assert json.loads((tmp_path / "ticket.json").read_text()) == result
