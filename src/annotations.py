"""Which findings can be pinned to a line, and which have to stay in the summary.

GitHub accepts an inline review comment only on a line that is part of the diff.
That single rule shapes everything here: the module builds the set of lines the
API will accept, then resolves each finding against it.

It also means the most valuable finding type is the least placeable.
`callers_outside_diff` is, by definition, about code this PR did not touch — so
the caller sites can never be inline, and the best available anchor is the
changed symbol's own definition. Similarly, cross-PR collisions anchor on this
PR's file, because the other PR's lines are not in this diff at all.

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


# Grammar shared with the dashboard's evidence parser (workspace/evidence.ts):
# path ':' digits ('-' digits)? (whitespace annotation)?  ->  first digit run.
REF_RE = re.compile(r"(.+?):(\d+)(?:-\d+)?(?:\s+\S.*)?")


def parse_ref(ref: str) -> tuple[str, int] | None:
    """`src/a.py:42`, `src/a.py:42-60`, `src/a.py:42 note` -> ("src/a.py", 42).

    None when there is no line number (`src/a.py:test_charge`, bare paths).
    """
    match = REF_RE.fullmatch((ref or "").strip())
    if not match:
        return None
    return match.group(1), int(match.group(2))


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
        evidence = claim.get("evidence") or []
        ref = next((parse_ref(e) for e in evidence if parse_ref(e)), None)
        # No usable file:line still yields a candidate: split() routes it to
        # leftover, where the summary comment reports it. Dropping it here would
        # lose the finding from both surfaces.
        path, line = ref if ref else (_file_of(evidence[0]) if evidence else "", None)
        out.append({"path": path, "line": line,
                    "body": f"**Claim {claim['id']} — {claim['status']}**\n\n"
                            f"{claim.get('note', '')}"})

    for caller in findings.get("callers_outside_diff") or []:
        if caller.get("risk") not in ("BROKEN", "NEEDS_UPDATE"):
            continue
        defined_at = caller.get("defined_at", "")
        ref = parse_ref(defined_at)
        # As above: an unparseable definition still reaches the summary.
        path, line = ref if ref else (_file_of(defined_at), None)
        sites = "\n".join(f"- `{c}`" for c in caller.get("callers") or []) or "- (none listed)"
        out.append({"path": path, "line": line,
                    "body": f"**Caller impact — {caller['risk']}**\n\n"
                            f"`{caller.get('symbol', '?')}` changed here. Callers this "
                            f"PR does not touch:\n{sites}\n\n{caller.get('note', '')}"})

    for contract in findings.get("contracts") or []:
        if contract.get("status") == "COMPATIBLE" or not contract.get("path"):
            continue
        out.append({"path": contract["path"], "line": None,
                    "body": f"**{contract['status']}** ({contract.get('kind', '?')})\n\n"
                            f"{contract.get('detail', '')}"})

    for collision in findings.get("cross_pr") or []:
        if collision.get("status") in (None, "NO_CONFLICT"):
            continue
        number = collision.get("pr", "?")
        evidence = collision.get("evidence") or []
        ref = next((parse_ref(e) for e in evidence if parse_ref(e)), None)
        # As above: an unanchorable collision still reaches the summary comment.
        path, line = ref if ref else (_file_of(evidence[0]) if evidence else "", None)
        out.append({"path": path, "line": line,
                    "body": f"**⚠️ Potential cross-PR collision — "
                            f"{collision['status']} with #{number}**\n\n"
                            f"`{collision.get('symbol') or 'this code'}` — "
                            f"{collision.get('detail', '')}\n\n"
                            f"Also being changed in #{number}, which is still open. "
                            f"Neither PR's CI can see the other."})

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
