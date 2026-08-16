# Spec — Roadmap: integrations and hardening

**Date:** 2026-08-17
**Status:** design under review — no workstream is approved for implementation yet

## Problem

Nine proposals arrived framed as one idea ("integrate MCP"). They are not one
subsystem. Two of them are already built, one duplicates a capability the SDK
provides for free, and three of the rest would quietly break an invariant the
current architecture depends on.

This document does not specify any of them in implementation detail. It fixes
the boundaries: what already exists, what each proposal is allowed to touch,
which invariants constrain it, and the order the workstreams must land in.
Each workstream then gets its own spec and its own plan.

## Where the architecture stands today

PR Sentinel runs seven phases (`src/run.py`). Each phase writes one artifact
into `sessions/<owner>/<repo>/pr-<n>/`; a phase whose artifact already exists is
skipped, so a re-run resumes instead of paying twice. The deep-dive agent
(`src/verify.py`) runs inside a disposable clone of the PR head with `Read`,
`Grep`, `Glob` and optionally `Bash`, and answers through a JSON schema. Writes
back to GitHub are performed by deterministic modules — `src/synthesize.py`,
`src/remediate.py`, `src/notify.py` — reading the persisted findings.

Four invariants hold today and every workstream below must preserve them.

- **I1 — The agent reads; modules write.** `agent.py` blocks
  `Write`/`Edit`/`NotebookEdit`/`WebFetch`/`WebSearch`, sets
  `permission_mode="dontAsk"` and `setting_sources=[]`. The review agent has no
  network egress and no write access. Every outward action is a deterministic
  module acting on a persisted artifact.
- **I2 — State is files, not a database.** `sessions/` is the store; `web/server.py`
  reads it directly as a read-only ledger. Nothing may introduce a service
  dependency (Redis, DynamoDB, SQLite) for review state.
- **I3 — Untrusted text is data.** PR titles, bodies, commit messages, review
  comments, diffs and (soon) ticket text are written by people outside the trust
  boundary. They are inputs to be judged, never instructions to be followed.
- **I4 — Evidence or UNVERIFIED.** A verdict without a real `file:line` is not a
  verdict. Anything unproven becomes a question for a human.

## Status of each proposal against the code

| # | Proposal | Verdict | Evidence in repo |
|---|---|---|---|
| A | Persist message history so replies resume context | **Bug, not a feature** — the store exists; the CI path never reaches it | `src/run.py:202-231`, `src/threads.py`, `.github/workflows/review.yml` |
| 1 | Separate data from instruction; sanitize untrusted text | **Real gap** | `verify.build_verify_prompt()`, `threads.build_followup_prompt()` interpolate untrusted text into f-strings |
| 2 | Native inline annotations + one-click suggestions | **Half built** — works for docs only | `gh.post_inline_comment`, `remediate.post_suggestions`, `inline_suggestions: true` |
| 3 | Deterministic pre-filtering of generated files | **Already built** — only format-only diffs remain | `src/prune.py`: 32 path rules, 27 binary suffixes, patch truncation, every removal recorded |
| 4 | Generate a PoC test when a finding is BROKEN | **Real gap** — pattern exists to copy | `remediate.draft_patches()` is the template: second agent pass, structured output, nothing written |
| 5 | Route thinking/model budget by PR class | **Real gap** — SDK supports it | `ClaudeAgentOptions` exposes `effort`, `thinking`, `max_thinking_tokens`, `max_budget_usd` |
| B | Pull Jira requirement into review context | **Worth building** | no ticket awareness anywhere; `impact` is judged against the PR body alone |
| C | Write review result back to the Jira ticket | **Worth building, as a module** | `src/notify.py` is the shape to copy |
| D | Internal MCP server for git / grep / AST | **Defer** | `Read`/`Grep`/`Glob` already run inside the clone; only AST is a genuine gap |

## W0 — Reply state durability (bug fix, no spec needed)

**The bug.** `.github/workflows/review.yml` passes `--reply` on comment events,
commented as "resume the previous session instead of paying for a full
re-review". It does not. On a fresh runner `sessions/` is empty, so
`_load_or_skip("findings.json", …)` returns `None` at `src/run.py:202`, the
`if findings is None:` branch at `:204` matches first, and the `elif args.reply:`
branch at `:208` is never reached. Every comment on a PR currently pays for a
complete review.

**Second layer.** Restoring `sessions/` alone is not sufficient.
`resume=session_id` resumes from the Claude Code CLI's own transcript store
under `~/.claude/projects/`, not from `verify-meta.json`. With `sessions/`
restored but the transcript gone, `run_followup` raises and `src/run.py:224`
falls back to a full re-review anyway.

**Fix — three tiers, most specific first.**

1. **True delta resume.** The SDK exposes `session_store`, an adapter that
   mirrors transcript entries to storage of our choosing (`append`/`load` are the
   only required methods). Point it at `sessions/<owner>/<repo>/pr-<n>/transcript.jsonl`
   so the transcript becomes one more phase artifact under I2, and restore
   `sessions/` on CI with `actions/cache` keyed on the PR number. `resume=` then
   works on any runner.
