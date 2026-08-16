"""The single integration point with the Claude Agent SDK.

Every LLM call in this project goes through `run_structured()`, which forces a
JSON-schema answer (`output_format`) and returns it as a plain dict. Callers
never touch the SDK, so tests inject a fake runner instead of mocking the SDK.

Safety defaults, applied to every call:
- `permission_mode="dontAsk"` — a tool that is not pre-approved is denied
  outright rather than prompting an operator that does not exist.
- `setting_sources=[]` — ignore the host machine's CLAUDE.md / settings /
  skills, so a review only ever sees the repo under review.
- tools default to read-only; the agent reports findings through the schema,
  it never edits the workspace.
- provider routing goes through `ClaudeAgentOptions.env`, so a third-party
  base URL and token never leak into the parent process's environment.
"""
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

import providers
from session_store import FileSessionStore

# Read-only inspection tools: enough to verify claims, trace callers and read docs.
READ_ONLY_TOOLS = ["Read", "Grep", "Glob"]
# Bash is opt-in (`allow_bash` in prsentinel.yml) for `git log`/`git grep` tracing.
BASH_TOOLS = READ_ONLY_TOOLS + ["Bash"]
# Never available, whatever the caller asks for: no writes, no network.
BLOCKED_TOOLS = ["Write", "Edit", "NotebookEdit", "WebFetch", "WebSearch"]


@dataclass
class AgentResult:
    """What one agent run produced, plus what it cost."""
    data: dict
    session_id: str = ""
    cost_usd: float | None = None
    num_turns: int = 0
    duration_ms: int = 0
    model: str = ""

    def usage_entry(self, phase: str) -> dict:
        return {"phase": phase, "session_id": self.session_id,
                "cost_usd": self.cost_usd, "num_turns": self.num_turns,
                "duration_ms": self.duration_ms, "model": self.model}


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


def _options(*, schema: dict | None, cwd: Path | str | None,
             tools: list[str] | None, model: str | None,
             max_turns: int | None, max_budget_usd: float | None,
             resume: str | None, system_prompt: str | None, env: dict,
             session_dir: Path | str | None):
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
        session_store=FileSessionStore(session_dir) if session_dir else None,
        output_format=({"type": "json_schema", "schema": schema}
                       if schema is not None else None),
    )


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

    Tried in order: the whole reply (the instructed shape is one bare object,
    and a bare reply whose string values happen to contain fences must not be
    mistaken for a fenced block); every fenced block, last first (a model that
    restates the schema before answering leaves the answer in the final
    block); then a brace-scan fallback over the first fence when there is
    one, the whole reply otherwise.
    """
    if not (text or "").strip():
        raise RuntimeError("agent returned an empty reply")
    body = text.strip()
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    fences = re.findall(r"```(?:json)?\s*(.+?)```", body, re.S)
    for fence in reversed(fences):
        try:
            data = json.loads(fence.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    body = fences[0].strip() if fences else body
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


def run_structured(prompt: str, *, schema: dict, cwd: Path | str | None = None,
                   tools: list[str] | None = None, model: str | None = None,
                   max_turns: int | None = None,
                   max_budget_usd: float | None = None,
                   resume: str | None = None,
                   system_prompt: str | None = None,
                   session_dir: Path | str | None = None,
                   provider: providers.Provider | None = None) -> AgentResult:
    """Run one agent turn-loop and return its schema-validated JSON answer.

    `tools=None` means no tools at all (a plain completion); pass
    `READ_ONLY_TOOLS` for a code-reading agent. Every SDK failure is re-raised
    as RuntimeError so callers can handle one exception type.

    `session_dir` mirrors the transcript into that directory so a later
    `resume=` works on a machine that never saw the original run.
    """
    from claude_agent_sdk import ClaudeSDKError

    if provider is None:
        provider = providers.BUILTIN["anthropic"]
    # A provider with no server-side schema enforcement gets the schema folded
    # into the prompt instead; the SDK never sees output_format for it.
    if not provider.is_native():
        prompt = compat_prompt(prompt, schema)
    options = _options(
        schema=schema if provider.is_native() else None,
        cwd=cwd, tools=tools, model=model, max_turns=max_turns,
        # A budget the provider cannot price is a hard stop that never fires.
        max_budget_usd=max_budget_usd if provider.reports_cost else None,
        resume=resume, system_prompt=system_prompt,
        session_dir=session_dir,
        env=providers.agent_env(provider),
    )
    try:
        message = asyncio.run(_query(prompt, options))
    except ClaudeSDKError as e:
        raise RuntimeError(f"Claude Agent SDK failed: {e}") from e

    repaired = False
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
            first_message = message
            repaired = True
            repair = _options(
                schema=None, cwd=cwd, tools=None, model=model, max_turns=2,
                # Same budget gating as the first call: a provider we trust to
                # price stays capped on the repair too.
                max_budget_usd=max_budget_usd if provider.reports_cost else None,
                resume=first_message.session_id,
                system_prompt=system_prompt, session_dir=session_dir,
                env=providers.agent_env(provider))
            try:
                message = asyncio.run(_query(
                    REPAIR_INSTRUCTION.format(error=first), repair))
            except ClaudeSDKError as e:
                raise RuntimeError(f"Claude Agent SDK failed: {e}") from e
            try:
                data = extract_json(message.result or "")
            except RuntimeError as second:
                raise RuntimeError(
                    f"repair turn failed too: {second}") from first

    # A repair turn is a second real attempt: fold its turns/time/cost into the
    # phase total instead of discarding the first attempt's accounting.
    num_turns = message.num_turns
    duration_ms = message.duration_ms
    cost_usd = message.total_cost_usd if provider.reports_cost else None
    if repaired:
        num_turns += first_message.num_turns
        duration_ms += first_message.duration_ms
        if provider.reports_cost:
            cost_usd = (cost_usd or 0.0) + (first_message.total_cost_usd or 0.0)

    return AgentResult(
        data=data,
        session_id=message.session_id,
        cost_usd=cost_usd,
        num_turns=num_turns,
        duration_ms=duration_ms,
        model=model or provider.model,
    )


def record_usage(session_dir: Path, phase: str, result: AgentResult) -> None:
    """Append one phase's cost to usage.json. Never fails a review."""
    path = session_dir / "usage.json"
    try:
        entries = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(entries, list):
            entries = []
    except (OSError, json.JSONDecodeError):
        entries = []
    entries = [e for e in entries if e.get("phase") != phase]
    entries.append(result.usage_entry(phase))
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, indent=2))
    except OSError:
        pass


def total_cost(session_dir: Path) -> float:
    """Sum of every recorded phase cost for a session (0.0 if unknown)."""
    path = session_dir / "usage.json"
    try:
        entries = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return 0.0
    return sum(e.get("cost_usd") or 0.0 for e in entries if isinstance(e, dict))
