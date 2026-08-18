import json
from pathlib import Path

import pytest

from gh import gh_available, run_gh


def test_run_gh_json(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, input=None):
        captured["cmd"] = cmd
        assert text is True
        return type("R", (), {"returncode": 0, "stdout": json.dumps({"ok": 1}), "stderr": ""})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    out = run_gh(["api", "repos/x/y/pulls/1"])
    assert out == {"ok": 1}
    assert "gh" in captured["cmd"][0]


def test_run_gh_error(monkeypatch):
    def fake_run(cmd, capture_output, text, input=None):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "not found"})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="gh api failed: not found"):
        run_gh(["api", "repos/x/y/pulls/1"])


def test_run_gh_invalid_json(monkeypatch):
    def fake_run(cmd, capture_output, text, input=None):
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        run_gh(["api", "repos/x/y"])


def test_gh_available(monkeypatch):
    def fake_run(cmd, capture_output, text, input=None):
        return type("R", (), {"returncode": 0, "stdout": "1\n", "stderr": ""})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    assert gh_available() is True


import json as _json

from gh import post_review


def test_post_review_sends_one_batched_request():
    seen = {}

    def fake(args, **kw):
        seen["args"] = args
        seen["stdin"] = kw.get("stdin")
        return {"id": 1}

    ok = post_review("o", "r", 7, commit_id="sha1",
                     comments=[{"path": "a.py", "line": 2, "body": "x"}],
                     body="summary", gh=fake)
    assert ok is True
    assert "repos/o/r/pulls/7/reviews" in " ".join(seen["args"])
    payload = _json.loads(seen["stdin"])
    assert payload["commit_id"] == "sha1"
    assert payload["event"] == "COMMENT"
    assert payload["body"] == "summary"
    assert payload["comments"] == [{"path": "a.py", "line": 2, "side": "RIGHT",
                                    "body": "x"}]


def test_post_review_does_nothing_without_comments():
    def fail(*a, **kw):
        raise AssertionError("must not call the API with an empty batch")

    assert post_review("o", "r", 7, commit_id="s", comments=[], gh=fail) is False


def test_post_review_returns_false_when_github_rejects_it(capsys):
    def fake(args, **kw):
        raise RuntimeError("422 Unprocessable Entity")

    assert post_review("o", "r", 7, commit_id="s",
                       comments=[{"path": "a.py", "line": 2, "body": "x"}],
                       gh=fake) is False
    assert "review batch rejected" in capsys.readouterr().out


def test_run_gh_passes_stdin_to_the_subprocess(monkeypatch):
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(argv, **kw):
        seen.update(kw)
        return _Proc()

    monkeypatch.setattr("subprocess.run", fake_run)
    from gh import run_gh
    run_gh(["api", "x"], stdin='{"a": 1}')
    assert seen["input"] == '{"a": 1}'


# ------------------------------------------------------- the active GitHub account

class _Ok:
    returncode = 0
    stdout = "{}"
    stderr = ""


def _capture(monkeypatch):
    seen = {}

    def fake_run(argv, **kw):
        seen.update(kw)
        return _Ok()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    return seen


def test_no_configured_account_leaves_the_environment_alone(monkeypatch):
    """gh keeps falling back to its keyring login, and to GH_TOKEN in CI."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr("github_accounts.active_token", lambda: "")
    run_gh(["api", "user"])
    assert "env" not in seen


def test_the_active_account_token_reaches_the_subprocess(monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setattr("github_accounts.active_token", lambda: "ghp_active")
    run_gh(["api", "user"])
    assert seen["env"]["GH_TOKEN"] == "ghp_active"
    assert seen["env"]["GITHUB_TOKEN"] == "ghp_active"
    assert "PATH" in seen["env"]  # the rest of the environment is still there


def test_an_explicit_token_overrides_the_active_account(monkeypatch):
    """How a token is verified before it is stored."""
    seen = _capture(monkeypatch)
    monkeypatch.setattr("github_accounts.active_token", lambda: "ghp_active")
    run_gh(["api", "user"], token="ghp_candidate")
    assert seen["env"]["GH_TOKEN"] == "ghp_candidate"


# --------------------------------------------------------------- git credentials

def test_no_account_means_git_runs_exactly_as_before(monkeypatch):
    from gh import git_env
    monkeypatch.setattr("github_accounts.active_token", lambda env=None: "")
    assert git_env() is None


def test_git_gets_the_account_credential_as_a_header(monkeypatch):
    """The clone must reach a private repo as the connected account, not as
    whatever the machine's own credential helper offers."""
    import base64

    from gh import git_env
    monkeypatch.setattr("github_accounts.active_token", lambda env=None: "ghp_active")
    env = git_env()

    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    scheme, _, value = env["GIT_CONFIG_VALUE_0"].partition(" Basic ")
    assert scheme == "Authorization:"
    assert base64.b64decode(value).decode() == "x-access-token:ghp_active"
    assert "PATH" in env


def test_the_git_credential_is_never_in_argv(monkeypatch):
    """`-c http.extraHeader=...` would put the token where `ps` can read it."""
    import verify

    seen = {}

    class _Ok:
        returncode = 0
        stderr = ""

    def fake_run(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env")
        return _Ok()

    monkeypatch.setattr("github_accounts.active_token", lambda env=None: "ghp_active")
    monkeypatch.setattr("verify.subprocess.run", fake_run)
    verify._run_git(["clone", "https://github.com/o/r.git", "/tmp/x"], Path("/tmp"))

    assert "ghp_active" not in " ".join(seen["argv"])
    assert "ghp_active" not in seen["env"]["GIT_CONFIG_VALUE_0"]  # base64, not raw
    assert seen["env"]["GIT_CONFIG_COUNT"] == "1"


def test_git_env_is_absent_when_no_account_is_connected(monkeypatch):
    import verify

    seen = {}

    class _Ok:
        returncode = 0
        stderr = ""

    def fake_run(argv, **kw):
        seen.update(kw)
        return _Ok()

    monkeypatch.setattr("github_accounts.active_token", lambda env=None: "")
    monkeypatch.setattr("verify.subprocess.run", fake_run)
    verify._run_git(["fetch"], Path("/tmp"))
    assert "env" not in seen
