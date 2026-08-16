import json
from types import SimpleNamespace

import pytest

import agent
import providers
from agent import AgentResult, record_usage, total_cost


def _result(cost: float | None, phase_turns: int = 3) -> AgentResult:
    return AgentResult(data={"ok": True}, session_id="s1", cost_usd=cost,
                       num_turns=phase_turns, duration_ms=1200, model="m")


def test_record_usage_writes_entry(tmp_path):
    record_usage(tmp_path, "verify", _result(0.25))
    entries = json.loads((tmp_path / "usage.json").read_text())
    assert entries == [{"phase": "verify", "session_id": "s1", "cost_usd": 0.25,
                        "num_turns": 3, "duration_ms": 1200, "model": "m"}]


def test_record_usage_replaces_same_phase(tmp_path):
    record_usage(tmp_path, "verify", _result(0.25))
    record_usage(tmp_path, "verify", _result(0.40))
    record_usage(tmp_path, "claims", _result(0.01))
    entries = json.loads((tmp_path / "usage.json").read_text())
    assert [e["phase"] for e in entries] == ["verify", "claims"]
    assert entries[0]["cost_usd"] == 0.40


def test_record_usage_survives_corrupt_file(tmp_path):
    (tmp_path / "usage.json").write_text("not json")
    record_usage(tmp_path, "claims", _result(0.02))
    assert json.loads((tmp_path / "usage.json").read_text())[0]["phase"] == "claims"


def test_total_cost_sums_phases(tmp_path):
    record_usage(tmp_path, "claims", _result(0.01))
    record_usage(tmp_path, "verify", _result(0.25))
    record_usage(tmp_path, "remediate", _result(None))  # unknown cost counts as 0
    assert total_cost(tmp_path) == 0.26


def test_total_cost_without_file(tmp_path):
    assert total_cost(tmp_path) == 0.0


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
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    seen = _capture(monkeypatch)
    result = agent.run_structured("hi", schema={"type": "object"}, model="m")
    assert result.data == {"ok": True}
    assert seen["options"].output_format == {"type": "json_schema",
                                             "schema": {"type": "object"}}
    assert seen["options"].env == {}
    assert seen["prompt"] == "hi"


def test_provider_env_reaches_the_subprocess(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    seen = _capture(monkeypatch)
    agent.run_structured("hi", schema={"type": "object"},
                         provider=providers.build("deepseek", {"structured_output": "native"}))
    env = seen["options"].env
    assert env["ANTHROPIC_BASE_URL"] == "https://api.deepseek.com/anthropic"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "k"
    assert env["ANTHROPIC_API_KEY"] == "k"


def test_native_path_still_rejects_a_missing_structured_output(monkeypatch):
    _capture(monkeypatch, _fake_result(structured_output=None))
    with pytest.raises(RuntimeError, match="no structured output"):
        agent.run_structured("hi", schema={"type": "object"})


def test_cost_is_dropped_when_the_provider_cannot_price_it(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _capture(monkeypatch)
    result = agent.run_structured("hi", schema={"type": "object"},
                                  provider=providers.build("deepseek", {"structured_output": "native"}))
    assert result.cost_usd is None


def test_budget_is_only_sent_to_a_provider_that_reports_cost(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    seen = _capture(monkeypatch)
    agent.run_structured("hi", schema={"type": "object"}, max_budget_usd=2.0,
                         provider=providers.build("deepseek", {"structured_output": "native"}))
    assert seen["options"].max_budget_usd is None


def test_a_session_dir_attaches_the_transcript_store(monkeypatch, tmp_path):
    seen = _capture(monkeypatch)
    agent.run_structured("hi", schema={"type": "object"}, session_dir=tmp_path)
    store = seen["options"].session_store
    assert store is not None
    assert store.root == tmp_path / "transcripts"


def test_no_session_dir_means_no_transcript_store(monkeypatch):
    seen = _capture(monkeypatch)
    agent.run_structured("hi", schema={"type": "object"})
    assert seen["options"].session_store is None


def test_extract_json_reads_a_bare_object():
    assert agent.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_reads_a_fenced_object():
    assert agent.extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_skips_a_quoted_code_fence():
    """A follow-up reply often quotes fenced code before the real answer."""
    text = ('The author suggested:\n```python\nx = 1\n```\n'
            'My answer:\n```json\n{"a": 1}\n```')
    assert agent.extract_json(text) == {"a": 1}


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


def test_extract_json_does_not_mistake_a_fence_inside_a_string_value():
    """remediate.PATCH_SCHEMA's old_snippet is documentation copied verbatim,
    and documentation contains fences constantly — a bare reply must be tried
    whole before the fence regex gets a chance to match inside a string."""
    text = '{"patches": [{"old_snippet": "see ```py\\nx=1\\n``` here"}]}'
    assert agent.extract_json(text) == {
        "patches": [{"old_snippet": "see ```py\nx=1\n``` here"}]}


def test_extract_json_prefers_the_last_fenced_block_over_an_echoed_schema():
    """compat_prompt puts the schema in the prompt; a model that echoes it
    back before answering must not have the echo mistaken for the answer."""
    text = ('Schema:\n```json\n{"type": "object", "properties": {}}\n```\n'
            'Answer:\n```json\n{"claims": []}\n```')
    assert agent.extract_json(text) == {"claims": []}


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


def test_repair_turn_accumulates_turns_duration_and_cost(monkeypatch):
    """A provider trusted to price cost (structured_output: prompt,
    reports_cost: true, as the README documents for a custom gateway) must not
    have the first attempt's turns/time/cost discarded when a repair turn
    runs, and the repair must stay under the same budget as the first call."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    calls = []

    async def fake_query(prompt, options):
        calls.append((prompt, options))
        if len(calls) == 1:
            return _fake_result(structured_output=None, result="no idea, sorry",
                                total_cost_usd=0.10, num_turns=3, duration_ms=500)
        return _fake_result(structured_output=None, result='{"claims": []}',
                            session_id="sess-2", total_cost_usd=0.05,
                            num_turns=2, duration_ms=300)

    monkeypatch.setattr(agent, "_query", fake_query)
    provider = providers.build("deepseek", {"reports_cost": True})
    result = agent.run_structured("extract", schema={"type": "object"},
                                  max_budget_usd=2.0, provider=provider)
    assert result.data == {"claims": []}
    assert result.num_turns == 5
    assert result.duration_ms == 800
    assert result.cost_usd == pytest.approx(0.15)
    _, repair_options = calls[1]
    assert repair_options.max_budget_usd == 2.0


def test_prompt_mode_gives_up_after_one_repair(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    _capture(monkeypatch, _fake_result(structured_output=None, result="still prose"))
    with pytest.raises(RuntimeError, match="no JSON object"):
        agent.run_structured("extract", schema={"type": "object"},
                             provider=providers.build("deepseek", None))
