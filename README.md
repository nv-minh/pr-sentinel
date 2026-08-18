# PR Sentinel — AI code review that has to show its evidence

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](pyproject.toml)
[![Built on the Claude Agent SDK](https://img.shields.io/badge/built%20on-Claude%20Agent%20SDK-d97757.svg)](https://code.claude.com/docs/en/agent-sdk/python)

PR descriptions overstate. Docs go stale. A five-line diff breaks ten files
nobody opened. PR Sentinel runs a Claude agent inside a checkout of the pull
request and reports what the code actually does — every verdict carrying a
`file:line` citation, and a merge decision CI can act on.

## What it checks

| | |
|---|---|
| **Claims** | Each sentence of the PR description becomes a claim, verified against the code: `PASS / FAIL / PARTIAL / UNVERIFIED`, with evidence |
| **Docs vs reality** | Documentation compared against the code it describes: `MATCH / STALE / WRONG / FABRICATED` |
| **Requirement impact** | Which business behaviour the change touches: `CHANGED / BROKEN / UNAFFECTED / RISK` |
| **Callers outside the diff** | Symbols whose behaviour changed, and the callers this PR *didn't* touch: `SAFE / NEEDS_UPDATE / BROKEN` |
| **Cross-PR collisions** | Other **open** pull requests changing the same code, compared against this one: `SEMANTIC_CONFLICT / DUPLICATE_WORK / MERGE_ORDER_RISK / NO_CONFLICT` |
| **Contract breakage** | API specs, migrations, protos and exported types: `BREAKING_API_CHANGE / SCHEMA_MIGRATION_RISK` |
| **Test integrity** | Whether new tests assert the new branch logic or only execute it, plus concrete uncovered edge cases |
| **Merge gate** | Verification score, doc drift and business risk → `pass / warn / fail`, wired to a CI exit code |

Everything else follows from those: doc fixes come back as GitHub suggestions,
an empty PR body gets a drafted description, replies on the PR are answered by
resuming the previous agent session instead of re-reviewing from scratch, the
review can be judged against the Jira ticket the PR is about, and how much a
review costs is routed by the risk of what it touches.

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

## Install

Requires Python 3.10+ and an authenticated `gh` CLI.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev,web]'
gh auth login
export ANTHROPIC_API_KEY=sk-ant-...   # or just log in with the Claude Code CLI
```

The Claude Agent SDK bundles its own CLI binary, and it reuses the credentials
of a logged-in Claude Code install — `ANTHROPIC_API_KEY` is optional locally,
required in CI.

## Review a pull request

```bash
PYTHONPATH=src python -m src.run owner/repo 123              # interactive
PYTHONPATH=src python -m src.run owner/repo 123 --skip-human # batch, no questions
PYTHONPATH=src python -m src.run owner/repo 123 --no-post    # don't touch the PR
PYTHONPATH=src python -m src.run owner/repo#123 --ci         # CI mode, gate → exit code
PYTHONPATH=src python -m src.run owner/repo 123 --reply      # answer new replies, cheaply
```

Results land in `sessions/<owner>/<repo>/pr-<n>/`: `findings.json`, `score.json`,
`ticket.json` (the requirement context, or why there is none), `siblings.json`
(the overlapping open PRs found, or why none were), `neutralized.json`
(instruction-shaped text stripped from prompts), `poc.json` (generated failing
tests), `usage.json` (what the review cost), `report.md`, and `transcripts/` —
the agent conversation, kept so a later `--reply` resumes it instead of
re-reviewing; if the transcript is gone, the follow-up runs stateless, carrying
the previous findings forward. Every phase is skipped when its result already
exists, so a re-run resumes rather than paying twice; `--force` re-runs them.

## How it runs

1. **Snapshot** — PR metadata, files, commits and review threads via the GitHub
   REST + GraphQL APIs. Lockfiles, build output, binary assets and reformat-only
   patches (a Prettier pass that changes no behaviour) are pruned from the
   context here, and every removal is recorded in the report.
2. **Tier** — before any model call, the PR is classified as trivial / standard /
   critical from the paths it touches, which picks the model, reasoning effort,
   turn limit and tool set for the run (see "Review budget by tier").
3. **Ticket** — the Jira ticket the PR is about, if any, is fetched once and
   cached as `ticket.json`; its text becomes the requirement `impact` is judged
   against. Unconfigured Jira simply records why and moves on.
4. **Sibling scan** — one GraphQL call lists the open pull requests, and any that
   change a file this PR changes — or a sensitive/contract directory it touches —
   have their diff fetched, trimmed and cached as `siblings.json`. Nothing is
   loaded when nothing overlaps.
5. **Describe** — if the body is empty or too thin to claim anything, a
   description is drafted from the diff (proposed in the comment; only rewritten
   on the PR when `auto_describe` is on).
6. **Claims** — the description is split into individually checkable statements.
7. **Verify** — a read-only Claude agent works inside a disposable clone of the
   PR head and fills in the findings schema: claims, docs, impact, callers
   outside the diff, contracts, tests, cross-PR collisions.
8. **Score** — the findings become a merge decision.
9. **Ask** — anything the agent could not prove becomes a question of at most 20
   words, for a human.
10. **Report** — **one** review event on the PR carrying every anchorable inline
    comment (doc fixes as one-click suggestions, findings on the lines they are
    about), plus a summary comment — updated in place — for everything that could
    not be anchored, generated failing tests for `BROKEN` findings, labels, a
    check run and optional Slack and Jira pings.

## CI gate

`.github/workflows/review.yml` reviews every push to a PR and re-runs cheaply
when someone comments. The job exits non-zero when the gate fails, so branch
protection blocks the merge.

```yaml
env:
  ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
run: python -m src.run "$GITHUB_REPOSITORY" "$PR_NUMBER" --ci --force
```

The job saves `sessions/` as an artifact after each review, so a later comment
triggers a follow-up that restores it and resumes the conversation. Without that
artifact the runner starts empty and every comment pays for a full review.

The gate is configured in `prsentinel.yml`:

```yaml
gate:
  verification_score_min: 0.8      # share of claims backed by a real file:line
  sensitive_areas: ["**/payment*/**", "**/auth*/**", "**/migrations/**"]
  core_docs: ["README.md", "docs/**", "**/openapi*.y*ml"]
```

- **fail** — a breaking contract, a broken caller, or broken behaviour in a
  sensitive area. CI exits 1.
- **warn** — verification below the threshold, core docs out of sync, or a
  medium risk. CI passes, the PR gets labelled.
- **pass** — every claim proven, nothing broken.

## Poll instead of CI

```bash
python -m src.autoreview --add-repo sample-app --mode auto
python -m src.autoreview --once         # one pass (cron/launchd)
python -m src.autoreview --daemon       # loop every interval_minutes
```

The poller reviews new PRs, re-reviews when the head commit changes, and — when
a PR was touched after its review was posted — runs the cheap reply pass.
`scripts/poll-once.sh` is a launchd-friendly wrapper that sources `.env`.

## Review against the Jira ticket

Jira is entirely optional — leave the three variables unset and reviews simply
run without Jira requirement context, recording why. When it is configured, the
review judges `impact` against the requirement the ticket states rather than
the description the PR author wrote — and can post the merge decision back to
the ticket.

```bash
export JIRA_BASE_URL=https://acme.atlassian.net
export JIRA_EMAIL=bot@acme.io
export JIRA_API_TOKEN=...
```

```yaml
jira:
  projects: [ABC, PRJ]      # allowlist for bare keys
  comment_result: true      # off by default
```

The ticket key is taken from a `/browse/` link in the PR body, a `ABC-123:`
title prefix, or the branch name, in that order; the first that resolves is the
primary requirement and at most three tickets are read. A bare key counts only
when its project is in `projects` — otherwise `UTF-8` and `CVE-2024-1234` parse
as tickets. Ticket text enters the prompt inside an untrusted block, so an
instruction written into a ticket description is reported rather than obeyed.

Jira never fails a review: an unconfigured, missing or unreachable ticket
degrades the review to the PR description and records why in the report. The
verdict comment is written by a deterministic module after scoring, never by the
agent, and it updates in place rather than accumulating one comment per push.
This workstream never changes a ticket's status, fields or description.

## Dashboard

```bash
(cd web/ui && npm ci && npm run build)
PRS_SESSION_ROOT=sessions python -m web.server     # http://127.0.0.1:6789
```

A read-only ledger over `sessions/` — no database. Repo list → repo detail
(KPIs, merge-decision band, open PRs) → PR detail, which opens on the review
pipeline as a graph: Snapshot → Describe → Claims → Verify → Score → Confirm →
Report, with the doc-fix branch off Verify and the reply loop back into it. Each
node carries its own status, cost and headline counts; clicking one opens that
phase's evidence below. Blocking findings are listed above the tabs, widest blast
radius first. Reviews started from the dashboard run in the background and the
graph follows them live.
A provider panel shows which gateway is active, whether its key is present, and
can switch providers (the switch rewrites the one `provider:` line in
`prsentinel.yml` — tokens never enter the file).

Demo data ships in `sessions/demo/app/` — open
`http://127.0.0.1:6789/repos/demo/app/pr/8` for a blocked review.

### Connecting a GitHub account

The **GitHub** page turns a personal access token into a browsable list of work:
paste one, and every project that account reaches — its own, the ones it was
added to, and its organisations' — is fetched with their open pull requests, each
row showing whether it has already been reviewed. Review or watch one from there;
nothing has to be typed into `prsentinel.yml` first.

The token needs `repo` and `read:org`. It is verified against GitHub before being
stored, then written to `.env` — never to `prsentinel.yml`, and never sent back to
the page. More than one account can be connected; whichever is active is the one
**every** GitHub call is made as — the REST and GraphQL calls through `gh`, and the
`git clone` of the pull request itself, which is what lets a work account review a
private repo the machine's own login cannot see. The credential reaches git as an
HTTP header through `GIT_CONFIG_*`, so it is never in a command line and never
written into the clone's `.git/config`. With no account connected, `gh` and `git`
authenticate exactly as they did before.

Switching account takes effect on the next GitHub call, including calls made by a
review already running — so a review started as one account can finish as another.
Switch between reviews, not during one.

The dashboard has no login of its own and binds to `127.0.0.1` — it can already
edit `prsentinel.yml` and start reviews, and now also holds a GitHub token
(`.env`, mode `600`). Do not serve it on a public interface.

## Providers

PR Sentinel runs on the Claude Agent SDK, which speaks the Anthropic wire
protocol — so it also runs against any gateway that exposes an
Anthropic-compatible endpoint. Pick one in `prsentinel.yml`, put its key in
`.env`:

```yaml
provider: deepseek          # anthropic (default) | deepseek | glm | your own
```

| Provider | Endpoint | Key | Deep dive | Claims |
|---|---|---|---|---|
| `anthropic` | *(default)* | `ANTHROPIC_API_KEY` | `claude-sonnet-5` | `claude-haiku-4-5-20251001` |
| `deepseek` | `https://api.deepseek.com/anthropic` | `DEEPSEEK_API_KEY` | `deepseek-v4-pro` | `deepseek-v4-flash` |
| `glm` | `https://api.z.ai/api/anthropic` | `ZAI_API_KEY` | `glm-5.2` | `glm-4.7` |

Anything else is a few lines of config — every key is required:

```yaml
provider: my-gateway
providers:
  my-gateway:
    base_url: https://llm.internal.example.com/anthropic
    token_env: MY_GATEWAY_TOKEN
    model: big-model
    claims_model: small-model
```

**Two things change on a non-Anthropic provider.** Structured output is an
Anthropic beta that third-party gateways ignore, so the JSON schema travels in
the prompt instead and the reply is parsed — a malformed answer costs one repair
turn, not a failed review. And `total_cost_usd` is priced from Anthropic's
table, so cost is recorded as unknown and `max_budget_usd` does not apply.
Set `structured_output: native` and `reports_cost: true` on a custom provider
only if it genuinely implements both.

Known limitation: the repair turn fires when a prompt-mode reply cannot be
*parsed*, not when it parses into the wrong *shape* — a missing required key,
a value outside an enum. Nothing enforces the schema server-side on a
prompt-mode provider, so a well-formed reply of the wrong shape fails the
phase instead of earning a second turn.

Tokens are read from the environment and never written to `prsentinel.yml`; the
dashboard shows whether a key is present, never the key.

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `PRS_PROVIDER` | `anthropic` | Overrides `provider:` in `prsentinel.yml` |
| `ANTHROPIC_API_KEY` | — | Optional if the Claude Code CLI is logged in |
| `ANTHROPIC_AUTH_TOKEN` | — | Key for any provider; wins over the provider's own variable |
| `ANTHROPIC_BASE_URL` | — | Point any provider at a different endpoint |
| `PRS_MODEL` | provider's | Model for the deep-dive agent |
| `PRS_CLAIMS_MODEL` | provider's | Model for claims + description drafting |
| `PRS_SESSION_ROOT` | `sessions` | Where per-phase results are written |
| `SLACK_WEBHOOK_URL` | — | Optional one-way notification |
| `JIRA_BASE_URL` | — | *Optional.* Jira Cloud site, e.g. `https://acme.atlassian.net`; unset skips Jira |
| `JIRA_EMAIL` | — | *Optional.* Account the API token belongs to |
| `JIRA_API_TOKEN` | — | *Optional.* Jira API token (never stored in `prsentinel.yml`) |

`prsentinel.yml` holds the rest. `language: en | vi` (default `en`) sets the
language the model writes its prose
in — findings notes, unresolved questions, drafted descriptions, PoC test
reasons, follow-up replies and the reason attached to a documentation fix. Fixed
labels stay English: the status vocabulary (`PASS`, `STALE`, `BREAKING_API_CHANGE`
…) is a schema enum that CI reads, and a documentation patch keeps the language
of the document it edits. Set it from the dashboard's Config page or in the file.

The dashboard's own language is a **separate** setting, stored per browser and
switched from the header. Reading a Vietnamese dashboard does not make the agent
write Vietnamese into a public pull request, and it is never written to
`prsentinel.yml`.

Four settings write outside the review comment
and three of them are **off by default**: `auto_describe` (rewrites the PR body),
`docs_fix_pr` (opens a follow-up PR with doc fixes), `jira.comment_result`
(posts the verdict to the Jira ticket), and `inline_suggestions` (suggestion
blocks on docs inside the diff — this one is on).

Cost control: `tiered_budget` routes each review's effort by what it touches,
`max_budget_usd` hard-stops a verify run, diff pruning keeps generated and
reformat-only files out of context, and `--reply` resumes the previous session
instead of starting over. `usage.json` records what each phase actually cost.

### Review budget by tier

A markdown fix and a change to the payment path should not cost the same review.
With `tiered_budget: true` (the default) each PR is classified from the paths it
touches, before any model call:

| Tier | When | What it gets |
|---|---|---|
| trivial | only docs, markdown, text or stylesheets | the cheap model, low effort, 15 turns |
| standard | anything else | the review model, medium effort, 60 turns |
| critical | a path matching `gate.sensitive_areas`, or a contract file (`*.proto`, `*.sql`, anything named `openapi`/`swagger`/`schema.graphql`) | the review model, high effort, 90 turns, `Bash` enabled |

The classification reuses `gate.sensitive_areas` rather than a second list, and
the chosen tier is printed at the start of the run. Reasoning effort rides the
Anthropic path; a third-party gateway may ignore it and reason at its own
default.

## Cross-PR collisions

Two pull requests can each be green and still break `main` together: PR A renames
`createInvoice()`, PR B calls it from a file PR A never touches. Git sees no
conflict, and neither CI run contains the other's commits.

Before the deep dive, PR Sentinel lists the open pull requests and keeps the ones
that overlap this PR — same file, or the same directory when that directory is a
`gate.sensitive_areas` match or holds a contract file. Their diffs, trimmed, go
into the review as untrusted material, and each one comes back judged:
`SEMANTIC_CONFLICT`, `DUPLICATE_WORK`, `MERGE_ORDER_RISK` or `NO_CONFLICT`.

```yaml
siblings:
  enabled: true
  max_siblings: 3           # how many overlapping PRs get their diff loaded
  include_drafts: false
```

A collision labels the PR `cross-pr-collision` and can take the gate to `warn`
only when both hold: the status is `SEMANTIC_CONFLICT` or `MERGE_ORDER_RISK`,
and confidence is at least 0.5. `DUPLICATE_WORK` is reported but never moves
the gate at any confidence, and below 0.5 confidence a `SEMANTIC_CONFLICT` or
`MERGE_ORDER_RISK` is reported but not gated either — a half-sure guess about a
branch that may never merge is not worth an amber CI run. Even a confident
collision never fails a review: the other branch may never merge, or may merge
after this one has already been fixed, and blocking a merge on a guess about a
branch that does not exist yet is a false positive nobody thanks you for.

Costs are bounded on purpose: at most 50 open PRs are scanned, at most 3 get
their diff loaded, and each of those is cut to 60 patch lines per file and 300
in total. No overlap means no sibling diff is loaded and no extra GitHub call
is paid for beyond the one GraphQL listing — the verify prompt itself always
carries the cross-PR instructions, whether or not any sibling exists.

**The scan sees the pull requests that were open when it ran.** A sibling opened
or merged afterwards is invisible until the review is re-run (`--force`, a new
head commit, or the poller). Catching the merge itself would take a post-merge
re-trigger, which this does not do.

## Safety

The verify agent gets `Read`, `Grep` and `Glob` and nothing else — no writes, no
network. `Bash` is off by default and enabled in exactly two ways: the
`allow_bash` setting, or the critical tier when `tiered_budget` is on (the
default) and the PR touches `gate.sensitive_areas` or a contract file. The agent
runs in a throwaway clone with `setting_sources=[]`, so the host machine's
`CLAUDE.md`, settings and skills never reach the review. Findings come back
through a JSON schema, so the agent never needs write access to report.

Text nobody on our side wrote — PR title and body, review threads, replies,
commit messages, Jira descriptions — enters every prompt inside delimited
`<<<UNTRUSTED ...>>>` blocks, and the system prompt states that a block's
contents are evidence to verify, never instruction to follow; an instruction
found there is itself reported as a finding. Instruction-shaped phrases
("ignore previous instructions", fake `<system>` tags) are additionally
stripped, and what was stripped is recorded in `neutralized.json` and surfaced
in the report — never dropped silently. The structural control is the block plus
the clause; the phrase list is defence in depth and is expected to be evadable
by rephrasing.

Outbound writes are deterministic code, never the agent: the review comment, the
batched inline review, labels and check runs are posted by Python modules after
scoring, so nothing a PR author wrote can steer them.

## Tests

```bash
python -m pytest -q
(cd web/ui && npm test -- --run)
```

## License

[MIT](LICENSE)
