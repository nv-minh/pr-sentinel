# W2 — Evidence Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put each finding where the reviewer is already looking — anchored to the line it is about — and back a `BROKEN` verdict with a test the author can run instead of a paragraph they have to believe.

**Architecture:** A new `src/annotations.py` turns findings into `(path, line, body)` anchors, resolving each against the set of lines GitHub will actually accept — the ones inside the diff. Everything anchorable, including the documentation suggestions `src/remediate.py` already drafts, goes out as a **single** review event through `POST /pulls/{n}/reviews`; everything else falls back to the summary comment through the `leftover` mechanism that module already models. A second, cheap agent pass in `src/poc.py` runs only when the findings actually contain a `BROKEN` verdict, and returns a runnable failing test per broken behaviour — generated, clearly labelled as not executed, and never written into the repository.

**Tech Stack:** Python 3.10+, `gh` CLI, pytest. No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-17-integrations-and-hardening.md` — section "W2 — Evidence delivery".

## Sequencing prerequisite

This plan is last in the workstream order (W0 → W3 → W1 → W2) because Task 4 adds an agent pass whose cost belongs under the tier routing W1 establishes. It does not hard-depend on W1 or W3 to compile, but Task 5 reads `cfg["effort"]`, which W1 Task 5 introduces. Verify before Task 5:

```bash
grep -n "effort" src/agent.py
```

If it does not match, either land W1 first or drop `effort=cfg.get("effort")` from Task 5's runner call and note the omission in your report.

## Global Constraints

- Core runtime dependencies stay exactly `claude-agent-sdk>=0.2.139` and `pyyaml`. No new dependency.
- Review state stays as files under `sessions/<owner>/<repo>/pr-<n>/` (spec invariant I2). No database.
- The review agent stays read-only with no network egress (spec invariant I1). The PoC pass gets `READ_ONLY_TOOLS` and returns its test through the schema — it never writes a file, and its output is never applied to the repository.
- **A generated test that was not executed is an unverified claim** (spec invariant I4). Every PoC must be labelled as not run, in the same block that shows it. Do not add an execution path; that needs write and exec permission and would break I1.
- **GitHub only accepts an inline comment on a line inside the diff.** `callers_outside_diff` — per the README the most valuable finding type — is by definition outside it, so most of those cannot be inline. This is a constraint to model, not a bug to work around.
- **Nothing is dropped silently.** Anything that cannot be anchored, and anything past the annotation cap, appears in the summary comment, the way `prune.py` records every file it removes and `remediate.post_suggestions` already folds its `leftover` into the comment.
- Tests are plain `pytest` functions. Run with `./.venv/bin/python -m pytest` from the repo root; `pyproject.toml` sets `pythonpath = ["src", "."]`.
- TDD throughout: write the failing test, run it and see it fail for the stated reason, implement, see it pass.

**Concurrency warning.** This branch is shared. Check `git status` before you start; if files you are about to edit are already modified, stop and report rather than working on top of someone else's uncommitted state. Stage only the paths your task names — never `git add -A`.

## File Structure

| File | Responsibility |
|---|---|
| `src/annotations.py` (create) | Which lines of which files are in the diff; which findings can anchor to one; the cap and the split into inline vs leftover. Pure — no I/O, no network, like `src/score.py`. |
| `src/gh.py` (modify) | `run_gh` gains stdin; one new `post_review` for the batched reviews endpoint. |
| `src/remediate.py` (modify) | `post_suggestions`' posting loop becomes a pure `suggestion_comments` split, so doc fixes join the same batch instead of firing their own notifications. |
| `src/poc.py` (create) | Detect the repo's test framework deterministically, and run one gated agent pass that returns a failing test per broken behaviour. |
| `src/run.py` (modify) | Post the single review; run the PoC pass; fold both overflows into the summary comment. |
| `src/synthesize.py` (modify) | Render the PoC block in `report.md`. |
| `prsentinel.yml`, `README.md` (modify) | Two settings and their documentation. |
| `tests/test_annotations.py`, `tests/test_poc.py` (create); `tests/test_gh.py`, `tests/test_remediate.py`, `tests/test_run.py`, `tests/test_synthesize.py` (append) | |

---

### Task 1: Anchor findings to lines in the diff

**Files:**
- Create: `src/annotations.py`
- Test: `tests/test_annotations.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `MAX_INLINE: int`; `diff_lines(snapshot: dict) -> dict[str, set[int]]`; `parse_ref(ref: str) -> tuple[str, int] | None`; `candidates(findings: dict) -> list[dict]` where each item is `{"path": str, "line": int | None, "body": str}`; `split(candidates: list[dict], index: dict[str, set[int]], cap: int = MAX_INLINE) -> tuple[list[dict], list[dict]]` returning `(inline, leftover)`. Task 3 calls `diff_lines`, `candidates` and `split`.

The whole task is deciding *where a finding can legally go*. GitHub rejects an inline comment whose line is not part of the diff, so the module computes that set from the patches in the snapshot and resolves every candidate against it.

Anchoring rules, one per finding type:

| Finding | Anchor |
|---|---|
| claim with status `FAIL` or `PARTIAL` | its first `file:line` evidence — one comment per claim, not one per evidence entry |
| `callers_outside_diff` with risk `BROKEN` or `NEEDS_UPDATE` | `defined_at`, the changed symbol. The callers themselves are outside the diff by definition |
| contract with status other than `COMPATIBLE` | the file's first line in the diff; contracts carry a path, not a line |
| test with `assertion_quality` `WEAK` or `MISSING` | the file part of `target` (`"file:function"`), first line in the diff |

