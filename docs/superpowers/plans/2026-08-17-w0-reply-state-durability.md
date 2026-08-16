# W0 — Reply State Durability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `--reply` genuinely resume the previous review on an ephemeral CI runner, instead of silently paying for a full re-review on every PR comment.

**Architecture:** The Claude Agent SDK replays a conversation from the CLI's own transcript store under `~/.claude/projects/`, which does not survive a GitHub Actions runner. The SDK also accepts a `session_store` adapter that receives a copy of every transcript line and is read back before a resume. A file-backed adapter writes the transcript into `sessions/<owner>/<repo>/pr-<n>/transcripts/`, making it one more phase artifact next to `findings.json`; the CI job caches `sessions/` between runs. When the transcript is missing but `findings.json` survived, the follow-up runs without `resume` and carries the previous findings in the prompt — cheaper than a full review, and free of any dependency on an undocumented on-disk layout.

**Tech Stack:** Python 3.10+, `claude-agent-sdk>=0.2.139`, pytest, GitHub Actions (`actions/cache@v4`). No new dependency.

**Spec:** `docs/superpowers/specs/2026-08-17-integrations-and-hardening.md` — section "W0 — Reply state durability".

## Global Constraints

- Core runtime dependencies stay exactly `claude-agent-sdk>=0.2.139` and `pyyaml`. No HTTP client, no database driver, no async test plugin.
- Review state remains files under `sessions/<owner>/<repo>/pr-<n>/` (spec invariant I2). No database.
- The review agent stays read-only: never add to `agent.BLOCKED_TOOLS`' escape hatches, never grant network tools (spec invariant I1).
- Tests use plain `pytest` functions. `pytest-asyncio` is NOT available — drive coroutines with `asyncio.run(...)` inside a synchronous test.
- Fake runners in existing tests have the signature `def runner(prompt, **kw)`, so new keyword arguments to `run_structured` are safe to add.
- Run the suite with `PYTHONPATH=src ./.venv/bin/python -m pytest`. `pyproject.toml` already sets `pythonpath = ["src", "."]`, so plain `./.venv/bin/python -m pytest` also works from the repo root.

## Sequencing prerequisite — read before starting

Task 2 edits `agent.run_structured`. The in-flight plan `docs/superpowers/plans/2026-08-16-multi-provider.md` **Task 4** rewrites that same function: it extracts a helper named `_options(...)` that builds `ClaudeAgentOptions`, changes `_query` to return the raw `ResultMessage`, and adds a `_capture(monkeypatch)` test helper to `tests/test_agent.py`.

**Task 1 of this plan is independent and may run at any time.** Tasks 2–5 must run **after** multi-provider Task 4 has landed, because Task 2 modifies `_options` and its tests reuse `_capture`. Verify before starting Task 2:

```bash
grep -n "_options" src/agent.py && grep -n "def _capture" tests/test_agent.py
```

Both must match. If they do not, stop and finish multi-provider Task 4 first — implementing Task 2 against today's inlined `ClaudeAgentOptions(...)` call guarantees a merge conflict in the same ten lines.

## File Structure

| File | Responsibility |
|---|---|
| `src/session_store.py` (create) | The `SessionStore` adapter: map a `SessionKey` to a JSONL file under the session directory; append with uuid de-duplication; load for resume. Nothing else. |
| `src/agent.py` (modify) | Accept `session_dir` and attach the adapter to the SDK options. One new parameter, one new line in `_options`. |
| `src/verify.py` (modify) | Pass `session_dir` through to the runner so the first review's transcript is captured. |
| `src/threads.py` (modify) | Decide the follow-up tier: resume when a transcript exists, otherwise carry previous findings in the prompt. |
| `.github/workflows/review.yml` (modify) | Persist `sessions/` between runs of the same PR. |
| `README.md` (modify) | Document the transcript artifact and the CI cache. |
| `tests/test_session_store.py` (create) | Adapter round-trip, de-duplication, unknown key, subagent subpath, corrupt line. |
| `tests/test_agent.py` (append) | The adapter is attached when `session_dir` is given, and absent when it is not. |
| `tests/test_verify.py` (append) | `run_verify` forwards `session_dir`. |
| `tests/test_threads.py` (append) | Tier selection: resume, stateless, and the error when neither is possible. |

---

### Task 1: File-backed session store adapter

