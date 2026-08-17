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
