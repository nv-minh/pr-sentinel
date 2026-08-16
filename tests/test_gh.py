import json

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