2. **Stateless follow-up.** When the transcript is absent but `findings.json`
   survived, pass the previous findings into `build_followup_prompt()` as data.
   Cheaper than a full review, and it removes the hard dependency on an
   undocumented transcript layout.
3. **Full re-review.** Today's fallback, unchanged.

**Known limit.** For public repos, a fork PR cannot read the base repository's
Actions cache and its token has no write permission. W0 degrades to tier 3
there; that is correct, not a defect.

**Explicitly rejected.** Encoding message history into a hidden HTML comment on
the PR. GitHub caps a comment at 65,536 characters, and anyone with write access
can edit that comment — putting agent-steering state on a surface the agent then
reads back is an injection channel, which violates I3. If a pointer is ever
needed, `src/synthesize.py` already carries a `MARKER`; store `head_sha` and
round number there, never a transcript.

## W1 — Context discipline

One question, three parts: what enters the agent's context, and on what budget.
All three touch `agent.py` / `verify.py` / `prsentinel.yml`, so they ship
together.

### 1. Data/instruction separation

Untrusted text reaches the model at four sites: `verify.build_verify_prompt()`
(title, body, review threads), `threads.build_followup_prompt()` (reply bodies),
`claims.py` (body), `describe.py` (patches).

The primary control is structural: one helper module wraps each untrusted value
in a uniquely delimited block, escapes delimiter collisions in the payload, and
`SYSTEM_PROMPT` states that content inside such a block is material to be
judged and never an instruction to follow. Pattern filtering (`<system>`,
"ignore previous instructions") is defence in depth layered on top — it is
trivially evaded by rephrasing and must not be treated as the control.

Neutralized patterns are **recorded, not silently dropped**, in the same spirit
as `prune.py` recording every removal, so the report can state what was
stripped.

**Residual risk, stated honestly.** Because of I1 and the enforced output
schema, an injected instruction cannot exfiltrate data, write files or reach the
network. The realistic threat is verdict manipulation — coercing `PASS` or
`MATCH`. This is hardening, not an open hole.

**Proposed upgrade.** Add an `injection_attempts` array to `FINDINGS_SCHEMA`:
the agent reports text that tried to steer it, with `file:line`. That converts
the threat into a review finding, and `score.py` can gate on it.

### 2. Format-only diffs

`prune.py` already removes generated, vendored, binary and oversized content.
What remains is the Prettier/ESLint reformat commit. Deterministic first: if a
file's added and removed patch lines are equal after whitespace normalization,
mark it `format-only`, drop the patch, keep the filename in the pruned record.
AST equivalence is deferred until whitespace normalization is shown to be
insufficient — the common case does not need a parser.

### 3. Budget routing

Reuse `gate.sensitive_areas`, already in `prsentinel.yml`, as the classifier
input; do not invent a second taxonomy. Three tiers, decided deterministically
from `snapshot.json`:

| Tier | Signal | Configuration |
|---|---|---|
| trivial | only docs/markdown/css, small diff | light model, thinking off, low `max_turns` |
| standard | logic files, no sensitive path | default model, moderate `effort`, `Grep` enabled |
| critical | path matches `sensitive_areas`, or migrations/contracts touched | strongest model, high `effort`, `allow_bash`/AST enabled, human gate required |

**Cross-check with the provider work on this branch.** `effort` and `thinking`
ride the Anthropic path. For providers declaring `structured_output="prompt"`
(`src/providers.py`), they may be ignored. Tier configuration must degrade
gracefully rather than assume they took effect.

## W2 — Evidence delivery

### 1. Inline annotations beyond docs

