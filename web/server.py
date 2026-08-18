"""JSON API for the dashboard, plus the built SPA.

The review endpoint starts the pipeline on a background thread and returns
immediately: a real review takes minutes, and an HTTP request should not be
holding a socket open for it. Progress is read back through
`/review/status` and `/review/log`.
"""
import contextlib
import json
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import providers
from autoreview_config import load_config as load_autoreview_config
from autoreview_config import (auto_repos, list_repos, remove_repo,
                               set_language, set_provider, set_repo_mode)
from config import load_config
from run import main as run_main
from web import metrics, trace

BASE = Path(__file__).resolve().parent
UI_DIST = BASE / "ui" / "dist"

app = FastAPI(title="PR Sentinel")


def _session_root() -> Path:
    return load_config().session_root


def _config_path() -> Path:
    return Path(os.environ.get("PRSENTINEL_CONFIG", "prsentinel.yml"))


def _require_config() -> Path:
    path = _config_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="prsentinel.yml not found")
    return path


# --------------------------------------------------------------------------- data

@app.get("/api/repos")
def api_repos():
    root = _session_root()
    repos = []
    for owner, repo in metrics.list_repos(root):
        rec = metrics.repo_record(root, owner, repo)
        if rec is not None:
            rec["has_data"] = True
            repos.append(rec)
    repos.sort(key=lambda r: r["prs_total"], reverse=True)

    seen = {(r["owner"], r["repo"]) for r in repos}
    modes: dict[str, str] = {}
    org = ""
    path = _config_path()
    if path.exists():
        try:
            cfg = load_autoreview_config(path)
            modes, org = dict(cfg.get("repos") or {}), cfg.get("org") or ""
            for owner, repo in auto_repos(cfg):
                if (owner, repo) not in seen:
                    repos.append({"owner": owner, "repo": repo, "prs_total": 0,
                                  "bugs_total": 0, "doc_errors_total": 0,
                                  "breaking_total": 0, "test_gaps_total": 0,
                                  "cost_total": 0.0, "has_data": False, "mode": "auto"})
        except (ValueError, OSError):
            pass
    for rec in repos:
        if "mode" not in rec:
            bare = modes.get(rec["repo"]) if org == rec["owner"] else None
            rec["mode"] = modes.get(f"{rec['owner']}/{rec['repo']}") or bare or "unlisted"
    return {"repos": repos}


@app.get("/api/repos/{owner}/{repo}")
def api_repo(owner: str, repo: str):
    from gh import run_gh

    root = _session_root()
    rec = metrics.repo_record(root, owner, repo)
    if rec is None:
        rec = {"owner": owner, "repo": repo, "prs_total": 0, "bugs_total": 0,
               "doc_errors_total": 0, "breaking_total": 0, "test_gaps_total": 0,
               "cost_total": 0.0, "avg_verification_score": None,
               "verdict_count": {v: 0 for v in metrics.VERDICTS},
               "gate_count": {g: 0 for g in metrics.GATES}, "prs": []}
    rec["open_questions"] = sum(p["open_questions"] for p in rec["prs"])
    rec["open_prs"] = metrics.open_prs(root, owner, repo, gh=run_gh)
    return rec