**Files:**
- Create: `src/session_store.py`
- Test: `tests/test_session_store.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `FileSessionStore(session_dir: Path | str)` with attribute `root: Path` (equal to `session_dir / "transcripts"`), method `path_for(key: dict) -> Path`, coroutine `append(key: dict, entries: list[dict]) -> None`, coroutine `load(key: dict) -> list[dict] | None`. Task 2 constructs it; Task 4 calls `path_for` to test for an existing transcript.

Background the implementer needs: the SDK's `SessionKey` is a `TypedDict` with `project_key: str`, `session_id: str`, and an optional `subpath: str` (present only for subagent transcripts). Entries are opaque JSON dicts; most carry a `uuid` the SDK documents as an idempotency key. Only `append` and `load` are required — the SDK probes for the other methods at runtime and never uses `isinstance`, so no base class is needed.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_store.py`:

```python
import asyncio
import json

from session_store import FileSessionStore

KEY = {"project_key": "p", "session_id": "sess-1"}
SUB = {"project_key": "p", "session_id": "sess-1", "subpath": "subagents/agent-2"}


def _append(store, key, entries):
    asyncio.run(store.append(key, entries))


def _load(store, key):
    return asyncio.run(store.load(key))


def test_append_then_load_round_trips(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"},
                         {"type": "assistant", "uuid": "b"}])
    assert _load(store, KEY) == [{"type": "user", "uuid": "a"},
                                 {"type": "assistant", "uuid": "b"}]


def test_transcript_lands_under_the_session_dir(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    assert store.root == tmp_path / "transcripts"
    assert (tmp_path / "transcripts" / "sess-1.jsonl").exists()


def test_a_repeated_uuid_is_written_once(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    _append(store, KEY, [{"type": "user", "uuid": "a"},
                         {"type": "assistant", "uuid": "b"}])
    assert [e["uuid"] for e in _load(store, KEY)] == ["a", "b"]


def test_entries_without_a_uuid_are_always_appended(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "title"}])
    _append(store, KEY, [{"type": "title"}])
    assert len(_load(store, KEY)) == 2


def test_dedup_survives_a_new_store_instance(tmp_path):
    _append(FileSessionStore(tmp_path), KEY, [{"type": "user", "uuid": "a"}])
    _append(FileSessionStore(tmp_path), KEY, [{"type": "user", "uuid": "a"}])
    assert len(_load(FileSessionStore(tmp_path), KEY)) == 1


def test_load_of_an_unwritten_key_is_none(tmp_path):
    assert _load(FileSessionStore(tmp_path), KEY) is None


def test_a_subagent_transcript_is_a_separate_file(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    _append(store, SUB, [{"type": "user", "uuid": "z"}])
    assert store.path_for(KEY) != store.path_for(SUB)
    assert [e["uuid"] for e in _load(store, SUB)] == ["z"]


def test_a_subpath_cannot_escape_the_transcript_dir(tmp_path):
    store = FileSessionStore(tmp_path)
    escaping = {"project_key": "p", "session_id": "s", "subpath": "../../etc/passwd"}
    assert store.path_for(escaping).parent == store.root


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [{"type": "user", "uuid": "a"}])
    path = store.path_for(KEY)
    path.write_text(path.read_text() + "{not json\n")
    assert [e["uuid"] for e in _load(store, KEY)] == ["a"]


def test_appending_nothing_creates_no_file(tmp_path):
    store = FileSessionStore(tmp_path)
    _append(store, KEY, [])
    assert not store.root.exists()


def test_entries_are_json_serialisable_round_trip(tmp_path):
    store = FileSessionStore(tmp_path)
    nested = {"type": "assistant", "uuid": "a",
              "message": {"content": [{"type": "text", "text": "hi"}]}}
    _append(store, KEY, [nested])
    assert json.loads(store.path_for(KEY).read_text().strip()) == nested
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_session_store.py -v`
Expected: FAIL at collection with `ModuleNotFoundError: No module named 'session_store'`.

- [ ] **Step 3: Write the implementation**

Create `src/session_store.py`:

