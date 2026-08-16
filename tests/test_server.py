import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autoreview_config import load_config
from web.server import app

SNAPSHOT = {"pr": 77, "title": "Google sign-in", "author": "dev1", "base": "main",
            "head": "x", "files": [], "commits": [], "threads": [],
            "pruned": [{"filename": "yarn.lock", "reason": "lockfile", "dropped": True}]}

FINDINGS = {
    "claims": [{"id": "C1", "status": "PASS", "evidence": ["a.dart:1"], "note": ""}],
    "docs": [{"path": "docs/PLAN.md", "status": "WRONG", "what": "doc is wrong"}],
    "impact": [{"requirement": "Auth", "impact": "CHANGED", "detail": "d"}],
    "callers_outside_diff": [{"symbol": "signIn()", "defined_at": "a.dart:3",
                              "callers": ["b.dart:9"], "risk": "NEEDS_UPDATE",
                              "note": ""}],
    "contracts": [{"kind": "API", "path": "openapi.yml",
                   "status": "BREAKING_API_CHANGE", "detail": "removed field"}],
    "tests": [{"target": "auth:sign_in", "assertion_quality": "WEAK",
               "uncovered_edge_cases": [{"case": "expired token", "where": "auth:sign_in"}],
               "note": ""}],
    "threads": [{"text": "check validation", "status": "STILL_VALID", "note": ""}],
    "unresolved_questions": ["Doc PLAN wrong?"],
}

SCORE = {"verification_score": 1.0, "doc_drift": ["docs/PLAN.md"],
         "business_risk": "high", "test_gaps": ["auth:sign_in"], "gate": "fail",
         "labels": ["breaking-change"], "reasons": ["BREAKING_API_CHANGE in openapi.yml"]}


def _write_session(root, owner, repo, pr):
    d = root / owner / repo / f"pr-{pr}"
    d.mkdir(parents=True, exist_ok=True)
    (d / "snapshot.json").write_text(json.dumps(SNAPSHOT))
    (d / "findings.json").write_text(json.dumps(FINDINGS))
    (d / "score.json").write_text(json.dumps(SCORE))
    (d / "usage.json").write_text(json.dumps([{"phase": "verify", "cost_usd": 0.42}]))
    (d / "answers.json").write_text(json.dumps(
        [{"question": "Doc PLAN wrong?", "kind": "doc", "answer": "SKIPPED"}]))
    return d


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path))
    _write_session(tmp_path, "sample-org", "sample-app", 77)
    return TestClient(app)


def _config(tmp_path, monkeypatch, body="org: sample-org\nrepos:\n  sample-app: auto\n"):
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text(body)
    monkeypatch.setenv("PRSENTINEL_CONFIG", str(cfg_path))
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    return cfg_path


# ----------------------------------------------------------------------- data API

def test_api_repos_lists_reviewed_repos(client):
    data = client.get("/api/repos").json()
    assert data["repos"][0]["repo"] == "sample-app"
    assert data["repos"][0]["prs_total"] == 1
    assert data["repos"][0]["cost_total"] == 0.42
    assert data["repos"][0]["breaking_total"] == 1


def test_api_repos_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path))
    monkeypatch.setenv("PRSENTINEL_CONFIG", str(tmp_path / "none.yml"))
    assert TestClient(app).get("/api/repos").json() == {"repos": []}


def test_api_repos_includes_auto_repos_without_data(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch)
    repos = TestClient(app).get("/api/repos").json()["repos"]
    assert repos == [{"owner": "sample-org", "repo": "sample-app", "prs_total": 0,
                      "bugs_total": 0, "doc_errors_total": 0, "breaking_total": 0,
                      "test_gaps_total": 0, "cost_total": 0.0, "has_data": False,
                      "mode": "auto"}]


def test_api_repo_merges_open_prs(client, monkeypatch):
    monkeypatch.setattr("gh.run_gh", lambda args, **kw: [
        {"number": 78, "title": "chore: update deps", "draft": False},
        {"number": 77, "title": "Google sign-in", "draft": False}])
    data = client.get("/api/repos/sample-org/sample-app").json()
    by_pr = {row["pr"]: row for row in data["open_prs"]}
    assert by_pr[78]["status"] == "not_reviewed"
    assert by_pr[77]["status"] == "reviewed"
    assert data["gate_count"]["fail"] == 1
    assert data["open_questions"] == 1


