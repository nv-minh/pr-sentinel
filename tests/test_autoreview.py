# tests/test_autoreview.py
import json
import os

from autoreview import (_acquire_lock, _release_lock, decide_pr, main,
                                   plan_reviews, run_pass)
from autoreview_config import load_config

EMPTY_FINDINGS = {"claims": [], "docs": [], "impact": [], "threads": [],
                  "unresolved_questions": []}

SNAPSHOT = {"pr": 7, "title": "T", "author": "a", "base": "main", "head": "x",
            "head_sha": "abc", "files": [], "commits": [], "threads": []}


def _write_session(root, owner, repo, n, snapshot=None):
    d = root / owner / repo / f"pr-{n}"
    d.mkdir(parents=True, exist_ok=True)
    if snapshot is not None:
        (d / "snapshot.json").write_text(json.dumps(snapshot))
    (d / "findings.json").write_text(json.dumps(EMPTY_FINDINGS))


def test_decide_pr_new(tmp_path):
    root = tmp_path / "sessions"
    _write_session(root, "o", "r", 5)
    d = root / "o" / "r" / "pr-5"
    (d / "snapshot.json").write_text(json.dumps(SNAPSHOT))
    # viết findings SAU snapshot → findings mới hơn → review hoàn chỉnh → SKIP
    (d / "findings.json").write_text(json.dumps(EMPTY_FINDINGS))
    assert decide_pr(root, "o", "r", 5, "abc") == "SKIP"
    assert decide_pr(root, "o", "r", 6, "def") == "NEW"


def test_decide_pr_head_changed(tmp_path):
    root = tmp_path / "sessions"
    _write_session(root, "o", "r", 5, snapshot=SNAPSHOT)  # head_sha=abc
    assert decide_pr(root, "o", "r", 5, "xyz") == "RE-RUN"


def test_decide_pr_old_snapshot_no_sha(tmp_path):
    # snapshot cũ không có head_sha → coi như chưa review
    root = tmp_path / "sessions"
    old = {k: v for k, v in SNAPSHOT.items() if k != "head_sha"}
    _write_session(root, "o", "r", 5, snapshot=old)
    assert decide_pr(root, "o", "r", 5, "xyz") == "RE-RUN"


def test_decide_pr_missing_snapshot_new(tmp_path):
    root = tmp_path / "sessions"
    _write_session(root, "o", "r", 5)  # findings.json rỗng, snapshot.json không tồn tại
    assert decide_pr(root, "o", "r", 5, "xyz") == "NEW"


def test_plan_reviews_skips_drafts(tmp_path):
    root = tmp_path / "sessions"
    prs = [
        {"number": 1, "head": {"sha": "a"}, "draft": True},
        {"number": 2, "head": {"sha": "b"}, "draft": False},
    ]
    plans = plan_reviews(root, "o", "r", prs, drafts=False)
    assert plans == [{"pr": 2, "head_sha": "b", "decision": "NEW"}]


def test_plan_reviews_statuses(tmp_path):
    root = tmp_path / "sessions"
    # pr-1 đã review với head_sha=a; pr-3 đã review với head_sha=old
    _write_session(root, "o", "r", 1, snapshot={**SNAPSHOT, "pr": 1,
                                                "head_sha": "a"})
    _write_session(root, "o", "r", 3, snapshot={**SNAPSHOT, "pr": 3,
                                                "head_sha": "old"})
    prs = [
        {"number": 1, "head": {"sha": "a"}, "draft": False},   # SKIP
        {"number": 2, "head": {"sha": "c"}, "draft": False},   # NEW
        {"number": 3, "head": {"sha": "b"}, "draft": False},   # RE-RUN
    ]
    plans = plan_reviews(root, "o", "r", prs, drafts=False)
    assert plans == [
        {"pr": 1, "head_sha": "a", "decision": "SKIP"},
        {"pr": 2, "head_sha": "c", "decision": "NEW"},
        {"pr": 3, "head_sha": "b", "decision": "RE-RUN"},
    ]


