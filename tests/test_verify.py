import json
import subprocess

import pytest

from agent import AgentResult
from verify import (build_verify_prompt, run_verify, setup_workspace,
                    validate_findings)

FINDINGS = {
    "claims": [{"id": "C1", "status": "PASS", "evidence": ["a.py:1"], "note": "",
                "confidence": 0.9}],
    "docs": [], "impact": [], "callers_outside_diff": [], "contracts": [],
    "tests": [], "threads": [], "unresolved_questions": [],
}

SNAPSHOT = {"owner": "demo", "repo": "app", "pr": 7, "title": "T", "body": "B",
            "base": "main", "head": "feat", "head_sha": "abc123",
            "files": [{"filename": "a.py", "additions": 1, "deletions": 0}],
            "threads": [{"body": "c1", "resolved": False, "author": "r"}],
            "commits": [], "pruned": [{"filename": "yarn.lock", "reason": "lockfile",
                                       "dropped": True}]}


def _origin_repo(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=origin, check=True)
    (origin / "app.py").write_text("print('base')\n")
    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "base"], cwd=origin, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "pull/7/head"], cwd=origin, check=True)
    (origin / "app.py").write_text("print('feature')\n")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qam", "feat"], cwd=origin, check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=origin, check=True)
    return origin


def test_setup_workspace_clones_and_checks_out(tmp_path):
    origin = _origin_repo(tmp_path)
    ws = tmp_path / "ws"
    setup_workspace("demo", "app", 7, ws, remote_url=str(origin))
    assert (ws / "app.py").read_text() == "print('feature')\n"


def test_setup_workspace_rerun_existing_checkout(tmp_path):
    origin = _origin_repo(tmp_path)
    ws = tmp_path / "ws"
    setup_workspace("demo", "app", 7, ws, remote_url=str(origin))

    subprocess.run(["git", "checkout", "-q", "pull/7/head"], cwd=origin, check=True)
    (origin / "app.py").write_text("print('feature v2')\n")
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qam", "feat2"], cwd=origin, check=True)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=origin, check=True)

    setup_workspace("demo", "app", 7, ws, remote_url=str(origin))
    assert (ws / "app.py").read_text() == "print('feature v2')\n"


def test_validate_findings_ok():
    assert validate_findings(dict(FINDINGS))["claims"][0]["status"] == "PASS"


def test_validate_findings_missing_section():
    broken = {k: v for k, v in FINDINGS.items() if k != "contracts"}
    with pytest.raises(RuntimeError, match="missing key contracts"):
        validate_findings(broken)


def test_validate_findings_bad_claim_status():
    broken = {**FINDINGS, "claims": [{"id": "C1", "status": "MAYBE", "evidence": []}]}
    with pytest.raises(RuntimeError, match="claim has invalid schema"):
        validate_findings(broken)


def test_validate_findings_bad_contract_status():
    broken = {**FINDINGS, "contracts": [{"kind": "API", "path": "x", "status": "NOPE"}]}
    with pytest.raises(RuntimeError, match="contract has invalid schema"):
        validate_findings(broken)


def test_build_verify_prompt_covers_every_section():
    claims = [{"id": "C1", "text": "x", "category": "feature", "files": [], "docs": []}]
    prompt = build_verify_prompt(SNAPSHOT, claims)
    for needle in ("C1", "FABRICATED", "UNVERIFIED", "BREAKING_API_CHANGE",
                   "callers_outside_diff", "assertion_quality", "yarn.lock"):
        assert needle in prompt


def test_run_verify_persists_findings_and_session(tmp_path):
    captured = {}

    def runner(prompt, **kw):
        captured.update(kw)
        return AgentResult(data=dict(FINDINGS), session_id="sess-1", cost_usd=0.3,
                           num_turns=8, duration_ms=999)

    session_dir = tmp_path / "s"
    findings = run_verify({"model": "m"}, tmp_path / "ws", session_dir,
                          SNAPSHOT, [], runner=runner)

    assert findings["claims"][0]["id"] == "C1"
    assert json.loads((session_dir / "findings.json").read_text()) == FINDINGS
    assert json.loads((session_dir / "verify-meta.json").read_text()) == {
        "session_id": "sess-1", "head_sha": "abc123"}
    assert json.loads((session_dir / "usage.json").read_text())[0]["cost_usd"] == 0.3
    assert captured["tools"] == ["Read", "Grep", "Glob"]


def test_run_verify_allows_bash_when_configured(tmp_path):
    captured = {}

    def runner(prompt, **kw):
        captured.update(kw)
        return AgentResult(data=dict(FINDINGS), session_id="s", cost_usd=0.0,
                           num_turns=1, duration_ms=1)

    run_verify({"model": "m", "allow_bash": True}, tmp_path / "ws", tmp_path / "s",
               SNAPSHOT, [], runner=runner)
    assert "Bash" in captured["tools"]


def test_run_verify_mirrors_the_transcript_into_the_session(tmp_path):
    captured = {}

    def runner(prompt, **kw):
        captured.update(kw)
        return AgentResult(data=dict(FINDINGS), session_id="sess-1", cost_usd=0.1,
                           num_turns=2, duration_ms=10)

    session_dir = tmp_path / "s"
    run_verify({"model": "m"}, tmp_path / "ws", session_dir, SNAPSHOT, [],
               runner=runner)
    assert captured["session_dir"] == session_dir
