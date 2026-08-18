"""Thin wrapper around the gh CLI.

gh authenticates itself (`gh auth login`, or `GH_TOKEN` in CI) unless the
dashboard has been given a GitHub account — see `github_accounts.py`. When it
has, every call made through here runs as that account, which is what makes one
switch in the UI reach the whole pipeline: snapshots, sibling scans, posted
comments and check runs alike.
"""
import base64
import json as _json
import os
import subprocess


def _gh_env(token: str | None) -> dict | None:
    """Environment for the gh subprocess, or None to inherit this process's.

    None is the no-account path and keeps today's behaviour exactly: gh falls
    back to its keyring login locally and to the workflow's GH_TOKEN in CI.
    """
    import github_accounts  # imported late: github_accounts calls run_gh

    with github_accounts.LOCK:  # os.environ must not grow mid-copy
        if token is None:
            token = github_accounts.active_token()
        token = (token or "").strip()
        if not token:
            return None
        # Both names: gh reads GH_TOKEN first, and overwriting GITHUB_TOKEN stops
        # an inherited one from winning inside GitHub Actions.
        return {**os.environ, "GH_TOKEN": token, "GITHUB_TOKEN": token}


def _run_gh_impl(args: list[str], stdin: str | None = None,
                 env: dict | None = None) -> subprocess.CompletedProcess:
    kwargs = {"capture_output": True, "text": True, "input": stdin}
    if env is not None:
        # subprocess.run(env=None) already inherits this process's environment;
        # the kwarg is left off entirely so the no-account call is byte-for-byte
        # the call this module made before accounts existed.
        kwargs["env"] = env
    return subprocess.run(["gh", *args], **kwargs)


def run_gh(args: list[str], *, json: bool = True, stdin: str | None = None,
           token: str | None = None) -> dict | list:
    """Run one gh command. `token` overrides the active account, for verifying
    a token that has not been stored yet."""
    proc = _run_gh_impl(args + (["--jq", "."] if json else []), stdin,
                        _gh_env(token))
    if proc.returncode != 0:
        raise RuntimeError(f"gh api failed: {proc.stderr.strip()}")
    if not json:
        return proc.stdout
    try:
        return _json.loads(proc.stdout)
    except _json.JSONDecodeError as e:
        raise RuntimeError(
            f"gh api returned invalid JSON: {e}. stdout={proc.stdout[:200]!r}"
        ) from e


def gh_available() -> bool:
    try:
        proc = _run_gh_impl(["--version"])
        return proc.returncode == 0
    except FileNotFoundError:
        return False


def add_labels(owner: str, repo: str, n: int, labels: list[str], *, gh=run_gh) -> None:
    """Add labels to a PR, creating them on the fly. Never fails the review."""
    if not labels:
        return
    args = ["api", f"repos/{owner}/{repo}/issues/{n}/labels"]
    for label in labels:
        args += ["-f", f"labels[]={label}"]
    try:
        gh(args)
    except RuntimeError as e:
        print(f"[gh] could not add labels {labels}: {e}")


def post_inline_comment(owner: str, repo: str, n: int, *, commit_id: str, path: str,
                        line: int, body: str, gh=run_gh) -> bool:
    """Post one review comment anchored to a line of the diff.

    Returns False when GitHub rejects the anchor (the line is not part of the
    diff) — the caller then falls back to the summary comment.
    """
    try:
        gh(["api", f"repos/{owner}/{repo}/pulls/{n}/comments",
            "-f", f"commit_id={commit_id}", "-f", f"path={path}",
            "-F", f"line={line}", "-f", "side=RIGHT", "-f", f"body={body}"])
        return True
    except RuntimeError as e:
        print(f"[gh] inline comment on {path}:{line} rejected: {e}")
        return False


def list_inline_comments(owner: str, repo: str, n: int, *, gh=run_gh) -> list:
    return gh(["api", f"repos/{owner}/{repo}/pulls/{n}/comments", "--paginate"])


def edit_pr_body(owner: str, repo: str, n: int, body: str, *, gh=run_gh) -> None:
    gh(["api", f"repos/{owner}/{repo}/pulls/{n}", "-X", "PATCH", "-f", f"body={body}"])


def create_check_run(owner: str, repo: str, head_sha: str, *, name: str,
                     conclusion: str, title: str, summary: str, gh=run_gh) -> None:
    """Publish a check run for the gate. Requires a token with checks:write."""
    try:
        gh(["api", f"repos/{owner}/{repo}/check-runs",
            "-f", f"name={name}", "-f", f"head_sha={head_sha}",
            "-f", "status=completed", "-f", f"conclusion={conclusion}",
            "-f", f"output[title]={title}", "-f", f"output[summary]={summary}"])
    except RuntimeError as e:
        print(f"[gh] could not create check run: {e}")


def post_review(owner: str, repo: str, n: int, *, commit_id: str,
                comments: list[dict], body: str = "", gh=run_gh) -> bool:
    """Post every inline comment as ONE review event.

    N separate comment calls produce N notifications; a reviewer who gets pinged
    twelve times for one review learns to mute the bot. The event is COMMENT
    rather than REQUEST_CHANGES — the gate already blocks the merge through a
    check run, and a bot that also formally requests changes fights branch
    protection instead of informing it.

    Returns False when GitHub rejects the batch, so the caller can fall back to
    the summary comment.
    """
    if not comments:
        return False
    payload = {
        "commit_id": commit_id,
        "event": "COMMENT",
        "body": body,
        "comments": [{"path": c["path"], "line": c["line"], "side": "RIGHT",
                      "body": c["body"]} for c in comments],
    }
    try:
        gh(["api", f"repos/{owner}/{repo}/pulls/{n}/reviews", "-X", "POST",
            "--input", "-"], stdin=_json.dumps(payload))
        return True
    except RuntimeError as e:
        print(f"[gh] review batch rejected ({len(comments)} comment(s)): {e}")
        return False


def git_env(env: dict | None = None) -> dict | None:
    """Environment for a git subprocess, or None to inherit this process's.

    The REST and GraphQL calls go through `gh`, but the review also *clones* the
    pull request, and git does not read GH_TOKEN. Without this, a connected work
    account could list an org's private repos and then fail to clone one,
    because git fell back to the machine's own credential helper.

    The credential is passed as an HTTP header through GIT_CONFIG_* rather than
    `-c` or a token-in-URL: `-c` puts it in argv where `ps` can read it, and a
    URL credential is written into the clone's .git/config and survives on disk.
    Scoping the key to github.com leaves a clone from anywhere else untouched.
    """
    import github_accounts

    with github_accounts.LOCK:
        token = github_accounts.active_token(env)
        if not token:
            return None
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        return {**os.environ,
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.https://github.com/.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}"}
