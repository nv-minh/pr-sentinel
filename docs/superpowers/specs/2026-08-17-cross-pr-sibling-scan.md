# Spec — Cross-PR sibling scan

**Date:** 2026-08-17
**Status:** design approved, ready for an implementation plan

## Problem

Two pull requests are open. PR A changes the signature of `createInvoice()`.
PR B, opened by somebody else the same afternoon, calls `createInvoice()` from a
file PR A never touches. Git reports no conflict — no line is contested. Both
CIs are green, because each ran against a `main` that did not contain the other.
Both merge. `main` breaks.

This is a semantic conflict, and nothing in PR Sentinel currently looks for it.
Every phase of a review reasons about **one** pull request against **one** base
commit. The most valuable existing check, `callers_outside_diff`, searches the
whole repository for callers this PR did not touch — but "the whole repository"
means the PR head checkout, which contains no other open branch. A caller that
exists only in a sibling PR is invisible to it by construction.

## Scope

This spec implements **one** mechanism: a sibling scan performed while both pull
requests are still open, so the collision is reported on the first review rather
than after a merge.

**Non-goals**, named so a reader does not look for them:

- **Post-merge re-trigger.** Re-running open PRs' reviews when a sibling merges
  is a CI-scheduling change, not a review-logic change. It is complementary and
  is left for a separate spec.
- **Virtual merge.** Merging two branches on a runner and type-checking the
  result requires build tooling per language. Out of scope.
- **Cross-repository siblings.** Only open PRs of the same repository are
  scanned.
