"""Which other open pull requests are changing the same code, and how.

Git reports a conflict when two branches contest a line. It says nothing when
PR A renames a function and PR B — touching no file in common — calls it. Both
CI runs are green, because each ran against a base that did not contain the
other, and `main` breaks on the second merge.

This module finds the pull requests worth comparing against, deterministically:
one GraphQL query for the open PRs and their file lists, path overlap computed
here, and each survivor's diff trimmed by prune.py. The agent fetches nothing;
it receives what this found and judges it (`cross_pr` in verify.py).
"""
import json
import sys
from pathlib import Path

import prune
from gh import run_gh as _default_gh
from score import DEFAULT_GATE, _matches
from tiers import _is_contract

MAX_OPEN_PRS = 50
MAX_SIBLING_FILES = 100
MAX_SIBLING_PATCH_LINES = 60
MAX_SIBLING_TOTAL_LINES = 300


def _dirname(path: str) -> str:
    return (path or "").rsplit("/", 1)[0] if "/" in (path or "") else ""


def our_paths(snapshot: dict) -> set[str]:
    """Source paths this PR touches: reviewed files, minus generated ones.

    A file whose patch was merely truncated is still a real source file, so
    `pruned` entries with `dropped=False` count.
    """
    names = [f.get("filename", "") for f in snapshot.get("files") or []]
    names += [p.get("filename", "") for p in snapshot.get("pruned") or []
              if not p.get("dropped")]
    return {n for n in names if n and prune.classify(n) is None}


def overlap_of(ours: set[str], theirs: set[str],
               sensitive: list[str]) -> tuple[str, list[str]]:
    """("file" | "module" | "", the paths the verdict is about).

    A shared file is a strong signal and always counts. A shared directory is a
    weak one and counts only where being wrong is expensive: a sensitive area,
    or a directory holding a contract file. In a repository whose whole source
    lives under `src/`, an unconditional module rule would make every open PR a
    sibling.

    The sensitivity test runs against real file paths, not the directory name —
    `gate.sensitive_areas` globs like `**/payment*/**` are written to match
    files.
    """
    common = sorted(ours & theirs)
    if common:
        return "file", common
    everything = ours | theirs
    shared = {_dirname(p) for p in ours if _dirname(p)} & {
        _dirname(p) for p in theirs if _dirname(p)}
    risky = sorted(
        d for d in shared
        if any(_matches(p, sensitive) or _is_contract(p)
               for p in everything if _dirname(p) == d))
    return ("module", risky) if risky else ("", [])


def rank(cands: list[dict], limit: int) -> list[dict]:
    """File overlaps first, then more overlapping paths, then most recent.

    Two passes rather than one key: recency sorts descending while the others
    sort ascending, and Python's sort is stable, so the first pass survives as
    the tie-break of the second.
    """
    by_recency = sorted(cands, key=lambda c: c.get("updated_at") or "",
                        reverse=True)
    ordered = sorted(by_recency, key=lambda c: (c["overlap"] != "file",
                                                -len(c["overlap_paths"])))
    return ordered[:max(int(limit), 0)]


QUERY = """
query($owner:String!,$repo:String!,$limit:Int!,$files:Int!){
  repository(owner:$owner,name:$repo){
    pullRequests(states:OPEN, first:$limit,
                 orderBy:{field:UPDATED_AT, direction:DESC}){
      nodes{
        number title isDraft baseRefName headRefName updatedAt url
        author{login}
        files(first:$files){ nodes{ path } }
      }
    }
  }
}
"""

NO_OVERLAP = ("no other open pull request changes the same files or a sensitive "
              "module this PR touches")


def _diffs_unreadable(count: int) -> str:
    return (f"found {count} overlapping open pull request(s) but could not read "
            f"any of their diffs")


def _nodes(payload) -> list[dict]:
    if not isinstance(payload, dict) or "errors" in payload or "data" not in payload:
        raise RuntimeError(f"graphql failed: {payload}")
    repo = (payload["data"] or {}).get("repository") or {}
    return (repo.get("pullRequests") or {}).get("nodes") or []