A candidate with `line: None` means "anchor anywhere in this file"; `split` resolves it to the file's lowest diff line. A candidate whose line is not in the diff becomes leftover rather than being moved somewhere plausible — a comment anchored to the wrong line is worse than one in the summary.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_annotations.py`:

```python
from annotations import MAX_INLINE, candidates, diff_lines, parse_ref, split

PATCH = ("@@ -1,3 +1,4 @@\n"
         " unchanged\n"
         "-old_line()\n"
         "+new_line()\n"
         "+another()\n"
         " tail\n")

SNAPSHOT = {"files": [
    {"filename": "src/a.py", "patch": PATCH},
    {"filename": "src/b.py", "patch": ""},
]}

FINDINGS = {
    "claims": [
        {"id": "C1", "status": "FAIL", "evidence": ["src/a.py:2"], "note": "not wired"},
        {"id": "C2", "status": "PASS", "evidence": ["src/a.py:3"], "note": ""},
        {"id": "C3", "status": "PARTIAL", "evidence": ["src/a.py:99"], "note": "half"},
    ],
    "callers_outside_diff": [
        {"symbol": "charge", "defined_at": "src/a.py:3", "callers": ["src/z.py:9"],
         "risk": "BROKEN", "note": "signature changed"},
        {"symbol": "ok", "defined_at": "src/a.py:2", "callers": [], "risk": "SAFE",
         "note": ""},
    ],
    "contracts": [
        {"kind": "API", "path": "src/a.py", "status": "BREAKING_API_CHANGE",
         "detail": "removed field"},
        {"kind": "API", "path": "src/a.py", "status": "COMPATIBLE", "detail": ""},
    ],
    "tests": [
        {"target": "src/a.py:test_charge", "assertion_quality": "MISSING",
         "uncovered_edge_cases": [], "note": "no test"},
        {"target": "src/a.py:test_ok", "assertion_quality": "STRONG",
         "uncovered_edge_cases": [], "note": ""},
    ],
}


def test_diff_lines_counts_added_and_context_lines():
    assert diff_lines(SNAPSHOT) == {"src/a.py": {1, 2, 3, 4}}


def test_a_file_without_a_patch_is_absent_from_the_index():
    assert "src/b.py" not in diff_lines(SNAPSHOT)


def test_diff_lines_handles_several_hunks():
    patch = "@@ -1,1 +1,1 @@\n+a\n@@ -10,1 +20,2 @@\n+b\n+c\n"
    assert diff_lines({"files": [{"filename": "x", "patch": patch}]}) == {"x": {1, 20, 21}}


def test_diff_lines_ignores_file_headers():
    patch = "--- a/x\n+++ b/x\n@@ -1,1 +1,1 @@\n+a\n"
    assert diff_lines({"files": [{"filename": "x", "patch": patch}]}) == {"x": {1}}


def test_parse_ref_splits_a_file_and_line():
    assert parse_ref("src/a.py:42") == ("src/a.py", 42)


def test_parse_ref_takes_the_last_colon():
    assert parse_ref("C:/win/a.py:7") == ("C:/win/a.py", 7)


def test_parse_ref_rejects_a_non_numeric_suffix():
    assert parse_ref("src/a.py:test_charge") is None
    assert parse_ref("src/a.py") is None
    assert parse_ref("") is None


def test_candidates_cover_a_failed_claim():
    got = [c for c in candidates(FINDINGS) if "C1" in c["body"]]
    assert got == [{"path": "src/a.py", "line": 2,
                    "body": got[0]["body"]}]
    assert "not wired" in got[0]["body"]


def test_candidates_skip_a_passing_claim():
    assert not any("C2" in c["body"] for c in candidates(FINDINGS))


def test_candidates_cover_a_broken_caller_at_its_definition():
    got = [c for c in candidates(FINDINGS) if "charge" in c["body"]]
    assert got[0]["path"] == "src/a.py" and got[0]["line"] == 3
    assert "src/z.py:9" in got[0]["body"]


def test_candidates_skip_a_safe_caller():
    assert not any("`ok`" in c["body"] for c in candidates(FINDINGS))


def test_a_contract_candidate_has_no_line():
    got = [c for c in candidates(FINDINGS) if "BREAKING_API_CHANGE" in c["body"]]
    assert got[0] == {"path": "src/a.py", "line": None, "body": got[0]["body"]}


def test_a_compatible_contract_is_not_a_candidate():
    assert not any("COMPATIBLE" in c["body"] for c in candidates(FINDINGS))


def test_a_weak_test_candidate_uses_the_file_part_of_target():
    got = [c for c in candidates(FINDINGS) if "MISSING" in c["body"]]
    assert got[0]["path"] == "src/a.py" and got[0]["line"] is None


def test_split_keeps_a_candidate_on_a_diff_line():
    index = diff_lines(SNAPSHOT)
    inline, leftover = split([{"path": "src/a.py", "line": 2, "body": "x"}], index)
    assert inline == [{"path": "src/a.py", "line": 2, "body": "x"}]
    assert leftover == []


def test_split_rejects_a_line_outside_the_diff():
    index = diff_lines(SNAPSHOT)
    inline, leftover = split([{"path": "src/a.py", "line": 99, "body": "x"}], index)
    assert inline == []
    assert leftover[0]["line"] == 99


def test_split_rejects_a_file_outside_the_diff():
    index = diff_lines(SNAPSHOT)
    inline, leftover = split([{"path": "src/gone.py", "line": 1, "body": "x"}], index)
    assert inline == [] and len(leftover) == 1


def test_split_resolves_a_lineless_candidate_to_the_first_diff_line():
    index = diff_lines(SNAPSHOT)
    inline, _ = split([{"path": "src/a.py", "line": None, "body": "x"}], index)
    assert inline[0]["line"] == 1


def test_split_caps_the_number_of_inline_comments():
    index = {"x": set(range(1, 100))}
    cands = [{"path": "x", "line": i, "body": "b"} for i in range(1, 40)]
    inline, leftover = split(cands, index, cap=5)
    assert len(inline) == 5
    assert len(leftover) == 34


def test_the_default_cap_is_exported():
    assert isinstance(MAX_INLINE, int) and MAX_INLINE > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_annotations.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'annotations'`.