```python
"""Mirror agent transcripts into the session directory.

`resume=<session_id>` replays a conversation from the Claude Code CLI's own
transcript store under `~/.claude/projects/`. On an ephemeral CI runner that
directory is gone by the time someone replies on the PR, so the follow-up pass
degrades into a full re-review without saying so.

The SDK accepts a `session_store` adapter: it receives a copy of every
transcript line, and is read back before a resume. Pointing it at the session
directory makes the transcript one more phase artifact beside findings.json —
restore `sessions/` and the resume works on any machine.

Duck-typed on purpose: the SDK probes for methods rather than using
`isinstance`, so only the two required ones are implemented.
"""
import json
from pathlib import Path

TRANSCRIPTS = "transcripts"


def _safe(part: str) -> str:
    """One path segment: no separators, no traversal, never empty."""
    cleaned = "".join(c if c.isalnum() or c in "-_." else "_" for c in part)
    return cleaned.strip(".") or "_"


class FileSessionStore:
    """One JSONL file per session (plus one per subagent) under the session dir."""

    def __init__(self, session_dir: Path | str):
        self.root = Path(session_dir) / TRANSCRIPTS
        self._seen: dict[Path, set[str]] = {}

    def path_for(self, key: dict) -> Path:
        name = _safe(key["session_id"])
        subpath = key.get("subpath")
        if subpath:
            name = f"{name}__{_safe(subpath)}"
        return self.root / f"{name}.jsonl"

    async def append(self, key: dict, entries: list[dict]) -> None:
        """Mirror a batch of transcript lines, dropping uuids already written."""
        if not entries:
            return
        path = self.path_for(key)
        seen = self._uuids(path)
        fresh = []
        for entry in entries:
            uid = entry.get("uuid")
            if uid:
                if uid in seen:
                    continue
                seen.add(uid)
            fresh.append(entry)
        if not fresh:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            for entry in fresh:
                fh.write(json.dumps(entry) + "\n")

    async def load(self, key: dict) -> list[dict] | None:
        """Every entry for a key, or None when it was never written."""
        path = self.path_for(key)
        if not path.exists():
            return None
        return list(self._read(path))

    def _uuids(self, path: Path) -> set[str]:
        """Uuids already on disk for this key, read once per store instance."""
        if path not in self._seen:
            self._seen[path] = {e["uuid"] for e in self._read(path) if e.get("uuid")}
        return self._seen[path]

    def _read(self, path: Path):
        if not path.exists():
            return
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_session_store.py -v`
Expected: PASS, 11 tests.

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add src/session_store.py tests/test_session_store.py
git commit -m "feat: file-backed session store for agent transcripts"
```

---

### Task 2: Attach the store to the SDK options

**Files:**
- Modify: `src/agent.py` — the `run_structured` signature and the `_options` helper
- Test: `tests/test_agent.py` (append)

**Interfaces:**
- Consumes: `FileSessionStore` from Task 1; `_options` and the `_capture` test helper from multi-provider Task 4.
- Produces: `run_structured(..., session_dir: Path | str | None = None)`. `None` means no mirroring, so every existing call site keeps working unchanged. Tasks 3 and 4 pass it.

**Check the prerequisite first** — `grep -n "_options" src/agent.py` must match. See "Sequencing prerequisite" above.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent.py`:

```python
def test_a_session_dir_attaches_the_transcript_store(monkeypatch, tmp_path):
    seen = _capture(monkeypatch)
    agent.run_structured("hi", schema={"type": "object"}, session_dir=tmp_path)
    store = seen["options"].session_store
    assert store is not None
    assert store.root == tmp_path / "transcripts"


def test_no_session_dir_means_no_transcript_store(monkeypatch):
    seen = _capture(monkeypatch)
    agent.run_structured("hi", schema={"type": "object"})
    assert seen["options"].session_store is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_agent.py -k transcript_store -v`
Expected: FAIL with `TypeError: run_structured() got an unexpected keyword argument 'session_dir'`.

- [ ] **Step 3: Write the implementation**

In `src/agent.py`, add the import at the top of the module, after the standard-library imports:

```python
from session_store import FileSessionStore
```

Add the parameter to `run_structured`'s keyword-only signature, immediately after `resume`:

```python
                   session_dir: Path | str | None = None,
```

Extend its docstring with one line:

```
    `session_dir` mirrors the transcript into that directory so a later
    `resume=` works on a machine that never saw the original run.
```

Then set exactly one field on the `ClaudeAgentOptions` being constructed, beside the existing `resume=resume,`:

```python
        session_store=FileSessionStore(session_dir) if session_dir else None,
```

**Where that line goes depends on whether multi-provider Task 4 has landed**, and the prerequisite check at the top of this plan tells you which world you are in:

