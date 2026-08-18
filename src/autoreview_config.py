"""Load, validate and edit prsentinel.yml config (single source of truth)."""
import os
import re
from pathlib import Path

import yaml

import providers
from score import DEFAULT_GATE

DEFAULTS = {
    "org": "",
    "default_mode": "manual",
    "interval_minutes": 2,
    "post_comment": True,
    "skip_human": True,
    "drafts": False,
    "skip_bots": True,
    # The language the model writes its output in (notes, questions,
    # descriptions, PoC reasons, follow-up replies, the reason attached to a
    # documentation fix). Fixed labels stay English.
    "language": "en",
    # Where LLM calls go. `providers` holds per-provider overrides; tokens are
    # never stored here, only the name of the env var that holds them.
    "provider": "anthropic",
    "providers": {},
    # Review behaviour
    "tiered_budget": True,     # route each review's effort by what it touches
    "allow_bash": False,        # let the agent run git/grep in the workspace
    "max_turns": 60,
    "max_budget_usd": None,     # hard stop on the cost of one verify run
    # Actions that write outside the review comment — opt-in on purpose
    "auto_describe": False,     # rewrite an empty PR body
    "docs_fix_pr": False,       # open a follow-up PR with doc fixes
    "inline_suggestions": True,  # suggestion blocks on docs inside the diff
    "poc_tests": True,          # generate a failing test for each BROKEN finding
    "max_inline_comments": 20,  # per review; the rest go in the summary comment
    # Cross-PR sibling scan: which other open PRs touch the same code.
    "siblings": {"enabled": True, "max_siblings": 3, "include_drafts": False},
    # Jira. Credentials live in the environment, never here.
    "jira": {"projects": [], "comment_result": False},
    "gate": dict(DEFAULT_GATE),
}


def load_config(path: Path) -> dict:
    """Read autoreview.yml, normalize, merge defaults. Raises OSError/ValueError."""
    try:
        raw = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"invalid config YAML: {e}") from e
    cfg = {**DEFAULTS, **raw}
    cfg["repos"] = _normalize_repos(cfg.get("repos") or {})
    cfg["gate"] = {**DEFAULT_GATE, **(raw.get("gate") or {})}
    cfg["providers"] = dict(raw.get("providers") or {})
    cfg["siblings"] = {**DEFAULTS["siblings"], **(raw.get("siblings") or {})}
    cfg["jira"] = {**DEFAULTS["jira"], **(raw.get("jira") or {})}
    validate_config(cfg)
    return cfg


def _normalize_repos(repos) -> dict:
    """dict {name: mode} → as-is; legacy list ['owner/repo'] → all auto."""
    if isinstance(repos, dict):
        return {str(k): str(v) for k, v in repos.items()}
    if isinstance(repos, list):
        return {str(r): "auto" for r in repos}
    return {}


def validate_config(cfg: dict) -> None:
    for name, mode in cfg.get("repos", {}).items():
        if mode not in ("auto", "manual"):
            raise ValueError(f"repo mode must be auto|manual: {name!r} -> {mode!r}")
    interval = cfg.get("interval_minutes")
    if not isinstance(interval, int) or interval <= 0:
        raise ValueError("interval_minutes must be a positive integer")
    if cfg.get("language") not in ("en", "vi"):
        raise ValueError("language must be 'en' or 'vi'")
    minimum = cfg.get("gate", {}).get("verification_score_min")
    if not isinstance(minimum, (int, float)) or not 0 <= minimum <= 1:
        raise ValueError("gate.verification_score_min must be between 0 and 1")
    jira_cfg = cfg.get("jira", {})
    projects = jira_cfg.get("projects")
    if not isinstance(projects, list) or not all(isinstance(p, str) for p in projects):
        raise ValueError("jira.projects must be a list of project keys, e.g. [ABC, PRJ]")
    if not isinstance(jira_cfg.get("comment_result"), bool):
        raise ValueError("jira.comment_result must be true or false")
    siblings_cfg = cfg.get("siblings", {})
    for key in ("enabled", "include_drafts"):
        if not isinstance(siblings_cfg.get(key), bool):
            raise ValueError(f"siblings.{key} must be true or false")
    cap = siblings_cfg.get("max_siblings")
    # bool first: True is an int and would otherwise pass as a cap of 1.
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError("siblings.max_siblings must be a positive integer")
    if not isinstance(cfg.get("poc_tests"), bool):
        raise ValueError("poc_tests must be true or false")
    cap = cfg.get("max_inline_comments")
    # bool first: True is an int, and would otherwise pass as a cap of 1.
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 1:
        raise ValueError("max_inline_comments must be a positive integer")
    providers.validate(cfg)


