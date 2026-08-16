# Spec — Roadmap: integrations and hardening

**Date:** 2026-08-17
**Status:** design under review — open questions resolved 2026-08-17, no workstream
approved for implementation yet

**Operating context (answers to the open questions, now closed):** Jira **Cloud**,
authenticated with email + API token. The reviewed repositories are **private and
internal** — no fork pull requests. Ticket keys may arrive from the **branch name,
a PR title prefix, or a link a human pastes into the PR body**.

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

**Reachability.** Because the reviewed repositories are private and internal,
every PR branch lives in the same repository. Actions cache is readable and the
token has write permission, so tiers 1 and 2 are the normal path — not a
best-effort optimization. (Were a fork PR ever reviewed, its cache is isolated
and its token read-only, so it would degrade to tier 3. That is correct
behaviour, not a defect, and needs no extra work.)

**Explicitly rejected.** Encoding message history into a hidden HTML comment on
the PR. GitHub caps a comment at 65,536 characters, and anyone with write access
can edit that comment — putting agent-steering state on a surface the agent then
reads back is an injection channel, which violates I3. If a pointer is ever
needed, `src/synthesize.py` already carries a `MARKER`; store `head_sha` and
round number there, never a transcript.

## W1 — Context discipline

One question, three parts: what enters the agent's context, and on what budget.
All three touch `agent.py` / `verify.py` / `prsentinel.yml`, so they ship
together — with one exception carved out below.

**Carve-out.** The untrusted-block helper (part 1) is a small, self-contained
module that W3 needs on day one, since ticket text is a new input class. It
ships **with W3**, not with W1. What stays in W1 is the rest of part 1
(neutralization recording, the optional findings field) plus parts 2 and 3.

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

**Threat model for internal repositories.** With no fork PRs, every author is
inside the trust boundary, which lowers the likelihood of a deliberate attack
substantially. It does not reach zero: dependency bumps, vendored code and
pasted third-party snippets all carry text nobody on the team wrote, and I3 is
about provenance rather than intent. The consequence is priority, not scope —
part 1 stays in the design, but it no longer justifies blocking business value
behind it. Hence the carve-out above, and the revised order below.

**Deferred.** Adding an `injection_attempts` array to `FINDINGS_SCHEMA` — the
agent reporting text that tried to steer it, with `file:line`, so `score.py`
can gate on it. Attractive, but it is a schema change and a scoring change for
a threat that internal repositories rarely see. Revisit if the repositories
ever accept outside contributions.

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

### Transport and auth

Jira Cloud, Basic authentication with `base64(email:api_token)`. Credentials
come from the environment only — `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
— never from `prsentinel.yml`, matching the rule that file already states for
provider tokens.

No new dependency. `src/notify.py` posts to Slack with `urllib.request` and an
injectable `opener=` parameter so tests never touch the network; the Jira client
copies that shape exactly. Core dependencies stay `claude-agent-sdk` + `pyyaml`.

**Use REST v2, not v3.** On Jira Cloud both are available, and v3 speaks
Atlassian Document Format: a `GET` returns the ticket description as an ADF JSON
tree that must be flattened before it can go in a prompt, and a `POST` comment
must be built as an ADF tree rather than text. v2 returns and accepts plain
strings in both directions. There is no capability here that v3 offers and v2
does not, so v2 removes an entire class of work from both halves of this
workstream.

### Ticket key discovery

Three sources, all supported, scanned in this precedence order:

1. **A browse link pasted in the PR body** — `…/browse/ABC-123`. Most explicit
   human intent, so it wins.
2. **A PR title prefix** — `ABC-123: …`.
3. **The branch name** — `feature/ABC-123-something`.

**False positives are the real hazard.** A bare `[A-Z][A-Z0-9]+-\d+` pattern
also matches `UTF-8`, `SHA-256`, `HTTP-2`, `RFC-7231` and `CVE-2024-1234`, all
of which appear routinely in PR text. The guard: a bare key is accepted only
when its project prefix is listed in `jira.projects` in `prsentinel.yml`; a key
arriving as a full browse URL is unambiguous and needs no allowlist.

At most three unique tickets are fetched per PR, to bound cost and context. The
first key found by precedence is the primary requirement; the rest are context.

### Read

Fetch during the snapshot phase, cache to `ticket.json` as a normal phase
artifact under I2, and inject the text into the verify prompt inside an
untrusted block (the W1 helper, which ships here). This upgrades `impact` from
"does the code match what the author wrote" to "does the code match what the
business asked for" — the single highest-value change in this document. `impact`
gains a `requirement_source` field so a verdict says where its requirement came
from.

A missing, unreachable or permission-denied ticket degrades the review to
today's behaviour and records why in the report. It never fails the run.

### Write — comment only

A deterministic module in the shape of `src/notify.py`, running after scoring,
reading `score.json` and `findings.json`, posting one comment with the merge
decision, failed claims and a PR link.

Idempotent the way `synthesize.py` is: the comment carries a marker,
`GET /rest/api/2/issue/{key}/comment` finds the previous one, and the module
issues a `PUT` on that comment id instead of appending on every run. Without
this, a PR that is pushed to ten times leaves ten bot comments on the ticket.

Only the primary ticket is commented on, even when several were read. Off by
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
W0 (bug fix)  →  W3 (+ untrusted-block helper)  →  W1  →  W2
```