@app.get("/api/repos/{owner}/{repo}/pr/{pr}")
def api_pr(owner: str, repo: str, pr: int):
    detail = metrics.pr_detail(_session_root(), owner, repo, pr)
    if detail is not None:
        return {"reviewed": True, "owner": owner, "repo": repo, **detail}

    from gh import run_gh
    try:
        meta = run_gh(["api", f"repos/{owner}/{repo}/pulls/{pr}"])
    except (RuntimeError, OSError):
        raise HTTPException(status_code=404, detail="PR not found in sessions")
    return {"reviewed": False, "owner": owner, "repo": repo, "pr": {
        "pr": pr, "title": meta.get("title", ""),
        "author": (meta.get("user") or {}).get("login", ""),
        "base": (meta.get("base") or {}).get("ref", ""),
        "head": (meta.get("head") or {}).get("ref", "")}}


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/report")
def api_report(owner: str, repo: str, pr: int):
    path = _session_root() / owner / repo / f"pr-{pr}" / "report.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no report yet")
    return {"markdown": path.read_text(errors="replace")}


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/graph")
def api_graph(owner: str, repo: str, pr: int):
    """The review pipeline as nodes and edges, for the dashboard's graph view."""
    graph = metrics.pipeline_graph(_session_root(), owner, repo, pr)
    if graph is None:
        raise HTTPException(status_code=404, detail="no session for this PR")
    return graph


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/files")
def api_pr_files(owner: str, repo: str, pr: int):
    """The snapshot's per-file diffs, for the workspace's diff viewer."""
    data = metrics.snapshot_slice(_session_root(), owner, repo, pr)
    if data is None:
        raise HTTPException(status_code=404, detail="no snapshot for this PR")
    return data


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/file")
def api_pr_file(owner: str, repo: str, pr: int, path: str,
                start: int = 1, end: int | None = None):
    """A line slice from the workspace clone — evidence outside the diff."""
    try:
        data = metrics.workspace_file(_session_root(), owner, repo, pr,
                                      path, start, end)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if data is None:
        raise HTTPException(status_code=404, detail="workspace or file not available")
    return data


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/extras")
def api_pr_extras(owner: str, repo: str, pr: int):
    """Optional artifacts (ticket, poc, patches, neutralized, description)."""
    data = metrics.pr_extras(_session_root(), owner, repo, pr)
    if data is None:
        raise HTTPException(status_code=404, detail="no session for this PR")
    return data


@app.get("/api/repos/{owner}/{repo}/pr/{pr}/trace")
def api_pr_trace(owner: str, repo: str, pr: int):
    """The agent's tool-call timeline per phase; [] when no transcript exists."""
    return trace.pr_trace(_session_root(), owner, repo, pr)


# ------------------------------------------------------------------------- config

@app.get("/api/config")
def api_config():
    path = _require_config()
    try:
        cfg = load_autoreview_config(path)
        repos = list_repos(path)
        # An unknown PRS_PROVIDER bypasses providers.validate() (it only runs
        # at YAML-load time), so resolve() must stay inside this try or a
        # one-character typo surfaces as a 500 instead of the usual 400.
        provider_info = providers.describe(providers.resolve(cfg))
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"invalid config: {e}")
    return {
        "org": cfg.get("org"),
        "default_mode": cfg.get("default_mode"),
        "language": cfg.get("language"),
        "interval_minutes": cfg.get("interval_minutes"),
        "post_comment": cfg.get("post_comment"),
        "skip_human": cfg.get("skip_human"),
        "drafts": cfg.get("drafts"),
        "auto_describe": cfg.get("auto_describe"),
        "docs_fix_pr": cfg.get("docs_fix_pr"),
        "inline_suggestions": cfg.get("inline_suggestions"),
        "gate": cfg.get("gate"),
        "provider": provider_info,
        "providers": providers.names(cfg),
        "repos": repos,
        "config_path": str(path),
    }


@app.post("/api/config/provider")
def api_set_provider(payload: dict):
    """Switch which gateway LLM calls go to. Tokens stay in the environment."""
    path = _require_config()
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        set_provider(path, name)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "provider": name}


@app.post("/api/config/language")
def api_set_language(payload: dict):
    """Set the language the review writes its prose in. Fixed labels stay English."""
    path = _require_config()
    language = (payload.get("language") or "").strip()
    try:
        set_language(path, language)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "language": language}


@app.post("/api/config/repos/{repo:path}/mode")
def api_set_mode(repo: str, payload: dict):
    path = _require_config()
    try:
        mode = payload.get("mode")
        set_repo_mode(path, repo, mode)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "repo": repo, "mode": mode}


@app.post("/api/config/repos")
def api_add_repo(payload: dict):
    path = _require_config()
    repo = (payload.get("repo") or "").strip()
    if not repo:
        raise HTTPException(status_code=400, detail="repo is required")
    try:
        cfg = load_autoreview_config(path)
        if "/" not in repo and not cfg.get("org"):
            raise HTTPException(status_code=400,
                                detail="org not set in config; use owner/repo format")
        set_repo_mode(path, repo, payload.get("mode", "auto"))
    except HTTPException:
        raise
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "repo": repo}


@app.delete("/api/config/repos/{repo:path}")
def api_remove_repo(repo: str):
    path = _require_config()
    try:
        remove_repo(path, repo)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "repo": repo}


