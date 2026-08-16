from pathlib import Path

import pytest

import providers
from providers import Provider


def test_builtin_anthropic_is_native_and_priced():
    p = providers.build("anthropic", None)
    assert p.base_url == ""
    assert p.model == "claude-sonnet-5"
    assert p.claims_model == "claude-haiku-4-5-20251001"
    assert p.is_native() is True
    assert p.reports_cost is True


def test_builtin_deepseek_uses_prompt_mode():
    p = providers.build("deepseek", None)
    assert p.base_url == "https://api.deepseek.com/anthropic"
    assert p.token_env == "DEEPSEEK_API_KEY"
    assert p.model == "deepseek-v4-pro"
    assert p.claims_model == "deepseek-v4-flash"
    assert p.is_native() is False
    assert p.reports_cost is False


def test_builtin_glm_endpoint():
    p = providers.build("glm", None)
    assert p.base_url == "https://api.z.ai/api/anthropic"
    assert p.token_env == "ZAI_API_KEY"
    assert p.model == "glm-5.2"


def test_overrides_layer_on_top_of_a_preset():
    p = providers.build("deepseek", {"model": "deepseek-v4-flash"})
    assert p.model == "deepseek-v4-flash"
    assert p.base_url == "https://api.deepseek.com/anthropic"  # preset survives


def test_custom_provider_needs_the_required_keys():
    with pytest.raises(ValueError, match="not built in"):
        providers.build("my-gateway", {"model": "big"})


def test_custom_provider_is_accepted_when_complete():
    p = providers.build("my-gateway", {
        "base_url": "https://llm.internal/anthropic", "token_env": "GW_TOKEN",
        "model": "big", "claims_model": "small"})
    assert p.name == "my-gateway"
    assert p.is_native() is False  # prompt mode is the safe default


def test_unknown_override_key_is_rejected():
    with pytest.raises(ValueError, match="unknown keys"):
        providers.build("deepseek", {"temperature": 0.2})


def test_bad_structured_output_is_rejected():
    with pytest.raises(ValueError, match="structured_output"):
        providers.build("deepseek", {"structured_output": "magic"})


def test_resolve_defaults_to_anthropic():
    assert providers.resolve({}, env={}).name == "anthropic"


def test_resolve_reads_the_yaml_selection():
    assert providers.resolve({"provider": "glm"}, env={}).name == "glm"


def test_env_beats_yaml():
    p = providers.resolve({"provider": "glm"}, env={"PRS_PROVIDER": "deepseek"})
    assert p.name == "deepseek"


def test_env_overrides_url_and_models():
    p = providers.resolve({"provider": "deepseek"}, env={
        "ANTHROPIC_BASE_URL": "https://proxy.local/anthropic",
        "PRS_MODEL": "custom-big", "PRS_CLAIMS_MODEL": "custom-small"})
    assert p.base_url == "https://proxy.local/anthropic"
    assert p.model == "custom-big"
    assert p.claims_model == "custom-small"


def test_resolve_uses_a_custom_entry():
    cfg = {"provider": "gw", "providers": {"gw": {
        "base_url": "https://llm.internal/anthropic", "token_env": "GW_TOKEN",
        "model": "big", "claims_model": "small"}}}
    assert providers.resolve(cfg, env={}).base_url == "https://llm.internal/anthropic"


def test_token_prefers_the_generic_variable():
    p = providers.build("deepseek", None)
    assert providers.token(p, env={"ANTHROPIC_AUTH_TOKEN": "a", "DEEPSEEK_API_KEY": "b"}) == "a"
    assert providers.token(p, env={"DEEPSEEK_API_KEY": "b"}) == "b"
    assert providers.token(p, env={}) == ""


def test_anthropic_accepts_a_logged_in_cli(tmp_path):
    cli = tmp_path / ".claude.json"
    cli.write_text("{}")
    p = providers.build("anthropic", None)
    assert providers.has_auth(p, env={}, cli_config=cli) is True


def test_third_party_requires_a_token(tmp_path):
    cli = tmp_path / ".claude.json"
    cli.write_text("{}")
    p = providers.build("deepseek", None)
    assert providers.has_auth(p, env={}, cli_config=cli) is False
    assert providers.has_auth(p, env={"DEEPSEEK_API_KEY": "k"}, cli_config=cli) is True


def test_anthropic_with_an_overridden_base_url_requires_a_token(tmp_path):
    cli = tmp_path / ".claude.json"
    cli.write_text("{}")
    p = providers.resolve({}, env={"ANTHROPIC_BASE_URL": "https://proxy.local"})
    assert providers.has_auth(p, env={}, cli_config=cli) is False


def test_agent_env_sets_url_and_both_token_variables():
    p = providers.build("deepseek", None)
    env = providers.agent_env(p, env={"DEEPSEEK_API_KEY": "k"})
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "k"
    assert env["ANTHROPIC_API_KEY"] == "k"


def test_agent_env_is_empty_for_plain_anthropic_without_a_token():
    p = providers.build("anthropic", None)
    assert providers.agent_env(p, env={}) == {}


def test_agent_env_leaves_the_default_anthropic_path_alone():
    p = providers.build("anthropic", None)
    assert providers.agent_env(p, env={"ANTHROPIC_API_KEY": "sk-ant-x"}) == {}


def test_validate_rejects_an_undefined_selection():
    with pytest.raises(ValueError, match="not built in"):
        providers.validate({"provider": "nope"})


def test_validate_accepts_a_complete_custom_block():
    providers.validate({"provider": "gw", "providers": {"gw": {
        "base_url": "https://llm.internal/anthropic", "token_env": "GW_TOKEN",
        "model": "big", "claims_model": "small"}}})


def test_describe_never_leaks_the_token():
    p = providers.build("deepseek", None)
    info = providers.describe(p, env={"DEEPSEEK_API_KEY": "super-secret"})
    assert info["token_present"] is True
    assert info["token_env"] == "DEEPSEEK_API_KEY"
    assert "super-secret" not in repr(info)