- [ ] **Step 3: Write the implementation**

Create `src/annotations.py`:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_annotations.py -v`
Expected: PASS, 20 tests.

- [ ] **Step 5: Commit**

```bash
git add src/annotations.py tests/test_annotations.py
git commit -m "feat: resolve findings to lines GitHub will accept a comment on"
```

---

### Task 2: One review instead of N comments

**Files:**
- Modify: `src/gh.py` — `_run_gh_impl`, `run_gh`, and a new `post_review`
- Test: `tests/test_gh.py` — append

**Interfaces:**
- Consumes: nothing.
- Produces: `run_gh(args, *, json=True, stdin=None)` — the new parameter is keyword-only with a default, so every existing call is unaffected; `post_review(owner, repo, n, *, commit_id, comments, body="", gh=run_gh) -> bool`. Task 3 calls `post_review`.

`POST /repos/{owner}/{repo}/pulls/{n}/reviews` takes a nested `comments` array, which `gh api -f key=value` cannot express. `gh api --input -` reads a JSON body from stdin, so `run_gh` gains stdin support rather than the payload being contorted into flags or written to a temp file.

The review is submitted with `event: "COMMENT"` — not `REQUEST_CHANGES`. The gate already blocks merges through a check run; a bot that also formally requests changes on every risky PR fights branch protection rather than informing it.

Return `False` rather than raising when GitHub rejects the batch: the caller then folds everything into the summary comment, exactly as `post_inline_comment` already does for a single rejected anchor.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_gh.py`:

```python
import json as _json

from gh import post_review


def test_post_review_sends_one_batched_request():
    seen = {}

    def fake(args, **kw):
        seen["args"] = args
        seen["stdin"] = kw.get("stdin")
        return {"id": 1}

    ok = post_review("o", "r", 7, commit_id="sha1",
                     comments=[{"path": "a.py", "line": 2, "body": "x"}],
                     body="summary", gh=fake)
    assert ok is True
    assert "repos/o/r/pulls/7/reviews" in " ".join(seen["args"])
    payload = _json.loads(seen["stdin"])
    assert payload["commit_id"] == "sha1"
    assert payload["event"] == "COMMENT"
    assert payload["body"] == "summary"
    assert payload["comments"] == [{"path": "a.py", "line": 2, "side": "RIGHT",
                                    "body": "x"}]


def test_post_review_does_nothing_without_comments():
    def fail(*a, **kw):
        raise AssertionError("must not call the API with an empty batch")

    assert post_review("o", "r", 7, commit_id="s", comments=[], gh=fail) is False


def test_post_review_returns_false_when_github_rejects_it(capsys):
    def fake(args, **kw):
        raise RuntimeError("422 Unprocessable Entity")

    assert post_review("o", "r", 7, commit_id="s",
                       comments=[{"path": "a.py", "line": 2, "body": "x"}],
                       gh=fake) is False
    assert "review batch rejected" in capsys.readouterr().out


def test_run_gh_passes_stdin_to_the_subprocess(monkeypatch):
    seen = {}

    class _Proc:
        returncode = 0
        stdout = "{}"
        stderr = ""

    def fake_run(argv, **kw):
        seen.update(kw)
        return _Proc()

    monkeypatch.setattr("subprocess.run", fake_run)
    from gh import run_gh
    run_gh(["api", "x"], stdin='{"a": 1}')
    assert seen["input"] == '{"a": 1}'
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_gh.py -k "review or stdin" -v`
Expected: FAIL at collection with `ImportError: cannot import name 'post_review' from 'gh'`.

- [ ] **Step 3: Write the implementation**

In `src/gh.py`, add `import json as _json_mod` is unnecessary — the module already imports `json as _json`. Change the two transport functions:

```python
def _run_gh_impl(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True, input=stdin)


def run_gh(args: list[str], *, json: bool = True,
           stdin: str | None = None) -> dict | list:
    proc = _run_gh_impl(args + (["--jq", "."] if json else []), stdin)
```

leaving the rest of `run_gh` unchanged. Then append:

