# Pluggable LLM Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator point PR Sentinel at DeepSeek, GLM (Z.ai), or any Anthropic-compatible gateway by configuring a `base_url` + token, instead of being hardwired to Anthropic.

**Architecture:** A new `src/providers.py` owns a `Provider` dataclass and a registry (three built-in presets plus anything declared under `providers:` in `prsentinel.yml`). `src/agent.py` — the single integration point with the Claude Agent SDK — injects `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` into the CLI subprocess via `ClaudeAgentOptions.env`, and gains a second way of obtaining JSON for providers that cannot enforce a schema server-side: the schema is appended to the prompt and the reply is parsed, with one session-resuming repair turn on a parse failure. Every phase module already receives a `cfg` dict from `run.py`; the resolved `Provider` rides along in that dict.

**Tech Stack:** Python 3.10+, `claude-agent-sdk>=0.2.139`, `pyyaml`, FastAPI (dashboard API), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-16-multi-provider.md`

## Global Constraints

- **Python 3.10 floor.** CI runs 3.10 and 3.13 (`.github/workflows/ci.yml`). No `match` statements, no 3.11+ typing syntax. `X | None` is fine (already used throughout).
- **No new runtime dependencies.** Declared deps stay `claude-agent-sdk>=0.2.139` and `pyyaml`.
- **Secrets never touch disk or the wire.** Tokens are read from environment variables only. `prsentinel.yml` must never gain a token key; `GET /api/config` must never return a token value — only a `token_present` boolean and the name of the env var to set.
- **Exact model IDs, copied verbatim:** `claude-sonnet-5`, `claude-haiku-4-5-20251001`, `deepseek-v4-pro`, `deepseek-v4-flash`, `glm-5.2`, `glm-4.7`.
- **Exact base URLs, copied verbatim:** `https://api.deepseek.com/anthropic` (DeepSeek), `https://api.z.ai/api/anthropic` (Z.ai).
- **Default behaviour must not change.** With no `provider:` key and no `PRS_PROVIDER`, the tool behaves exactly as it does today.
- **House style.** Every module opens with a docstring explaining *why* it exists, not what it contains. Comments explain constraints, never narrate the next line. Smallest change that satisfies the task; no speculative abstraction.
- **Test command:** `python -m pytest -q` from the repo root (pytest is configured with `pythonpath = ["src", "."]`, so modules import as `from providers import ...`).
- **Commit style:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`).

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `src/providers.py` | **create** | `Provider` dataclass, built-in presets, resolution from YAML + env, token/auth lookup, subprocess env, validation, dashboard description |
| `src/config.py` | modify | Add `provider`, `base_url`, `auth_token` env fields; `model`/`claims_model` become "" when unset so the provider supplies the default |
| `src/agent.py` | modify | Inject provider env into `ClaudeAgentOptions`; add prompt-mode structured output + repair turn; suppress untrustworthy cost |
| `src/autoreview_config.py` | modify | `provider` / `providers` defaults, validation, `set_provider()` writer |
| `src/run.py` | modify | Resolve the provider once, put it in `cfg`, provider-aware auth pre-flight, budget warning |
| `src/claims.py` | modify | Pass `provider=cfg.get("provider")` to the runner |
| `src/describe.py` | modify | Same |
| `src/verify.py` | modify | Same |
| `src/remediate.py` | modify | Same |
| `src/threads.py` | modify | Same |
| `web/server.py` | modify | Provider block on `GET /api/config`; `POST /api/config/provider`; provider-aware auth check on review trigger |
| `web/ui/src/api.ts` | modify | `ProviderInfo` type + `setProvider()` call |
| `web/ui/src/pages/Config.tsx` | modify | Provider panel (read-only status + switcher) |
| `tests/test_providers.py` | **create** | Registry resolution, precedence, validation, auth, subprocess env |
| `tests/test_agent.py` | modify | Prompt-mode extraction, repair turn, env injection, cost suppression |
| `tests/test_config.py` | modify | New env fields |
| `tests/test_autoreview_config.py` | modify | Provider validation + `set_provider` |
| `tests/test_run.py` | modify | Provider reaches `cfg`; auth pre-flight |
| `tests/test_server.py` | modify | Provider API surface |
| `prsentinel.yml` | modify | Documented `provider:` / `providers:` block |
| `.env.example` | modify | Provider token variables |
| `README.md` | modify | Providers section + config table |

---

### Task 1: Provider registry

**Files:**
- Create: `src/providers.py`
- Test: `tests/test_providers.py`

**Interfaces:**
- Consumes: nothing (leaf module; imports only `os`, `dataclasses`, and `config.CLI_CONFIG`)
- Produces:
  - `Provider` frozen dataclass with fields `name: str`, `base_url: str`, `token_env: str`, `model: str`, `claims_model: str`, `structured_output: str`, `reports_cost: bool`, and method `is_native() -> bool`
  - `BUILTIN: dict[str, Provider]`
  - `build(name: str, overrides: dict | None) -> Provider`
  - `resolve(review_cfg: dict, env: dict | None = None) -> Provider`
  - `token(provider: Provider, env: dict | None = None) -> str`
  - `has_auth(provider: Provider, env: dict | None = None, cli_config: Path | None = None) -> bool`
  - `auth_hint(provider: Provider) -> str`
  - `agent_env(provider: Provider, env: dict | None = None) -> dict[str, str]`
  - `validate(cfg: dict) -> None`
  - `names(cfg: dict) -> list[str]` — every provider the operator may switch to
  - `describe(provider: Provider, env: dict | None = None) -> dict`

- [ ] **Step 1: Write the failing test**

Create `tests/test_providers.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_providers.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'providers'`

- [ ] **Step 3: Write the implementation**

Create `src/providers.py`:

```python
"""Where LLM calls go, and how they hand back JSON.

The Claude Agent SDK always speaks the Anthropic wire protocol: it spawns the
Claude Code CLI, and that CLI honours `ANTHROPIC_BASE_URL` and
`ANTHROPIC_AUTH_TOKEN`. So any gateway that exposes an Anthropic-compatible
endpoint — DeepSeek's `/anthropic`, Z.ai's `/api/anthropic`, a self-hosted proxy
— is reachable by pointing those two variables at the subprocess.

What does *not* carry over is structured output. `output_format` reaches the CLI
as `--json-schema`, which rides on Anthropic's structured-outputs beta, and the
third-party gateways document that they ignore the `anthropic-beta` header — the
model answers in prose and `structured_output` comes back empty. Every provider
therefore declares how it returns JSON:

- `native` — the SDK enforces the schema (Anthropic only).
- `prompt` — the schema is appended to the prompt and `agent.py` parses the reply.

Cost is the same story: `total_cost_usd` is priced from Anthropic's table, so
`reports_cost` says whether to believe it.
"""
import os
from dataclasses import dataclass, replace
from pathlib import Path

