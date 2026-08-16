"""Local poller: auto-review new PRs / re-review PRs with changed head SHA.

Modes:
  --once      single pass (cron/launchd)
  --daemon    loop with interval_minutes
  --dry-run   print planned reviews without dispatching
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import providers
from autoreview_config import auto_repos, list_repos, load_config, \
    remove_repo, set_repo_mode
from config import load_config as load_env_config
from gh import gh_available, run_gh

CONFIG_PATH = Path("prsentinel.yml")
LOCK_PATH = Path("prsentinel.lock")


def _epoch(timestamp: str) -> float:
    """GitHub ISO-8601 → epoch seconds, 0.0 when unparseable."""
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()
    except (AttributeError, ValueError):
        return 0.0


def decide_pr(session_root: Path, owner: str, repo: str, n: int,
              head_sha: str, updated_at: str = "") -> str:
    """Return NEW / RE-RUN / REPLY / SKIP for one PR.

    REPLY means the code is unchanged but the PR has been touched since the
    review was posted — someone probably answered the bot, which is handled by a
    cheap resumed follow-up instead of a full re-review.
    """
    session_dir = session_root / owner / repo / f"pr-{n}"
    snapshot_path = session_dir / "snapshot.json"
    if not snapshot_path.exists():
        return "NEW"
    try:
        snapshot = json.loads(snapshot_path.read_text())
    except (json.JSONDecodeError, OSError):
        return "RE-RUN"  # snapshot hỏng → chạy lại cho an toàn
    old_sha = snapshot.get("head_sha", "")
    if old_sha and old_sha == head_sha:
        # head khớp nhưng snapshot mới hơn findings (re-review fail giữa chừng
        # sau khi fetch head mới) → review chưa hoàn thành → chạy lại
        findings_path = session_dir / "findings.json"
        report_path = session_dir / "report.md"
        try:
            if snapshot_path.stat().st_mtime > findings_path.stat().st_mtime:
                return "RE-RUN"
        except OSError:
            return "RE-RUN"  # thiếu findings → review dở dang
        try:
            if updated_at and _epoch(updated_at) > report_path.stat().st_mtime:
                return "REPLY"
        except OSError:
            pass
        return "SKIP"
    return "RE-RUN"


def plan_reviews(session_root: Path, owner: str, repo: str, prs: list[dict],
                 drafts: bool = False, skip_bots: bool = True) -> list[dict]:
    """Return [{pr, head_sha, decision}] for open PRs of one repo.

    Bot PRs (user.type == "Bot") are skipped by default — they are usually
    dependency bots (Renovate/Dependabot). Manual triggers bypass this.
    """
    plans = []
    for p in prs:
        if p.get("draft") and not drafts:
            continue
        if skip_bots and (p.get("user") or {}).get("type") == "Bot":
            print(f"SKIP-BOT {owner}/{repo}#{p['number']} "
                  f"({(p.get('user') or {}).get('login')})")
            continue
        n = p["number"]
        head_sha = (p.get("head") or {}).get("sha", "")
        decision = decide_pr(session_root, owner, repo, n, head_sha,
                             p.get("updated_at", ""))
        plans.append({"pr": n, "head_sha": head_sha, "decision": decision})
    return plans


def fetch_open_prs(owner: str, repo: str, gh=run_gh) -> list[dict]:
    """Open PRs of a repo via gh api (returns raw list items)."""
    return gh(["api", f"repos/{owner}/{repo}/pulls?state=open", "--paginate"])


def _acquire_lock() -> bool:
    # Lock cũ mà PID chết → dọn và giành lại
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip() or "0")
            if pid > 0:
                os.kill(pid, 0)  # alive → từ chối
            else:
                LOCK_PATH.unlink()
        except ProcessLookupError:
            LOCK_PATH.unlink()
        except FileNotFoundError:
            pass
        except (PermissionError, ValueError):
            return False
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock() -> None:
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def _clean_rerun_session(session_dir: Path) -> None:
    """Xóa kết quả phase cũ trước khi re-review (giữ snapshot)."""
    for name in ("findings.json", "answers.json", "report.md", "agent-log.txt"):
        (session_dir / name).unlink(missing_ok=True)


def _dispatch(cfg: dict, owner: str, repo: str, n: int,
              head_sha: str, decision: str = "NEW") -> int:
    """Chạy pipeline cho 1 PR. Trả về exit code."""
    from run import main

    args = [f"{owner}/{repo}", str(n)]
    args.append("--reply" if decision == "REPLY" else "--force")
    if cfg.get("skip_human", True):
        args.append("--skip-human")
    if not cfg.get("post_comment", True):
        args.append("--no-post")
    return main(args)


def run_pass(cfg: dict, session_root: Path, dry_run: bool = False,
             gh=run_gh) -> int:
    """One poll pass over all auto repos. Returns count of dispatched."""
    dispatched = 0
    for owner, repo in auto_repos(cfg):
        try:
            prs = fetch_open_prs(owner, repo, gh=gh)
        except RuntimeError as e:
            print(f"POLL-ERROR {owner}/{repo}: {e}", file=sys.stderr)
            continue
        plans = plan_reviews(session_root, owner, repo, prs,
                             drafts=cfg.get("drafts", False),
                             skip_bots=cfg.get("skip_bots", True))
        for plan in plans:
            n = plan["pr"]
            line = f"{plan['decision']} {owner}/{repo}#{n}"
            if plan["decision"] == "SKIP":
                print(line)
                continue
            if dry_run:
                print(f"[dry-run] would review: {line}")
                dispatched += 1
                continue
            session_dir = session_root / owner / repo / f"pr-{n}"
            if (session_dir / "review.lock").exists():
                print(f"SKIP {owner}/{repo}#{n}: manual review running")
                continue
            if plan["decision"] == "RE-RUN":
                _clean_rerun_session(session_dir)
            print(line)
            try:
                code = _dispatch(cfg, owner, repo, n, plan["head_sha"],
                                 plan["decision"])
            except (RuntimeError, ValueError, OSError) as e:
                print(f"FAILED {owner}/{repo}#{n}: {e}", file=sys.stderr)
                continue
            if code != 0:
                print(f"FAILED {owner}/{repo}#{n}: exit {code}", file=sys.stderr)
                continue
            dispatched += 1
    return dispatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autoreview")
    parser.add_argument("--once", action="store_true", help="single pass")
    parser.add_argument("--daemon", action="store_true", help="loop forever")
    parser.add_argument("--dry-run", action="store_true",
                        help="print plans without dispatching")
    parser.add_argument("--config", type=Path, default=CONFIG_PATH,
                        help="path to prsentinel.yml")
    parser.add_argument("--add-repo", metavar="REPO",
                        help="add repo (name or owner/name) and set its mode")
    parser.add_argument("--rm-repo", metavar="REPO", help="remove a repo")
    parser.add_argument("--mode", choices=["auto", "manual"], default="auto",
                        help="mode for --add-repo (default: auto)")
    parser.add_argument("--repos", action="store_true",
                        help="list configured + org repos with modes")
    args = parser.parse_args(argv)

    if args.add_repo:
        set_repo_mode(args.config, args.add_repo, args.mode)
        print(f"{args.add_repo} -> {args.mode}")
        return 0
    if args.rm_repo:
        remove_repo(args.config, args.rm_repo)
        print(f"removed {args.rm_repo}")
        return 0
    if args.repos:
        for r in list_repos(args.config):
            print(f"{r['name']:<40} {r['mode']}")
        return 0

    cfg = load_config(args.config)
    env = load_env_config()
    provider = providers.resolve(cfg)
    if not providers.has_auth(provider):
        print(providers.auth_hint(provider), file=sys.stderr)
        return 3
    if not gh_available():
        print("gh CLI not installed or not authenticated (gh auth login)",
              file=sys.stderr)
        return 2

    session_root = env.session_root
    while True:
        if not _acquire_lock():
            print("another autoreview process is running — exiting",
                  file=sys.stderr)
            return 1
        try:
            run_pass(cfg, session_root, dry_run=args.dry_run)
        finally:
            _release_lock()
        if args.once or args.dry_run:
            return 0
        time.sleep(cfg["interval_minutes"] * 60)


if __name__ == "__main__":
    sys.exit(main())
