"""Post the merge decision back to the ticket, as one comment that gets updated.

The shape is src/notify.py's: a deterministic module that runs after scoring,
reads what the review already persisted, and writes outward. The agent is not
involved and never sees Jira, so nothing a PR author wrote can steer this call.

Idempotent the way synthesize.post_comment is — find the previous comment by its
marker and PUT over it. Without that, a PR pushed to ten times leaves ten bot
comments on the ticket, which is how an integration earns itself a mute.

The marker is plain text, not synthesize.py's HTML comment: a Jira v2 comment is
not rendered Markdown, so `<!-- ... -->` would show up as clutter.
"""
import jira_client

MARKER = "[pr-sentinel]"
GATE_LINE = {"pass": "PASS — every claim proven, nothing broken",
             "warn": "WARN — merged with caveats",
             "fail": "FAIL — blocking merge"}


def build_body(snapshot: dict, findings: dict, scores: dict) -> str:
    """The ticket comment: verdict, why, what failed, where to look."""
    pr_url = (f"https://github.com/{snapshot['owner']}/{snapshot['repo']}"
              f"/pull/{snapshot['pr']}")
    gate = scores.get("gate", "")
    lines = [
        f"PR Sentinel reviewed {snapshot['owner']}/{snapshot['repo']} "
        f"#{snapshot['pr']} — {snapshot.get('title', '')}",
        pr_url,
        "",
        f"Gate: {GATE_LINE.get(gate, gate)}",
        f"Verification score: {scores.get('verification_score', 0):.0%} | "
        f"business risk: {scores.get('business_risk', 'unknown')}",
    ]

    reasons = scores.get("reasons") or []
    if reasons:
        lines += ["", "Why:"] + [f"* {r}" for r in reasons]

    failed = [c for c in findings.get("claims") or [] if c.get("status") == "FAIL"]
    lines += ["", "Failed claims:"]
    lines += ([f"* {c['id']}: {c.get('note', '')}" for c in failed] if failed
              else ["* No failed claims."])

    questions = findings.get("unresolved_questions") or []
    if questions:
        lines += ["", "Open questions for the author:"] + [f"* {q}" for q in questions]

    lines += ["", MARKER]
    return "\n".join(lines)


def post_result(cfg, key: str, body: str, *, opener=None) -> bool:
    """Create or update this ticket's single PR Sentinel comment. Never raises."""
    if not key:
        return False
    kwargs = {"opener": opener} if opener is not None else {}
    for comment in jira_client.list_comments(cfg, key, **kwargs):
        if MARKER in (comment.get("body") or ""):
            return jira_client.update_comment(cfg, key, comment["id"], body, **kwargs)
    return jira_client.add_comment(cfg, key, body, **kwargs)
