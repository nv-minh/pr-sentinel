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
