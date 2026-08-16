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

## Configuration

| Env | Default | Meaning |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Optional if the Claude Code CLI is logged in |
| `PRS_MODEL` | `claude-sonnet-5` | Model for the deep-dive agent |
| `PRS_CLAIMS_MODEL` | `claude-haiku-4-5-20251001` | Model for claims + description drafting |
| `PRS_SESSION_ROOT` | `sessions` | Where per-phase results are written |
| `SLACK_WEBHOOK_URL` | — | Optional one-way notification |

`prsentinel.yml` holds the rest. Three settings write outside the review comment
and are **off by default**: `auto_describe` (rewrites the PR body),
`docs_fix_pr` (opens a follow-up PR with doc fixes), and `inline_suggestions`
(suggestion blocks on docs inside the diff — this one is on).

Cost control: `max_budget_usd` hard-stops a verify run, diff pruning keeps
generated files out of context, and `--reply` resumes the previous session
instead of starting over. `usage.json` records what each phase actually cost.

## Safety

The verify agent gets `Read`, `Grep` and `Glob` and nothing else — no writes, no
network, no shell unless `allow_bash` is set. It runs in a throwaway clone with
`setting_sources=[]`, so the host machine's `CLAUDE.md`, settings and skills
never reach the review. Findings come back through a JSON schema, so the agent
never needs write access to report.

## Tests

```bash
python -m pytest -q            # 183 tests
(cd web/ui && npm test -- --run)
```

## License

[MIT](LICENSE)
