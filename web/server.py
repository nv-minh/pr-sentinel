"""FastAPI app: PR review dashboard + repo auto/manual config management."""
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from autoreview_config import load_config as load_autoreview_config
from autoreview_config import auto_repos, list_repos, remove_repo, set_repo_mode
from config import AUTH_HINT, load_config
from run import main as run_main
from web import metrics

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="PR Review Dashboard")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def _session_root() -> Path:
    return load_config().session_root


def _config_path() -> Path:
    return Path(os.environ.get("PRSENTINEL_CONFIG", "prsentinel.yml"))


@app.get("/", response_class=HTMLResponse)
def repo_list(request: Request):
    root = _session_root()
    repos = []
    for owner, repo in metrics.list_repos(root):
        rec = metrics.repo_record(root, owner, repo)
        if rec is not None:
            rec["has_data"] = True
            repos.append(rec)
    repos.sort(key=lambda r: r["prs_total"], reverse=True)

    # merge auto-configured repos that have no review data yet
    seen = {(r["owner"], r["repo"]) for r in repos}
    path = _config_path()
    if path.exists():
        try:
            cfg = load_autoreview_config(path)
            for owner, repo in auto_repos(cfg):
                if (owner, repo) not in seen:
                    repos.append({
                        "owner": owner, "repo": repo,
                        "prs_total": 0, "bugs_total": 0,
                        "doc_errors_total": 0, "has_data": False,
                        "mode": "auto",
                    })
        except (ValueError, OSError):
            pass

    return templates.TemplateResponse(
        request, "repo_list.html", {"repos": repos})


@app.get("/config", response_class=HTMLResponse)
def config_page(request: Request):
    cfg_state = None
    path = _config_path()
    if path.exists():
        try:
            cfg = load_autoreview_config(path)
            cfg_state = {
                "org": cfg.get("org"),
                "interval": cfg.get("interval_minutes"),
                "drafts": cfg.get("drafts"),
                "post_comment": cfg.get("post_comment"),
                "repos": list_repos(path),
                "config_path": str(path),
            }
        except (ValueError, OSError) as e:
            cfg_state = {"error": str(e)}
    return templates.TemplateResponse(
        request, "config.html", {"cfg": cfg_state})


@app.get("/repos/{owner}/{repo}", response_class=HTMLResponse)
def repo_page(request: Request, owner: str, repo: str):
    rec = metrics.repo_record(_session_root(), owner, repo)
    if rec is None:
        raise HTTPException(status_code=404, detail="Repo not found in sessions")
    verdict_json = json.dumps(rec["verdict_count"])
    open_qs = sum(p["open_questions"] for p in rec["prs"])
    from gh import run_gh

    pr_rows = metrics.open_prs(_session_root(), owner, repo, gh=run_gh)
    return templates.TemplateResponse(
        request, "repo.html",
        {"repo": rec, "verdict_json": verdict_json, "open_qs": open_qs,
         "pr_rows": pr_rows})


@app.get("/repos/{owner}/{repo}/pr/{pr}", response_class=HTMLResponse)
def pr_page(request: Request, owner: str, repo: str, pr: int):
    detail = metrics.pr_detail(_session_root(), owner, repo, pr)
    if detail is None:
        # PR chưa review → hiện placeholder + nút Review now (title từ gh)
        from gh import run_gh

        try:
            meta = run_gh(["api", f"repos/{owner}/{repo}/pulls/{pr}"])
            pr_info = {"pr": pr, "title": meta.get("title", ""),
                       "author": (meta.get("user") or {}).get("login", ""),
                       "base": (meta.get("base") or {}).get("ref", ""),
                       "head": (meta.get("head") or {}).get("ref", "")}
        except (RuntimeError, OSError):
            raise HTTPException(status_code=404,
                                detail="PR not found in sessions")
        return templates.TemplateResponse(
            request, "pr.html",
            {"detail": None, "pr_info": pr_info, "not_reviewed": True,
             "repo_owner": owner, "repo_name": repo})
    return templates.TemplateResponse(
        request, "pr.html",
        {"detail": detail, "pr_info": None, "not_reviewed": False,
         "repo_owner": owner, "repo_name": repo})


@app.get("/api/config")
def api_config():
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="prsentinel.yml not found")
    try:
        cfg = load_autoreview_config(path)
        repos = list_repos(path)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"invalid config: {e}")
    return {
        "org": cfg.get("org"),
        "default_mode": cfg.get("default_mode"),
        "interval_minutes": cfg.get("interval_minutes"),
        "post_comment": cfg.get("post_comment"),
        "skip_human": cfg.get("skip_human"),
        "drafts": cfg.get("drafts"),
        "repos": repos,
        "config_path": str(path),
    }