- **After the refactor (expected):** `_options(...)` builds the options object. Add `session_dir` to its parameter list, add the field to the `ClaudeAgentOptions(...)` call inside it, and pass `session_dir=session_dir` from `run_structured` at the `_options(...)` call site.
- **Before the refactor (only if you were told to proceed anyway):** `run_structured` constructs `ClaudeAgentOptions(...)` inline at `src/agent.py:79-92`. Add the field directly there. Expect a conflict when multi-provider Task 4 lands, resolved by moving this one line into `_options`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_agent.py -v`
Expected: PASS, including the multi-provider tests already in the file.

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agent.py tests/test_agent.py
git commit -m "feat: mirror agent transcripts into the session directory"
```

---

### Task 3: Capture the first review's transcript

**Files:**
- Modify: `src/verify.py:run_verify` — the `runner(...)` call
- Test: `tests/test_verify.py` (append)

**Interfaces:**
- Consumes: `run_structured(..., session_dir=...)` from Task 2.
- Produces: nothing new. Task 4 depends on the transcript this task starts writing.

Without this task there is nothing to resume from: `run_verify` is the pass whose conversation the follow-up replays.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_verify.py`:

```python
def test_run_verify_mirrors_the_transcript_into_the_session(tmp_path):
    captured = {}

    def runner(prompt, **kw):
        captured.update(kw)
        return AgentResult(data=dict(FINDINGS), session_id="sess-1", cost_usd=0.1,
                           num_turns=2, duration_ms=10)

    session_dir = tmp_path / "s"
    run_verify({"model": "m"}, tmp_path / "ws", session_dir, SNAPSHOT, [],
               runner=runner)
    assert captured["session_dir"] == session_dir
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_verify.py -k mirrors_the_transcript -v`
Expected: FAIL with `KeyError: 'session_dir'`.

- [ ] **Step 3: Write the implementation**

In `src/verify.py`, inside `run_verify`, add one argument to the `runner(...)` call, after `max_budget_usd`:

```python
        session_dir=session_dir,
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_verify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/verify.py tests/test_verify.py
git commit -m "feat: capture the verify transcript in the session directory"
```

---

### Task 4: Three-tier follow-up

**Files:**
- Modify: `src/threads.py` — `build_followup_prompt`, `run_followup`, plus two new helpers
- Test: `tests/test_threads.py` (append)

**Interfaces:**
- Consumes: `FileSessionStore.path_for` from Task 1; `run_structured(..., session_dir=...)` from Task 2.
- Produces: `load_previous_findings(session_dir: Path) -> dict | None`; `can_resume(session_dir: Path, session_id: str) -> bool`; `build_followup_prompt(replies, new_commits, previous_findings=None)` — the third parameter is keyword-optional so existing callers and tests are unaffected. `run_followup` keeps its signature and return type. The loader is named `load_previous_findings`, not `previous_findings`, so it does not shadow the prompt builder's parameter of that name.

The three tiers, most specific first: **resume** when a transcript file exists for the recorded session id; **stateless** when it does not but `findings.json` did survive, passing those findings in the prompt and omitting `resume`; **raise** when neither is available, leaving `src/run.py:224` to fall back to a full review as it does today.

Checking for the transcript file matters: a `session_id` in `verify-meta.json` whose transcript is gone would make the SDK fail mid-run and throw away the turn, instead of quietly taking the cheaper stateless path.

- [ ] **Step 1: Write the failing tests**

First add one import to the block at the top of `tests/test_threads.py`, beside the existing `from threads import (...)`:

```python
from session_store import FileSessionStore
```

Then append the rest to the end of the file:

```python
REPLY = [{"source": "conversation", "author": "dev1", "body": "ok", "path": None}]


def _seed(session_dir, *, session_id="sess-9", transcript=True, findings=True):
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "verify-meta.json").write_text(
        json.dumps({"session_id": session_id, "head_sha": "sha1"}))
    if findings:
        (session_dir / "findings.json").write_text(json.dumps(FINDINGS))
    if transcript:
        path = FileSessionStore(session_dir).path_for({"session_id": session_id})
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"type": "user", "uuid": "a"}) + "\n")


def _capture_runner(captured):
    def runner(prompt, **kw):
        captured.update(kw, prompt=prompt)
        return AgentResult(data=dict(FINDINGS), session_id="sess-10", cost_usd=0.05,
                           num_turns=3, duration_ms=10)
    return runner


