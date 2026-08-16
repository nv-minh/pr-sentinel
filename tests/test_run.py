import json

import providers
import run
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
    for name in ("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
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

    def fake_run_verify(cfg, workspace, session_dir, snapshot, claims, ticket=None,
                        runner=None):
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


def test_reply_mode_does_nothing_without_new_replies(tmp_path, monkeypatch, capsys):
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    monkeypatch.setattr("threads.fetch_replies", lambda *a, **kw: [])

    assert main(["demo/app", "7", "--no-post", "--skip-human", "--reply"]) == 0
    assert "No new replies" in capsys.readouterr().out


def test_reply_mode_resumes_instead_of_reviewing(tmp_path, monkeypatch):
    verify_calls = []
    _patch_pipeline(monkeypatch, tmp_path, verify_calls, [])
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0

    reply = {"id": 5, "source": "conversation", "author": "dev1",
             "body": "refactored, see the new commit", "path": None}
    followups = []

    def fake_followup(cfg, workspace, session_dir, snapshot, replies, new_commits,
                      runner=None):
        followups.append(replies)
        return dict(FINDINGS)

    monkeypatch.setattr("threads.fetch_replies", lambda *a, **kw: [reply])
    monkeypatch.setattr("threads.run_followup", fake_followup)

    assert main(["demo/app", "7", "--no-post", "--skip-human", "--reply"]) == 0
    assert followups == [[reply]]
    assert len(verify_calls) == 1          # the full verify never ran again
    assert json.loads((_session(tmp_path) / "replies.json").read_text())[0]["id"] == 5
    assert (_session(tmp_path) / "rounds.txt").read_text().strip() == "2"


def test_reply_mode_falls_back_to_a_full_review(tmp_path, monkeypatch):
    verify_calls = []
    _patch_pipeline(monkeypatch, tmp_path, verify_calls, [])
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0

    def cannot_resume(*a, **kw):
        raise RuntimeError("no previous verify session to resume")

    monkeypatch.setattr("threads.fetch_replies",
                        lambda *a, **kw: [{"id": 5, "source": "conversation",
                                           "author": "dev1", "body": "hi", "path": None}])
    monkeypatch.setattr("threads.run_followup", cannot_resume)

    assert main(["demo/app", "7", "--no-post", "--skip-human", "--reply"]) == 0
    assert len(verify_calls) == 2          # fell back to the full pass


def test_failed_phase_writes_failure_report(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch, tmp_path, [], [])

    def boom(owner, repo, n, session_dir, gh=None):
        session_dir.mkdir(parents=True, exist_ok=True)
        raise RuntimeError("github exploded")

    monkeypatch.setattr("snapshot.build_snapshot", boom)
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 1
    assert "github exploded" in (_session(tmp_path) / "report.md").read_text()


def test_agent_config_carries_the_resolved_provider(monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    monkeypatch.delenv("PRS_MODEL", raising=False)
    monkeypatch.delenv("PRS_CLAIMS_MODEL", raising=False)
    env = run.load_config()
    cfg = run.agent_config(env, {"provider": "deepseek"})
    assert cfg["provider"].name == "deepseek"
    assert cfg["model"] == "deepseek-v4-pro"
    assert cfg["claims_model"] == "deepseek-v4-flash"


def test_agent_config_defaults_to_anthropic(monkeypatch):
    for name in ("PRS_PROVIDER", "PRS_MODEL", "PRS_CLAIMS_MODEL"):
        monkeypatch.delenv(name, raising=False)
    cfg = run.agent_config(run.load_config(), {})
    assert cfg["provider"].name == "anthropic"
    assert cfg["model"] == "claude-sonnet-5"


def test_run_refuses_a_provider_without_a_token(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRS_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    assert run.main(["owner/repo", "1"]) == 3
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err


def test_phases_forward_the_provider_to_the_runner(tmp_path):
    """Every phase must pass cfg["provider"] through, or a gateway silently
    falls back to Anthropic credentials."""
    import claims

    seen = {}

    def fake_runner(prompt, **kw):
        seen.update(kw)
        return providers  # unused; we raise before the return value matters

    cfg = {"claims_model": "m", "provider": providers.build("glm", None)}
    snapshot = {"title": "t", "body": "b", "files": []}
    try:
        claims.extract_claims(snapshot, cfg, tmp_path, runner=fake_runner)
    except Exception:
        pass
    assert seen["provider"].name == "glm"


def test_a_review_records_why_it_had_no_requirement(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    ticket = json.loads(
        (tmp_path / "sessions/demo/app/pr-7/ticket.json").read_text())
    assert ticket == {"primary": "", "tickets": [],
                      "skipped": "Jira is not configured (JIRA_BASE_URL, "
                                 "JIRA_EMAIL, JIRA_API_TOKEN)"}


def test_the_ticket_reaches_verify(tmp_path, monkeypatch):
    seen = {}
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    fetched = {"primary": "ABC-1", "tickets": [{"key": "ABC-1"}], "skipped": ""}

    def fake_fetch(snapshot, session_dir, jira_cfg, **kw):
        seen["projects"] = jira_cfg.get("projects")
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "ticket.json").write_text(json.dumps(fetched))
        return fetched

    def capturing_verify(cfg, workspace, session_dir, snapshot, claims,
                         ticket=None, runner=None):
        seen["ticket"] = ticket
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "findings.json").write_text(json.dumps(FINDINGS))
        return dict(FINDINGS)

    monkeypatch.setattr("tickets.fetch_tickets", fake_fetch)
    monkeypatch.setattr("verify.run_verify", capturing_verify)
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    assert seen["ticket"] == fetched
    assert seen["projects"] == []


def test_the_ticket_comment_is_skipped_when_not_enabled(tmp_path, monkeypatch):
    posted = []
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    monkeypatch.setattr("jira_report.post_result",
                        lambda *a, **kw: posted.append(a) or True)
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    assert posted == []
