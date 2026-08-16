import json

import pytest

from gh import gh_available, run_gh


def test_run_gh_json(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        assert text is True
        return type("R", (), {"returncode": 0, "stdout": json.dumps({"ok": 1}), "stderr": ""})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    out = run_gh(["api", "repos/x/y/pulls/1"])
    assert out == {"ok": 1}
    assert "gh" in captured["cmd"][0]


def test_run_gh_error(monkeypatch):
    def fake_run(cmd, capture_output, text):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "not found"})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="gh api failed: not found"):
        run_gh(["api", "repos/x/y/pulls/1"])


def test_run_gh_invalid_json(monkeypatch):
    def fake_run(cmd, capture_output, text):
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    with pytest.raises(RuntimeError, match="invalid JSON"):
        run_gh(["api", "repos/x/y"])


def test_gh_available(monkeypatch):
    def fake_run(cmd, capture_output, text):
        return type("R", (), {"returncode": 0, "stdout": "1\n", "stderr": ""})()

    monkeypatch.setattr("gh.subprocess.run", fake_run)
    assert gh_available() is True
