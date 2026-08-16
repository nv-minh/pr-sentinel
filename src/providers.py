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

import config
from config import AUTH_HINT

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
        # Looked up on the module, not imported by name, so tests that patch
        # config.CLI_CONFIG (there's no other place it's defined) still apply.
        return Path(cli_config or config.CLI_CONFIG).exists()
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
