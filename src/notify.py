"""One-way Slack notification when a review finishes.

Fire-and-forget by design: a broken webhook must never fail a review, so every
error is swallowed after being printed.
"""
import json
import urllib.error
import urllib.request

GATE_ICON = {"pass": ":white_check_mark:", "warn": ":warning:", "fail": ":no_entry:"}


def build_payload(snapshot: dict, findings: dict, scores: dict,
                  verdict: str, dashboard_url: str = "") -> dict:
    """The Slack message body: verdict, gate, top risks, links."""
    pr_url = (f"https://github.com/{snapshot['owner']}/{snapshot['repo']}"
              f"/pull/{snapshot['pr']}")
    icon = GATE_ICON.get(scores.get("gate", ""), ":mag:")
    title = (f"{icon} *{snapshot['owner']}/{snapshot['repo']}* "
             f"<{pr_url}|#{snapshot['pr']}> — {verdict}")
    facts = (f"Gate *{scores.get('gate', '?')}* · "
             f"score {scores.get('verification_score', 0):.0%} · "
             f"risk {scores.get('business_risk', '?')}")
    reasons = "\n".join(f"• {r}" for r in (scores.get("reasons") or [])[:5])
    unresolved = findings.get("unresolved_questions") or []
    if unresolved:
        reasons += ("\n" if reasons else "") + \
            f"• {len(unresolved)} open question(s) for the author"
    text = f"{title}\n{facts}"
    if reasons:
        text += f"\n{reasons}"
    if dashboard_url:
        text += f"\n<{dashboard_url}|Open dashboard>"
    return {"text": text}


def notify(webhook_url: str, payload: dict, *, opener=urllib.request.urlopen) -> bool:
    """POST to a Slack incoming webhook. Returns False instead of raising."""
    if not webhook_url:
        return False
    req = urllib.request.Request(
        webhook_url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with opener(req, timeout=10):
            return True
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[notify] slack webhook failed: {e}")
        return False
