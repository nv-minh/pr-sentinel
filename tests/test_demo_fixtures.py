"""The committed demo sessions are the dashboard's offline acceptance surface.

These tests lock the fixture quality: patches must be real unified diffs whose
hunk arithmetic is consistent, and the findings' evidence refs must land on
lines those hunks actually cover — otherwise the review workspace demos with
nothing anchored.
"""
import json
import re
from pathlib import Path

from annotations import diff_lines, parse_ref

DEMO = Path("sessions/demo/app")
HUNK = re.compile(r"^@@ -\d+(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# Refs that intentionally point outside the shown diff, exercised by the UI as
# unanchored findings and workspace-peek targets.
OUT_OF_DIFF = {("src/auth/google.py", 64)}


def _snapshot(pr: int) -> dict:
    return json.loads((DEMO / f"pr-{pr}" / "snapshot.json").read_text())


def _findings(pr: int) -> dict:
    return json.loads((DEMO / f"pr-{pr}" / "findings.json").read_text())


def _hunks(patch: str) -> list[tuple[int, int, list[str]]]:
    """[(old_count, new_count, body_lines)] per hunk."""
    hunks: list[tuple[int, int, list[str]]] = []
    body: list[str] = []
    counts: tuple[int, int] | None = None
    for line in patch.splitlines():
        m = HUNK.match(line)
        if m:
            if counts is not None:
                hunks.append((*counts, body))
            counts = (int(m.group(1) or 1), int(m.group(3) or 1))
            body = []
        elif counts is not None:
            body.append(line)
    if counts is not None:
        hunks.append((*counts, body))
    return hunks


def test_demo_patches_have_valid_hunk_headers():
    for pr in (7, 8):
        snapshot = _snapshot(pr)
        index = diff_lines(snapshot)
        for entry in snapshot["files"]:
            name, patch = entry["filename"], entry["patch"]
            assert _hunks(patch), f"pr-{pr} {name}: no valid @@ hunk header"
            assert index.get(name), f"pr-{pr} {name}: no diff lines parsed"
            # prune.py keeps the original header when it truncates a patch,
            # so the sentinel's count makes up the difference in the last hunk.
            sentinel = re.search(r"… patch truncated: (\d+) more lines$", patch)
            hunks = _hunks(patch)
            for i, (old_count, new_count, body) in enumerate(hunks):
                old = sum(1 for l in body if l.startswith((" ", "-")))
                new = sum(1 for l in body if l.startswith((" ", "+")))
                if sentinel and i == len(hunks) - 1:
                    assert new + int(sentinel.group(1)) == new_count and old <= old_count, (
                        f"pr-{pr} {name}: truncated hunk shows {new} of {new_count}")
                    continue
                assert (old, new) == (old_count, new_count), (
                    f"pr-{pr} {name}: hunk declares -{old_count} +{new_count}, "
                    f"body has {old}/{new}")


def test_demo_evidence_refs_land_in_the_diff():
    for pr in (7, 8):
        index = diff_lines(_snapshot(pr))
        findings = _findings(pr)
        refs = [e for c in findings.get("claims", []) for e in c.get("evidence", [])]
        refs += [c["defined_at"] for c in findings.get("callers_outside_diff", [])]
        refs += [e for c in findings.get("cross_pr", []) or [] for e in c.get("evidence", [])]
        for raw in refs:
            parsed = parse_ref(raw)
            if parsed is None or parsed[0] not in index or parsed in OUT_OF_DIFF:
                continue
            path, line = parsed
            assert line in index[path], f"pr-{pr}: {raw} not on a diff line"


def test_demo_truncation_sentinel_is_recorded_in_pruned():
    snapshot = _snapshot(7)
    google = next(f for f in snapshot["files"] if f["filename"] == "src/auth/google.py")
    assert re.search(r"… patch truncated: \d+ more lines$", google["patch"])
    reasons = [p["reason"] for p in snapshot["pruned"]
               if p["filename"] == "src/auth/google.py"]
    assert reasons == ["patch truncated to 26 of 72 lines"]
    assert all(not p["dropped"] for p in snapshot["pruned"]
               if p["filename"] == "src/auth/google.py")


def test_demo_file_counts_match_untruncated_patches():
    for pr in (7, 8):
        snapshot = _snapshot(pr)
        truncated = {p["filename"] for p in snapshot["pruned"]
                     if "truncated" in p["reason"]}
        for entry in snapshot["files"]:
            if entry["filename"] in truncated:
                continue
            body = [l for _, _, b in _hunks(entry["patch"]) for l in b]
            assert entry["additions"] == sum(1 for l in body if l.startswith("+")), \
                f"pr-{pr} {entry['filename']}: additions mismatch"
            assert entry["deletions"] == sum(1 for l in body if l.startswith("-")), \
                f"pr-{pr} {entry['filename']}: deletions mismatch"
