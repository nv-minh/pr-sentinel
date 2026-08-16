import json

from agent import AgentResult
from poc import POC_SCHEMA, broken, comment_section, detect_framework, draft_pocs

FINDINGS = {
    "impact": [
        {"requirement": "retry twice", "requirement_source": "ABC-1", "impact": "BROKEN",
         "area": "payment", "paths": ["src/pay.py"], "detail": "only retries once"},
        {"requirement": "log it", "requirement_source": "ABC-1", "impact": "CHANGED",
         "area": "infra", "paths": ["src/log.py"], "detail": ""},
    ],
    "callers_outside_diff": [
        {"symbol": "charge", "defined_at": "src/pay.py:3", "callers": ["src/z.py:9"],
         "risk": "BROKEN", "note": "signature changed"},
        {"symbol": "ok", "defined_at": "src/pay.py:8", "callers": [], "risk": "SAFE",
         "note": ""},
    ],
}

CLEAN = {"impact": [], "callers_outside_diff": []}

POC = {"target": "src/pay.py", "framework": "pytest",
       "test_code": "def test_retries_twice():\n    assert charge() == 2",
       "why_it_fails": "charge() retries once, so it returns 1"}


def _runner(data):
    return lambda prompt, **kw: AgentResult(data=data, session_id="s", cost_usd=0.02,
                                            num_turns=2, duration_ms=20)


def test_broken_finds_broken_impact_and_callers():
    got = broken(FINDINGS)
    assert len(got) == 2
    assert "retry twice" in got[0]["what"]
    assert "charge" in got[1]["what"]


def test_broken_ignores_healthy_findings():
    assert broken(CLEAN) == []
    assert not any("log it" in b["what"] for b in broken(FINDINGS))


def test_detect_framework_finds_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    assert detect_framework(tmp_path) == "pytest"


def test_detect_framework_finds_pytest_from_conftest(tmp_path):
    (tmp_path / "conftest.py").write_text("")
    assert detect_framework(tmp_path) == "pytest"


def test_detect_framework_finds_vitest(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"devDependencies": {"vitest": "^1.0.0"}}))
    assert detect_framework(tmp_path) == "vitest"


def test_detect_framework_finds_jest(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"devDependencies": {"jest": "^29"}}))
    assert detect_framework(tmp_path) == "jest"


def test_detect_framework_finds_go_test(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    assert detect_framework(tmp_path) == "go test"


def test_detect_framework_survives_broken_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{not json")
    assert detect_framework(tmp_path) == "unknown"


def test_detect_framework_on_an_empty_workspace(tmp_path):
    assert detect_framework(tmp_path) == "unknown"


def test_draft_pocs_is_skipped_when_nothing_is_broken(tmp_path):
    def fail(*a, **kw):
        raise AssertionError("must not pay for an agent pass with no broken findings")

    assert draft_pocs(CLEAN, {"model": "m"}, tmp_path, tmp_path, runner=fail) == []


def test_draft_pocs_persists_and_returns(tmp_path):
    pocs = draft_pocs(FINDINGS, {"model": "m"}, tmp_path, tmp_path,
                      runner=_runner({"tests": [POC]}))
    assert pocs == [POC]
    assert json.loads((tmp_path / "poc.json").read_text()) == [POC]
    assert json.loads((tmp_path / "usage.json").read_text())[0]["phase"] == "poc"


def test_draft_pocs_drops_an_entry_without_code(tmp_path):
    bad = {**POC, "test_code": ""}
    assert draft_pocs(FINDINGS, {"model": "m"}, tmp_path, tmp_path,
                      runner=_runner({"tests": [bad, POC]})) == [POC]


def test_the_schema_requires_the_failure_reason():
    item = POC_SCHEMA["properties"]["tests"]["items"]
    assert set(item["required"]) == {"target", "framework", "test_code", "why_it_fails"}


def test_comment_section_labels_the_test_as_not_executed():
    section = comment_section([POC])
    assert "not been executed" in section
    assert "def test_retries_twice" in section
    assert "charge() retries once" in section


def test_comment_section_is_empty_without_pocs():
    assert comment_section([]) == ""