The plumbing exists: `gh.post_inline_comment` posts to
`POST /repos/{owner}/{repo}/pulls/{n}/comments`, and `remediate.post_suggestions`
already emits ` ```suggestion ` blocks — but only for docs with status
`STALE`/`WRONG`/`FABRICATED`. Claims, callers, contracts and tests still land
only in the summary comment.

**Hard constraint.** GitHub accepts an inline comment only on a line that is
part of the diff. `callers_outside_diff` — per the README the most valuable
finding type — is by definition outside the diff, so most of those cannot be
inline. `remediate.post_suggestions` already models this correctly with its
`leftover` return value folding into the summary; the generalization must
inherit that mechanism, not replace it.

Two changes worth deciding: batch the annotations through
`POST /pulls/{n}/reviews` with a `comments[]` array so the author receives one
review event instead of N notifications; and cap the inline count, recording the
overflow in the summary the way `prune.py` records what it cut.

### 2. PoC test for BROKEN and RISK

Mirror `remediate.draft_patches()`: a second agent pass, gated on the findings
actually containing `BROKEN` or `RISK`, read-only, returning structured
`poc_tests[]` — target, framework, test code, why it fails. Never written into
the repo; attached to the report in a collapsed block for the author to run
locally. The test framework is detected deterministically from the workspace,
not guessed by the model.

**Honest caveat.** A PoC test the agent cannot execute is itself an unverified
claim, and I4 applies to it. It must be labelled as not executed. Executing it
would require write and exec permission, breaking I1. The SDK does expose
`sandbox`, so a sandboxed execution path is possible later — out of scope here.

## W3 — Jira

**Read.** Parse issue keys from the branch name, PR title and PR body. Fetch
once during the snapshot phase, cache to `ticket.json` as a normal phase
artifact under I2, and inject the text into the verify prompt inside a W1
untrusted block. This upgrades `impact` from "does the code match what the
author wrote" to "does the code match what the business asked for" — the single
highest-value change in this document. `impact` gains a `requirement_source`
field so a verdict says where its requirement came from.

**Write — comment only.** A deterministic module in the shape of
`src/notify.py`, running after scoring, reading `score.json` and `findings.json`,
posting one comment with the merge decision, failed claims and a PR link. It is
idempotent the way `synthesize.py` is: find the previous bot comment on the
ticket by marker and update it rather than appending on every run. Off by
default in `prsentinel.yml` alongside `auto_describe` and `docs_fix_pr`.

**Boundary — this workstream never transitions status, never edits fields,
never rewrites a description.** Those are destructive against state other people
own, and they would need a per-project workflow map. If wanted later, they are a
separate spec with their own approval.

**Why not a Jira MCP tool inside the agent loop.** It would be a live network
egress path open while the agent reads attacker-controlled text, contradicting
I1 directly, and it would make a review of the same commit non-reproducible,
contradicting I2.

## W4 — Internal MCP server (deferred)

Wrapping `git` and `grep` in an MCP server re-packages what `Read`/`Grep`/`Glob`
already do inside the workspace clone, at the cost of another process and
another protocol. The genuine gap is AST: `callers_outside_diff` is currently
found by text grep, which cannot distinguish a call from a mention in a comment,
or follow a re-export. That gap is closed more cheaply by an `ast-grep` binary
invoked through `Bash`.

**The one argument that would justify MCP.** `allow_bash` is a binary switch —
on means a full shell in the workspace. An MCP server exposing exactly
`git_log`, `git_blame` and `ast_query`, enforced by `can_use_tool`, is strictly
safer than a shell. The SDK supports this (`mcp_servers`, `strict_mcp_config`,
`sandbox`). Revisit if and when `allow_bash: true` becomes the default; until
then it is speculative infrastructure.

## Dependency order

```
W0 (bug fix)  →  W1  →  W2
                  ↓
                 W3
```

W0 first: it is small, it fixes money currently being burned on every PR
comment, and it needs no design decisions.

W1 before W3, because W3 introduces a new class of untrusted text (ticket
descriptions written by anyone with Jira access) and should land into a codebase
that already has the untrusted-block helper.

W1 before W2, because W2 adds new agent passes whose cost belongs under the tier
routing W1 establishes.

W2 and W3 are independent of each other and may run in either order.

## Decisions

1. No database. Review state stays as files under `sessions/` (I2). W0 extends
   that store with a transcript artifact rather than replacing it.
2. Transcript persistence uses the SDK's `session_store` adapter, not caching of
   `~/.claude/projects/`.
3. No agent-visible state is ever stored on a GitHub comment.
4. Data/instruction separation is structural (delimited blocks + system prompt
   clause); pattern filtering is defence in depth only.
5. Neutralized injection patterns and dropped inline annotations are recorded
   and surfaced, never silently discarded.
6. Budget tiers classify from `gate.sensitive_areas`, reusing existing config.
7. Format-only detection is whitespace normalization; AST equivalence deferred.
8. PoC tests are generated, labelled not-executed, and never written to the repo.
9. Jira writes are comments only, idempotent, opt-in, and performed outside the
   agent loop.
10. No MCP server until `allow_bash` needs to be on by default.

## Out of scope

- Jira status transitions, field writes, description edits, sub-task creation.
- MongoDB Atlas or any database introspection.
- Executing generated PoC tests.
- AST-based diff equivalence.
- Replacing `prune.py`'s existing rules.
- Any change to `web/` beyond rendering new artifacts that already exist.

## Acceptance

- **W0** — a comment on a PR in CI produces a follow-up run whose recorded cost
  in `usage.json` is materially below a full verify, and `run.py` logs that it
  resumed rather than re-reviewed.
- **W1** — a PR whose body contains an injection attempt is reviewed with
  correct verdicts, the attempt appears in the findings, and a format-only
  commit produces an empty or near-empty diff context.
- **W2** — findings with an in-diff `file:line` appear as inline comments in one
  review event; out-of-diff findings appear in the summary; a `BROKEN` finding
  carries a runnable, clearly-labelled PoC test.
- **W3** — a PR linked to a ticket is reviewed against the ticket's requirement
  text, `impact` cites `requirement_source`, and the ticket carries exactly one
  bot comment regardless of how many times the review runs.

## Open questions

1. **Jira deployment** — Cloud (email + API token) or Server/Data Center (PAT)?
   This changes the auth model and the REST path in W3.
2. **Trust boundary of the reviewed repos** — private/internal only, or public
   with fork PRs? This decides whether W0 tiers 1–2 are ever reachable and how
   much weight W1 deserves.
3. **Where the ticket link lives** — branch name convention, PR title prefix, or
   a body field? Determines the parser in W3.
