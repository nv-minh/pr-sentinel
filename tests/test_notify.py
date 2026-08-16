import json

from notify import build_payload, notify

SNAPSHOT = {"owner": "demo", "repo": "app", "pr": 7}
SCORES = {"gate": "fail", "verification_score": 0.5, "business_risk": "high",
          "reasons": ["BREAKING_API_CHANGE in openapi.yml"]}


def test_build_payload_has_verdict_gate_and_link():
    text = build_payload(SNAPSHOT, {"unresolved_questions": []}, SCORES,
                         "MISLEADING")["text"]
    assert "https://github.com/demo/app/pull/7" in text
    assert "MISLEADING" in text
    assert "Gate *fail*" in text
    assert "score 50%" in text
    assert "BREAKING_API_CHANGE" in text


def test_build_payload_counts_open_questions():
    findings = {"unresolved_questions": ["a?", "b?"]}
    text = build_payload(SNAPSHOT, findings, SCORES, "PARTIAL")["text"]
    assert "2 open question(s)" in text


def test_build_payload_adds_dashboard_link():
    text = build_payload(SNAPSHOT, {}, SCORES, "ACCURATE",
                         dashboard_url="http://localhost:6789/x")["text"]
    assert "http://localhost:6789/x" in text


def test_notify_posts_json():
    sent = {}

    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(req, timeout=None):
        sent["url"] = req.full_url
        sent["body"] = json.loads(req.data.decode())
        return FakeResponse()

    assert notify("https://hooks.slack.test/x", {"text": "hi"}, opener=opener) is True
    assert sent["url"] == "https://hooks.slack.test/x"
    assert sent["body"] == {"text": "hi"}


def test_notify_without_webhook_is_a_noop():
    assert notify("", {"text": "hi"}) is False


def test_notify_swallows_failures():
    def opener(req, timeout=None):
        raise OSError("slack is down")

    assert notify("https://hooks.slack.test/x", {"text": "hi"}, opener=opener) is False