def _write_atomic(path: Path, cfg: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False))
    os.replace(tmp, path)


def _write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def set_repo_mode(path: Path, repo: str, mode: str) -> dict:
    """Add or change mode for a repo. Returns the updated config.

    Writes to an existing entry when one matches (exact key, else the same
    trailing name segment, mirroring remove_repo) so a full-name write does
    not duplicate a bare-name entry or vice versa.
    """
    if mode not in ("auto", "manual"):
        raise ValueError(f"mode must be auto|manual: {mode!r}")
    cfg = load_config(path)
    key = repo
    if repo not in cfg["repos"]:
        for existing in cfg["repos"]:
            if existing.split("/")[-1] == repo.split("/")[-1]:
                key = existing
                break
    cfg["repos"][key] = mode
    _write_atomic(path, cfg)
    return cfg


def remove_repo(path: Path, repo: str) -> dict:
    """Remove a repo (match full key or by repo name). Returns updated config."""
    cfg = load_config(path)
    if repo in cfg["repos"]:
        del cfg["repos"][repo]
    else:
        for key in list(cfg["repos"]):
            if key.split("/")[-1] == repo.split("/")[-1]:
                del cfg["repos"][key]
    _write_atomic(path, cfg)
    return cfg


def auto_repos(cfg: dict) -> list[tuple[str, str]]:
    """(owner, repo) pairs to auto-review, in config order."""
    pairs = []
    for name, mode in cfg.get("repos", {}).items():
        if mode != "auto":
            continue
        if "/" in name:
            owner, repo = name.split("/", 1)
        else:
            owner, repo = cfg.get("org", ""), name
        if owner and repo:
            pairs.append((owner, repo))
    return pairs


def list_repos(path: Path, gh=None) -> list[dict]:
    """[{name, mode}] — configured repos + org repos (unlisted) when org set.

    gh must be callable like run_gh(args, **kw); default imports gh.run_gh.
    Org lookup failure is silent (returns configured repos only).
    """
    cfg = load_config(path)
    if gh is None:
        from gh import run_gh
        gh = run_gh
    names = list(cfg["repos"].keys())
    if cfg.get("org"):
        try:
            data = gh(["api", f"orgs/{cfg['org']}/repos", "--paginate"])
            org_names = [r["name"] for r in data if isinstance(r, dict)]
            names = org_names + [n for n in names if n not in org_names]
        except (RuntimeError, OSError):
            pass
    return [{"name": n, "mode": cfg["repos"].get(n, "unlisted")}
            for n in sorted(names)]


def set_provider(path: Path, name: str) -> dict:
    """Switch the active provider. Never writes a token: the file records only
    which provider is active and where it points.

    The edit rewrites the one top-level `provider:` line in place, so comments,
    ordering and formatting in the operator's file survive the switch.
    """
    cfg = load_config(path)
    providers.build(name, cfg["providers"].get(name))
    text = path.read_text() if path.exists() else ""
    if re.search(r"(?m)^provider:", text):
        text = re.sub(r"(?m)^provider:[ \t]*.*$",
                      lambda _m: f"provider: {name}", text, count=1)
    elif text.strip():
        text = text.rstrip("\n") + f"\nprovider: {name}\n"
    else:
        text = f"provider: {name}\n"
    _write_text_atomic(path, text)
    return load_config(path)


def set_language(path: Path, language: str) -> dict:
    """Switch the language the model writes its output in.

    Edits the one top-level `language:` line in the raw text, the way
    set_provider does, so the operator's comments and ordering survive. A yaml
    round-trip through _write_atomic would rewrite the whole document and delete
    every comment in the file — including the block that documents this key.
    """
    load_config(path)
    if language not in ("en", "vi"):
        raise ValueError("language must be 'en' or 'vi'")
    text = path.read_text() if path.exists() else ""
    if re.search(r"(?m)^language:", text):
        text = re.sub(r"(?m)^language:[ \t]*.*$",
                      lambda _m: f"language: {language}", text, count=1)
    elif text.strip():
        text = text.rstrip("\n") + f"\nlanguage: {language}\n"
    else:
        text = f"language: {language}\n"
    _write_text_atomic(path, text)
    return load_config(path)
