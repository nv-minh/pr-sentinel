"""Which findings can be pinned to a line, and which have to stay in the summary.

GitHub accepts an inline review comment only on a line that is part of the diff.
That single rule shapes everything here: the module builds the set of lines the
API will accept, then resolves each finding against it.

It also means the most valuable finding type is the least placeable.
`callers_outside_diff` is, by definition, about code this PR did not touch — so
the caller sites can never be inline, and the best available anchor is the
changed symbol's own definition.

Pure functions over the snapshot and findings, like score.py: no I/O, no network.
"""
import re

MAX_INLINE = 20

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def diff_lines(snapshot: dict) -> dict[str, set[int]]:
    """New-side line numbers GitHub will accept a comment on, per file."""
    index: dict[str, set[int]] = {}
    for entry in snapshot.get("files") or []:
        patch = entry.get("patch") or ""
        if not patch:
            continue
        lines: set[int] = set()
        number = 0
        for line in patch.splitlines():
            hunk = HUNK_RE.match(line)
            if hunk:
                number = int(hunk.group(1))
                continue
            if line.startswith(("+++", "---")):
                continue
            if line.startswith("+") or line.startswith(" "):
                lines.add(number)
                number += 1
            # a "-" line exists only on the old side and consumes no new number
        if lines:
            index[entry.get("filename", "")] = lines
    return index


def parse_ref(ref: str) -> tuple[str, int] | None:
    """`src/a.py:42` -> ("src/a.py", 42). None when there is no line number."""
    path, _, line = (ref or "").rpartition(":")
    if not path or not line.isdigit():
        return None
    return path, int(line)


def _file_of(target: str) -> str:
    """The file part of a `file:function` target, which carries no line."""
    path, _, _ = (target or "").rpartition(":")
    return path or (target or "")


def candidates(findings: dict) -> list[dict]:
    """Every finding worth pinning, as `{path, line, body}`.

    `line` is None when the finding names a file but not a line; `split`
    resolves those to the file's first line in the diff.
    """
    out: list[dict] = []

    for claim in findings.get("claims") or []:
        if claim.get("status") not in ("FAIL", "PARTIAL"):
            continue
        ref = next((parse_ref(e) for e in claim.get("evidence") or []
                    if parse_ref(e)), None)
        if ref:
            out.append({"path": ref[0], "line": ref[1],
                        "body": f"**Claim {claim['id']} — {claim['status']}**\n\n"
                                f"{claim.get('note', '')}"})

    for caller in findings.get("callers_outside_diff") or []:
        if caller.get("risk") not in ("BROKEN", "NEEDS_UPDATE"):
            continue
        ref = parse_ref(caller.get("defined_at", ""))
        if not ref:
            continue
        sites = "\n".join(f"- `{c}`" for c in caller.get("callers") or []) or "- (none listed)"
        out.append({"path": ref[0], "line": ref[1],
                    "body": f"**Caller impact — {caller['risk']}**\n\n"
                            f"`{caller.get('symbol', '?')}` changed here. Callers this "
                            f"PR does not touch:\n{sites}\n\n{caller.get('note', '')}"})

    for contract in findings.get("contracts") or []:
        if contract.get("status") == "COMPATIBLE" or not contract.get("path"):
            continue
        out.append({"path": contract["path"], "line": None,
                    "body": f"**{contract['status']}** ({contract.get('kind', '?')})\n\n"
                            f"{contract.get('detail', '')}"})

    for test in findings.get("tests") or []:
        if test.get("assertion_quality") not in ("WEAK", "MISSING"):
            continue
        path = _file_of(test.get("target", ""))
        if not path:
            continue
        cases = "\n".join(f"- {c.get('case', '')} — add to `{c.get('where', '?')}`"
                          for c in test.get("uncovered_edge_cases") or [])
        body = (f"**Test coverage — {test['assertion_quality']}**\n\n"
                f"`{test.get('target', '')}`: {test.get('note', '')}")
        out.append({"path": path, "line": None,
                    "body": body + (f"\n\nUncovered:\n{cases}" if cases else "")})

    return out


def split(candidates: list[dict], index: dict[str, set[int]],
          cap: int = MAX_INLINE) -> tuple[list[dict], list[dict]]:
    """Partition candidates into (inline, leftover).

    Leftover is everything GitHub would reject plus everything past the cap. A
    candidate is never re-anchored to a different line to make it fit: a comment
    in the wrong place is worse than one in the summary.
    """
    inline: list[dict] = []
    leftover: list[dict] = []
    for candidate in candidates:
        lines = index.get(candidate["path"])
        line = candidate["line"]
        if line is None and lines:
            line = min(lines)
        if not lines or line not in lines or len(inline) >= cap:
            leftover.append(candidate)
            continue
        inline.append({**candidate, "line": line})
    return inline, leftover
