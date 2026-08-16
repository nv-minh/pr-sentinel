from config import DEFAULT_CLAIMS_MODEL, DEFAULT_MODEL, Config, load_config


def _clear(monkeypatch):
    for name in ("ANTHROPIC_API_KEY", "PRS_MODEL", "PRS_CLAIMS_MODEL",
                 "PRS_SESSION_ROOT", "SLACK_WEBHOOK_URL"):
        monkeypatch.delenv(name, raising=False)


def test_load_config_defaults(monkeypatch):
    _clear(monkeypatch)
    cfg = load_config()
    assert cfg.api_key == ""
    assert cfg.model == DEFAULT_MODEL
    assert cfg.claims_model == DEFAULT_CLAIMS_MODEL
    assert cfg.session_root.name == "sessions"
    assert cfg.slack_webhook == ""


def test_load_config_from_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("PRS_MODEL", "claude-opus-5")
    monkeypatch.setenv("PRS_CLAIMS_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("PRS_SESSION_ROOT", "/tmp/my-sessions")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    cfg = load_config()
    assert cfg.api_key == "sk-ant-test"
    assert cfg.model == "claude-opus-5"
    assert cfg.claims_model == "claude-haiku-4-5-20251001"
    assert str(cfg.session_root) == "/tmp/my-sessions"
    assert cfg.slack_webhook == "https://hooks.slack.test/x"


def _config(api_key: str, tmp_path) -> Config:
    return Config(api_key=api_key, model="m", claims_model="c",
                  session_root=tmp_path, slack_webhook="")


def test_has_auth_accepts_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "missing.json")
    assert _config("sk-ant-test", tmp_path).has_auth() is True


def test_has_auth_accepts_logged_in_cli(tmp_path, monkeypatch):
    cli = tmp_path / ".claude.json"
    cli.write_text("{}")
    monkeypatch.setattr("config.CLI_CONFIG", cli)
    assert _config("", tmp_path).has_auth() is True


def test_has_auth_false_without_either(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "missing.json")
    assert _config("", tmp_path).has_auth() is False
