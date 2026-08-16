from config import load_config

ENV_NAMES = ("PRS_SESSION_ROOT", "SLACK_WEBHOOK_URL")


def _clear(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_load_config_defaults(monkeypatch):
    _clear(monkeypatch)
    cfg = load_config()
    assert cfg.session_root.name == "sessions"
    assert cfg.slack_webhook == ""


def test_load_config_from_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PRS_SESSION_ROOT", "/tmp/my-sessions")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    cfg = load_config()
    assert str(cfg.session_root) == "/tmp/my-sessions"
    assert cfg.slack_webhook == "https://hooks.slack.test/x"