def _candidates(snapshot: dict, nodes: list[dict], cfg: dict,
                gate: dict) -> list[dict]:
    """Open PRs worth comparing against, before any diff is fetched."""
    ours = our_paths(snapshot)
    sensitive = {**DEFAULT_GATE, **(gate or {})}["sensitive_areas"]
    out: list[dict] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("number") == snapshot.get("pr"):
            continue
        if node.get("isDraft") and not cfg.get("include_drafts", False):
            continue
        if node.get("baseRefName") != snapshot.get("base"):
            continue
        login = (node.get("author") or {}).get("login") or ""
        if login.endswith("[bot]"):
            continue
        theirs = {f.get("path", "") for f in
                  ((node.get("files") or {}).get("nodes") or [])
                  if f.get("path") and prune.classify(f["path"]) is None}
        kind, paths = overlap_of(ours, theirs, sensitive)
        if not kind:
            continue
        out.append({"pr": node.get("number"), "title": node.get("title") or "",
                    "author": login, "url": node.get("url") or "",
                    "base": node.get("baseRefName") or "",
                    "head": node.get("headRefName") or "",
                    "updated_at": node.get("updatedAt") or "",
                    "overlap": kind, "overlap_paths": paths,
                    "files": [], "pruned": []})
    return out


def _fetch_diff(owner: str, repo: str, sibling: dict, gh) -> bool:
    """Fill in the sibling's overlapping patches, trimmed. False when unreadable.

    Only the overlapping paths are kept: the rest of somebody else's PR is not
    what this review is about, and the prompt budget is small on purpose.
    """
    wanted = set(sibling["overlap_paths"])
    by_dir = sibling["overlap"] == "module"
    try:
        files = gh(["api", f"repos/{owner}/{repo}/pulls/{sibling['pr']}/files",
                    "--paginate"])
    except RuntimeError as e:
        print(f"[siblings] could not read the diff of #{sibling['pr']}: {e}",
              file=sys.stderr)
        return False
    picked = [{"filename": f.get("filename", ""), "status": f.get("status", ""),
               "additions": f.get("additions", 0),
               "deletions": f.get("deletions", 0), "patch": f.get("patch", "")}
              for f in files if isinstance(f, dict)
              and (f.get("filename") in wanted
                   or (by_dir and _dirname(f.get("filename", "")) in wanted))]
    kept, pruned = prune.prune_files(
        picked, max_patch_lines=MAX_SIBLING_PATCH_LINES,
        max_total_lines=MAX_SIBLING_TOTAL_LINES)
    sibling["files"] = kept
    sibling["pruned"] = pruned
    return True


def fetch_siblings(snapshot: dict, session_dir: Path, cfg: dict,
                   gate: dict | None = None, *, gh=_default_gh) -> dict:
    """Find overlapping open PRs, persist siblings.json. Never raises.

    Returns `{"scanned", "truncated", "skipped", "siblings"}`; `skipped` is a
    sentence for the report and is non-empty exactly when nothing was fetched.
    """
    owner = snapshot.get("owner", "")
    repo = snapshot.get("repo", "")
    result: dict = {"scanned": 0, "truncated": False, "skipped": "", "siblings": []}
    picked: list[dict] = []
    try:
        nodes = _nodes(gh(["api", "graphql", "-f", f"query={QUERY}",
                           "-F", f"owner={owner}", "-F", f"repo={repo}",
                           "-F", f"limit={MAX_OPEN_PRS}",
                           "-F", f"files={MAX_SIBLING_FILES}"]))
    except RuntimeError as e:
        nodes = []
        result["skipped"] = f"could not list open pull requests: {e}"

    if nodes:
        result["scanned"] = len(nodes)
        result["truncated"] = len(nodes) >= MAX_OPEN_PRS or any(
            len(((n.get("files") or {}).get("nodes") or [])) >= MAX_SIBLING_FILES
            for n in nodes if isinstance(n, dict))
        picked = rank(_candidates(snapshot, nodes, cfg, gate or {}),
                      cfg.get("max_siblings", 3))
        result["siblings"] = [s for s in picked
                              if _fetch_diff(owner, repo, s, gh)]
    # `skipped` is non-empty here only when the GraphQL call itself failed —
    # leave that message alone. Otherwise: overlapping PRs were found but every
    # diff fetch failed (`picked` non-empty, `siblings` empty) is a different,
    # and opposite, truth from genuinely finding no overlap at all.
    if not result["siblings"] and not result["skipped"]:
        result["skipped"] = _diffs_unreadable(len(picked)) if picked else NO_OVERLAP

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "siblings.json").write_text(json.dumps(result, indent=2))
    if result["truncated"]:
        print(f"[siblings] warning: scan capped at {MAX_OPEN_PRS} open PRs / "
              f"{MAX_SIBLING_FILES} files each — overlap data incomplete",
              file=sys.stderr)
    print(f"[siblings] scanned {result['scanned']} open PR(s), "
          f"{len(result['siblings'])} overlapping"
          + (f" — {result['skipped']}" if result["skipped"] else ""))
    return result