def test_followup_resumes_when_the_transcript_survived(tmp_path):
    captured = {}
    _seed(tmp_path)
    run_followup({"model": "m"}, tmp_path / "ws", tmp_path, {"head_sha": "sha2"},
                 REPLY, [], runner=_capture_runner(captured))
    assert captured["resume"] == "sess-9"
    assert captured["session_dir"] == tmp_path
    assert "Previous findings" not in captured["prompt"]


def test_followup_goes_stateless_when_the_transcript_is_gone(tmp_path, capsys):
    captured = {}
    _seed(tmp_path, transcript=False)
    run_followup({"model": "m"}, tmp_path / "ws", tmp_path, {"head_sha": "sha2"},
                 REPLY, [], runner=_capture_runner(captured))
    assert captured["resume"] is None
    assert "Previous findings" in captured["prompt"]
    assert '"C1"' in captured["prompt"]
    assert "stateless" in capsys.readouterr().out


def test_followup_raises_when_no_state_survived_at_all(tmp_path):
    with pytest.raises(RuntimeError, match="no previous verify session"):
        run_followup({}, tmp_path / "ws", tmp_path, {}, REPLY, [],
                     runner=lambda *a, **kw: None)


def test_followup_is_stateless_when_only_findings_survived(tmp_path):
    captured = {}
    (tmp_path / "findings.json").write_text(json.dumps(FINDINGS))
    run_followup({"model": "m"}, tmp_path / "ws", tmp_path, {"head_sha": "sha2"},
                 REPLY, [], runner=_capture_runner(captured))
    assert captured["resume"] is None
    assert "Previous findings" in captured["prompt"]