def test_api_repo_survives_github_failure(client, monkeypatch):
    def boom(args, **kw):
        raise RuntimeError("rate limited")

    monkeypatch.setattr("gh.run_gh", boom)
    data = client.get("/api/repos/sample-org/sample-app").json()
    assert data["open_prs"][0]["unavailable"] is True


def test_api_repo_unknown_is_empty_not_404(client, monkeypatch):
    monkeypatch.setattr("gh.run_gh", lambda args, **kw: [])
    data = client.get("/api/repos/sample-org/nope").json()
    assert data["prs_total"] == 0
    assert data["prs"] == []


def test_api_pr_returns_every_section(client):
    data = client.get("/api/repos/sample-org/sample-app/pr/77").json()
    assert data["reviewed"] is True
    assert data["claims"][0]["id"] == "C1"
    assert data["callers"][0]["symbol"] == "signIn()"
    assert data["contracts"][0]["status"] == "BREAKING_API_CHANGE"
    assert data["tests"][0]["assertion_quality"] == "WEAK"
    assert data["pruned"][0]["filename"] == "yarn.lock"
    assert data["score"]["gate"] == "fail"
    assert data["pr"]["cost_usd"] == 0.42


def test_api_pr_not_reviewed_placeholder(client, monkeypatch):
    monkeypatch.setattr("gh.run_gh", lambda args, **kw: {
        "number": 78, "title": "chore: update deps", "user": {"login": "bot"},
        "base": {"ref": "main"}, "head": {"ref": "renovate"}})
    data = client.get("/api/repos/sample-org/sample-app/pr/78").json()
    assert data["reviewed"] is False
    assert data["pr"]["title"] == "chore: update deps"


def test_api_pr_unknown_404(client, monkeypatch):
    def boom(args, **kw):
        raise RuntimeError("not found")

    monkeypatch.setattr("gh.run_gh", boom)
    assert client.get("/api/repos/sample-org/sample-app/pr/999").status_code == 404


def test_api_report(client, tmp_path):
    (tmp_path / "sample-org" / "sample-app" / "pr-77" / "report.md").write_text("# hi")
    assert client.get("/api/repos/sample-org/sample-app/pr/77/report").json() == {
        "markdown": "# hi"}


def test_api_report_missing(client):
    assert client.get("/api/repos/sample-org/sample-app/pr/77/report").status_code == 404


# ------------------------------------------------------------------------- config

def test_api_config_and_toggle(tmp_path, monkeypatch):
    cfg_path = _config(tmp_path, monkeypatch)
    monkeypatch.setattr("gh.run_gh",
                        lambda args, **kw: [{"name": "sample-app"}, {"name": "admin-web"}])
    client = TestClient(app)

    data = client.get("/api/config").json()
    assert data["org"] == "sample-org"
    assert data["gate"]["verification_score_min"] == 0.8
    by_name = {x["name"]: x["mode"] for x in data["repos"]}
    assert by_name == {"sample-app": "auto", "admin-web": "unlisted"}

    assert client.post("/api/config/repos/sample-app/mode",
                       json={"mode": "manual"}).status_code == 200
    assert load_config(cfg_path)["repos"]["sample-app"] == "manual"

    assert client.post("/api/config/repos", json={"repo": "payments"}).status_code == 200
    assert load_config(cfg_path)["repos"]["payments"] == "auto"

    assert client.delete("/api/config/repos/payments").status_code == 200
    assert "payments" not in load_config(cfg_path)["repos"]


def test_api_add_repo_without_org_rejects_bare_name(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, "repos:\n  sample-app: auto\n")
    r = TestClient(app).post("/api/config/repos", json={"repo": "payments"})
    assert r.status_code == 400
    assert "org" in r.json()["detail"]


def test_api_toggle_bad_mode_400(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch)
    assert TestClient(app).post("/api/config/repos/sample-app/mode",
                                json={"mode": "x"}).status_code == 400


def test_api_config_missing_file_404(tmp_path, monkeypatch):
    monkeypatch.setenv("PRSENTINEL_CONFIG", str(tmp_path / "none.yml"))
    assert TestClient(app).get("/api/config").status_code == 404


# ------------------------------------------------------------------------- review

@pytest.fixture
def inline_jobs(monkeypatch):
    """Run the background review job synchronously so tests can assert on it."""
    monkeypatch.setattr("web.server._spawn", lambda target: target())