- **Re-scanning during the reply pass.** `--reply` carries the previous
  `cross_pr` verdicts forward rather than re-fetching siblings (see "The reply
  pass").

## Invariants preserved

The four invariants from `2026-08-17-integrations-and-hardening.md` all hold.
Two of them constrain this design directly.

- **I1 — the agent reads; modules write.** Sibling data is fetched by a
  deterministic Python module through the `gh` CLI. No new tool is granted to
  the agent, no network egress is added, `agent.py` is not touched.
- **I3 — untrusted text is data.** Sibling PR titles and patch text are written
  by people outside the trust boundary and enter the prompt inside
  `<<<UNTRUSTED …>>>` blocks. This is the first time raw **diff text** enters
  any prompt in this project — the current PR's own patches never do; the agent
  reads that code from disk.

An explicit fifth rule for this feature:

- **I5 — a speculative finding never blocks a merge.** A collision is a claim
  about a branch that may never merge, or may merge after this PR has already
  been fixed. It can take the gate to `warn`; it can never take it to `fail`.

## Rejected alternatives

**An agent-callable `inspect_sibling_prs` tool** (an in-process SDK MCP server,
the shape the feature was originally proposed in). Rejected: the overlap set is
computable exactly, for free, in Python. Paying tokens and turns for the model to
discover a set we already know is a worse trade, and it would make `agent.py` —
today a single narrow integration point, `run_structured()` — carry tool
registration plus a tool-use path that has to work on prompt-mode gateways
(`deepseek`, `glm`) where a repair turn already exists. If prefetch later proves
too coarse, a tool can be layered on top reading the cached `siblings.json`, with
no rewrite and still no network for the agent.

**Writing sibling patches into the workspace for the agent to `Grep`.**
Rejected: it breaks a load-bearing property. `score.py` and `annotations.py`
both trust that a `file:line` in evidence names a real file of the repository
under review. Files that are not part of the repo, sitting inside the checkout,
invite evidence pointing at them.

## Architecture

Facts are deterministic; verdicts are judged.

```
snapshot.json ──┐
                ├─► siblings.fetch_siblings()  ──► siblings.json
gh GraphQL ─────┘        Python, no LLM               │
                                                      ▼
                         verify.build_verify_prompt(…, siblings=…)
                                                      │
                                                      ▼
                                        findings["cross_pr"]
                                                      │
                 ┌──────────────┬────────────────────┬──────────────┐
                 ▼              ▼                    ▼              ▼
             score.py     synthesize.py       annotations.py   web/metrics.py
          (medium + label) (two tables)      (inline comment)  (phase node + tab)
```

`siblings.json` is rendered in the report **whether or not** the agent finds a
collision. "Scanned 12 open PRs, 2 overlap, no conflict found" is a result;
silence is indistinguishable from never having looked.

The phase runs after **Ticket** and before **Describe**, and obeys the pipeline's
resume rule: `_load_or_skip("siblings.json", session_dir, args.force)`.

## `src/siblings.py`

New module. Fetch and overlap detection only — prompt rendering lives in
`verify.py` next to `_requirement_section`, which it mirrors.

```python
def our_paths(snapshot: dict) -> set[str]
def overlap_of(ours: set[str], theirs: set[str],
               sensitive: list[str]) -> tuple[str, list[str]]
def rank(cands: list[dict], limit: int) -> list[dict]
def fetch_siblings(snapshot: dict, session_dir: Path, cfg: dict, gate: dict, *,
                   gh=_default_gh) -> dict
```

`cfg` is the `siblings:` block of `prsentinel.yml`, `gate` is the `gate:` block.
`fetch_siblings` never raises, exactly like `tickets.fetch_tickets`.

### One GraphQL query

```graphql
query($owner:String!,$repo:String!){
  repository(owner:$owner,name:$repo){
    pullRequests(states:OPEN, first:50,
                 orderBy:{field:UPDATED_AT, direction:DESC}){
      nodes{
        number title isDraft baseRefName headRefName updatedAt url
        author{login}
        files(first:100){ nodes{ path } }
      }
    }
  }
}
```

One call, not one per PR. `first: 50` bounds a repository with hundreds of open
PRs; `UPDATED_AT desc` keeps the survivors the ones somebody is actually working
on. When 50 nodes come back, or any `files` list returns 100 entries,
`truncated` is set and `snapshot.py`'s existing warning style is followed:
`print("[siblings] warning: …", file=sys.stderr)`.

### Selection

1. Drop this PR itself (`number == snapshot["pr"]`).
2. Drop drafts unless `cfg["include_drafts"]`.
3. Drop any PR whose `baseRefName != snapshot["base"]` — two PRs targeting
   different bases do not land in the same tree.
4. Drop bot authors (`login` ends with `[bot]`).
5. `our_paths(snapshot)` = filenames of `snapshot["files"]` plus
   `snapshot["pruned"]` entries with `dropped=False`, minus anything
   `prune.classify()` names. The sibling's paths from the GraphQL result are
   filtered through `prune.classify()` the same way — that side has not been
   pruned by anything yet, and it is where the filter earns its keep. Two PRs
   both bumping `package-lock.json` are not a semantic conflict.
6. `overlap_of` returns `("file", paths)` when the path sets intersect;
   otherwise `("module", paths)` when their `dirname` sets intersect **and** that
   directory matches `gate["sensitive_areas"]` (via `score._matches`) or holds a
   file `tiers._is_contract` accepts; otherwise `("", [])`, meaning not a
   sibling.
7. `rank` orders `file` overlaps before `module` ones, more overlapping paths
   first, more recently updated first, then truncates to `cfg["max_siblings"]`.
8. For each survivor: `gh api repos/{owner}/{repo}/pulls/{n}/files --paginate`,
   keep only the overlapping paths, then
   `prune.prune_files(files, max_patch_lines=60, max_total_lines=300)` — the
   existing, tested trimmer, at tighter limits.

Worst case added to the prompt: 3 siblings × 300 patch lines. Worst case added
to GitHub: 1 GraphQL call + 3 REST calls. No overlap means **zero** tokens and a
verify prompt byte-identical to today's.

### `siblings.json`

```json
{
  "scanned": 12,
  "truncated": false,
  "skipped": "",
  "siblings": [
    {
      "pr": 456,
      "title": "Split invoice creation into a service",
      "author": "dev_b",
      "url": "https://github.com/acme/app/pull/456",
      "base": "main",
      "head": "feat/invoice-service",
      "updated_at": "2026-08-16T09:12:33Z",
      "overlap": "file",
      "overlap_paths": ["src/services/payment/invoice.py"],
      "files": [{"filename": "src/services/payment/invoice.py",
                 "status": "modified", "additions": 12, "deletions": 3,
                 "patch": "@@ -18,7 +18,7 @@ …"}],
      "pruned": []
    }
  ]
}
```

`scanned` is how many open PRs the query returned, before filtering — it is what
lets the report say "we looked at 12". `skipped` is a sentence for the report,
non-empty exactly when nothing was fetched — the same contract as `ticket.json`.

## `src/run.py`

```python
from siblings import fetch_siblings          # inside the non-fixtures branch

siblings = None
if review_cfg.get("siblings", {}).get("enabled", True):
    siblings = _load_or_skip("siblings.json", session_dir, args.force)
    if siblings is None:
        siblings = fetch_siblings(snapshot, session_dir,
                                  review_cfg.get("siblings") or {},
                                  review_cfg.get("gate") or {})
…
findings = run_verify(cfg, workspace, session_dir, snapshot, claims,
                      ticket=ticket, siblings=siblings)
```

Placed directly after the ticket phase, so `siblings` is also in scope for the
`--reply` branch's `run_verify` fallback, which passes it too. `siblings=None` —
the disabled case and every pre-existing caller — is indistinguishable
downstream from "no overlap".

## Configuration

```yaml
siblings:
  enabled: true         # false skips the phase entirely: no gh call, no tokens
  max_siblings: 3
  include_drafts: false
```

`autoreview_config.DEFAULTS` gains that block; `load_config` merges it like
`jira`; `validate_config` raises `ValueError` when `enabled`/`include_drafts` are
not booleans or `max_siblings` is not a positive integer (checking `bool` before
`int`, as `max_inline_comments` already does).

## `src/verify.py`

### Schema

```python
CROSS_PR_STATUS = ["NO_CONFLICT", "SEMANTIC_CONFLICT", "DUPLICATE_WORK",
                   "MERGE_ORDER_RISK"]

"cross_pr": _array({
    "pr": {"type": "integer", "description": "the other open PR's number"},
    "status": {"type": "string", "enum": CROSS_PR_STATUS},
    "symbol": {"type": "string",
               "description": "function/endpoint/column at stake, '' if none"},
    "paths": _strings(),
    "evidence": {**_strings(),
                 "description": "file:line in THIS checkout"},
    "detail": {"type": "string"},
    "confidence": {"type": "number", "description": "0.0-1.0"},
}, ["pr", "status", "symbol", "paths", "evidence", "detail", "confidence"]),
```

Added to `FINDINGS_SCHEMA["required"]` so the model always answers, `[]` when
there is nothing.

**Evidence is asymmetric on purpose.** The agent has this PR's code on disk and
only the sibling's patch text. `evidence` therefore holds `file:line` from *this*
checkout; the other side is named in `detail` as `PR #456: path`. Nothing asks
the model to cite a line in a file it cannot open.

### Validation

```python
def validate_findings(data: dict, sibling_numbers: set[int] | None = None) -> dict
```

- A missing `cross_pr` key is normalized to `[]` rather than raising. Findings
  written before this feature — `sessions/demo/app/`, test fixtures, any session
  on disk — must still score, and every consumer already reads
  `.get(key) or []`.
- An entry whose `status` is outside `CROSS_PR_STATUS` raises, like `docs` and
  `contracts` do.
- When `sibling_numbers` is given, an entry naming a PR outside that set is
  **dropped** and reported on stderr
  (`[verify] dropped cross_pr entry citing unknown PR #999`). An invented PR
  number is a hallucination, not a schema break; it must not cost the review.
  `run_verify` derives the set from the `siblings` argument. `threads.py` calls
  `validate_findings` without it — those numbers were already validated when
  first written.

### Prompt

`_siblings_section(siblings: dict | None, found: list[str] | None = None) -> str`
mirrors `_requirement_section`: `""` when there is nothing, so a PR with no
overlapping sibling produces exactly the prompt it produced before this feature
existed. Placed after "Review threads":

```
Other open pull requests changing the same code. Their code is NOT in this
checkout — you have only the diff below.

PR #456 by @dev_b, updated 2026-08-16T09:12:33Z
overlap: same file — src/services/payment/invoice.py
<<<UNTRUSTED pr-456>>>
Split invoice creation into a service

--- src/services/payment/invoice.py
@@ -18,7 +18,7 @@ …
<<<END pr-456>>>
```

Title and patch travel in **one** block per sibling, and `found` is threaded
through so anything neutralized lands in `neutralized.json` and in the report's
"Neutralized in untrusted text" table.

Instruction, inserted as item 8; `unresolved_questions` becomes item 9:

```
8. cross_pr — for each pull request listed under "Other open pull requests"
   above, decide whether merging BOTH would break behaviour that neither PR's
   own CI can see: SEMANTIC_CONFLICT (this PR invalidates an assumption the
   other relies on, or vice versa — a renamed or removed symbol it calls, a
   changed default, a narrowed type, an incompatible migration), DUPLICATE_WORK
   (both implement the same behaviour), MERGE_ORDER_RISK (safe in one merge
   order only) or NO_CONFLICT. Cite file:line from THIS checkout in evidence;
   refer to the other side as "PR #<n>: <path>" — you cannot read its code.
   Never name a PR number that is not listed above. If no pull requests are
   listed, return an empty array.
```

`run_verify` and `build_verify_prompt` both take `siblings: dict | None = None`.

## `src/score.py`

Cross-PR risk stays **out** of `business_risk()`. That function answers "how
risky is this PR as it stands", and a sibling branch is not part of what this PR
stands on. Keeping it separate also means `business_risk`'s existing behaviour
and tests are untouched.

```python
CROSS_PR_MIN_CONFIDENCE = 0.5
LABEL_CROSS_PR = "cross-pr-collision"
RISKY_CROSS_PR = ("SEMANTIC_CONFLICT", "MERGE_ORDER_RISK")

def cross_pr(findings: dict) -> tuple[list[dict], list[dict]]:
    """(collisions that raise risk to medium, collisions reported only)."""
```

- `SEMANTIC_CONFLICT` / `MERGE_ORDER_RISK` with `confidence >= 0.5` → bumping.
- The same statuses below the threshold, and every `DUPLICATE_WORK` → reported
  only. A half-sure guess about a branch that may never merge does not move a
  gate.
- `NO_CONFLICT` → neither list.

In `score()`:

```python
bumping, noted = cross_pr(findings)
if bumping and risk == "none":
    risk = "medium"                      # never "high" — see I5
reasons.extend(f"cross-PR {c['status']} with #{c['pr']}: {c['detail']}"
               for c in bumping + noted)
if bumping or noted:
    labels.append(LABEL_CROSS_PR)
```

The returned dict gains `"cross_pr": ["#456 SEMANTIC_CONFLICT", …]`, flat
strings like `doc_drift` and `test_gaps`. `verification_score`, `doc_drift`,
`business_risk` and `test_gaps` keep their current meanings.

`CROSS_PR_MIN_CONFIDENCE` is a module constant, not a config key. It becomes one
when somebody needs a different value.

## `src/annotations.py`

Each collision becomes a candidate in `candidates()`, anchored to the first
parseable `file:line` in `evidence` — a file of this PR, so it will usually be
inside the diff and land inline. An unparseable one still becomes a candidate
with `line=None`, exactly as claims and callers already do, so `split()` routes
it to the summary rather than dropping it.

```
**⚠️ Potential cross-PR collision — SEMANTIC_CONFLICT with #456**

`createInvoice()` — detail…

Also being changed in #456 (open).
```

`#456` is left as bare text: GitHub auto-links it. No new parameter, no URL, no
signature change. `NO_CONFLICT` entries produce no candidate.

## `src/synthesize.py`

`build_report` gains two tables, and reads `siblings.json` from `session_dir`
itself — the pattern `ticket.json` and `poc.json` already use, so no signature
changes.

1. `## Cross-PR collisions` — `| PR | Status | Symbol | Paths | Evidence |
   Detail | Confidence |`. Empty: `- No collision found with the open pull
   requests listed below.`
2. `## Parallel open pull requests` — `| PR | Author | Overlap | Files |
   Updated |`, each PR as a markdown link to its `url`. When `skipped` is
   non-empty, that sentence replaces the table. When `truncated` is true, a line
   says the scan was capped.

`build_comment` needs no change: it nests the report, and collision reasons
already reach the comment header through `scores["reasons"]`.

## The reply pass

`threads.run_followup` reuses `FINDINGS_SCHEMA` and overwrites `findings.json`
with a complete object, so `cross_pr` has to survive it. Sibling diffs are not
re-fetched and are not in the follow-up prompt, so `build_followup_prompt` gains
one sentence:

```
cross_pr verdicts were judged against other open pull requests whose diffs are
not in this prompt. Carry them over unchanged unless a reply is explicitly
about one of them.
```

## Dashboard

`web/metrics.py`:

- `PHASES` gains `{"id": "siblings", "label": "Sibling scan", "artifact":
  "siblings.json"}`; `EDGES` gains `("snapshot", "siblings")` and
  `("siblings", "verify")` (and drops nothing — `("snapshot", "describe")`
  stays); `ORDER` inserts `"siblings"` after `"snapshot"`.
- `_phase_skipped("siblings", …)` returns `True`: a missing artifact means the
  phase was disabled or the session predates it, never "not yet".
- `_phase_metrics("siblings", …)` reads `siblings.json` and returns
  `[{"label": "scanned", …}, {"label": "overlapping", …}]`.
- The per-PR row gains `"cross_pr": <count of non-NO_CONFLICT entries>`;
  `pr_detail` gains `"cross_pr": findings.get("cross_pr", [])` and
  `"siblings": _read_json(session_dir / "siblings.json") or {}`.

`web/ui/src`: `api.ts` types for both, and a **Cross-PR** tab in the PR detail
listing each collision with its status, symbol, evidence and the sibling it
concerns. No new repo-level KPI.

## Failure modes

| Situation | Behaviour |
|---|---|
| `siblings.enabled: false` | Phase does not run. No `gh` call, no prompt section. |
| GraphQL error, rate limit, no permission to list PRs | `skipped` sentence, review continues (`tickets.py` precedent). |
| No open PR overlaps | `siblings: []`, `skipped: ""`, no prompt section, zero tokens. |
| More than 50 open PRs, or a PR with more than 100 files | `truncated: true`, stderr warning, report says the scan was capped. |
| A sibling's `/files` call fails | That sibling is dropped, the others are kept, stderr notes it. |
| Agent names a PR that was not listed | Entry dropped, stderr notes it, review continues. |
| Sibling merged or closed between the scan and the report | Report shows the state at scan time. Staleness is bounded by `--force` and by the poller's re-review on head change. Documented, not fixed here — that is what a post-merge re-trigger would fix. |
| `--fixtures` mode | Phase not reached; that branch bypasses GitHub entirely. |

## Testing

New `tests/test_siblings.py`, driven by a fake `gh` callable like
`tests/test_tickets.py`:

- file overlap detected; module overlap detected only inside
  `gate.sensitive_areas` or beside a contract file; no overlap → not a sibling
- self, drafts, different `baseRefName`, `[bot]` authors excluded;
  `include_drafts: true` admits drafts
- `max_siblings` cap and rank order (file before module, then path count, then
  recency)
- a shared `package-lock.json` is not an overlap
- GraphQL failure → `skipped` non-empty, no exception; per-sibling `/files`
  failure drops only that sibling
- 50 nodes or 100 files → `truncated: true`
- patches trimmed to the tighter `prune_files` limits

Extensions to existing suites:

- `test_verify.py` — sibling section renders with untrusted markers and a
  neutralized phrase is recorded; **no siblings → prompt identical to the
  pre-feature prompt** (regression guard); `validate_findings` normalizes a
  missing `cross_pr`, raises on a bad status, drops an unlisted PR number
- `test_score.py` — a confident `SEMANTIC_CONFLICT` yields `warn` + label and
  never `fail`; below the threshold and `DUPLICATE_WORK` give a reason with no
  risk change; a `high` risk from another source is not lowered
- `test_annotations.py` — a collision anchors inline on its evidence line;
  `NO_CONFLICT` produces nothing
- `test_synthesize.py` — both tables render; the `skipped` sentence replaces the
  second one
- `test_autoreview_config.py` — defaults merge, and each invalid `siblings:`
  value raises
- `test_run.py` — the phase runs once, is skipped when `siblings.json` exists,
  re-runs under `--force`, and is not called when `enabled: false`
- `test_metrics.py` and `web/ui/src/App.test.tsx` — the phase node and the tab

## README

`## What it checks` gains a **Cross-PR collisions** row. "How it runs" gains the
phase. A short section documents the `siblings:` block, the caps, the
warn-never-fail rule, and states the staleness limit plainly: the scan sees the
siblings that were open when it ran.