@app.post("/api/config/repos/{repo}/mode")
def api_set_mode(repo: str, payload: dict):
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="prsentinel.yml not found")
    try:
        mode = payload.get("mode")
        set_repo_mode(path, repo, mode)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "repo": repo, "mode": mode}


@app.post("/api/config/repos")
def api_add_repo(payload: dict):
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="prsentinel.yml not found")
    repo = (payload.get("repo") or "").strip()
    if not repo:
        raise HTTPException(status_code=400, detail="repo is required")
    try:
        cfg = load_autoreview_config(path)
        if "/" not in repo and not cfg.get("org"):
            raise HTTPException(
                status_code=400,
                detail="org not set in config; use owner/repo format")
        set_repo_mode(path, repo, payload.get("mode", "auto"))
    except HTTPException:
        raise
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "repo": repo}


@app.delete("/api/config/repos/{repo}")
def api_remove_repo(repo: str):
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="prsentinel.yml not found")
    try:
        remove_repo(path, repo)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "repo": repo}


def _review_lock_path(session_root: Path, owner: str, repo: str, n: int) -> Path:
    return session_root / owner / repo / f"pr-{n}" / "review.lock"


def _write_review_lock(lock: Path) -> None:
    """Atomically create the review lock with pid + started_at metadata."""
    data = json.dumps({"pid": os.getpid(),
                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(fd, data.encode())
    finally:
        os.close(fd)


def review_status(session_root: Path, owner: str, repo: str, n: int) -> dict:
    """Lock metadata if the review process is alive; stale flag if PID dead."""
    lock = _review_lock_path(session_root, owner, repo, n)
    if not lock.exists():
        return {"running": False, "stale": False}
    try:
        meta = json.loads(lock.read_text())
        pid = int(meta.get("pid", 0))
    except (json.JSONDecodeError, OSError, ValueError):
        pid = 0
    if pid > 0 and _pid_alive(pid):
        started_at = meta.get("started_at", "")
        elapsed = None
        try:
            from datetime import datetime

            started = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%S")
            elapsed = int((datetime.now() - started).total_seconds())
        except ValueError:
            pass
        return {"running": True, "pid": pid, "started_at": started_at,
                "elapsed_seconds": elapsed}
    return {"running": False, "stale": True}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/review/status")
def review_status_api(owner: str, repo: str, pr: int):
    return review_status(_session_root(), owner, repo, pr)


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/review/log")
def review_log_api(owner: str, repo: str, pr: int, lines: int = 200):
    path = _session_root() / owner / repo / f"pr-{pr}" / "review.log"
    log_text = ""
    if path.exists():
        try:
            log_text = "\n".join(path.read_text(errors="replace")
                                 .splitlines()[-max(1, min(lines, 2000)):])
        except OSError:
            log_text = ""
    return {"log": log_text,
            "running": review_status(_session_root(), owner, repo, pr)["running"]}


@app.post("/api/repos/{owner}/{repo}/pr/{pr}/review")
def trigger_review(owner: str, repo: str, pr: int):
    """Run a review synchronously using the repo's autoreview config."""
    cfg_path = _config_path()
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail="prsentinel.yml not found")
    try:
        cfg = load_autoreview_config(cfg_path)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"invalid config: {e}")

    env = load_config()
    if not env.has_auth():
        raise HTTPException(status_code=400, detail=AUTH_HINT)

    lock = _review_lock_path(_session_root(), owner, repo, pr)
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and review_status(_session_root(), owner, repo, pr)["running"]:
        status = review_status(_session_root(), owner, repo, pr)
        raise HTTPException(
            status_code=409,
            detail=(f"review already running — PID {status['pid']}, "
                    f"started {status['started_at']} "
                    f"({status['elapsed_seconds']}s ago)"))
    if lock.exists():  # stale lock → dọn và chạy lại
        try:
            lock.unlink()
        except OSError:
            pass
    try:
        _write_review_lock(lock)
    except FileExistsError:
        raise HTTPException(status_code=409,
                            detail=f"review already running for #{pr}")

    import contextlib

    log_path = lock.parent / "review.log"
    try:
        with open(log_path, "w") as logf:
            with contextlib.redirect_stdout(logf), \
                    contextlib.redirect_stderr(logf):
                args = [f"{owner}/{repo}", str(pr), "--force"]
                if cfg.get("skip_human", True):
                    args.append("--skip-human")
                if not cfg.get("post_comment", True):
                    args.append("--no-post")
                exit_code = run_main(args)
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass

    if exit_code != 0:
        raise HTTPException(
            status_code=500,
            detail=f"review failed (exit {exit_code}): "
                   f"check server log / sessions/{owner}/{repo}/pr-{pr}/report.md")
    return {"ok": True, "exit": exit_code,
            "report": f"sessions/{owner}/{repo}/pr-{pr}/report.md"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=6789)
