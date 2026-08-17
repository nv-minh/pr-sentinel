# tests/test_autoreview_config.py
import pytest

from autoreview_config import (DEFAULTS, auto_repos, list_repos, load_config,
                               remove_repo, set_language, set_provider,
                               set_repo_mode)

NEW_YML = """
org: sample-org
default_mode: manual
interval_minutes: 2
post_comment: true
skip_human: true
drafts: false
repos:
  sample-app: auto
  sample-api: auto
"""


def _write(path, text):
    path.write_text(text)
    return path


def test_load_config_new_format(tmp_path):
    cfg = load_config(_write(tmp_path / "a.yml", NEW_YML))
    assert cfg["org"] == "sample-org"
    assert cfg["default_mode"] == "manual"
    assert cfg["repos"] == {"sample-app": "auto", "sample-api": "auto"}
    assert cfg["interval_minutes"] == 2


def test_load_config_legacy_list(tmp_path):
    cfg = load_config(_write(tmp_path / "a.yml",
                             "repos:\n  - sample-org/sample-app\n"))
    assert cfg["repos"] == {"sample-org/sample-app": "auto"}


def test_load_config_empty_repos_allowed(tmp_path):
    cfg = load_config(_write(tmp_path / "a.yml", "org: sample-org\n"))
    assert cfg["repos"] == {}
    assert cfg["default_mode"] == "manual"


def test_load_config_invalid_mode(tmp_path):
    with pytest.raises(ValueError, match="mode must be auto|manual"):
        load_config(_write(tmp_path / "a.yml",
                           "repos:\n  sample-app: sometimes\n"))


def test_load_config_invalid_interval(tmp_path):
    with pytest.raises(ValueError, match="interval_minutes"):
        load_config(_write(tmp_path / "a.yml", "interval_minutes: -5\n"))


def test_load_config_bad_yaml(tmp_path):
    with pytest.raises(ValueError, match="invalid config YAML"):
        load_config(_write(tmp_path / "a.yml", "repos: [unclosed\n"))


def test_set_repo_mode_add_and_change(tmp_path):
    p = _write(tmp_path / "a.yml", "org: sample-org\nrepos:\n  sample-app: manual\n")
    set_repo_mode(p, "admin-web", "auto")          # add by name
    cfg = load_config(p)
    assert cfg["repos"]["admin-web"] == "auto"
    set_repo_mode(p, "sample-app", "auto")          # change
    assert load_config(p)["repos"]["sample-app"] == "auto"


def test_set_repo_mode_invalid(tmp_path):
    p = _write(tmp_path / "a.yml", "org: sample-org\n")
    with pytest.raises(ValueError, match="mode must be auto|manual"):
        set_repo_mode(p, "sample-app", "banana")


def test_remove_repo(tmp_path):
    p = _write(tmp_path / "a.yml", NEW_YML)
    remove_repo(p, "sample-api")
    cfg = load_config(p)
    assert "sample-api" not in cfg["repos"]
    assert "sample-app" in cfg["repos"]


def test_auto_repos_resolves_org(tmp_path):
    cfg = load_config(_write(tmp_path / "a.yml", NEW_YML))
    assert auto_repos(cfg) == [("sample-org", "sample-app"),
                               ("sample-org", "sample-api")]


def test_auto_repos_full_path(tmp_path):
    cfg = load_config(_write(
        tmp_path / "a.yml",
        "repos:\n  other/legacy: auto\n  sample-app: manual\n"))
    assert auto_repos(cfg) == [("other", "legacy")]


def test_list_repos_with_org_merge(tmp_path):
    p = _write(tmp_path / "a.yml", NEW_YML)  # sample-app auto, sample-api auto

    def fake_gh(args, **kw):
        assert "orgs/sample-org/repos" in args[1]
        return [{"name": "sample-app"}, {"name": "admin-web"}]

    rows = list_repos(p, gh=fake_gh)
    by_name = {r["name"]: r["mode"] for r in rows}
    assert by_name["sample-app"] == "auto"
    assert by_name["admin-web"] == "unlisted"
    assert by_name["sample-api"] == "auto"   # configured but not in org list


def test_list_repos_without_org(tmp_path):
    p = _write(tmp_path / "a.yml", "repos:\n  sample-app: auto\n")
    rows = list_repos(p, gh=lambda args, **kw: None)  # gh không được gọi
    assert rows == [{"name": "sample-app", "mode": "auto"}]


def test_defaults_include_the_provider_block():
    assert DEFAULTS["provider"] == "anthropic"
    assert DEFAULTS["providers"] == {}


def test_load_config_defaults_to_anthropic(tmp_path):
    cfg = load_config(_write(tmp_path / "prsentinel.yml", "repos:\n  app: auto\n"))
    assert cfg["provider"] == "anthropic"
    assert cfg["providers"] == {}


def test_load_config_keeps_a_custom_provider(tmp_path):
    cfg = load_config(_write(tmp_path / "prsentinel.yml", """
provider: gw
providers:
  gw:
    base_url: https://llm.internal/anthropic
    token_env: GW_TOKEN
    model: big
    claims_model: small
repos:
  app: auto
"""))
    assert cfg["provider"] == "gw"
    assert cfg["providers"]["gw"]["model"] == "big"


