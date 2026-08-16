"""Thin wrapper around the gh CLI. gh must already be authenticated (gh auth login)."""
import json as _json
import subprocess


def _run_gh_impl(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def run_gh(args: list[str], *, json: bool = True) -> dict | list:
    proc = _run_gh_impl(args + (["--jq", "."] if json else []))
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