def test_trigger_review_starts_job(tmp_path, monkeypatch, inline_jobs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr("web.server.run_main", lambda argv: calls.append(argv) or 0)

    r = TestClient(app).post("/api/repos/sample-org/sample-app/pr/78/review")
    assert r.status_code == 202
    assert r.json()["status"] == "started"
    args = calls[0]
    assert "sample-org/sample-app" in args and "78" in args
    assert "--force" in args
    assert "--skip-human" in args        # config default skip_human: true
    assert "--no-post" not in args       # config default post_comment: true


def test_trigger_review_reply_mode(tmp_path, monkeypatch, inline_jobs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr("web.server.run_main", lambda argv: calls.append(argv) or 0)

    TestClient(app).post("/api/repos/sample-org/sample-app/pr/78/review?reply=true")
    assert "--reply" in calls[0]
    assert "--force" not in calls[0]


def test_trigger_review_honours_config_flags(tmp_path, monkeypatch, inline_jobs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch,
            "org: sample-org\nrepos:\n  sample-app: auto\n"
            "post_comment: false\nskip_human: false\n")
    calls = []
    monkeypatch.setattr("web.server.run_main", lambda argv: calls.append(argv) or 0)

    TestClient(app).post("/api/repos/sample-org/sample-app/pr/78/review")
    assert "--no-post" in calls[0]
    assert "--skip-human" not in calls[0]


def test_trigger_review_records_failure_and_releases_lock(tmp_path, monkeypatch,
                                                          inline_jobs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch)
    monkeypatch.setattr("web.server.run_main", lambda argv: 2)
    client = TestClient(app)

    assert client.post("/api/repos/sample-org/sample-app/pr/78/review").status_code == 202
    status = client.get("/api/repos/sample-org/sample-app/pr/78/review/status").json()
    assert status["running"] is False
    assert status["last"]["exit"] == 2
    session = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78"
    assert not (session / "review.lock").exists()


def test_trigger_review_releases_lock_when_the_pipeline_crashes(tmp_path, monkeypatch,
                                                                inline_jobs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch)

    def boom(argv):
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr("web.server.run_main", boom)
    client = TestClient(app)
    client.post("/api/repos/sample-org/sample-app/pr/78/review")

    session = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78"
    assert not (session / "review.lock").exists()
    assert "pipeline exploded" in (session / "review.log").read_text()


def test_trigger_review_without_auth(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "no-cli.json")
    _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/repos/sample-org/sample-app/pr/78/review")
    assert r.status_code == 400
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


def test_trigger_review_concurrent_409(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch)
    lock = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78" / "review.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "started_at": "2026-08-16T10:00:00"}))

    r = TestClient(app).post("/api/repos/sample-org/sample-app/pr/78/review")
    assert r.status_code == 409
    assert "already running" in r.json()["detail"]


def test_trigger_review_replaces_a_stale_lock(tmp_path, monkeypatch, inline_jobs):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _config(tmp_path, monkeypatch)
    monkeypatch.setattr("web.server.run_main", lambda argv: 0)
    lock = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78" / "review.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": 999999, "started_at": "2026-08-16T10:00:00"}))

    assert TestClient(app).post(
        "/api/repos/sample-org/sample-app/pr/78/review").status_code == 202


def test_review_status_running(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    lock = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78" / "review.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": os.getpid(), "started_at": "2026-08-16T10:00:00"}))
    data = TestClient(app).get(
        "/api/repos/sample-org/sample-app/pr/78/review/status").json()
    assert data["running"] is True
    assert data["pid"] == os.getpid()


def test_review_status_stale(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    lock = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78" / "review.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"pid": 999999, "started_at": "2026-08-16T10:00:00"}))
    data = TestClient(app).get(
        "/api/repos/sample-org/sample-app/pr/78/review/status").json()
    assert data["running"] is False
    assert data["stale"] is True