```python
def post_review(owner: str, repo: str, n: int, *, commit_id: str,
                comments: list[dict], body: str = "", gh=run_gh) -> bool:
    """Post every inline comment as ONE review event.

    N separate comment calls produce N notifications; a reviewer who gets pinged
    twelve times for one review learns to mute the bot. The event is COMMENT
    rather than REQUEST_CHANGES — the gate already blocks the merge through a
    check run, and a bot that also formally requests changes fights branch
    protection instead of informing it.

    Returns False when GitHub rejects the batch, so the caller can fall back to
    the summary comment.
    """
    if not comments:
        return False
    payload = {
        "commit_id": commit_id,
        "event": "COMMENT",
        "body": body,
        "comments": [{"path": c["path"], "line": c["line"], "side": "RIGHT",
                      "body": c["body"]} for c in comments],
    }
    try:
        gh(["api", f"repos/{owner}/{repo}/pulls/{n}/reviews", "-X", "POST",
            "--input", "-"], stdin=_json.dumps(payload))
        return True
    except RuntimeError as e:
        print(f"[gh] review batch rejected ({len(comments)} comment(s)): {e}")
        return False
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_gh.py -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS — `run_gh`'s new parameter is keyword-only with a default, so no existing caller changes.

- [ ] **Step 6: Commit**

```bash
git add src/gh.py tests/test_gh.py
git commit -m "feat: post inline comments as one batched review"
```

---

### Task 3: Deliver every anchorable finding inline

**Files:**
- Modify: `src/remediate.py` — replace `post_suggestions` with a pure `suggestion_comments`
- Modify: `src/run.py` — `_remediate` and the posting block
- Test: `tests/test_remediate.py`, `tests/test_run.py` — append and adjust

**Interfaces:**
- Consumes: `annotations.diff_lines` / `candidates` / `split` (Task 1); `gh.post_review` (Task 2).
- Produces: `remediate.suggestion_comments(patches: list[dict], snapshot: dict) -> tuple[list[dict], list[dict]]` returning `(comments, leftover_patches)`, where a comment is the same `{path, line, body}` shape `annotations` produces. `post_suggestions` is removed.

Today `remediate.post_suggestions` posts one API call per doc patch, and nothing else is ever inline. After this task there is exactly one review event carrying doc suggestions and finding annotations together, and one summary comment carrying everything that could not be anchored.

**`post_suggestions` is deleted, not left beside the new path.** Two ways to post the same thing is how the two drift. Its `suggestion_body` / `diff_block` / `comment_section` helpers all stay — only the posting loop moves out, and the split it computed becomes the pure function above.

- [ ] **Step 1: Write the failing tests**

In `tests/test_remediate.py`, run `grep -n post_suggestions tests/test_remediate.py` and delete every test that calls it, plus its entry in the file's `from remediate import (...)` line. Those tests asserted on the posting behaviour that no longer exists there; the four below assert the same splits against the pure function that replaces it. Add these:

```python
from remediate import suggestion_comments


def test_suggestion_comments_anchors_a_doc_inside_the_diff():
    comments, leftover = suggestion_comments([PATCH], SNAPSHOT)
    assert comments == [{"path": "docs/api.md", "line": 12,
                         "body": comments[0]["body"]}]
    assert "```suggestion" in comments[0]["body"]
    assert leftover == []


def test_a_doc_outside_the_diff_is_leftover():
    patch = {**PATCH, "path": "docs/elsewhere.md"}
    comments, leftover = suggestion_comments([patch], SNAPSHOT)
    assert comments == []
    assert leftover == [patch]


def test_a_patch_without_a_usable_line_hint_is_leftover():
    patch = {**PATCH, "line_hint": 0}
    comments, leftover = suggestion_comments([patch], SNAPSHOT)
    assert comments == [] and leftover == [patch]


def test_no_head_sha_makes_everything_leftover():
    comments, leftover = suggestion_comments([PATCH], {**SNAPSHOT, "head_sha": ""})
    assert comments == [] and leftover == [PATCH]
```

Append to `tests/test_run.py`:

```python
def test_findings_are_posted_as_one_review(tmp_path, monkeypatch):
    posted = []
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    monkeypatch.setattr("run.post_comment", lambda *a, **kw: True)
    monkeypatch.setattr("gh.post_review",
                        lambda *a, **kw: posted.append(kw) or True)
    monkeypatch.setattr("annotations.candidates",
                        lambda findings: [{"path": "src/a.py", "line": 1, "body": "x"}])
    monkeypatch.setattr("annotations.diff_lines", lambda snapshot: {"src/a.py": {1}})
    assert main(["demo/app", "7", "--skip-human"]) == 0
    assert len(posted) == 1
    assert posted[0]["comments"] == [{"path": "src/a.py", "line": 1, "body": "x"}]