from config import AUTH_HINT, CLI_CONFIG

STRUCTURED_MODES = ("native", "prompt")


@dataclass(frozen=True)
class Provider:
    """One place LLM calls can go, and what it can be trusted to do."""
    name: str
    base_url: str
    token_env: str
    model: str
    claims_model: str
    structured_output: str = "prompt"
    reports_cost: bool = False

    def is_native(self) -> bool:
        """True when the SDK can enforce the JSON schema server-side."""
        return self.structured_output == "native"


BUILTIN = {
    "anthropic": Provider(
        name="anthropic", base_url="", token_env="ANTHROPIC_API_KEY",
        model="claude-sonnet-5", claims_model="claude-haiku-4-5-20251001",
        structured_output="native", reports_cost=True),
    "deepseek": Provider(
        name="deepseek", base_url="https://api.deepseek.com/anthropic",
        token_env="DEEPSEEK_API_KEY",
        model="deepseek-v4-pro", claims_model="deepseek-v4-flash"),
    "glm": Provider(
        name="glm", base_url="https://api.z.ai/api/anthropic",
        token_env="ZAI_API_KEY",
        model="glm-5.2", claims_model="glm-4.7"),
}

# Keys a prsentinel.yml `providers:` entry may set. A custom provider (one with
# no built-in preset to fall back on) must set the first four.
OVERRIDABLE = ("base_url", "token_env", "model", "claims_model",
               "structured_output", "reports_cost")
REQUIRED_CUSTOM = ("base_url", "token_env", "model", "claims_model")


def build(name, overrides=None):
    """A Provider from its built-in preset plus prsentinel.yml overrides."""
    over = dict(overrides or {})
    unknown = sorted(set(over) - set(OVERRIDABLE))
    if unknown:
        raise ValueError(f"provider {name!r}: unknown keys {unknown} "
                         f"(allowed: {list(OVERRIDABLE)})")
    base = BUILTIN.get(name)
    if base is None:
        missing = [k for k in REQUIRED_CUSTOM if not over.get(k)]
        if missing:
            raise ValueError(
                f"provider {name!r} is not built in, so providers.{name} must set "
                f"{missing} (built in: {sorted(BUILTIN)})")
        base = Provider(name=name, base_url="", token_env="", model="", claims_model="")
    provider = replace(base, name=name, **over)
    if provider.structured_output not in STRUCTURED_MODES:
        raise ValueError(f"provider {name!r}: structured_output must be one of "
                         f"{list(STRUCTURED_MODES)}")
    return provider


def resolve(review_cfg, env=None):
    """The active provider: prsentinel.yml, with the environment layered on top.

    The environment wins so CI can retarget a committed config without editing it.
    """
    env = os.environ if env is None else env
    entries = review_cfg.get("providers") or {}
    name = env.get("PRS_PROVIDER") or review_cfg.get("provider") or "anthropic"
    provider = build(name, entries.get(name))
    if env.get("ANTHROPIC_BASE_URL"):
        provider = replace(provider, base_url=env["ANTHROPIC_BASE_URL"])
    if env.get("PRS_MODEL"):
        provider = replace(provider, model=env["PRS_MODEL"])
    if env.get("PRS_CLAIMS_MODEL"):
        provider = replace(provider, claims_model=env["PRS_CLAIMS_MODEL"])
    return provider


def token(provider, env=None):
    """The API key for this provider, or "" when none is configured."""
    env = os.environ if env is None else env
    return env.get("ANTHROPIC_AUTH_TOKEN") or env.get(provider.token_env, "")


def has_auth(provider, env=None, cli_config=None):
    """True when the SDK can authenticate against this provider.

    A logged-in Claude Code CLI only proves anything about Anthropic's own
    endpoint, so every other target needs a real token.
    """
    if token(provider, env):
        return True
    if provider.name == "anthropic" and not provider.base_url:
        return Path(cli_config or CLI_CONFIG).exists()
    return False


def auth_hint(provider):
    """What the operator has to set, phrased for the provider they picked."""
    if provider.name == "anthropic" and not provider.base_url:
        return AUTH_HINT
    return (f"no auth for provider {provider.name!r}: set {provider.token_env} "
            f"(or ANTHROPIC_AUTH_TOKEN) in .env")


def agent_env(provider, env=None):
    """Environment for the CLI subprocess the SDK spawns.

    Both token variables are set: DeepSeek's docs read ANTHROPIC_API_KEY, Z.ai's
    read ANTHROPIC_AUTH_TOKEN, and writing both also overrides a stale Anthropic
    key inherited from the parent process (the SDK merges over os.environ and
    cannot unset).
    """
    out = {}
    if provider.base_url:
        out["ANTHROPIC_BASE_URL"] = provider.base_url
    key = token(provider, env)
    if key:
        out["ANTHROPIC_AUTH_TOKEN"] = key
        out["ANTHROPIC_API_KEY"] = key
    return out


def validate(cfg):
    """Raise ValueError when prsentinel.yml's provider block is unusable."""
    entries = cfg.get("providers") or {}
    if not isinstance(entries, dict):
        raise ValueError("providers must be a mapping of name -> settings")
    for name, over in entries.items():
        if over is not None and not isinstance(over, dict):
            raise ValueError(f"provider {name!r}: settings must be a mapping")
        build(str(name), over)
    name = cfg.get("provider") or "anthropic"
    if name not in BUILTIN and name not in entries:
        raise ValueError(f"provider {name!r} is not built in and not defined under "
                         f"providers: (built in: {sorted(BUILTIN)})")
    build(str(name), entries.get(name))


def names(cfg):
    """Every provider the operator may switch to, in a stable order."""
    return sorted(set(BUILTIN) | set(cfg.get("providers") or {}))


