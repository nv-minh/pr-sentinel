"""Semantic diff pruning: keep the agent's context on code humans wrote.

Lockfiles, build output and binary assets add thousands of diff lines and no
review value. They are dropped from the file list, and oversized patches are
truncated — but every removal is recorded so the report can say what was skipped
instead of silently shrinking the review.
"""
from fnmatch import fnmatch

# (glob, reason) — matched against the full path and against the basename.
PRUNE_RULES: list[tuple[str, str]] = [
    ("*.lock", "lockfile"),
    ("package-lock.json", "lockfile"),
    ("pnpm-lock.yaml", "lockfile"),
    ("yarn.lock", "lockfile"),
    ("poetry.lock", "lockfile"),
    ("Pipfile.lock", "lockfile"),
    ("Gemfile.lock", "lockfile"),
    ("composer.lock", "lockfile"),
    ("go.sum", "lockfile"),
    ("dist/*", "build output"),
    ("build/*", "build output"),
    ("out/*", "build output"),
    (".next/*", "build output"),
    ("coverage/*", "build output"),
    ("*/dist/*", "build output"),
    ("*/build/*", "build output"),
    ("*/__generated__/*", "generated code"),
    ("*/generated/*", "generated code"),
    ("*.min.js", "generated code"),
    ("*.min.css", "generated code"),
    ("*.map", "generated code"),
    ("*.pb.go", "generated code"),
    ("*_pb2.py", "generated code"),
    ("*_pb2.pyi", "generated code"),
    ("*.g.dart", "generated code"),
    ("*.freezed.dart", "generated code"),
    ("*.snap", "test snapshot"),
    ("vendor/*", "vendored dependency"),
    ("*/vendor/*", "vendored dependency"),
    ("node_modules/*", "vendored dependency"),
    ("*/node_modules/*", "vendored dependency"),
    ("third_party/*", "vendored dependency"),
]

BINARY_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
                   ".woff", ".woff2", ".ttf", ".eot", ".otf", ".pdf", ".zip",
                   ".gz", ".tar", ".mp4", ".mov", ".mp3", ".wav", ".jar",
                   ".so", ".dylib", ".dll", ".class", ".pyc", ".wasm")

MAX_PATCH_LINES = 400
MAX_TOTAL_PATCH_LINES = 6000


def classify(filename: str) -> str | None:
    """Why this file should be dropped from the diff context, or None to keep it."""
    lower = filename.lower()
    base = lower.rsplit("/", 1)[-1]
    if lower.endswith(BINARY_SUFFIXES):
        return "binary asset"
    for pattern, reason in PRUNE_RULES:
        if fnmatch(lower, pattern) or fnmatch(base, pattern):
            return reason
    return None


def _truncate(patch: str, limit: int) -> tuple[str, int, int]:
    lines = patch.splitlines()
    if len(lines) <= limit:
        return patch, len(lines), len(lines)
    kept = "\n".join(lines[:limit])
    return f"{kept}\n… patch truncated: {len(lines) - limit} more lines", limit, len(lines)


def prune_files(files: list[dict], *, max_patch_lines: int = MAX_PATCH_LINES,
                max_total_lines: int = MAX_TOTAL_PATCH_LINES
                ) -> tuple[list[dict], list[dict]]:
    """Split a PR's file list into (files to review, records of what was cut).

    A pruned record is `{filename, reason, dropped}`: dropped=True means the file
    left the review context entirely, dropped=False means only its patch was
    shortened. The agent can still read any of them from the workspace on disk.
    """
    kept: list[dict] = []
    pruned: list[dict] = []
    budget = max_total_lines

    for f in files:
        reason = classify(f["filename"])
        if reason:
            pruned.append({"filename": f["filename"], "reason": reason, "dropped": True})
            continue
        entry = dict(f)
        patch = entry.get("patch") or ""
        limit = min(max_patch_lines, budget) if budget > 0 else 0
        if limit <= 0:
            entry["patch"] = ""
            pruned.append({"filename": f["filename"],
                           "reason": "diff budget exhausted", "dropped": False})
        else:
            new_patch, used, total = _truncate(patch, limit)
            entry["patch"] = new_patch
            budget -= used
            if total > used:
                pruned.append({"filename": f["filename"],
                               "reason": f"patch truncated to {used} of {total} lines",
                               "dropped": False})
        kept.append(entry)

    return kept, pruned
