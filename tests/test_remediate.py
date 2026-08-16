import json

from agent import AgentResult
from remediate import (apply_to_workspace, comment_section, diff_block,
                       draft_patches, fixable_docs, post_suggestions,
                       suggestion_body)

FINDINGS = {"docs": [
    {"path": "docs/api.md", "status": "WRONG", "what": "says GET, code does POST"},
    {"path": "docs/ok.md", "status": "MATCH", "what": ""},
    {"path": "README.md", "status": "STALE", "what": "old flag name"},
]}

PATCH = {"path": "docs/api.md", "old_snippet": "GET /users",
         "new_snippet": "POST /users", "line_hint": 12,
         "why": "the handler is registered for POST"}

SNAPSHOT = {"head_sha": "sha123", "head": "feature/x",
            "files": [{"filename": "docs/api.md"}]}


def test_fixable_docs_ignores_matching_docs():
    assert [d["path"] for d in fixable_docs(FINDINGS)] == ["docs/api.md", "README.md"]


def test_suggestion_body_is_a_github_suggestion():
    body = suggestion_body(PATCH)
    assert "```suggestion\nPOST /users\n```" in body
    assert "registered for POST" in body


def test_diff_block_shows_both_sides():
    block = diff_block(PATCH)
    assert "-GET /users" in block
    assert "+POST /users" in block


def test_comment_section_is_empty_without_patches():
    assert comment_section([]) == ""
    assert "docs/api.md" in comment_section([PATCH])


def test_draft_patches_filters_incomplete_entries(tmp_path):
    data = {"patches": [PATCH, {"path": "x.md", "old_snippet": "", "new_snippet": "y"}]}
    runner = lambda prompt, **kw: AgentResult(data=data, session_id="s", cost_usd=0.02,
                                              num_turns=4, duration_ms=10)
    patches = draft_patches(FINDINGS, {"model": "m"}, tmp_path / "ws", tmp_path,
                            runner=runner)
    assert patches == [PATCH]
    assert json.loads((tmp_path / "patches.json").read_text()) == [PATCH]
    assert json.loads((tmp_path / "usage.json").read_text())[0]["phase"] == "remediate"


def test_draft_patches_skips_the_model_when_nothing_is_broken(tmp_path):
    def runner(prompt, **kw):
        raise AssertionError("should not call the model")

    assert draft_patches({"docs": []}, {}, tmp_path, tmp_path, runner=runner) == []


def test_post_suggestions_splits_by_diff_membership():
    posted_calls = []

    def fake_gh(args, **kw):
        posted_calls.append(args)
        return {}

    outside = {**PATCH, "path": "docs/other.md"}
    posted, leftover = post_suggestions("o", "r", 7, [PATCH, outside], SNAPSHOT, gh=fake_gh)
    assert posted == [PATCH]
    assert leftover == [outside]
    assert len(posted_calls) == 1


def test_post_suggestions_falls_back_when_github_rejects_the_anchor():
    def fake_gh(args, **kw):
        raise RuntimeError("line is not part of the diff")

    posted, leftover = post_suggestions("o", "r", 7, [PATCH], SNAPSHOT, gh=fake_gh)
    assert posted == []
    assert leftover == [PATCH]


def test_apply_to_workspace_replaces_matching_text(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/api.md").write_text("# API\n\nGET /users\n")
    applied, rejected = apply_to_workspace([PATCH], tmp_path)
    assert applied == [PATCH]
    assert rejected == []
    assert "POST /users" in (tmp_path / "docs/api.md").read_text()


def test_apply_to_workspace_rejects_a_stale_snippet(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/api.md").write_text("# API\n\nPATCH /users\n")
    applied, rejected = apply_to_workspace([PATCH], tmp_path)
    assert applied == []
    assert rejected[0]["reason"] == "old_snippet did not match the file"


def test_apply_to_workspace_rejects_paths_outside_the_clone(tmp_path):
    applied, rejected = apply_to_workspace(
        [{**PATCH, "path": "../../etc/passwd"}], tmp_path)
    assert applied == []
    assert rejected[0]["reason"] == "file not found in workspace"
