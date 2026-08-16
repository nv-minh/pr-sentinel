import json

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
