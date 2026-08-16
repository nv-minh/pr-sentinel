import json

from run import main

SNAPSHOT = {"owner": "demo", "repo": "app", "pr": 7, "title": "T",
            "body": "B" * 200, "author": "a", "base": "main", "head": "x",
            "head_sha": "sha1", "labels": [], "files": [], "commits": [],
            "threads": [], "pruned": []}

FINDINGS = {"claims": [], "docs": [], "impact": [], "callers_outside_diff": [],
            "contracts": [], "tests": [], "threads": [], "unresolved_questions": []}

FIXTURES = {"snapshot.json": SNAPSHOT, "claims.json": [], "findings.json": FINDINGS}


def _fixtures_dir(tmp_path):
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for name, data in FIXTURES.items():
        (fixtures / name).write_text(json.dumps(data))
    return fixtures


def _session(tmp_path):
    return tmp_path / "sessions" / "demo" / "app" / "pr-7"


def test_main_fixtures_mode(tmp_path, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))

    assert main(["demo/app", "7", "--fixtures", str(_fixtures_dir(tmp_path)),
                 "--no-post"]) == 0
    assert (_session(tmp_path) / "report.md").exists()
    assert (_session(tmp_path) / "score.json").exists()


def test_main_requires_gh(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr("run.gh_available", lambda: False)
    assert main(["demo/app", "7", "--no-post"]) == 2


def test_main_requires_auth(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "missing.json")
    assert main(["demo/app", "7", "--no-post"]) == 3


def test_main_owner_repo_hash_parsing(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    assert main(["demo/app#7", "--fixtures", str(_fixtures_dir(tmp_path)),
                 "--no-post"]) == 0
    assert (_session(tmp_path) / "report.md").exists()


def test_main_rejects_bad_arguments():
    assert main(["not-an-owner-repo", "7"]) == 2
    assert main(["demo/app#abc"]) == 2


def _patch_pipeline(monkeypatch, tmp_path, verify_calls, setup_calls):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    monkeypatch.setattr("run.gh_available", lambda: True)

    def fake_build_snapshot(owner, repo, n, session_dir, gh=None):
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "snapshot.json").write_text(json.dumps(SNAPSHOT))
        return SNAPSHOT

    def fake_extract_claims(snapshot, cfg, session_dir, runner=None):
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "claims.json").write_text("[]")
        return []

    def fake_setup_workspace(owner, repo, n, workspace, remote_url=None):
        setup_calls.append(1)

    def fake_run_verify(cfg, workspace, session_dir, snapshot, claims, runner=None):
        # the real run_verify persists findings.json — the resume logic depends on it
        verify_calls.append(1)
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "findings.json").write_text(json.dumps(FINDINGS))
        return dict(FINDINGS)

    monkeypatch.setattr("snapshot.build_snapshot", fake_build_snapshot)
    monkeypatch.setattr("claims.extract_claims", fake_extract_claims)
    monkeypatch.setattr("verify.setup_workspace", fake_setup_workspace)
    monkeypatch.setattr("verify.run_verify", fake_run_verify)


def test_rerun_skips_verify(tmp_path, monkeypatch):
    verify_calls, setup_calls = [], []
    _patch_pipeline(monkeypatch, tmp_path, verify_calls, setup_calls)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    assert main(["demo/app", "7", "--no-post"]) == 0
    assert len(verify_calls) == 1 and len(setup_calls) == 1
    assert (_session(tmp_path) / "findings.json").exists()

    assert main(["demo/app", "7", "--no-post"]) == 0
    assert len(verify_calls) == 1 and len(setup_calls) == 1


def test_verify_run_bumps_rounds(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    rounds = _session(tmp_path) / "rounds.txt"

    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    assert rounds.read_text().strip() == "1"
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    assert rounds.read_text().strip() == "1"          # cached, no new round
    assert main(["demo/app", "7", "--no-post", "--skip-human", "--force"]) == 0
    assert rounds.read_text().strip() == "2"


def test_ci_mode_exits_nonzero_when_gate_fails(tmp_path, monkeypatch):
    breaking = {**FINDINGS, "contracts": [
        {"kind": "API", "path": "openapi.yml", "status": "BREAKING_API_CHANGE",
         "detail": "removed field"}]}
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "snapshot.json").write_text(json.dumps(SNAPSHOT))
    (fixtures / "claims.json").write_text("[]")
    (fixtures / "findings.json").write_text(json.dumps(breaking))
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))

    # --fixtures never posts, so this exercises the gate exit code alone
    assert main(["demo/app", "7", "--fixtures", str(fixtures), "--ci"]) == 1
    scores = json.loads((_session(tmp_path) / "score.json").read_text())
    assert scores["gate"] == "fail"


def test_ci_mode_exits_zero_when_gate_passes(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    assert main(["demo/app", "7", "--fixtures", str(_fixtures_dir(tmp_path)),
                 "--ci"]) == 0


def test_failed_phase_writes_failure_report(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch, tmp_path, [], [])

    def boom(owner, repo, n, session_dir, gh=None):
        session_dir.mkdir(parents=True, exist_ok=True)
        raise RuntimeError("github exploded")

    monkeypatch.setattr("snapshot.build_snapshot", boom)
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 1
    assert "github exploded" in (_session(tmp_path) / "report.md").read_text()
