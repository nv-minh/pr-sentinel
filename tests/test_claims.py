import json

import pytest

from agent import AgentResult
from claims import build_prompt, extract_claims

RESPONSE = {"claims": [
    {"id": "C1", "text": "Adds checkout", "category": "feature",
     "files": ["src/checkout.py"], "docs": []},
    {"id": "C2", "text": "Fixes payment retry", "category": "bugfix",
     "files": ["src/payment.py"], "docs": ["docs/payment.md"]},
]}

SNAPSHOT = {
    "title": "Add checkout flow",
    "body": "Adds checkout. Fixes payment retry.",
    "files": [{"filename": "src/checkout.py"}, {"filename": "src/payment.py"}],
}


def _runner(data):
    return lambda prompt, **kw: AgentResult(data=data, session_id="s", cost_usd=0.01,
                                            num_turns=1, duration_ms=10)


def test_extract_claims(tmp_path):
    session_dir = tmp_path / "s"
    claims = extract_claims(SNAPSHOT, {"claims_model": "m"}, session_dir,
                            runner=_runner(RESPONSE))
    assert claims[0]["id"] == "C1"
    assert claims[1]["category"] == "bugfix"
    assert claims[1]["docs"] == ["docs/payment.md"]
    assert len(json.loads((session_dir / "claims.json").read_text())) == 2


def test_extract_claims_records_cost(tmp_path):
    session_dir = tmp_path / "s"
    extract_claims(SNAPSHOT, {"claims_model": "m"}, session_dir, runner=_runner(RESPONSE))
    usage = json.loads((session_dir / "usage.json").read_text())
    assert usage[0]["phase"] == "claims"


def test_extract_claims_rejects_missing_list(tmp_path):
    with pytest.raises(RuntimeError, match="missing 'claims' list"):
        extract_claims(SNAPSHOT, {"claims_model": "m"}, tmp_path / "s",
                       runner=_runner({"nope": []}))


def test_extract_claims_rejects_bad_category(tmp_path):
    bad = {"claims": [{"id": "C1", "text": "x", "category": "nonsense",
                       "files": [], "docs": []}]}
    with pytest.raises(RuntimeError, match="invalid schema"):
        extract_claims(SNAPSHOT, {"claims_model": "m"}, tmp_path / "s",
                       runner=_runner(bad))


def test_build_prompt_lists_files_and_body():
    prompt = build_prompt(SNAPSHOT)
    assert "src/checkout.py" in prompt
    assert "Fixes payment retry" in prompt


def test_build_prompt_marks_empty_body():
    prompt = build_prompt({"title": "t", "body": "", "files": []})
    assert "(empty)" in prompt
    assert "- (none)" in prompt