def test_load_config_rejects_an_undefined_provider(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "provider: nope\nrepos:\n  app: auto\n")
    with pytest.raises(ValueError, match="not built in"):
        load_config(path)


def test_load_config_rejects_an_incomplete_custom_provider(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "provider: gw\nproviders:\n  gw:\n    model: big\n")
    with pytest.raises(ValueError, match="not built in"):
        load_config(path)


def test_set_provider_writes_only_the_selection(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "provider: anthropic\nrepos:\n  app: auto\n")
    cfg = set_provider(path, "deepseek")
    assert cfg["provider"] == "deepseek"
    assert load_config(path)["provider"] == "deepseek"
    assert "token" not in path.read_text().lower()
    assert load_config(path)["repos"] == {"app": "auto"}


def test_set_provider_preserves_comments_and_formatting(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", (
        "# PR Sentinel configuration.\n"
        "interval_minutes: 2   # fast loop\n"
        "provider: anthropic\n"
        "providers: {}\n"
        "repos:\n"
        "  app: auto\n"))
    set_provider(path, "deepseek")
    out = path.read_text()
    assert "# PR Sentinel configuration." in out
    assert "# fast loop" in out
    assert "provider: deepseek" in out
    assert "provider: anthropic" not in out


def test_set_provider_adds_the_key_when_missing(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "repos:\n  app: auto\n")
    cfg = set_provider(path, "glm")
    assert cfg["provider"] == "glm"
    assert load_config(path)["provider"] == "glm"


def test_set_provider_rejects_an_unknown_name(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "repos:\n  app: auto\n")
    with pytest.raises(ValueError, match="not built in"):
        set_provider(path, "nope")


def test_jira_defaults_are_off_and_empty(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("org: acme\n")
    cfg = load_config(path)
    assert cfg["jira"] == {"projects": [], "comment_result": False}


def test_jira_block_is_merged_over_the_defaults(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("jira:\n  projects: [ABC]\n  comment_result: true\n")
    cfg = load_config(path)
    assert cfg["jira"] == {"projects": ["ABC"], "comment_result": True}


def test_jira_projects_must_be_a_list_of_strings(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("jira:\n  projects: ABC\n")
    with pytest.raises(ValueError, match="jira.projects"):
        load_config(path)


def test_jira_comment_result_must_be_a_bool(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("jira:\n  comment_result: yes-please\n")
    with pytest.raises(ValueError, match="jira.comment_result"):
        load_config(path)


def test_language_defaults_to_english(tmp_path):
    cfg = load_config(_write(tmp_path / "a.yml", "org: sample-org\n"))
    assert cfg["language"] == "en"


def test_language_must_be_en_or_vi(tmp_path):
    with pytest.raises(ValueError, match="language"):
        load_config(_write(tmp_path / "a.yml", "language: fr\n"))


def test_poc_tests_must_be_a_bool(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("poc_tests: sometimes\n")
    with pytest.raises(ValueError, match="poc_tests"):
        load_config(path)


def test_max_inline_comments_must_be_a_positive_int(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("max_inline_comments: '20'\n")
    with pytest.raises(ValueError, match="max_inline_comments"):
        load_config(path)


def test_max_inline_comments_rejects_zero(tmp_path):
    path = tmp_path / "c.yml"
    path.write_text("max_inline_comments: 0\n")
    with pytest.raises(ValueError, match="max_inline_comments"):
        load_config(path)


def test_max_inline_comments_rejects_a_bool(tmp_path):
    """True is an int in Python and would otherwise sail through as a cap of 1."""
    path = tmp_path / "c.yml"
    path.write_text("max_inline_comments: true\n")
    with pytest.raises(ValueError, match="max_inline_comments"):
        load_config(path)


def test_set_language_writes_only_the_selection(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "language: en\nrepos:\n  app: auto\n")
    cfg = set_language(path, "vi")
    assert cfg["language"] == "vi"
    assert load_config(path)["language"] == "vi"
    assert load_config(path)["repos"] == {"app": "auto"}


def test_set_language_preserves_comments_and_formatting(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", (
        "# PR Sentinel configuration.\n"
        "# The language the model writes its output in. en | vi\n"
        "language: en\n"
        "interval_minutes: 2   # fast loop\n"
        "repos:\n"
        "  app: auto\n"))
    set_language(path, "vi")
    out = path.read_text()
    assert "# PR Sentinel configuration." in out
    assert "# The language the model writes its output in. en | vi" in out
    assert "# fast loop" in out
    assert "language: vi" in out
    assert "language: en" not in out


def test_set_language_adds_the_key_when_missing(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "repos:\n  app: auto\n")
    assert set_language(path, "vi")["language"] == "vi"
    assert load_config(path)["language"] == "vi"


def test_set_language_rejects_an_unsupported_language(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "language: en\nrepos:\n  app: auto\n")
    with pytest.raises(ValueError, match="language"):
        set_language(path, "fr")
    assert path.read_text().count("language: en") == 1
