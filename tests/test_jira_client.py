import base64
import json

import jira_client

CFG = jira_client.JiraConfig(base_url="https://acme.atlassian.net",
                      email="bot@acme.io", token="tok")

ISSUE = {
    "key": "ABC-123",
    "fields": {
        "summary": "Retry failed payments",
        "description": "As a customer I want a failed charge retried twice.",
        "status": {"name": "In Progress"},
        "issuetype": {"name": "Story"},
        "priority": {"name": "High"},
        "labels": ["payments"],
    },
}


class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _opener(payload, seen=None):
    def opener(req, timeout=None):
        if seen is not None:
            seen.append(req)
        return _Resp(payload)
    return opener


def _boom(req, timeout=None):
    raise OSError("connection refused")


def test_configured_requires_all_three_values():
    assert CFG.configured()
    assert not jira_client.JiraConfig(base_url="", email="a", token="b").configured()
    assert not jira_client.JiraConfig(base_url="u", email="", token="b").configured()
    assert not jira_client.JiraConfig(base_url="u", email="a", token="").configured()


def test_auth_header_is_basic_email_colon_token():
    expected = base64.b64encode(b"bot@acme.io:tok").decode()
    assert CFG.auth_header() == f"Basic {expected}"


def test_load_config_reads_the_environment(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://x.atlassian.net/")
    monkeypatch.setenv("JIRA_EMAIL", "e@x.io")
    monkeypatch.setenv("JIRA_API_TOKEN", "t")
    cfg = jira_client.load_config()
    assert cfg.base_url == "https://x.atlassian.net"      # trailing slash trimmed
    assert cfg.configured()


def test_load_config_without_env_is_unconfigured(monkeypatch):
    for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert not jira_client.load_config().configured()


def test_get_issue_normalises_the_payload():
    issue = jira_client.get_issue(CFG, "ABC-123", opener=_opener(ISSUE))
    assert issue == {
        "key": "ABC-123",
        "summary": "Retry failed payments",
        "description": "As a customer I want a failed charge retried twice.",
        "status": "In Progress",
        "type": "Story",
        "priority": "High",
        "labels": ["payments"],
        "url": "https://acme.atlassian.net/browse/ABC-123",
    }


def test_get_issue_uses_rest_v2_and_authenticates():
    seen = []
    jira_client.get_issue(CFG, "ABC-123", opener=_opener(ISSUE, seen))
    assert "/rest/api/2/issue/ABC-123" in seen[0].full_url
    assert seen[0].get_header("Authorization") == CFG.auth_header()


def test_get_issue_returns_none_when_unconfigured():
    unset = jira_client.JiraConfig(base_url="", email="", token="")
    assert jira_client.get_issue(unset, "ABC-1", opener=_boom) is None


def test_get_issue_returns_none_on_a_transport_failure():
    assert jira_client.get_issue(CFG, "ABC-1", opener=_boom) is None


def test_get_issue_survives_missing_fields():
    issue = jira_client.get_issue(CFG, "ABC-1", opener=_opener({"key": "ABC-1", "fields": {}}))
    assert issue["summary"] == "" and issue["labels"] == []
    assert issue["description"] == ""


def test_get_issue_returns_none_on_a_null_description():
    issue = jira_client.get_issue(
        CFG, "ABC-1", opener=_opener({"key": "ABC-1", "fields": {"description": None}}))
    assert issue["description"] == ""


def test_list_comments_returns_the_comment_array():
    payload = {"comments": [{"id": "1", "body": "hi"}]}
    assert jira_client.list_comments(CFG, "ABC-1", opener=_opener(payload)) == payload["comments"]


def test_list_comments_is_empty_on_failure():
    assert jira_client.list_comments(CFG, "ABC-1", opener=_boom) == []


def test_add_comment_posts_a_plain_string_body():
    seen = []
    assert jira_client.add_comment(CFG, "ABC-1", "hello", opener=_opener({"id": "9"}, seen)) is True
    assert seen[0].get_method() == "POST"
    assert "/rest/api/2/issue/ABC-1/comment" in seen[0].full_url
    assert json.loads(seen[0].data.decode()) == {"body": "hello"}


def test_update_comment_puts_to_the_comment_id():
    seen = []
    assert jira_client.update_comment(CFG, "ABC-1", "42", "new",
                               opener=_opener({"id": "42"}, seen)) is True
    assert seen[0].get_method() == "PUT"
    assert seen[0].full_url.endswith("/rest/api/2/issue/ABC-1/comment/42")


def test_writes_return_false_on_failure():
    assert jira_client.add_comment(CFG, "ABC-1", "x", opener=_boom) is False
    assert jira_client.update_comment(CFG, "ABC-1", "1", "x", opener=_boom) is False


def test_writes_return_false_when_unconfigured():
    unset = jira_client.JiraConfig(base_url="", email="", token="")
    assert jira_client.add_comment(unset, "ABC-1", "x", opener=_boom) is False