def test_run_pass_skips_manual(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    root.mkdir(parents=True)
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text(
        "org: sample-org\nrepos:\n  sample-app: manual\n  sample-api: auto\n")
    cfg = load_config(cfg_path)

    prs_by_repo = {
        "sample-org/sample-api": [{"number": 1, "head": {"sha": "a"},
                                     "draft": False}],
    }

    def fake_gh(args, **kw):
        repo_ref = args[1].split("?")[0].split("repos/")[1].removesuffix("/pulls")
        return prs_by_repo[repo_ref]

    dispatched = []
    monkeypatch.setattr("autoreview._dispatch",
                        lambda c, o, r, n, sha, decision="NEW": (dispatched.append((o, r, n)) or 0))
    count = run_pass(cfg, root, dry_run=False, gh=fake_gh)
    assert count == 1
    assert dispatched == [("sample-org", "sample-api", 1)]


def test_main_add_repo_writes_config(tmp_path, monkeypatch):
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text("org: sample-org\nrepos:\n  sample-app: manual\n")
    monkeypatch.setattr("autoreview.CONFIG_PATH", cfg_path)
    code = main(["--add-repo", "admin-web", "--mode", "auto"])
    assert code == 0
    cfg = load_config(cfg_path)
    assert cfg["repos"]["admin-web"] == "auto"
    assert cfg["repos"]["sample-app"] == "manual"


def test_main_rm_repo(tmp_path, monkeypatch):
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text("org: sample-org\nrepos:\n  sample-app: auto\n")
    monkeypatch.setattr("autoreview.CONFIG_PATH", cfg_path)
    code = main(["--rm-repo", "sample-app"])
    assert code == 0
    assert load_config(cfg_path)["repos"] == {}


def test_main_repos_lists_status(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text("repos:\n  sample-app: auto\n")
    monkeypatch.setattr("autoreview.CONFIG_PATH", cfg_path)
    code = main(["--repos"])
    assert code == 0
    out = capsys.readouterr().out
    assert "sample-app" in out and "auto" in out


def test_main_refuses_a_provider_without_a_token(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text("provider: deepseek\n")
    monkeypatch.setattr("autoreview.CONFIG_PATH", cfg_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path / "sessions"))
    assert main([]) == 3
    assert "DEEPSEEK_API_KEY" in capsys.readouterr().err


def test_run_pass_skips_manual_review_lock(tmp_path, monkeypatch, capsys):
    root = tmp_path / "sessions"
    root.mkdir(parents=True)
    cfg_path = tmp_path / "prsentinel.yml"
    cfg_path.write_text("org: sample-org\nrepos:\n  sample-api: auto\n")
    cfg = load_config(cfg_path)
    lock = root / "sample-org" / "sample-api" / "pr-1" / "review.lock"
    lock.parent.mkdir(parents=True)
    lock.touch()

    dispatched = []
    monkeypatch.setattr("autoreview._dispatch",
                        lambda c, o, r, n, sha, decision="NEW": (dispatched.append((o, r, n)) or 0))
    count = run_pass(cfg, root, dry_run=False,
                     gh=lambda args, **kw: [{"number": 1, "head": {"sha": "a"},
                                             "draft": False}])
    assert count == 0
    assert dispatched == []
    assert "manual review running" in capsys.readouterr().out


def test_plan_reviews_skips_bots(tmp_path, capsys):
    root = tmp_path / "sessions"
    prs = [
        {"number": 1, "head": {"sha": "a"}, "draft": False,
         "user": {"login": "renovate[bot]", "type": "Bot"}},
        {"number": 2, "head": {"sha": "b"}, "draft": False,
         "user": {"login": "dev1", "type": "User"}},
    ]
    plans = plan_reviews(root, "o", "r", prs)
    assert [p["pr"] for p in plans] == [2]
    assert "SKIP-BOT" in capsys.readouterr().out


def test_plan_reviews_bots_when_disabled(tmp_path):
    root = tmp_path / "sessions"
    prs = [
        {"number": 1, "head": {"sha": "a"}, "draft": False,
         "user": {"login": "renovate[bot]", "type": "Bot"}},
    ]
    plans = plan_reviews(root, "o", "r", prs, skip_bots=False)
    assert [p["pr"] for p in plans] == [1]


def test_acquire_lock_stale_pid(tmp_path, monkeypatch):
    monkeypatch.setattr("autoreview.LOCK_PATH", tmp_path / "autoreview.lock")
    (tmp_path / "autoreview.lock").write_text("999999")  # PID chết
    assert _acquire_lock() is True
    _release_lock()


def test_acquire_lock_alive(tmp_path, monkeypatch):
    monkeypatch.setattr("autoreview.LOCK_PATH", tmp_path / "autoreview.lock")
    (tmp_path / "autoreview.lock").write_text(str(os.getpid()))  # PID sống
    assert _acquire_lock() is False


def test_decide_pr_incomplete_review(tmp_path):
    # head khớp nhưng snapshot mới hơn findings (re-review fail giữa chừng)
    root = tmp_path / "sessions"
    d = root / "o" / "r" / "pr-5"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text(json.dumps({**SNAPSHOT, "head_sha": "abc"}))
    (d / "findings.json").write_text(json.dumps(EMPTY_FINDINGS))
    import os
    os.utime(d / "snapshot.json", (1700000000, 1700000000))
    os.utime(d / "findings.json", (1699999000, 1699999000))  # cũ hơn
    assert decide_pr(root, "o", "r", 5, "abc") == "RE-RUN"


def test_decide_pr_complete_review_skips(tmp_path):
    root = tmp_path / "sessions"
    d = root / "o" / "r" / "pr-5"
    d.mkdir(parents=True)
    (d / "snapshot.json").write_text(json.dumps({**SNAPSHOT, "head_sha": "abc"}))
    (d / "findings.json").write_text(json.dumps(EMPTY_FINDINGS))
    import os
    os.utime(d / "snapshot.json", (1699999000, 1699999000))
    os.utime(d / "findings.json", (1700000000, 1700000000))  # mới hơn
    assert decide_pr(root, "o", "r", 5, "abc") == "SKIP"