def test_unanchorable_findings_reach_the_summary_comment(tmp_path, monkeypatch):
    bodies = []
    _patch_pipeline(monkeypatch, tmp_path, [], [])
    monkeypatch.setattr("run.post_comment",
                        lambda o, r, n, body, **kw: bodies.append(body) or True)
    monkeypatch.setattr("gh.post_review", lambda *a, **kw: True)
    monkeypatch.setattr("annotations.candidates",
                        lambda findings: [{"path": "gone.py", "line": 4, "body": "orphan"}])
    assert main(["demo/app", "7", "--skip-human"]) == 0
    assert "orphan" in bodies[0]
    assert "could not be anchored" in bodies[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_remediate.py tests/test_run.py -k "suggestion_comments or leftover or review or anchored" -v`
Expected: FAIL — `ImportError: cannot import name 'suggestion_comments' from 'remediate'`.

- [ ] **Step 3: Turn the doc posting loop into a pure split**

In `src/remediate.py`, delete `post_suggestions` and add in its place:

```python
def suggestion_comments(patches: list[dict], snapshot: dict) -> tuple[list[dict], list[dict]]:
    """Doc patches that can carry a ```suggestion block, as review comments.

    Returns `(comments, leftover)`. A comment is the `{path, line, body}` shape
    annotations.py uses, so both sources go out in one review. GitHub only
    accepts a suggestion on a line inside the diff, which is what leftover means.
    """
    in_diff = {f["filename"] for f in snapshot.get("files", [])}
    head_sha = snapshot.get("head_sha", "")
    comments, leftover = [], []
    for patch in patches:
        line = patch.get("line_hint")
        if (patch["path"] not in in_diff or not head_sha
                or not isinstance(line, int) or line < 1):
            leftover.append(patch)
            continue
        comments.append({"path": patch["path"], "line": line,
                         "body": suggestion_body(patch)})
    return comments, leftover
```

- [ ] **Step 4: Post one review from run.py**

In `src/run.py`, change `_remediate` so it returns the comments instead of posting them. Its signature becomes:

```python
def _remediate(review_cfg: dict, cfg: dict, owner: str, repo: str, num: int,
               workspace: Path, session_dir: Path, snapshot: dict, findings: dict,
               post: bool) -> tuple[str, list[dict]]:
```

every `return ""` becomes `return "", []`, and the delivery block at the end becomes:

```python
    comments: list[dict] = []
    leftover = patches
    if review_cfg.get("inline_suggestions", True):
        comments, leftover = remediate.suggestion_comments(patches, snapshot)
    if post and leftover and review_cfg.get("docs_fix_pr"):
        try:
            url = remediate.create_docs_fix_pr(owner, repo, num, leftover, snapshot, workspace)
            if url:
                return f"Documentation fixes opened as a follow-up PR: {url}", comments
        except RuntimeError as e:
            print(f"[run] docs-fix PR failed: {e}", file=sys.stderr)
    return remediate.comment_section(leftover), comments
```

At the `_remediate` call site, unpack the pair:

```python
            section, doc_comments = _remediate(review_cfg, cfg, owner, repo, int(num),
                                               session_dir / "workspace", session_dir,
                                               snapshot, findings, post)
            extra_comment = "\n\n".join(x for x in (extra_comment, section) if x)
```

and initialise `doc_comments: list[dict] = []` beside `extra_comment = ""` so the fixtures branch still defines it.

Then, immediately before the `if post:` block that posts the summary comment, add:

```python
        import annotations
        inline, orphans = annotations.split(
            doc_comments + annotations.candidates(findings),
            annotations.diff_lines(snapshot))
        if orphans:
            extra_comment = "\n\n".join(x for x in (extra_comment, _orphan_section(orphans)) if x)
        if post and inline:
            from gh import post_review
            if post_review(owner, repo, int(num), commit_id=snapshot.get("head_sha", ""),
                           comments=inline):
                print(f"Posted {len(inline)} inline comment(s) as one review.")
```

and add this helper beside `_remediate`:

```python
def _orphan_section(orphans: list[dict]) -> str:
    """Findings GitHub would not accept inline, folded into the summary comment."""
    blocks = "\n\n".join(f"**`{o['path']}`**\n\n{o['body']}" for o in orphans)
    return ("<details>\n\n<summary>Findings that could not be anchored to the diff "
            f"({len(orphans)})</summary>\n\n{blocks}\n\n</details>")
```

The order matters: `orphans` must be folded into `extra_comment` **before** `build_comment` is called, and the review must be posted whether or not any orphan exists.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_remediate.py tests/test_run.py -v`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/remediate.py src/run.py tests/test_remediate.py tests/test_run.py
git commit -m "feat: deliver every anchorable finding in one inline review"
```

---

### Task 4: A failing test for every broken behaviour

**Files:**
- Create: `src/poc.py`
- Test: `tests/test_poc.py`

**Interfaces:**
- Consumes: `agent.READ_ONLY_TOOLS`, `agent.record_usage`, `agent.run_structured`.
- Produces: `detect_framework(workspace: Path) -> str`; `broken(findings: dict) -> list[dict]`; `POC_SCHEMA: dict`; `draft_pocs(findings, cfg, workspace, session_dir, runner=...) -> list[dict]`; `comment_section(pocs: list[dict]) -> str`. Task 5 calls `broken`, `draft_pocs` and `comment_section`.

The module mirrors `src/remediate.py`: a second read-only agent pass, gated on the findings actually containing something broken, returning structured output that a deterministic module renders. Read `remediate.draft_patches` before writing this — it is the template.

**Detect the framework in code, not in the model.** A model guessing "probably jest" produces a test the author cannot run. The workspace is on disk; look.

**Label every PoC as not executed.** The agent cannot run it — running it needs write and exec permission, which invariant I1 forbids — so a generated test is an unverified claim under I4 and must say so where it is shown. The SDK does expose a `sandbox` setting, which is the door to executing these later; that is a separate spec, not a thing to sneak in here.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_poc.py`:

```python
import json

from agent import AgentResult
from poc import POC_SCHEMA, broken, comment_section, detect_framework, draft_pocs

FINDINGS = {
    "impact": [
        {"requirement": "retry twice", "requirement_source": "ABC-1", "impact": "BROKEN",
         "area": "payment", "paths": ["src/pay.py"], "detail": "only retries once"},
        {"requirement": "log it", "requirement_source": "ABC-1", "impact": "CHANGED",
         "area": "infra", "paths": ["src/log.py"], "detail": ""},
    ],
    "callers_outside_diff": [
        {"symbol": "charge", "defined_at": "src/pay.py:3", "callers": ["src/z.py:9"],
         "risk": "BROKEN", "note": "signature changed"},
        {"symbol": "ok", "defined_at": "src/pay.py:8", "callers": [], "risk": "SAFE",
         "note": ""},
    ],
}

CLEAN = {"impact": [], "callers_outside_diff": []}

POC = {"target": "src/pay.py", "framework": "pytest",
       "test_code": "def test_retries_twice():\n    assert charge() == 2",
       "why_it_fails": "charge() retries once, so it returns 1"}


def _runner(data):
    return lambda prompt, **kw: AgentResult(data=data, session_id="s", cost_usd=0.02,
                                            num_turns=2, duration_ms=20)


def test_broken_finds_broken_impact_and_callers():
    got = broken(FINDINGS)
    assert len(got) == 2
    assert "retry twice" in got[0]["what"]
    assert "charge" in got[1]["what"]


def test_broken_ignores_healthy_findings():
    assert broken(CLEAN) == []
    assert not any("log it" in b["what"] for b in broken(FINDINGS))


def test_detect_framework_finds_pytest(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    assert detect_framework(tmp_path) == "pytest"


def test_detect_framework_finds_pytest_from_conftest(tmp_path):
    (tmp_path / "conftest.py").write_text("")
    assert detect_framework(tmp_path) == "pytest"


def test_detect_framework_finds_vitest(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"devDependencies": {"vitest": "^1.0.0"}}))
    assert detect_framework(tmp_path) == "vitest"


def test_detect_framework_finds_jest(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"devDependencies": {"jest": "^29"}}))
    assert detect_framework(tmp_path) == "jest"


def test_detect_framework_finds_go_test(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n")
    assert detect_framework(tmp_path) == "go test"


def test_detect_framework_survives_broken_package_json(tmp_path):
    (tmp_path / "package.json").write_text("{not json")
    assert detect_framework(tmp_path) == "unknown"


def test_detect_framework_on_an_empty_workspace(tmp_path):
    assert detect_framework(tmp_path) == "unknown"


def test_draft_pocs_is_skipped_when_nothing_is_broken(tmp_path):
    def fail(*a, **kw):
        raise AssertionError("must not pay for an agent pass with no broken findings")

    assert draft_pocs(CLEAN, {"model": "m"}, tmp_path, tmp_path, runner=fail) == []


def test_draft_pocs_persists_and_returns(tmp_path):
    pocs = draft_pocs(FINDINGS, {"model": "m"}, tmp_path, tmp_path,
                      runner=_runner({"tests": [POC]}))
    assert pocs == [POC]
    assert json.loads((tmp_path / "poc.json").read_text()) == [POC]
    assert json.loads((tmp_path / "usage.json").read_text())[0]["phase"] == "poc"


def test_draft_pocs_drops_an_entry_without_code(tmp_path):
    bad = {**POC, "test_code": ""}
    assert draft_pocs(FINDINGS, {"model": "m"}, tmp_path, tmp_path,
                      runner=_runner({"tests": [bad, POC]})) == [POC]


def test_the_schema_requires_the_failure_reason():
    item = POC_SCHEMA["properties"]["tests"]["items"]
    assert set(item["required"]) == {"target", "framework", "test_code", "why_it_fails"}


def test_comment_section_labels_the_test_as_not_executed():
    section = comment_section([POC])
    assert "not been executed" in section
    assert "def test_retries_twice" in section
    assert "charge() retries once" in section


def test_comment_section_is_empty_without_pocs():
    assert comment_section([]) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_poc.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'poc'`.

- [ ] **Step 3: Write the implementation**

Create `src/poc.py`:

```python
"""Turn "this is BROKEN" into a test the author can run.

A reviewer reading "the retry only fires once" has to take it on faith. A
failing test with concrete inputs is the same claim, checkable in ten seconds.
This is the same move remediate.py makes for documentation: a second read-only
agent pass, gated so it costs nothing on a clean review, returning structured
output that a deterministic module renders.

Two rules it must keep. The framework is detected from the workspace, never
guessed by the model — a model that picks jest for a pytest repo produces a test
nobody can run. And every generated test is labelled as not executed: the agent
has no way to run it, so under the project's own standard it is an unverified
claim and has to say so.
"""
import json
from pathlib import Path

from agent import READ_ONLY_TOOLS, record_usage
from agent import run_structured as _default_runner

POC_SCHEMA = {
    "type": "object",
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "file the test covers"},
                    "framework": {"type": "string"},
                    "test_code": {"type": "string",
                                  "description": "a complete, runnable failing test"},
                    "why_it_fails": {"type": "string",
                                     "description": "the concrete input and the wrong output"},
                },
                "required": ["target", "framework", "test_code", "why_it_fails"],
            },
        },
    },
    "required": ["tests"],
}

SYSTEM_PROMPT = (
    "You write the smallest failing test that demonstrates a specific broken "
    "behaviour. You read the real code first and use the project's existing test "
    "conventions, imports and helpers. The test must fail against the current "
    "code for the stated reason — never write a test that passes."
)


def detect_framework(workspace: Path) -> str:
    """The repo's test runner, read off disk. 'unknown' when nothing matches."""
    if (workspace / "conftest.py").exists() or (workspace / "pytest.ini").exists():
        return "pytest"
    package = workspace / "package.json"
    if package.exists():
        try:
            data = json.loads(package.read_text())
        except (OSError, json.JSONDecodeError):
            return "unknown"
        deps = {**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})}
        for name in ("vitest", "jest", "mocha"):
            if name in deps:
                return name
    pyproject = workspace / "pyproject.toml"
    if pyproject.exists():
        try:
            if "pytest" in pyproject.read_text():
                return "pytest"
        except OSError:
            pass
    if (workspace / "go.mod").exists():
        return "go test"
    if (workspace / "Cargo.toml").exists():
        return "cargo test"
    return "unknown"


def broken(findings: dict) -> list[dict]:
    """Behaviours a review called broken, as `{what, where}` pairs."""
    out = []
    for impact in findings.get("impact") or []:
        if impact.get("impact") == "BROKEN":
            out.append({"what": f"{impact.get('requirement', '?')} — "
                                f"{impact.get('detail', '')}",
                        "where": ", ".join(impact.get("paths") or []) or "?"})
    for caller in findings.get("callers_outside_diff") or []:
        if caller.get("risk") == "BROKEN":
            out.append({"what": f"`{caller.get('symbol', '?')}` — "
                                f"{caller.get('note', '')}",
                        "where": caller.get("defined_at", "?")})
    return out


def build_prompt(items: list[dict], framework: str) -> str:
    listed = "\n".join(f"- {b['what']} (in {b['where']})" for b in items)
    return f"""
A review found these behaviours broken:

{listed}

This repository's test framework is: {framework}

For each one, write the smallest test that FAILS against the current code and
demonstrates the break. Read the real code and the existing tests first, and
match their conventions, imports and helpers so the author can paste the test in
and run it. State in `why_it_fails` the concrete input and the wrong output it
produces. If you cannot write a test that genuinely fails, skip that item rather
than inventing one.
""".strip()


def draft_pocs(findings: dict, cfg: dict, workspace: Path, session_dir: Path,
               runner=_default_runner) -> list[dict]:
    """One failing test per broken behaviour. Writes poc.json, returns the list."""
    items = broken(findings)
    if not items:
        return []
    result = runner(
        build_prompt(items, detect_framework(Path(workspace))),
        schema=POC_SCHEMA,
        cwd=workspace,
        tools=READ_ONLY_TOOLS,
        model=cfg.get("model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=cfg.get("max_turns", 30),
        effort=cfg.get("effort"),
        provider=cfg.get("provider"),
    )
    pocs = [p for p in result.data.get("tests") or []
            if p.get("test_code") and p.get("target")]

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "poc.json").write_text(json.dumps(pocs, indent=2))
    record_usage(session_dir, "poc", result)
    return pocs


def comment_section(pocs: list[dict]) -> str:
    """The generated tests, folded into the review comment and the report."""
    if not pocs:
        return ""
    blocks = "\n\n".join(
        f"**`{p['target']}`** — {p.get('why_it_fails', '')}\n\n"
        f"```{p.get('framework', '')}\n{p['test_code']}\n```" for p in pocs)
    return ("<details>\n\n<summary>Failing tests that reproduce the broken behaviour "
            f"({len(pocs)})</summary>\n\nThese tests were generated from the review and "
            "have **not been executed** — run them locally to confirm the break.\n\n"
            f"{blocks}\n\n</details>")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_poc.py -v`
Expected: PASS, 15 tests.

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/poc.py tests/test_poc.py
git commit -m "feat: generate a failing test for every broken behaviour"
```

---

### Task 5: Wire the PoC pass into a review

**Files:**
- Modify: `src/run.py` — the phase block
- Modify: `src/synthesize.py` — `build_report`
- Modify: `src/autoreview_config.py`, `prsentinel.yml`, `README.md`
- Test: `tests/test_run.py`, `tests/test_synthesize.py` — append

**Interfaces:**
- Consumes: `poc.broken`, `poc.draft_pocs`, `poc.comment_section` (Task 4).
- Produces: nothing further; this is the last task.

The pass runs after scoring, alongside `_remediate`, and is skipped entirely when nothing is broken — so a clean review pays nothing. Its result is cached as `poc.json` like every other phase, so a re-run resumes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_synthesize.py`:

```python
def test_report_includes_generated_tests(tmp_path):
    (tmp_path / "poc.json").write_text(json.dumps(
        [{"target": "src/pay.py", "framework": "pytest",
          "test_code": "def test_x(): assert False", "why_it_fails": "returns 1"}]))
    report = build_report(SNAPSHOT, CLAIMS, FINDINGS, [], tmp_path)
    assert "not been executed" in report
    assert "def test_x" in report


def test_report_has_no_test_section_without_pocs(tmp_path):
    assert "not been executed" not in build_report(SNAPSHOT, CLAIMS, FINDINGS, [], tmp_path)
```

`tests/test_synthesize.py` will need `import json` if it does not already have it.

Append to `tests/test_run.py`:

```python
def test_a_clean_review_never_pays_for_the_poc_pass(tmp_path, monkeypatch):
    _patch_pipeline(monkeypatch, tmp_path, [], [])

    def fail(*a, **kw):
        raise AssertionError("draft_pocs must not run without a BROKEN finding")

    monkeypatch.setattr("poc.draft_pocs", fail)
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0


def test_a_broken_finding_triggers_the_poc_pass(tmp_path, monkeypatch):
    called = []
    broken_findings = {**FINDINGS, "callers_outside_diff": [
        {"symbol": "charge", "defined_at": "a.py:1", "callers": [], "risk": "BROKEN",
         "note": "n"}]}
    _patch_pipeline(monkeypatch, tmp_path, [], [])

    def fake_verify(cfg, workspace, session_dir, snapshot, claims, ticket=None, runner=None):
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "findings.json").write_text(json.dumps(broken_findings))
        return dict(broken_findings)

    monkeypatch.setattr("verify.run_verify", fake_verify)
    monkeypatch.setattr("poc.draft_pocs",
                        lambda *a, **kw: called.append(1) or [])
    assert main(["demo/app", "7", "--no-post", "--skip-human"]) == 0
    assert called == [1]
```

Drop `ticket=None` from `fake_verify` if W3 has not landed — it must match whatever `verify.run_verify` accepts.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_run.py -k poc tests/test_synthesize.py -k generated -v`
Expected: FAIL — `ModuleNotFoundError` on the `poc.draft_pocs` monkeypatch target, and no test section in the report.

- [ ] **Step 3: Render the tests in the report**

In `src/synthesize.py`, add `import poc` and insert immediately before the `"## Confirmation log"` block in `build_report`:

```python
    try:
        pocs = json.loads((session_dir / "poc.json").read_text())
    except (OSError, json.JSONDecodeError):
        pocs = []
    section = poc.comment_section(pocs)
    if section:
        lines += ["", section]
```

Add `import json` to `src/synthesize.py` if it is not already imported.

- [ ] **Step 4: Run the pass from run.py**

In `src/run.py`, add this immediately after the `_remediate` call site, inside the same `if args.fixtures is None:` block:

```python
            if review_cfg.get("poc_tests", True) and poc.broken(findings):
                pocs = _load_or_skip("poc.json", session_dir, args.force)
                if pocs is None:
                    try:
                        pocs = poc.draft_pocs(findings, cfg, session_dir / "workspace",
                                              session_dir)
                    except RuntimeError as e:
                        print(f"[run] PoC test drafting failed: {e}", file=sys.stderr)
                        pocs = []
                extra_comment = "\n\n".join(
                    x for x in (extra_comment, poc.comment_section(pocs)) if x)
```

and add `import poc` to the phase-module import group.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_run.py tests/test_synthesize.py -v`
Expected: PASS.

- [ ] **Step 6: Add the settings**

In `src/autoreview_config.py`, add to `DEFAULTS` beside `inline_suggestions`:

```python
    "poc_tests": True,          # generate a failing test for each BROKEN finding
    "max_inline_comments": 20,  # per review; the rest go in the summary comment
```

In `prsentinel.yml`, beside `inline_suggestions`:

```yaml
poc_tests: true             # a failing test for each BROKEN finding (only runs when
                            # a review finds one, so a clean PR pays nothing)
max_inline_comments: 20     # per review; anything past this goes in the summary
```

Have Task 3's `annotations.split(...)` call read the cap:

```python
            annotations.diff_lines(snapshot),
            cap=review_cfg.get("max_inline_comments", annotations.MAX_INLINE))
```

- [ ] **Step 7: Document it**

Add to the README, after the "What it checks" table:

```markdown
### Where the findings land

Findings that point at a line inside the diff are posted as **one** review event
anchored to those lines — documentation fixes as one-click `suggestion` blocks,
everything else as a comment on the line it is about. Anything GitHub will not
accept inline goes into the summary comment under "Findings that could not be
anchored to the diff". That includes most `callers_outside_diff` results, which
are by definition about code the PR did not touch.

When a review finds something `BROKEN`, a second pass writes the smallest test
that reproduces it, using the framework detected from the repository. Those tests
are **generated and not executed** — they are shown so the author can run them,
never applied to the branch.
```

- [ ] **Step 8: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/run.py src/synthesize.py src/autoreview_config.py prsentinel.yml README.md \
        tests/test_run.py tests/test_synthesize.py
git commit -m "feat: run the PoC pass and surface its tests in the review"
```

---

## Verification after all tasks

```bash
./.venv/bin/python -m pytest -q
```

Expected: the pre-existing suite plus 49 new tests — 20 (anchoring) + 4 (batched review) + 6 (delivery) + 15 (PoC) + 4 (wiring) — all passing, with `tests/test_remediate.py`'s `post_suggestions` tests replaced rather than simply deleted.

Behavioural checks against a real PR:

1. A PR with a failed claim whose evidence points inside the diff produces exactly **one** review event in the timeline, not several — check the PR's "Files changed" tab shows the comment on the right line.
2. A `callers_outside_diff` finding appears in the summary comment under "could not be anchored", not inline.
3. A PR with more than `max_inline_comments` anchorable findings posts the cap inline and the remainder in the summary — the count in the summary heading must match what is missing.
4. A `BROKEN` finding yields a test in the correct framework for the repo, in a block that says it was not executed.
5. A clean PR records no `poc` entry in `usage.json`.

## Out of scope for this plan

- Executing the generated tests. That needs write and exec permission, which invariant I1 forbids. The SDK's `sandbox` setting is the door to doing it later, behind its own spec.
- **PoC tests for `RISK` findings, which the spec's heading names alongside `BROKEN`.** Deliberately excluded, because the two cannot both hold: a `RISK` verdict means the review could not establish that the behaviour is broken, so a test reproducing it either fails — in which case the finding was `BROKEN` and was mislabelled — or passes, which violates this pass's own rule that it must never write a passing test. Widening the gate would produce green tests presented as evidence of a problem, which is worse than no evidence. If `RISK` deserves generated code, it wants a characterization test with its own design, not this one.
- Writing generated tests into the branch, or opening a PR with them — `docs_fix_pr` exists for documentation because a doc fix is mechanical; a test is a design decision the author owns.
- `REQUEST_CHANGES` reviews. The gate blocks merges through its check run; a bot that also formally requests changes fights branch protection instead of informing it.
- Resolving or replying to existing review threads.
- Anchoring to the old side of the diff (`side: LEFT`). Every finding here is about the code as it now stands.
