"""Find the Jira ticket a pull request is about, and fetch it once.

Three sources, most explicit first: a /browse/ link a human pasted into the PR
body, a key prefixing the PR title, the branch name. The link wins because
somebody chose to put it there.

The hazard is not missing a key, it is inventing one. A bare `ABC-123` shape
also matches UTF-8, SHA-256, HTTP-2, RFC-7231 and CVE-2024-1234, all of which
turn up in ordinary PR text. So a bare key counts only when its project prefix
is configured in `jira.projects`, while a key inside a browse URL is
unambiguous and needs no allowlist — and bare keys loose in the body are not a
source at all.
"""
import json
import re
from pathlib import Path

import jira_client

MAX_TICKETS = 3

_KEY = r"[A-Za-z][A-Za-z0-9]{1,9}-\d{1,6}"
BROWSE_RE = re.compile(rf"https?://[^\s/]+/browse/({_KEY})")
TITLE_RE = re.compile(rf"^\s*({_KEY})\b")
BRANCH_RE = re.compile(rf"(?:^|[/_-])({_KEY})(?:$|[/_-])")


def _allowed(key: str, projects: list[str]) -> bool:
    prefix = key.split("-")[0].upper()
    return prefix in {p.upper() for p in projects}


def find_keys(snapshot: dict, projects: list[str]) -> list[str]:
    """Ticket keys for this PR, most explicit first, at most MAX_TICKETS."""
    keys: list[str] = []

    def add(key: str) -> None:
        key = key.upper()
        if key not in keys:
            keys.append(key)

    for match in BROWSE_RE.finditer(snapshot.get("body") or ""):
        add(match.group(1))

    title = TITLE_RE.match(snapshot.get("title") or "")
    if title and _allowed(title.group(1), projects):
        add(title.group(1))

    for match in BRANCH_RE.finditer(snapshot.get("head") or ""):
        if _allowed(match.group(1), projects):
            add(match.group(1))

    return keys[:MAX_TICKETS]


NOT_CONFIGURED = ("Jira is not configured (JIRA_BASE_URL, JIRA_EMAIL, "
                  "JIRA_API_TOKEN)")


def fetch_tickets(snapshot: dict, session_dir: Path, jira_cfg: dict, *,
                  config=None, opener=None) -> dict:
    """Fetch this PR's tickets once and persist ticket.json. Never raises.

    Returns `{"primary", "tickets", "skipped"}`; `skipped` is a sentence for the
    report and is non-empty exactly when nothing was fetched.
    """
    cfg = config if config is not None else jira_client.load_config()
    result = {"primary": "", "tickets": [], "skipped": ""}

    if not cfg.configured():
        result["skipped"] = NOT_CONFIGURED
    else:
        keys = find_keys(snapshot, list(jira_cfg.get("projects") or []))
        if not keys:
            result["skipped"] = ("no ticket key in the branch name, PR title or a "
                                 "browse link in the body")
        else:
            kwargs = {"opener": opener} if opener is not None else {}
            missed = []
            for key in keys:
                try:
                    issue = jira_client.get_issue(cfg, key, **kwargs)
                except Exception as e:  # noqa: BLE001 — see below
                    # The outermost boundary of an optional integration. Jira is
                    # context, never a gate: anything that escapes the client
                    # costs this review its requirement text and nothing more.
                    print(f"[tickets] {key} lookup raised: {e}")
                    issue = None
                if issue is None:
                    missed.append(key)
                else:
                    result["tickets"].append(issue)
            if result["tickets"]:
                result["primary"] = result["tickets"][0]["key"]
            else:
                result["skipped"] = (f"could not read {', '.join(missed)} — missing, "
                                     "unreachable or not permitted")

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "ticket.json").write_text(json.dumps(result, indent=2))
    if result["skipped"]:
        print(f"[tickets] no requirement context: {result['skipped']}")
    return result
