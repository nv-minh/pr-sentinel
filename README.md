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
| **Contract breakage** | API specs, migrations, protos and exported types: `BREAKING_API_CHANGE / SCHEMA_MIGRATION_RISK` |
| **Test integrity** | Whether new tests assert the new branch logic or only execute it, plus concrete uncovered edge cases |
| **Merge gate** | Verification score, doc drift and business risk → `pass / warn / fail`, wired to a CI exit code |

Everything else follows from those: doc fixes come back as GitHub suggestions,
an empty PR body gets a drafted description, and replies on the PR are answered
by resuming the previous agent session instead of re-reviewing from scratch.

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
`usage.json` (what the review cost), `report.md`, and `transcripts/` — the agent
conversation, kept so a later `--reply` resumes it instead of re-reviewing. Every
phase is skipped when its result already exists, so a re-run resumes rather than
paying twice; `--force` re-runs them.

## How it runs

1. **Snapshot** — PR metadata, files, commits and review threads via the GitHub
   REST + GraphQL APIs. Lockfiles, build output and binary assets are pruned from
   the context here, and every removal is recorded in the report.
2. **Describe** — if the body is empty or too thin to claim anything, a
   description is drafted from the diff (proposed in the comment; only rewritten
   on the PR when `auto_describe` is on).
3. **Claims** — the description is split into individually checkable statements.
4. **Verify** — a read-only Claude agent works inside a disposable clone of the
   PR head and fills in the findings schema: claims, docs, impact, callers
   outside the diff, contracts, tests.
5. **Score** — the findings become a merge decision.
6. **Ask** — anything the agent could not prove becomes a question of at most 20
   words, for a human.
7. **Report** — one comment on the PR, updated in place, plus doc suggestions,
   labels, a check run and an optional Slack ping.

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

With Jira configured, the review judges `impact` against the requirement the
ticket states rather than the description the PR author wrote — and can post the
merge decision back to the ticket.

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

A read-only ledger over `sessions/` — no database. Repo list → repo detail (KPIs,
merge-decision band, open PRs) → PR detail (Claims / Docs / Impact / Callers /
Contracts / Tests / Threads / Confirm / Context). Reviews started from the
dashboard run in the background; the page follows the log until they finish.

Demo data ships in `sessions/demo/app/` — open
`http://127.0.0.1:6789/repos/demo/app/pr/8` for a blocked review.

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
| `JIRA_BASE_URL` | — | Jira Cloud site, e.g. `https://acme.atlassian.net` |
| `JIRA_EMAIL` | — | Account the API token belongs to |
| `JIRA_API_TOKEN` | — | Jira API token (never stored in `prsentinel.yml`) |

`prsentinel.yml` holds the rest. Three settings write outside the review comment
and are **off by default**: `auto_describe` (rewrites the PR body),
`docs_fix_pr` (opens a follow-up PR with doc fixes), and `inline_suggestions`
(suggestion blocks on docs inside the diff — this one is on).

Cost control: `max_budget_usd` hard-stops a verify run, diff pruning keeps
generated files out of context, and `--reply` resumes the previous session
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

## Safety

The verify agent gets `Read`, `Grep` and `Glob` and nothing else — no writes, no
network, no shell unless `allow_bash` is set. It runs in a throwaway clone with
`setting_sources=[]`, so the host machine's `CLAUDE.md`, settings and skills
never reach the review. Findings come back through a JSON schema, so the agent
never needs write access to report.

## Tests

```bash
python -m pytest -q
(cd web/ui && npm test -- --run)
```

## License

[MIT](LICENSE)