def describe(provider, env=None):
    """Provider status for the dashboard. Never includes the token itself."""
    return {
        "name": provider.name,
        "base_url": provider.base_url or "https://api.anthropic.com",
        "model": provider.model,
        "claims_model": provider.claims_model,
        "structured_output": provider.structured_output,
        "reports_cost": provider.reports_cost,
        "token_env": provider.token_env,
        "token_present": bool(token(provider, env)),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_providers.py -q`
Expected: PASS (23 tests)

- [ ] **Step 5: Run the full suite — nothing else may break**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/providers.py tests/test_providers.py
git commit -m "feat: provider registry for Anthropic-compatible gateways"
```

---

### Task 2: Environment plumbing for provider selection

**Files:**
- Modify: `src/config.py:39-59`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing from Task 1 (deliberately — `providers.py` imports `config`, not the reverse)
- Produces: `Config` gains `provider: str`, `base_url: str`, `auth_token: str`; `model` and `claims_model` become `""` when their env vars are unset, so `providers.resolve()` supplies the default. `Config.has_auth()` is **removed** — auth is provider-dependent and now lives in `providers.has_auth()`. `AUTH_HINT` and `CLI_CONFIG` stay exported (both are imported by `providers.py`).

The old `DEFAULT_MODEL` / `DEFAULT_CLAIMS_MODEL` constants move to `providers.BUILTIN["anthropic"]` and are deleted from `config.py`.

- [ ] **Step 1: Write the failing test**

Replace the whole of `tests/test_config.py` with:

```python
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


def test_config_is_constructible_for_tests(tmp_path):
    cfg = Config(api_key="", auth_token="", base_url="", provider="", model="",
                 claims_model="", session_root=tmp_path, slack_webhook="")
    assert cfg.session_root == tmp_path
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'DEFAULT_CLAIMS_MODEL'` is gone from the file, but `Config` has no field `auth_token` → `TypeError: Config.__init__() got an unexpected keyword argument 'auth_token'`

- [ ] **Step 3: Write the implementation**

Replace `src/config.py` lines 1–59 with:

```python
"""Configuration from the environment. All env vars are optional.

A `.env` file next to the working directory is loaded first (simple KEY=VALUE
parser — no dotenv dependency); real environment variables win over it.

Model and provider defaults deliberately live in `providers.py`, not here: this
module only reports what the environment said, and empty means "the provider
decides". Auth is provider-dependent too — see `providers.has_auth()`.
"""
import os
from dataclasses import dataclass
from pathlib import Path

CLI_CONFIG = Path.home() / ".claude.json"
AUTH_HINT = ("no Claude auth found: set ANTHROPIC_API_KEY (see .env.example) "
             "or log in with the Claude Code CLI")


def _load_dotenv() -> None:
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Config:
    api_key: str
    auth_token: str
    base_url: str
    provider: str
    model: str
    claims_model: str
    session_root: Path
    slack_webhook: str


def load_config() -> Config:
    return Config(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        auth_token=os.environ.get("ANTHROPIC_AUTH_TOKEN", ""),
        base_url=os.environ.get("ANTHROPIC_BASE_URL", ""),
        provider=os.environ.get("PRS_PROVIDER", ""),
        model=os.environ.get("PRS_MODEL", ""),
        claims_model=os.environ.get("PRS_CLAIMS_MODEL", ""),
        session_root=Path(os.environ.get("PRS_SESSION_ROOT", "sessions")),
        slack_webhook=os.environ.get("SLACK_WEBHOOK_URL", ""),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_config.py tests/test_providers.py -q`
Expected: PASS

- [ ] **Step 5: Check what the removal broke**

Run: `python -m pytest -q 2>&1 | tail -30`
Expected: FAIL in `tests/test_run.py` and `tests/test_server.py` — both call `env.has_auth()` or construct `Config(...)`. That is exactly what Tasks 6–8 fix; leave the failures for now and note them.

- [ ] **Step 6: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "refactor: move model and auth defaults out of config into providers"
```

---

### Task 3: `prsentinel.yml` provider block

**Files:**
- Modify: `src/autoreview_config.py:9-26` (DEFAULTS), `:51-60` (validate_config), and append `set_provider`
- Modify: `prsentinel.yml`
- Test: `tests/test_autoreview_config.py`

**Interfaces:**
- Consumes: `providers.validate(cfg)`, `providers.BUILTIN`, `providers.names(cfg)` from Task 1
- Produces: `set_provider(path: Path, name: str) -> dict` — writes only the `provider:` key and returns the reloaded config. `DEFAULTS` gains `"provider": "anthropic"` and `"providers": {}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_autoreview_config.py`:

```python
import pytest

from autoreview_config import DEFAULTS, load_config, set_provider


def _write(tmp_path, body):
    path = tmp_path / "prsentinel.yml"
    path.write_text(body)
    return path


def test_defaults_include_the_provider_block():
    assert DEFAULTS["provider"] == "anthropic"
    assert DEFAULTS["providers"] == {}


def test_load_config_defaults_to_anthropic(tmp_path):
    cfg = load_config(_write(tmp_path, "repos:\n  app: auto\n"))
    assert cfg["provider"] == "anthropic"
    assert cfg["providers"] == {}


def test_load_config_keeps_a_custom_provider(tmp_path):
    cfg = load_config(_write(tmp_path, """
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
    path = _write(tmp_path, "provider: nope\nrepos:\n  app: auto\n")
    with pytest.raises(ValueError, match="not built in"):
        load_config(path)


def test_load_config_rejects_an_incomplete_custom_provider(tmp_path):
    path = _write(tmp_path, "provider: gw\nproviders:\n  gw:\n    model: big\n")
    with pytest.raises(ValueError, match="not built in"):
        load_config(path)


def test_set_provider_writes_only_the_selection(tmp_path):
    path = _write(tmp_path, "provider: anthropic\nrepos:\n  app: auto\n")
    cfg = set_provider(path, "deepseek")
    assert cfg["provider"] == "deepseek"
    assert load_config(path)["provider"] == "deepseek"
    assert "token" not in path.read_text().lower()
    assert load_config(path)["repos"] == {"app": "auto"}


def test_set_provider_rejects_an_unknown_name(tmp_path):
    path = _write(tmp_path, "repos:\n  app: auto\n")
    with pytest.raises(ValueError, match="not built in"):
        set_provider(path, "nope")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_autoreview_config.py -q`
Expected: FAIL — `ImportError: cannot import name 'set_provider' from 'autoreview_config'`

- [ ] **Step 3: Write the implementation**

In `src/autoreview_config.py`, add the import beside the existing `from score import DEFAULT_GATE`:

```python
import providers
```

Add two keys to `DEFAULTS`, immediately after `"skip_bots": True,`:

```python
    # Where LLM calls go. `providers` holds per-provider overrides; tokens are
    # never stored here, only the name of the env var that holds them.
    "provider": "anthropic",
    "providers": {},
```

In `load_config`, after `cfg["gate"] = {...}`, add:

```python
    cfg["providers"] = dict(raw.get("providers") or {})
```

In `validate_config`, add as the final statement:

```python
    providers.validate(cfg)
```

Append at the end of the module:

```python
def set_provider(path: Path, name: str) -> dict:
    """Switch the active provider. Writes only the `provider:` key."""
    cfg = load_config(path)
    providers.build(name, cfg["providers"].get(name))
    if name not in providers.BUILTIN and name not in cfg["providers"]:
        raise ValueError(f"provider {name!r} is not built in and not defined "
                         f"under providers:")
    cfg["provider"] = name
    _write_atomic(path, cfg)
    return cfg
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_autoreview_config.py -q`
Expected: PASS

- [ ] **Step 5: Update the shipped config**

In `prsentinel.yml`, insert after the `skip_bots: true` line:

```yaml
# Where LLM calls go. Built in: anthropic (default), deepseek, glm.
# Tokens are NEVER stored here — set them in .env:
#   anthropic -> ANTHROPIC_API_KEY   deepseek -> DEEPSEEK_API_KEY   glm -> ZAI_API_KEY
provider: anthropic
providers: {}
# Example of a gateway that is not built in — every key below is required:
# providers:
#   my-gateway:
#     base_url: https://llm.internal.example.com/anthropic
#     token_env: MY_GATEWAY_TOKEN
#     model: big-model
#     claims_model: small-model
#     structured_output: prompt   # native only if it implements Anthropic's
#     reports_cost: false         # structured-outputs beta and prices in USD
```

- [ ] **Step 6: Verify the shipped config still loads**

Run: `python -c "import sys; sys.path.insert(0,'src'); from pathlib import Path; from autoreview_config import load_config; print(load_config(Path('prsentinel.yml'))['provider'])"`
Expected: prints `anthropic`

- [ ] **Step 7: Commit**

```bash
git add src/autoreview_config.py tests/test_autoreview_config.py prsentinel.yml
git commit -m "feat: provider block in prsentinel.yml"
```

---

### Task 4: Route the subprocess at the provider

**Files:**
- Modify: `src/agent.py:66-100`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `providers.Provider`, `providers.agent_env`, `providers.BUILTIN` from Task 1
- Produces: `run_structured(..., provider: Provider | None = None)`. `None` means the `anthropic` preset, so every existing call site keeps working. Internal helper `_options(...)` builds `ClaudeAgentOptions`; `_query(prompt, options)` now returns the raw `ResultMessage` instead of an `AgentResult`.

This task keeps the native path only. Prompt mode is Task 5.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent.py`:

```python
from types import SimpleNamespace

import agent
import providers


def _fake_result(**kw):
    base = dict(subtype="success", session_id="sess-1", total_cost_usd=0.5,
                num_turns=4, duration_ms=900, structured_output={"ok": True},
                result=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _capture(monkeypatch, message=None):
    """Run run_structured against a fake SDK, returning the options it built."""
    seen = {}

    async def fake_query(prompt, options):
        seen["prompt"] = prompt
        seen["options"] = options
        return message or _fake_result()

    monkeypatch.setattr(agent, "_query", fake_query)
    return seen


def test_anthropic_keeps_the_native_schema_path(monkeypatch):
    seen = _capture(monkeypatch)
    result = agent.run_structured("hi", schema={"type": "object"}, model="m")
    assert result.data == {"ok": True}
    assert seen["options"].output_format == {"type": "json_schema",
                                             "schema": {"type": "object"}}
    assert seen["options"].env == {}
    assert seen["prompt"] == "hi"


def test_provider_env_reaches_the_subprocess(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    seen = _capture(monkeypatch, _fake_result(structured_output=None,
                                              result='{"ok": true}'))
    agent.run_structured("hi", schema={"type": "object"},
                         provider=providers.build("deepseek", None))
    env = seen["options"].env
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "k"


def test_native_path_still_rejects_a_missing_structured_output(monkeypatch):
    _capture(monkeypatch, _fake_result(structured_output=None))
    with pytest.raises(RuntimeError, match="no structured output"):
        agent.run_structured("hi", schema={"type": "object"})


def test_cost_is_dropped_when_the_provider_cannot_price_it(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _capture(monkeypatch, _fake_result(structured_output=None, result='{"ok": true}'))
    result = agent.run_structured("hi", schema={"type": "object"},
                                  provider=providers.build("deepseek", None))
    assert result.cost_usd is None


def test_budget_is_only_sent_to_a_provider_that_reports_cost(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    seen = _capture(monkeypatch, _fake_result(structured_output=None,
                                              result='{"ok": true}'))
    agent.run_structured("hi", schema={"type": "object"}, max_budget_usd=2.0,
                         provider=providers.build("deepseek", None))
    assert seen["options"].max_budget_usd is None
```

Add `import pytest` to the top of the file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_agent.py -q`
Expected: FAIL — `AttributeError: module 'agent' has no attribute '_query'` is satisfied, but `run_structured() got an unexpected keyword argument 'provider'`

- [ ] **Step 3: Write the implementation**

In `src/agent.py`, replace lines 44–100 (`_query` and `run_structured`) with:

```python
async def _query(prompt: str, options):
    """One turn-loop against the SDK. Returns the CLI's final result message."""
    from claude_agent_sdk import ResultMessage, query

    result = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            result = message
    if result is None:
        raise RuntimeError("agent returned no result message")
    if result.subtype != "success":
        raise RuntimeError(f"agent stopped: {result.subtype}")
    return result


def _options(*, schema, cwd, tools, model, max_turns, max_budget_usd, resume,
             system_prompt, env):
    from claude_agent_sdk import ClaudeAgentOptions

    allowed = list(tools or [])
    return ClaudeAgentOptions(
        cwd=str(cwd) if cwd else None,
        model=model,
        tools=allowed,
        allowed_tools=allowed,
        disallowed_tools=BLOCKED_TOOLS,
        permission_mode="dontAsk",
        setting_sources=[],
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
        resume=resume,
        system_prompt=system_prompt,
        env=env,
        output_format=({"type": "json_schema", "schema": schema}
                       if schema is not None else None),
    )


def run_structured(prompt: str, *, schema: dict, cwd: Path | str | None = None,
                   tools: list[str] | None = None, model: str | None = None,
                   max_turns: int | None = None,
                   max_budget_usd: float | None = None,
                   resume: str | None = None,
                   system_prompt: str | None = None,
                   provider=None) -> AgentResult:
    """Run one agent turn-loop and return its schema-validated JSON answer.

    `tools=None` means no tools at all (a plain completion); pass
    `READ_ONLY_TOOLS` for a code-reading agent. Every SDK failure is re-raised
    as RuntimeError so callers can handle one exception type.
    """
    from claude_agent_sdk import ClaudeSDKError

    if provider is None:
        provider = providers.BUILTIN["anthropic"]
    options = _options(
        schema=schema if provider.is_native() else None,
        cwd=cwd, tools=tools, model=model, max_turns=max_turns,
        # A budget the provider cannot price is a hard stop that never fires.
        max_budget_usd=max_budget_usd if provider.reports_cost else None,
        resume=resume, system_prompt=system_prompt,
        env=providers.agent_env(provider),
    )
    try:
        message = asyncio.run(_query(prompt, options))
    except ClaudeSDKError as e:
        raise RuntimeError(f"Claude Agent SDK failed: {e}") from e

    if message.structured_output is None:
        raise RuntimeError("agent returned no structured output")
    data = message.structured_output

    return AgentResult(
        data=data,
        session_id=message.session_id,
        cost_usd=message.total_cost_usd if provider.reports_cost else None,
        num_turns=message.num_turns,
        duration_ms=message.duration_ms,
        model=model or provider.model,
    )
```

Add `import providers` to the imports at the top of `src/agent.py`, and extend the module docstring with a fourth safety bullet:

```
- provider routing goes through `ClaudeAgentOptions.env`, so a third-party
  base URL and token never leak into the parent process's environment.
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_agent.py -q`
Expected: FAIL on the two DeepSeek tests — prompt mode is not implemented yet, so `structured_output is None` still raises. The three Anthropic-path tests PASS.

That is the expected intermediate state; Task 5 closes it.

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: route the agent subprocess at a configured provider"
```

---

### Task 5: Prompt-mode structured output with a repair turn

**Files:**
- Modify: `src/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `_options`, `_query`, `run_structured` from Task 4
- Produces: `compat_prompt(prompt: str, schema: dict) -> str`, `extract_json(text: str) -> dict`, and a `run_structured` branch that uses them. Both helpers are pure and unit-testable without the SDK.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_agent.py`:

```python
import json


def test_extract_json_reads_a_bare_object():
    assert agent.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_reads_a_fenced_object():
    assert agent.extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_ignores_surrounding_prose():
    text = 'Sure — here is the result:\n\n```\n{"a": [1, 2]}\n```\n\nHope that helps.'
    assert agent.extract_json(text) == {"a": [1, 2]}


def test_extract_json_rejects_an_empty_reply():
    with pytest.raises(RuntimeError, match="empty reply"):
        agent.extract_json("")


def test_extract_json_rejects_prose_without_json():
    with pytest.raises(RuntimeError, match="no JSON object"):
        agent.extract_json("I could not do that.")


def test_extract_json_rejects_a_json_array():
    with pytest.raises(RuntimeError, match="no JSON object"):
        agent.extract_json("[1, 2, 3]")


def test_extract_json_reports_a_syntax_error():
    with pytest.raises(RuntimeError, match="not valid JSON"):
        agent.extract_json('{"a": 1,}')


def test_compat_prompt_carries_the_schema():
    out = agent.compat_prompt("do the thing", {"type": "object"})
    assert out.startswith("do the thing")
    assert '"type": "object"' in out
    assert "ONE JSON object" in out


def test_prompt_mode_parses_the_reply(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    seen = _capture(monkeypatch, _fake_result(
        structured_output=None, result='```json\n{"claims": []}\n```'))
    result = agent.run_structured("extract", schema={"type": "object"},
                                  provider=providers.build("deepseek", None))
    assert result.data == {"claims": []}
    assert seen["options"].output_format is None
    assert "ONE JSON object" in seen["prompt"]


def test_prompt_mode_repairs_a_bad_reply_by_resuming(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    calls = []

    async def fake_query(prompt, options):
        calls.append((prompt, options))
        if len(calls) == 1:
            return _fake_result(structured_output=None, result="no idea, sorry")
        return _fake_result(structured_output=None, result='{"claims": []}',
                            session_id="sess-2")

    monkeypatch.setattr(agent, "_query", fake_query)
    result = agent.run_structured("extract", schema={"type": "object"},
                                  tools=["Read"],
                                  provider=providers.build("deepseek", None))
    assert result.data == {"claims": []}
    assert len(calls) == 2
    repair_prompt, repair_options = calls[1]
    assert repair_options.resume == "sess-1"    # resumes, does not re-explore
    assert repair_options.max_turns == 2
    assert repair_options.allowed_tools == []   # nothing left to read
    assert "could not be parsed" in repair_prompt


def test_prompt_mode_gives_up_after_one_repair(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _capture(monkeypatch, _fake_result(structured_output=None, result="still prose"))
    with pytest.raises(RuntimeError, match="no JSON object"):
        agent.run_structured("extract", schema={"type": "object"},
                             provider=providers.build("deepseek", None))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_agent.py -q`
Expected: FAIL — `AttributeError: module 'agent' has no attribute 'extract_json'`

- [ ] **Step 3: Write the implementation**

Add `import re` to the imports in `src/agent.py`, and insert these module-level pieces above `run_structured`:

```python
JSON_INSTRUCTION = """Reply with ONE JSON object and nothing else — no prose
before or after it. It must validate against this JSON Schema:

{schema}"""

REPAIR_INSTRUCTION = """Your last reply could not be parsed: {error}

Send the same answer again as ONE JSON object matching the schema you were
given. No prose, no explanation — just the object."""


def compat_prompt(prompt: str, schema: dict) -> str:
    """The prompt for a provider that cannot enforce a schema server-side."""
    return (f"{prompt}\n\n---\n\n"
            + JSON_INSTRUCTION.format(schema=json.dumps(schema, indent=2)))


def extract_json(text: str) -> dict:
    """The JSON object in a free-text model reply.

    Providers in prompt mode wrap the answer in fences, prose, or both, so this
    takes the fenced block when there is one and the outermost braces otherwise.
    """
    if not (text or "").strip():
        raise RuntimeError("agent returned an empty reply")
    body = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", body, re.S)
    if fence:
        body = fence.group(1).strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        raise RuntimeError(f"agent reply contained no JSON object: {text[:200]!r}")
    try:
        data = json.loads(body[start:end + 1])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"agent reply was not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError(f"agent reply was not a JSON object: {text[:200]!r}")
    return data
```

Then replace the result-handling block of `run_structured` (everything from `if message.structured_output is None:` down to the `return AgentResult(...)`) with:

```python
    if provider.is_native():
        if message.structured_output is None:
            raise RuntimeError("agent returned no structured output")
        data = message.structured_output
    else:
        try:
            data = extract_json(message.result or "")
        except RuntimeError as first:
            # One repair turn, resuming the same session: the model already did
            # the work, it just wrote the answer the wrong way.
            repair = _options(
                schema=None, cwd=cwd, tools=None, model=model, max_turns=2,
                max_budget_usd=None, resume=message.session_id,
                system_prompt=system_prompt, env=providers.agent_env(provider))
            try:
                message = asyncio.run(_query(
                    REPAIR_INSTRUCTION.format(error=first), repair))
            except ClaudeSDKError as e:
                raise RuntimeError(f"Claude Agent SDK failed: {e}") from e
            data = extract_json(message.result or "")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_agent.py tests/test_providers.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: prompt-mode structured output for gateways without the schema beta"
```

---

### Task 6: Hand the provider to every phase

**Files:**
- Modify: `src/run.py:41-49` (`agent_config`), `:149-165` (auth pre-flight)
- Modify: `src/claims.py:64-70`, `src/describe.py:86-91`, `src/verify.py:212-221`, `src/remediate.py:76-84`, `src/threads.py:119-129`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: `providers.resolve`, `providers.has_auth`, `providers.auth_hint` from Task 1; `run_structured(..., provider=...)` from Tasks 4–5
- Produces: `agent_config(env, review_cfg)` returns a dict that additionally carries `"provider": Provider`. `model` and `claims_model` in that dict come from the provider, so the phases keep reading `cfg.get("model")` unchanged.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run.py`:

```python
import providers
import run


def test_agent_config_carries_the_resolved_provider(monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    monkeypatch.delenv("PRS_MODEL", raising=False)
    monkeypatch.delenv("PRS_CLAIMS_MODEL", raising=False)
    env = run.load_config()
    cfg = run.agent_config(env, {"provider": "deepseek"})
    assert cfg["provider"].name == "deepseek"
    assert cfg["model"] == "deepseek-v4-pro"
    assert cfg["claims_model"] == "deepseek-v4-flash"


def test_agent_config_defaults_to_anthropic(monkeypatch):
    for name in ("PRS_PROVIDER", "PRS_MODEL", "PRS_CLAIMS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    cfg = run.agent_config(run.load_config(), {})
    assert cfg["provider"].name == "anthropic"
    assert cfg["model"] == "claude-sonnet-5"


def test_run_refuses_a_provider_without_a_token(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRS_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    assert run.main(["owner/repo", "1"]) == 3
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err


def test_phases_forward_the_provider_to_the_runner(tmp_path):
    """Every phase must pass cfg["provider"] through, or a gateway silently
    falls back to Anthropic credentials."""
    import claims

    seen = {}

    def fake_runner(prompt, **kw):
        seen.update(kw)
        return providers  # unused; we raise before the return value matters

    cfg = {"claims_model": "m", "provider": providers.build("glm", None)}
    snapshot = {"title": "t", "body": "b", "files": []}
    try:
        claims.extract_claims(snapshot, cfg, tmp_path, runner=fake_runner)
    except Exception:
        pass
    assert seen["provider"].name == "glm"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_run.py -q`
Expected: FAIL — `KeyError: 'provider'` from `agent_config`

- [ ] **Step 3: Write the implementation**

In `src/run.py`, add `import providers` to the imports and replace `agent_config`:

```python
def agent_config(env, review_cfg: dict) -> dict:
    """The knobs the agent phases care about, from env + prsentinel.yml."""
    provider = providers.resolve(review_cfg)
    return {
        "provider": provider,
        "model": provider.model,
        "claims_model": provider.claims_model,
        "allow_bash": review_cfg.get("allow_bash", False),
        "max_turns": review_cfg.get("max_turns", 60),
        "max_budget_usd": review_cfg.get("max_budget_usd"),
    }
```

Replace the auth pre-flight in `main` (currently `if not env.has_auth():`):

```python
    if args.fixtures is None:
        provider = cfg["provider"]
        if not providers.has_auth(provider):
            print(providers.auth_hint(provider), file=sys.stderr)
            return 3
        if review_cfg.get("max_budget_usd") and not provider.reports_cost:
            print(f"[run] max_budget_usd is ignored: provider "
                  f"{provider.name!r} does not report cost", file=sys.stderr)
        if not gh_available():
            print("gh CLI not installed or not authenticated (gh auth login)",
                  file=sys.stderr)
            return 2
```

Remove the now-unused `AUTH_HINT` from the `from config import ...` line, leaving `from config import load_config`.

In each of the five phase modules, add `provider=cfg.get("provider"),` to the `runner(...)` keyword arguments:

- `src/claims.py` — inside `extract_claims`, after `max_turns=2,`
- `src/describe.py` — inside `draft_description`, after `max_turns=2,`
- `src/verify.py` — inside `run_verify`, after `max_budget_usd=cfg.get("max_budget_usd"),`
- `src/remediate.py` — inside `draft_patches`, after `max_turns=cfg.get("max_turns", 30),`
- `src/threads.py` — inside `run_followup`, after `resume=session_id,`

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_run.py -q`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: FAIL only in `tests/test_server.py` (still calls `env.has_auth()`) — Task 8 fixes it.

- [ ] **Step 6: Commit**

```bash
git add src/run.py src/claims.py src/describe.py src/verify.py src/remediate.py src/threads.py tests/test_run.py
git commit -m "feat: pass the active provider through every review phase"
```

---

### Task 7: End-to-end smoke against a fake gateway

**Files:**
- Test: `tests/test_provider_e2e.py` (create)

**Interfaces:**
- Consumes: everything from Tasks 1–6
- Produces: nothing importable — this is the regression net that proves a `prompt`-mode provider survives a whole run without an Anthropic key anywhere.

The existing `tests/test_e2e.py` runs the pipeline with `--fixtures`, which skips the model entirely. This adds the missing case: real phase code, fake SDK.

- [ ] **Step 1: Write the failing test**

Create `tests/test_provider_e2e.py`:

```python
"""A whole review on a prompt-mode gateway, with the SDK faked out.

Guards the seam that `--fixtures` cannot reach: claims and verify actually run,
but the transport is a stub, so the assertion is "the phases produce valid
artifacts through the prompt-mode path", not "the model is smart".
"""
import json
from types import SimpleNamespace

import agent
import claims as claims_mod
import providers
import verify as verify_mod

SNAPSHOT = {
    "owner": "demo", "repo": "app", "pr": 1, "title": "Speed up checkout",
    "body": "Caches the price lookup. No behaviour change.",
    "base": "main", "head": "perf/x", "head_sha": "abc123",
    "files": [{"filename": "src/pricing.py", "additions": 10, "deletions": 2}],
    "commits": [], "threads": [], "pruned": [],
}

CLAIMS_REPLY = json.dumps({"claims": [
    {"id": "C1", "text": "Caches the price lookup", "category": "perf",
     "files": ["src/pricing.py"], "docs": []}]})

FINDINGS_REPLY = json.dumps({
    "claims": [{"id": "C1", "status": "PASS", "evidence": ["src/pricing.py:12"],
                "note": "", "confidence": 0.9}],
    "docs": [], "impact": [], "callers_outside_diff": [], "contracts": [],
    "tests": [], "threads": [], "unresolved_questions": [],
})


def _sdk(monkeypatch, replies):
    """Fake the SDK, handing back `replies` in order as free text."""
    queue = list(replies)
    prompts = []

    async def fake_query(prompt, options):
        prompts.append(prompt)
        return SimpleNamespace(
            subtype="success", session_id="sess-1", total_cost_usd=0.9,
            num_turns=3, duration_ms=100, structured_output=None,
            result=queue.pop(0))

    monkeypatch.setattr(agent, "_query", fake_query)
    return prompts


def test_prompt_mode_provider_completes_claims_and_verify(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "zai-token")
    prompts = _sdk(monkeypatch, [CLAIMS_REPLY, FINDINGS_REPLY])
    cfg = {"provider": providers.build("glm", None), "model": "glm-5.2",
           "claims_model": "glm-4.7", "max_turns": 10}

    extracted = claims_mod.extract_claims(SNAPSHOT, cfg, tmp_path)
    assert extracted[0]["id"] == "C1"
    assert json.loads((tmp_path / "claims.json").read_text())[0]["category"] == "perf"

    findings = verify_mod.run_verify(cfg, tmp_path, tmp_path, SNAPSHOT, extracted)
    assert findings["claims"][0]["status"] == "PASS"
    assert (tmp_path / "findings.json").exists()

    # The schema travelled in the prompt, because the gateway cannot enforce it.
    assert "ONE JSON object" in prompts[0]
    assert "unresolved_questions" in prompts[1]

    # Cost is not invented for a provider that cannot price itself.
    usage = json.loads((tmp_path / "usage.json").read_text())
    assert all(entry["cost_usd"] is None for entry in usage)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_provider_e2e.py -q`
Expected: FAIL if any phase forgot to forward `provider` (the fake reply would be parsed by the native path and raise "no structured output")

- [ ] **Step 3: Fix whatever it catches**

No new code is planned here. If the test fails, the cause is a missed `provider=cfg.get("provider")` in Task 6 — add it to that phase module.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_provider_e2e.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_provider_e2e.py
git commit -m "test: whole-pipeline coverage for a prompt-mode provider"
```

---

### Task 8: Provider API and dashboard panel

**Files:**
- Modify: `web/server.py:19-24` (imports), `:120-141` (`api_config`), `:293-305` (auth check), and add `POST /api/config/provider`
- Modify: `web/ui/src/api.ts`, `web/ui/src/pages/Config.tsx`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `providers.resolve`, `providers.describe`, `providers.names`, `providers.has_auth`, `providers.auth_hint`; `autoreview_config.set_provider` from Task 3
- Produces:
  - `GET /api/config` gains `"provider": {name, base_url, model, claims_model, structured_output, reports_cost, token_env, token_present}` and `"providers": [name, ...]`
  - `POST /api/config/provider` with body `{"name": "deepseek"}` → `{"ok": true, "provider": "deepseek"}`; 400 on an unknown name
  - `api.setProvider(name: string)` in `web/ui/src/api.ts`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_server.py`:

```python
def test_api_config_reports_the_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dsk-secret")
    _config(tmp_path, monkeypatch,
            "provider: deepseek\nrepos:\n  sample-app: auto\n")
    body = TestClient(app).get("/api/config").json()
    assert body["provider"]["name"] == "deepseek"
    assert body["provider"]["base_url"] == "https://api.deepseek.com/anthropic"
    assert body["provider"]["structured_output"] == "prompt"
    assert body["provider"]["token_present"] is True
    assert body["provider"]["token_env"] == "DEEPSEEK_API_KEY"
    assert "dsk-secret" not in TestClient(app).get("/api/config").text
    assert "deepseek" in body["providers"] and "anthropic" in body["providers"]


def test_api_config_flags_a_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    _config(tmp_path, monkeypatch,
            "provider: deepseek\nrepos:\n  sample-app: auto\n")
    body = TestClient(app).get("/api/config").json()
    assert body["provider"]["token_present"] is False


def test_switch_provider_writes_the_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    cfg_path = _config(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.post("/api/config/provider", json={"name": "glm"}).status_code == 200
    assert load_config(cfg_path)["provider"] == "glm"
    assert "token" not in cfg_path.read_text().lower()


def test_switch_provider_rejects_an_unknown_name(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/config/provider", json={"name": "nope"})
    assert r.status_code == 400
    assert "not built in" in r.json()["detail"]


def test_trigger_review_uses_the_provider_auth_rule(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "no-cli.json")
    monkeypatch.setenv("PRS_PROVIDER", "glm")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/repos/demo/app/pr/8/review")
    assert r.status_code == 400
    assert "ZAI_API_KEY" in r.json()["detail"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_server.py -q`
Expected: FAIL — existing tests error on `env.has_auth()` (removed in Task 2) and the new ones 404 on `/api/config/provider`

- [ ] **Step 3: Write the implementation**

In `web/server.py`, change the imports:

```python
import providers
from autoreview_config import load_config as load_autoreview_config
from autoreview_config import (auto_repos, list_repos, remove_repo,
                               set_provider, set_repo_mode)
from config import load_config
```

(`AUTH_HINT` is no longer imported.)

In `api_config`, add to the returned dict, after `"gate": cfg.get("gate"),`:

```python
        "provider": providers.describe(providers.resolve(cfg)),
        "providers": providers.names(cfg),
```

Add a new endpoint immediately after `api_config`:

```python
@app.post("/api/config/provider")
def api_set_provider(payload: dict):
    """Switch which gateway LLM calls go to. Tokens stay in the environment."""
    path = _require_config()
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        set_provider(path, name)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "provider": name}
```

In `trigger_review`, replace the auth block:

```python
    provider = providers.resolve(cfg)
    if not providers.has_auth(provider):
        raise HTTPException(status_code=400, detail=providers.auth_hint(provider))
```

and delete the now-unused `env = load_config()` line if nothing else in that function uses it.

In `web/ui/src/api.ts`, add the type and the call:

```ts
export interface ProviderInfo {
  name: string
  base_url: string
  model: string
  claims_model: string
  structured_output: 'native' | 'prompt'
  reports_cost: boolean
  token_env: string
  token_present: boolean
}
```

and inside the `api` object, after `config`:

```ts
  setProvider: (name: string) =>
    request<any>('/api/config/provider', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
```

In `web/ui/src/pages/Config.tsx`, extend `ConfigState`:

```ts
  provider: ProviderInfo
  providers: string[]
```

and add a panel between the `<div className="tiles">` block and `<Eyebrow>Repositories</Eyebrow>`:

```tsx
      <Eyebrow>Model provider</Eyebrow>
      {!cfg.provider.token_present && (
        <div className="notice notice-fail">
          No key for <code>{cfg.provider.name}</code> — set{' '}
          <code>{cfg.provider.token_env}</code> in <code>.env</code>. Reviews will
          refuse to start until it is there.
        </div>
      )}
      <div className="tiles">
        <Tile label="Provider" value={cfg.provider.name} note={cfg.provider.base_url} />
        <Tile label="Deep dive" value={cfg.provider.model} />
        <Tile label="Claims" value={cfg.provider.claims_model} />
        <Tile
          label="Schema"
          value={cfg.provider.structured_output === 'native' ? 'enforced' : 'prompted'}
          note={cfg.provider.structured_output === 'native'
            ? 'the API validates the JSON'
            : 'the reply is parsed and repaired'}
        />
        <Tile label="Key" value={cfg.provider.token_present ? 'set' : 'missing'}
              note={cfg.provider.token_env} />
        <Tile label="Costs" value={cfg.provider.reports_cost ? 'tracked' : 'unknown'}
              note={cfg.provider.reports_cost ? '' : 'budget caps do not apply'} />
      </div>
      <div className="toolbar">
        <select value={cfg.provider.name}
                onChange={(e) => act(() => api.setProvider(e.target.value))}>
          {cfg.providers.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
        <span className="linkish">tokens are read from the environment only</span>
      </div>
```

Add `ProviderInfo` to the `import type` line from `../api`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_server.py -q`
Expected: PASS

Run: `cd web/ui && npm run build && npm test -- --run && cd ../..`
Expected: PASS (build clean, existing UI tests unchanged)

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`
Expected: PASS — every suite green

- [ ] **Step 6: Commit**

```bash
git add web/server.py web/ui/src/api.ts web/ui/src/pages/Config.tsx tests/test_server.py
git commit -m "feat: provider status and switcher in the dashboard"
```

---

### Task 9: Documentation

**Files:**
- Modify: `.env.example`, `README.md`

**Interfaces:**
- Consumes: the finished feature
- Produces: nothing importable

- [ ] **Step 1: Update `.env.example`**

Replace the auth and model section at the top with:

```bash
# --- Provider -----------------------------------------------------------------
# Which gateway LLM calls go to. Built in: anthropic (default), deepseek, glm.
# Overrides `provider:` in prsentinel.yml.
PRS_PROVIDER=

# Auth for the provider you picked. Only one of these is needed.
# anthropic: set ANTHROPIC_API_KEY, or leave it empty and log in with the
# Claude Code CLI (`claude setup-token`) — the SDK reuses that session.
ANTHROPIC_API_KEY=
# deepseek — https://api.deepseek.com/anthropic
DEEPSEEK_API_KEY=
# glm (Z.ai) — https://api.z.ai/api/anthropic
ZAI_API_KEY=
# Any provider: overrides the one above, and is what a custom gateway reads.
ANTHROPIC_AUTH_TOKEN=

# Point any provider somewhere else (a proxy, a self-hosted gateway).
ANTHROPIC_BASE_URL=

# Override the provider's model choices. Empty = the provider's own defaults.
PRS_MODEL=
PRS_CLAIMS_MODEL=

# --- Everything else ----------------------------------------------------------
# Where per-phase results are written.
PRS_SESSION_ROOT=sessions

# Optional: one-way Slack notification when a review finishes.
SLACK_WEBHOOK_URL=
```

- [ ] **Step 2: Update the README install section**

Replace the `export ANTHROPIC_API_KEY=...` line in **Install** with:

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or just log in with the Claude Code CLI
```

and add a **Providers** section immediately before **Configuration**:

````markdown
## Providers

PR Sentinel runs on the Claude Agent SDK, which speaks the Anthropic wire
protocol — so it also runs against any gateway that exposes an
Anthropic-compatible endpoint. Pick one in `prsentinel.yml`, put its key in
`.env`:

```yaml
provider: deepseek          # anthropic (default) | deepseek | glm | your own
```

| Provider | Endpoint | Key | Deep dive | Claims |
|---|---|---|---|---|
| `anthropic` | *(default)* | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | `claude-haiku-4-5-20251001` |
| `deepseek` | `api.deepseek.com/anthropic` | `DEEPSEEK_API_KEY` | `deepseek-v4-pro` | `deepseek-v4-flash` |
| `glm` | `api.z.ai/api/anthropic` | `ZAI_API_KEY` | `glm-5.2` | `glm-4.7` |

Anything else is a few lines of config — every key is required:

```yaml
provider: my-gateway
providers:
  my-gateway:
    base_url: https://llm.internal.example.com/anthropic
    token_env: MY_GATEWAY_TOKEN
    model: big-model
    claims_model: small-model
```

**Two things change on a non-Anthropic provider.** Structured output is an
Anthropic beta that third-party gateways ignore, so the JSON schema travels in
the prompt instead and the reply is parsed — a malformed answer costs one repair
turn, not a failed review. And `total_cost_usd` is priced from Anthropic's
table, so cost is recorded as unknown and `max_budget_usd` does not apply.
Set `structured_output: native` and `reports_cost: true` on a custom provider
only if it genuinely implements both.

Tokens are read from the environment and never written to `prsentinel.yml`; the
dashboard shows whether a key is present, never the key.
````

- [ ] **Step 3: Update the Configuration table**

Replace the env table in **Configuration** with:

| Env | Default | Meaning |
|---|---|---|
| `PRS_PROVIDER` | `anthropic` | Overrides `provider:` in `prsentinel.yml` |
| `ANTHROPIC_API_KEY` | — | Optional if the Claude Code CLI is logged in |
| `ANTHROPIC_AUTH_TOKEN` | — | Key for any provider; wins over the provider's own variable |
| `ANTHROPIC_BASE_URL` | — | Point any provider at a different endpoint |
| `PRS_MODEL` | provider's | Model for the deep-dive agent |
| `PRS_CLAIMS_MODEL` | provider's | Model for claims + description drafting |
| `PRS_SESSION_ROOT` | `sessions` | Where per-phase results are written |
| `SLACK_WEBHOOK_URL` | — | Optional one-way notification |

- [ ] **Step 4: Update the test count**

Run: `python -m pytest -q | tail -2`

Replace `# 183 tests` in the README **Tests** section with the number that command prints.

- [ ] **Step 5: Verify**

Run: `python -m pytest -q && (cd web/ui && npm run build)`
Expected: PASS, clean build

- [ ] **Step 6: Commit**

```bash
git add README.md .env.example
git commit -m "docs: multi-provider configuration"
```

---

## Manual verification (after Task 9)

Not part of the automated suite — run once against a real gateway before calling
the feature done:

```bash
export PRS_PROVIDER=deepseek DEEPSEEK_API_KEY=sk-...
PYTHONPATH=src python -m src.run <owner>/<repo> <pr> --skip-human --no-post --force
```

Confirm: `claims.json` and `findings.json` are well-formed, `usage.json` records
`"cost_usd": null`, and the console prints a real gate line. Repeat with
`PRS_PROVIDER=glm ZAI_API_KEY=...`.