def test_review_log_tail(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    session_dir = tmp_path / "sessions" / "sample-org" / "sample-app" / "pr-78"
    session_dir.mkdir(parents=True)
    (session_dir / "review.log").write_text("line1\nline2\nline3\n")
    data = TestClient(app).get(
        "/api/repos/sample-org/sample-app/pr/78/review/log?lines=2").json()
    assert data["log"] == "line2\nline3"
    assert data["running"] is False


def test_review_log_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    data = TestClient(app).get(
        "/api/repos/sample-org/sample-app/pr/78/review/log").json()
    assert data == {"log": "", "running": False}


# ---------------------------------------------------------------------------- SPA

def test_spa_reports_an_unbuilt_dashboard(client, tmp_path, monkeypatch):
    monkeypatch.setattr("web.server.UI_DIST", tmp_path / "not-built")
    r = client.get("/")
    assert r.status_code == 503
    assert "npm run build" in r.json()["detail"]


def test_spa_does_not_serve_a_sibling_of_dist(tmp_path, monkeypatch):
    """A path escaping UI_DIST must fall through to index.html, not the file."""
    from web.server import spa

    root = tmp_path / "ui"
    root.mkdir()
    (root / "index.html").write_text('<div id="root"></div>')
    sibling = tmp_path / "ui-extra"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("secret")

    monkeypatch.setattr("web.server.UI_DIST", root)
    resp = spa("../ui-extra/secret.txt")
    assert Path(resp.path).resolve() == (root / "index.html").resolve()


@pytest.mark.skipif(not (Path(__file__).resolve().parents[1] / "web/ui/dist/index.html").exists(),
                    reason="dashboard not built")
def test_spa_serves_client_routes(client):
    for path in ("/", "/config", "/repos/demo/app/pr/8"):
        r = client.get(path)
        assert r.status_code == 200
        assert "<div id=\"root\">" in r.text


# ------------------------------------------------------------------------ providers

def test_api_config_reports_the_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dsk-secret")
    _config(tmp_path, monkeypatch,
            "provider: deepseek\nrepos:\n  sample-app: auto\n")
    body = TestClient(app).get("/api/config").json()
    assert body["provider"]["name"] == "deepseek"
    assert body["provider"]["base_url"] == "https://api.deepseek.com/anthropic"
    assert body["provider"]["structured_output"] == "prompt"
    assert body["provider"]["token_present"] is True
    assert body["provider"]["token_env"] == "DEEPSEEK_API_KEY"
    assert "dsk-secret" not in TestClient(app).get("/api/config").text
    assert "deepseek" in body["providers"] and "anthropic" in body["providers"]


def test_api_config_flags_a_missing_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    _config(tmp_path, monkeypatch,
            "provider: deepseek\nrepos:\n  sample-app: auto\n")
    body = TestClient(app).get("/api/config").json()
    assert body["provider"]["token_present"] is False


def test_api_config_rejects_an_unknown_env_provider_as_400(tmp_path, monkeypatch):
    """PRS_PROVIDER bypasses providers.validate() (YAML-load time only) — the
    dashboard's Config page must get the usual 400, not a 500."""
    monkeypatch.setenv("PRS_PROVIDER", "typo")
    _config(tmp_path, monkeypatch)
    r = TestClient(app).get("/api/config")
    assert r.status_code == 400
    assert "not built in" in r.json()["detail"]


def test_trigger_review_rejects_an_unknown_env_provider_as_400(tmp_path, monkeypatch):
    """Same scenario as the /api/config case above, on the review-trigger
    endpoint: a typo'd PRS_PROVIDER must not turn into a 500 there either."""
    monkeypatch.setenv("PRS_PROVIDER", "typo")
    _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/repos/demo/app/pr/8/review")
    assert r.status_code == 400
    assert "not built in" in r.json()["detail"]


def test_switch_provider_writes_the_yaml(tmp_path, monkeypatch):
    monkeypatch.delenv("PRS_PROVIDER", raising=False)
    cfg_path = _config(tmp_path, monkeypatch)
    client = TestClient(app)
    assert client.post("/api/config/provider", json={"name": "glm"}).status_code == 200
    assert load_config(cfg_path)["provider"] == "glm"
    assert "token" not in cfg_path.read_text().lower()


def test_switch_provider_rejects_an_unknown_name(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/config/provider", json={"name": "nope"})
    assert r.status_code == 400
    assert "not built in" in r.json()["detail"]


def test_trigger_review_uses_the_provider_auth_rule(tmp_path, monkeypatch):
    monkeypatch.setattr("config.CLI_CONFIG", tmp_path / "no-cli.json")
    monkeypatch.setenv("PRS_PROVIDER", "glm")
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/repos/demo/app/pr/8/review")
    assert r.status_code == 400
    assert "ZAI_API_KEY" in r.json()["detail"]
