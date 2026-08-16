"""Jira Cloud REST v2 over urllib. No new dependency, no exception ever escapes.

v2 rather than v3 deliberately. On Jira Cloud both are live, but v3 speaks
Atlassian Document Format in both directions: a GET hands back the description
as an ADF tree that would have to be flattened before it could enter a prompt,
and a comment would have to be assembled as an ADF tree rather than written as
text. v2 exchanges plain strings and offers nothing less that this project
needs, which deletes an entire class of work from both halves of the feature.

Credentials come from the environment only, never from prsentinel.yml.

Every function degrades instead of raising, like src/notify.py: a Jira outage
costs a review its requirement context, it never fails the review.
"""
import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

TIMEOUT = 10
FIELDS = "summary,description,status,issuetype,priority,labels"


@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    email: str
    token: str

    def configured(self) -> bool:
        return bool(self.base_url and self.email and self.token)

    def auth_header(self) -> str:
        raw = f"{self.email}:{self.token}".encode()
        return f"Basic {base64.b64encode(raw).decode()}"


def load_config() -> JiraConfig:
    return JiraConfig(
        base_url=os.environ.get("JIRA_BASE_URL", "").rstrip("/"),
        email=os.environ.get("JIRA_EMAIL", ""),
        token=os.environ.get("JIRA_API_TOKEN", ""),
    )


def _request(cfg: JiraConfig, path: str, *, method: str = "GET",
             payload: dict | None = None, opener=urllib.request.urlopen):
    """One authenticated call. Returns the decoded body, or None on any failure."""
    if not cfg.configured():
        return None
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{cfg.base_url}{path}", data=data, method=method,
        headers={"Authorization": cfg.auth_header(),
                 "Accept": "application/json",
                 "Content-Type": "application/json"})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            body = resp.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[jira] {method} {path} failed: {e}")
        return None
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        print(f"[jira] {method} {path} returned invalid JSON: {e}")
        return None


def get_issue(cfg: JiraConfig, key: str, *, opener=urllib.request.urlopen) -> dict | None:
    """One issue, flattened to the handful of fields a review cares about."""
    data = _request(cfg, f"/rest/api/2/issue/{key}?fields={FIELDS}", opener=opener)
    if not isinstance(data, dict) or "fields" not in data:
        return None
    fields = data.get("fields") or {}

    def name_of(field: str) -> str:
        value = fields.get(field) or {}
        return value.get("name", "") if isinstance(value, dict) else ""

    return {
        "key": data.get("key", key),
        "summary": fields.get("summary") or "",
        "description": fields.get("description") or "",
        "status": name_of("status"),
        "type": name_of("issuetype"),
        "priority": name_of("priority"),
        "labels": list(fields.get("labels") or []),
        "url": f"{cfg.base_url}/browse/{data.get('key', key)}",
    }


def list_comments(cfg: JiraConfig, key: str, *, opener=urllib.request.urlopen) -> list[dict]:
    data = _request(cfg, f"/rest/api/2/issue/{key}/comment", opener=opener)
    if not isinstance(data, dict):
        return []
    return list(data.get("comments") or [])


def add_comment(cfg: JiraConfig, key: str, body: str, *,
                opener=urllib.request.urlopen) -> bool:
    result = _request(cfg, f"/rest/api/2/issue/{key}/comment", method="POST",
                      payload={"body": body}, opener=opener)
    return result is not None


def update_comment(cfg: JiraConfig, key: str, comment_id: str, body: str, *,
                   opener=urllib.request.urlopen) -> bool:
    result = _request(cfg, f"/rest/api/2/issue/{key}/comment/{comment_id}",
                      method="PUT", payload={"body": body}, opener=opener)
    return result is not None