**Revised on 2026-08-17**, after the operating context was confirmed. The first
draft put W1 ahead of W3 on the argument that ticket text is a new class of
untrusted input. With private internal repositories and no fork PRs, that
argument no longer justifies holding back the highest-value change: the helper
itself is small, so it ships inside W3 and W1 keeps the rest.

W0 first: small, needs no design decisions, and it stops money currently being
burned on every PR comment.

W3 second: reviewing code against the real requirement instead of the PR
author's own description is the largest single improvement available, and
nothing else blocks it now.

W1 third: the remaining hardening plus the two cost levers — format-only
pruning and tier routing.

W2 last: it adds new agent passes, whose cost belongs under the tier routing W1
establishes.

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
11. Jira Cloud over REST **v2**, not v3 — v2 exchanges plain strings where v3
    requires Atlassian Document Format in both directions.
12. Jira credentials live in the environment (`JIRA_BASE_URL`, `JIRA_EMAIL`,
    `JIRA_API_TOKEN`), never in `prsentinel.yml`. No new dependency: the client
    uses `urllib.request` with an injectable opener, as `src/notify.py` does.
13. A bare ticket key is honoured only when its project prefix appears in
    `jira.projects`; a full browse URL needs no allowlist. Without this guard
    `UTF-8` and `CVE-2024-1234` parse as tickets.
14. The untrusted-block helper ships with W3 rather than W1, so business value
    is not held behind hardening that internal repositories need less urgently.

## Out of scope

- Jira status transitions, field writes, description edits, sub-task creation.
- MongoDB Atlas or any database introspection.
- Executing generated PoC tests.
- AST-based diff equivalence.
- Replacing `prune.py`'s existing rules.
- Any change to `web/` beyond rendering new artifacts that already exist.

## Acceptance

Listed in execution order.

- **W0** — a comment on a PR in CI produces a follow-up run whose recorded cost
  in `usage.json` is materially below a full verify, and `run.py` logs that it
  resumed rather than re-reviewed.
- **W3** — a ticket key is found from each of the three sources; `UTF-8` and
  `CVE-2024-1234` in a PR body are not mistaken for tickets; the review cites
  the ticket's requirement text with `requirement_source` on `impact`; the
  ticket carries exactly one bot comment regardless of how many times the review
  runs; and a ticket that 404s or 403s degrades the review instead of failing it.
- **W1** — a PR body carrying an injection attempt is reviewed with correct
  verdicts and the report states that text was neutralized; a format-only commit
  produces an empty or near-empty diff context; a docs-only PR and a PR touching
  a `sensitive_areas` path resolve to different tiers, visible in `usage.json`.
- **W2** — findings with an in-diff `file:line` appear as inline comments in one
  review event; out-of-diff findings appear in the summary; a `BROKEN` finding
  carries a runnable, clearly-labelled PoC test.

## Resolved questions

1. **Jira deployment** — Cloud, email + API token. Settles the auth model and,
   with decision 11, the REST version.
2. **Trust boundary** — private internal repositories, no fork PRs. Makes W0
   tiers 1–2 the normal path and lowers W1's priority relative to W3.
3. **Ticket key location** — all three: branch name, PR title prefix, and a
   link pasted into the PR body. Settles the parser and its precedence order.

## Still open

None blocking. Two items to settle inside their own workstream specs rather
than here: the exact tier thresholds in W1 (diff size and file-type cutoffs are
easier to choose against real `usage.json` data than in advance), and the
`jira.projects` allowlist values, which are a deployment detail.