# ------------------------------------------------------------------------- review

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


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def review_status(session_root: Path, owner: str, repo: str, n: int) -> dict:
    """Lock metadata if the review is alive; stale flag if the PID is dead."""
    session_dir = session_root / owner / repo / f"pr-{n}"
    lock = _review_lock_path(session_root, owner, repo, n)
    last = {}
    result_path = session_dir / "review-result.json"
    if result_path.exists():
        try:
            last = json.loads(result_path.read_text())
        except (json.JSONDecodeError, OSError):
            last = {}
    if not lock.exists():
        return {"running": False, "stale": False, "last": last}
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
                "elapsed_seconds": elapsed, "last": last}
    return {"running": False, "stale": True, "last": last}


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


def _spawn(target) -> None:
    """Run a review off the request thread. Tests replace this to run inline."""
    threading.Thread(target=target, daemon=True).start()


def _review_job(args: list[str], lock: Path, log_path: Path) -> None:
    """Run the pipeline, capture its output, always release the lock."""
    exit_code = 1
    try:
        with open(log_path, "w") as logf:
            with contextlib.redirect_stdout(logf), contextlib.redirect_stderr(logf):
                exit_code = run_main(args)
    except Exception as e:  # a crashed review must still clear its lock
        try:
            with open(log_path, "a") as logf:
                logf.write(f"\nreview crashed: {e}\n")
        except OSError:
            pass
    finally:
        try:
            (lock.parent / "review-result.json").write_text(json.dumps(
                {"exit": exit_code, "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S")}))
        except OSError:
            pass
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


@app.post("/api/repos/{owner}/{repo}/pr/{pr}/review", status_code=202)
def trigger_review(owner: str, repo: str, pr: int, reply: bool = False):
    """Start a review in the background. Poll `review/status` for the outcome."""
    cfg_path = _require_config()
    try:
        cfg = load_autoreview_config(cfg_path)
        # An unknown PRS_PROVIDER bypasses providers.validate() (it only runs
        # at YAML-load time), so resolve() must stay inside this try or a
        # one-character typo surfaces as a 500 instead of the usual 400.
        provider = providers.resolve(cfg)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=f"invalid config: {e}")

    if not providers.has_auth(provider):
        raise HTTPException(status_code=400, detail=providers.auth_hint(provider))

    root = _session_root()
    lock = _review_lock_path(root, owner, repo, pr)
    lock.parent.mkdir(parents=True, exist_ok=True)
    status = review_status(root, owner, repo, pr)
    if status["running"]:
        raise HTTPException(
            status_code=409,
            detail=(f"review already running — PID {status['pid']}, "
                    f"started {status['started_at']} "
                    f"({status['elapsed_seconds']}s ago)"))
    if lock.exists():  # stale lock → clear it and run again
        try:
            lock.unlink()
        except OSError:
            pass
    try:
        _write_review_lock(lock)
    except FileExistsError:
        raise HTTPException(status_code=409,
                            detail=f"review already running for #{pr}")

    args = [f"{owner}/{repo}", str(pr), "--reply" if reply else "--force"]
    if cfg.get("skip_human", True):
        args.append("--skip-human")
    if not cfg.get("post_comment", True):
        args.append("--no-post")

    log_path = lock.parent / "review.log"
    (lock.parent / "review-result.json").unlink(missing_ok=True)
    _spawn(lambda: _review_job(args, lock, log_path))
    return {"ok": True, "status": "started", "pr": pr, "args": args}


# ---------------------------------------------------------------------------- SPA

# Register new /api routes ABOVE this guard: it must stay the last /api GET so
# an unknown API path is a JSON 404 instead of index.html from the catch-all.
@app.get("/api/{rest:path}")
def api_not_found(rest: str):
    raise HTTPException(status_code=404, detail=f"unknown API path: /api/{rest}")


if (UI_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(UI_DIST / "assets")), name="assets")


@app.get("/{full_path:path}")
def spa(full_path: str):
    """Serve the built SPA; every non-API path is handled by the client router."""
    index = UI_DIST / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=503,
            detail="dashboard not built — run `npm ci && npm run build` in web/ui")
    candidate = (UI_DIST / full_path).resolve()
    if full_path and candidate.is_file() and candidate.is_relative_to(UI_DIST.resolve()):
        return FileResponse(candidate)
    return FileResponse(index)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=6789)