def test_build_followup_prompt_omits_the_findings_block_by_default():
    prompt = build_followup_prompt(REPLY, [])
    assert "Previous findings" not in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_threads.py -k followup -v`
Expected: FAIL — `test_followup_resumes_when_the_transcript_survived` errors with `KeyError: 'session_dir'`, and the stateless tests raise `RuntimeError: no previous verify session to resume`.

- [ ] **Step 3: Write the implementation**

In `src/threads.py`, add the import beside the existing ones:

```python
from session_store import FileSessionStore
```

Add the two helpers next to `previous_session`:

```python
def load_previous_findings(session_dir: Path) -> dict | None:
    """The findings of the last review, or None if they did not survive."""
    try:
        return json.loads((session_dir / "findings.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def can_resume(session_dir: Path, session_id: str) -> bool:
    """True when the transcript for `session_id` is on disk next to the findings.

    A session id whose transcript is gone is worse than no session id: the SDK
    would fail the resume mid-run instead of taking the cheaper stateless path.
    """
    if not session_id:
        return False
    return FileSessionStore(session_dir).path_for({"session_id": session_id}).exists()
```

Change `build_followup_prompt` to take the optional findings and append one block. Its signature becomes:

```python
def build_followup_prompt(replies: list[dict], new_commits: list[dict],
                          previous_findings: dict | None = None) -> str:
```

and immediately before the final `return`, build the block:

```python
    carried = ""
    if previous_findings is not None:
        carried = ("\nPrevious findings — your own verdicts from the earlier "
                   "review, carried over because the session could not be "
                   "resumed. Treat them as your prior conclusions, re-check the "
                   "ones these replies and commits affect, and keep the rest:\n"
                   f"{json.dumps(previous_findings, indent=2)}\n")
```

then insert `{carried}` into the f-string, on its own line between the `Replies:` block and the `Re-check only what…` paragraph.

Replace the opening of `run_followup` — the three lines from `session_id = previous_session(session_dir)` through the `raise` — with:

```python
    session_id = previous_session(session_dir)
    resuming = can_resume(session_dir, session_id)
    carried = None if resuming else load_previous_findings(session_dir)
    if not resuming and carried is None:
        raise RuntimeError("no previous verify session to resume")
    mode = (f"resuming {session_id}" if resuming
            else "stateless (transcript gone, carrying previous findings)")
    print(f"[threads] follow-up: {mode}")
```

and change the `runner(...)` call: pass the prompt built with the carried findings, make `resume` conditional, and forward the session dir:

```python
    result = runner(
        build_followup_prompt(replies, new_commits, previous_findings=carried),
        schema=FINDINGS_SCHEMA,
        cwd=workspace,
        tools=tools,
        model=cfg.get("model"),
        system_prompt=SYSTEM_PROMPT,
        max_turns=cfg.get("max_turns", 40),
        max_budget_usd=cfg.get("max_budget_usd"),
        resume=session_id if resuming else None,
        session_dir=session_dir,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_threads.py -v`
Expected: PASS, including the pre-existing `test_run_followup_without_a_session_to_resume` (that fixture writes neither a transcript nor `findings.json`, so tier 3 still raises).

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/threads.py tests/test_threads.py
git commit -m "feat: fall back to a stateless follow-up when the transcript is gone"
```

---

### Task 5: Persist the session directory across CI runs

**Files:**
- Modify: `.github/workflows/review.yml`
- Modify: `README.md:53-56`
- Test: none — a workflow change is verified by running it, and the tier logic it feeds is already covered by Task 4.

**Interfaces:**
- Consumes: the transcript written by Tasks 2–3 and the tier logic from Task 4.
- Produces: nothing other tasks depend on. This is the last task.

Two changes to the workflow. `PR_NUMBER` currently lives in the `Review` step's `env:`, but the cache step needs it too, so it moves to job level. `actions/cache` entries are immutable, so the key carries `github.run_id` to make each save unique while `restore-keys` matches the most recent earlier run for the same PR.

- [ ] **Step 1: Move `PR_NUMBER` to job level**

In `.github/workflows/review.yml`, in the `review:` job, add an `env:` block directly under `runs-on: ubuntu-latest`:

```yaml
    env:
      PR_NUMBER: ${{ github.event.pull_request.number || github.event.issue.number }}
```

and delete the `PR_NUMBER:` line from the `Review` step's own `env:` block, leaving the other four variables there.

- [ ] **Step 2: Add the cache step**

Insert directly after the `actions/checkout@v6` step:

```yaml
      - name: Restore review state
        uses: actions/cache@v4
        with:
          path: sessions
          key: pr-sentinel-sessions-${{ env.PR_NUMBER }}-${{ github.run_id }}
          restore-keys: |
            pr-sentinel-sessions-${{ env.PR_NUMBER }}-
```

- [ ] **Step 3: Verify the workflow still parses**

Run:

```bash
./.venv/bin/python -c "import yaml,sys; d=yaml.safe_load(open('.github/workflows/review.yml')); j=d['jobs']['review']; print('PR_NUMBER at job level:', 'PR_NUMBER' in j.get('env',{})); print('steps:', [s.get('name') or s.get('uses') for s in j['steps']])"
```

Expected: `PR_NUMBER at job level: True`, and `Restore review state` appearing second in the step list.

- [ ] **Step 4: Document the new artifact**

In `README.md`, replace the sentence listing what lands in a session directory (currently "`findings.json`, `score.json`, `usage.json` (what the review cost), and `report.md`") with a version that names the transcript:

```markdown
Results land in `sessions/<owner>/<repo>/pr-<n>/`: `findings.json`, `score.json`,
`usage.json` (what the review cost), `report.md`, and `transcripts/` — the agent
conversation, kept so a later `--reply` resumes it instead of re-reviewing. Every
phase is skipped when its result already exists, so a re-run resumes rather than
paying twice; `--force` re-runs them.
```

Then, in the CI gate section, add after the workflow snippet:

```markdown
The job caches `sessions/` between runs of the same PR, so a comment triggers a
follow-up that resumes the previous conversation. Without that cache the runner
starts empty and every comment pays for a full review.
```

- [ ] **Step 5: Run the whole suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/review.yml README.md
git commit -m "fix: cache the session directory so --reply resumes in CI"
```

---

## Verification after all tasks

Local proof of the tier logic, which is what the CI change exists to enable:

```bash
./.venv/bin/python -m pytest -q
```

Expected: the pre-existing suite plus 19 new tests (11 + 2 + 1 + 5), all passing.

End-to-end proof belongs on a real PR: comment on one, and confirm the job log
contains `[threads] follow-up: resuming sess-…` rather than the full-review path,
and that the `followup` entry in `usage.json` costs materially less than the
`verify` entry from the same session. That log line is the spec's "logs that it
resumed rather than re-reviewed" acceptance criterion; it is emitted from
`threads.py`, where the tier is decided, and reaches the same job log.

## Out of scope for this plan

- Caching `~/.claude/projects/` — the whole point of the adapter is to stop depending on that layout.
- Any state stored on a GitHub comment (spec decision 3).
- Retention or pruning of old transcripts. `sessions/*` is already git-ignored, and Actions caches expire on their own.
- Surfacing the transcript in the dashboard.
