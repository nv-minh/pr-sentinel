import json

import pytest

from agent import AgentResult
from describe import (build_prompt, comment_section, draft_description,
                      needs_description)

SNAPSHOT = {"title": "Add checkout", "body": "", "files": [
    {"filename": "src/checkout.py", "additions": 40, "deletions": 2,
     "patch": "@@\n+def checkout():"}],
    "commits": [{"sha": "a1", "message": "feat: checkout\n\ndetail"}]}

DRAFT = {"description": "## What\nAdds checkout.", "summary": "Adds checkout"}


def _runner(data):
    return lambda prompt, **kw: AgentResult(data=data, session_id="s", cost_usd=0.01,
                                            num_turns=1, duration_ms=5)


def test_needs_description_for_empty_and_thin_bodies():
    assert needs_description({"body": ""}) is True
    assert needs_description({"body": "fix"}) is True
    assert needs_description({"body": "x" * 200}) is False


def test_build_prompt_includes_commits_and_diff():
    prompt = build_prompt(SNAPSHOT)
    assert "feat: checkout" in prompt
    assert "src/checkout.py" in prompt
    assert "+def checkout():" in prompt
    assert "## Testing" in prompt          # the template the model must follow


def test_draft_description_saves_and_records(tmp_path):
    draft = draft_description(SNAPSHOT, {"claims_model": "m"}, tmp_path,
                              runner=_runner(DRAFT))
    assert draft["summary"] == "Adds checkout"
    assert json.loads((tmp_path / "description.json").read_text()) == DRAFT
    assert json.loads((tmp_path / "usage.json").read_text())[0]["phase"] == "describe"


def test_draft_description_rejects_an_empty_answer(tmp_path):
    with pytest.raises(RuntimeError, match="missing 'description'"):
        draft_description(SNAPSHOT, {}, tmp_path, runner=_runner({"description": ""}))


def test_comment_section_is_collapsible():
    section = comment_section(DRAFT)
    assert "<details>" in section
    assert "Adds checkout." in section
