# Spec — Pluggable LLM providers (base_url + token)

**Date:** 2026-08-16
**Status:** agreed, ready to implement

## Problem

Every LLM call in PR Sentinel goes through `agent.run_structured()`, which is
hardwired to Anthropic: the Claude Agent SDK picks up `ANTHROPIC_API_KEY` (or a
logged-in Claude Code CLI) from the ambient environment, and the model is chosen
by `PRS_MODEL` / `PRS_CLAIMS_MODEL`. There is no way to point the tool at
DeepSeek, GLM (Z.ai), or a self-hosted gateway.

## What we are building

A provider registry. The operator picks an active provider; PR Sentinel injects
the right `base_url` + token into the CLI subprocess the SDK spawns, and adapts
the way structured output is obtained.

## Key technical finding — structured output does not carry over

The Claude Agent SDK always speaks the **Anthropic wire protocol**. It spawns
the bundled Claude Code CLI, and that CLI honours `ANTHROPIC_BASE_URL` and
`ANTHROPIC_AUTH_TOKEN`. Both DeepSeek and Z.ai publish Anthropic-compatible
endpoints, so reaching them is a matter of two environment variables.

But `agent.py` passes `output_format={"type": "json_schema", "schema": ...}`,
which the SDK turns into a `--json-schema` CLI flag (see
`claude_agent_sdk/_internal/transport/subprocess_cli.py`, the `output_format`
branch). That rides on Anthropic's structured-outputs beta, and **DeepSeek's
compatibility docs state the `anthropic-beta` header is ignored**; Z.ai is the
same class of gateway. Against those providers the model answers in prose and
`ResultMessage.structured_output` comes back `None`, so today's code raises
`RuntimeError("agent returned no structured output")` on the very first phase.

Therefore each provider declares a `structured_output` mode:

| mode | who enforces the schema | how the answer is read |
|---|---|---|
| `native` | the SDK / Anthropic API | `ResultMessage.structured_output` |
| `prompt` | nobody — the schema is appended to the prompt | parse `ResultMessage.result`, one repair turn on failure |

The repair turn **resumes the same session** (`resume=session_id`, `max_turns=2`,
no tools) so a malformed reply costs one extra turn, not a whole re-exploration.

## Second finding — cost accounting is Anthropic-only

`ResultMessage.total_cost_usd` is computed from Anthropic's price table. For a
third-party gateway it is meaningless. Each provider carries `reports_cost`;
when false, `AgentResult.cost_usd` is recorded as `null` (the dashboard already
treats a missing cost as `$0`) and `max_budget_usd` is not passed to the SDK,
with a warning printed at startup so the operator knows the hard stop is off.

## Decisions

1. **Providers supported:** built-in presets for `anthropic`, `deepseek`, `glm`,
   plus an open registry — any name defined under `providers:` in
   `prsentinel.yml` with `base_url`, `token_env`, `model`, `claims_model`.
2. **No OpenAI-protocol support.** The Agent SDK cannot speak it; that would
   require an external translating proxy and is explicitly out of scope.
3. **Configuration lives in `prsentinel.yml` + `.env`.** The YAML holds
   `provider:` (which one is active) and `providers:` (base URLs, model names,
   modes). **Tokens are only ever read from environment variables** — never
   written to the YAML, never returned by the HTTP API, never rendered in the
   dashboard.
4. **Dashboard gets a provider panel** on the Config page: shows the active
   provider, its base URL, its models, whether the required token is present,
   and lets the operator switch between configured providers. Switching writes
   only the `provider:` key.
5. **Environment overrides YAML.** `PRS_PROVIDER`, `ANTHROPIC_BASE_URL`,
   `PRS_MODEL`, `PRS_CLAIMS_MODEL` win over the file, so CI can override without
   editing a committed config.

## Built-in presets

| name | base_url | token env | model | claims model | structured | cost |
|---|---|---|---|---|---|---|
| `anthropic` | *(default)* | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | `claude-haiku-4-5-20251001` | `native` | yes |
| `deepseek` | `https://api.deepseek.com/anthropic` | `DEEPSEEK_API_KEY` | `deepseek-v4-pro` | `deepseek-v4-flash` | `prompt` | no |
| `glm` | `https://api.z.ai/api/anthropic` | `ZAI_API_KEY` | `glm-5.2` | `glm-4.7` | `prompt` | no |

## Authentication rules

- `anthropic` **with no base_url override**: a token, or a logged-in Claude Code
  CLI (`~/.claude.json`), is enough — today's behaviour.
- Every other provider: a token is **required**; a logged-in CLI proves nothing
  about a third-party gateway.
- The token is read from `ANTHROPIC_AUTH_TOKEN` first, then the provider's own
  `token_env`.
- For the subprocess, **both** `ANTHROPIC_AUTH_TOKEN` and `ANTHROPIC_API_KEY`
  are set to the resolved token. DeepSeek's docs use the latter, Z.ai's the
  former, and setting both also overrides any stale Anthropic key inherited from
  the parent process.

## Out of scope

- Translating between the Anthropic and OpenAI protocols.
- Per-phase provider routing (claims on one gateway, verify on another).
- Storing or rotating secrets from the dashboard.
- Re-pricing usage for third-party providers.

## Acceptance

- `PRS_PROVIDER=deepseek python -m src.run owner/repo 123 --skip-human` completes
  a full review, writing valid `claims.json`, `findings.json`, `score.json`.
- A malformed JSON reply on a `prompt`-mode provider is repaired in one extra
  turn rather than failing the phase.
- `prsentinel.yml` never contains a token; `GET /api/config` never returns one.
- `python -m pytest -q` green; existing Anthropic behaviour unchanged when no
  provider is configured.
