from config import Config, load_config

ENV_NAMES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
             "PRS_PROVIDER", "PRS_MODEL", "PRS_CLAIMS_MODEL",
             "PRS_SESSION_ROOT", "SLACK_WEBHOOK_URL")


def _clear(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_load_config_defaults(monkeypatch):
    _clear(monkeypatch)
    cfg = load_config()
    assert cfg.api_key == ""
    assert cfg.auth_token == ""
    assert cfg.base_url == ""
    assert cfg.provider == ""
    # empty means "let the provider decide"
    assert cfg.model == ""
    assert cfg.claims_model == ""
    assert cfg.session_root.name == "sessions"
    assert cfg.slack_webhook == ""


def test_load_config_from_env(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.local/anthropic")
    monkeypatch.setenv("PRS_PROVIDER", "deepseek")
    monkeypatch.setenv("PRS_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("PRS_CLAIMS_MODEL", "deepseek-v4-flash")
    monkeypatch.setenv("PRS_SESSION_ROOT", "/tmp/my-sessions")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    cfg = load_config()
    assert cfg.api_key == "sk-ant-test"
    assert cfg.auth_token == "tok"
    assert cfg.base_url == "https://proxy.local/anthropic"
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-v4-pro"
    assert cfg.claims_model == "deepseek-v4-flash"
    assert str(cfg.session_root) == "/tmp/my-sessions"
    assert cfg.slack_webhook == "https://hooks.slack.test/x"


def _config(api_key: str, tmp_path, auth_token: str = "") -> Config:
    return Config(api_key=api_key, auth_token=auth_token, base_url="", provider="",
                  model="", claims_model="", session_root=tmp_path, slack_webhook="")


def test_has_auth_accepts_api_key(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "missing.json")
    assert _config("sk-ant-test", tmp_path).has_auth() is True


def test_has_auth_accepts_auth_token(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "missing.json")
    assert _config("", tmp_path, auth_token="tok").has_auth() is True


def test_has_auth_accepts_logged_in_cli(tmp_path, monkeypatch):
    cli = tmp_path / ".claude.json"
    cli.write_text("{}")
    monkeypatch.setattr("config.CLI_CONFIG", cli)
    assert _config("", tmp_path).has_auth() is True


def test_has_auth_false_without_either(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "missing.json")
    assert _config("", tmp_path).has_auth() is False
