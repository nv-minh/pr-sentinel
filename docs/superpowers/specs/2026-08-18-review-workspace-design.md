# Spec — Review workspace (agentic-editor UI), PR/repo management, meaning-based Vietnamese

**Date:** 2026-08-18
**Status:** agreed, ready to implement

## Problem

1. **Reviewing is hard.** The PR page is tiles + a graph + 10 flat tabs of prose. Evidence
   citations (`file:line`) are non-clickable chips; no diff or code is ever rendered — although
   `snapshot.json` stores the unified diff per file, `workspace/` holds a git clone at the PR
   head, and `transcripts/*.jsonl` holds the agent's tool-call trace.
2. **Repo/PR management is thin.** `/` is two flat lists without search or actions; add/remove
   repo hides on Config; RepoDetail never polls (running reviews freeze on screen); PrDetail
   polls forever even when idle.
3. **Vietnamese is word-by-word.** 201 dictionary pairs contain literal calques — "Hợp đồng"
   (API contracts), "Tuyên bố" (claims), "Ảnh chụp" (snapshot), "Kho mã" (repos) — with no
   glossary pinning which terms stay English.

## What we are building

- **`/` Repos = repo management home.** Card grid: KPIs, gate band, verdict chips, mode badge +
  inline mode switch, two-step remove, inline add-repo, search/sort persisted in the URL query.
  Config keeps provider/language/poller and drops its repo table.
- **`/repos/:o/:r` = PR queue.** Sections Running / Blocked / Warned / Passed / Not scored /
  Not reviewed / Draft; verdict+gate chips and actions per row; text + gate filters; polls
  `/review/status` only while something runs and refetches once on the running→false edge.
- **`/repos/:o/:r/pr/:n` = review workspace** (three panes, full width; `pages/PrDetail.tsx`
  replaced by `src/workspace/`):
  - Header: title, gate banner with collapsible reasons, actions, 11-phase status strip.
  - Left: findings grouped by blast radius (contract → caller → claim → impact → doc → test →
    cross-PR → thread) + changed-file tree with per-file finding counts and viewed marks
    (localStorage keyed by `head_sha`).
  - Center: GitHub-style per-file diffs (`@git-diff-view/react`, lazy chunk, unified/split),
    finding cards inline under their anchored lines; PoC failing tests and doc-fix patches as
    attached sub-cards with copy buttons; unanchorable findings in a trailing section;
    fallback ladder for empty/truncated/unparseable patches.
  - Right (tabs): Overview · Pipeline (existing React Flow graph relocated) · Report (rendered
    `report.md`, in-house XSS-safe GFM-subset renderer) · Run (live log, per-phase cost, agent
    trace timeline).
  - Evidence chips parse defensively (`path:12`, `path:12-34`, `path:12 words`, else plain);
    in-diff → scroll+flash, outside diff → workspace peek (graceful 404). Deep links
    `?tab=&file=&finding=`; keyboard j/k/v/Escape.
- **Backend (read-only, disk-derived):** `GET …/pr/{n}/files`, `…/file?path&start&end`
  (traversal-guarded), `…/extras`, `…/trace`; JSON 404 for unknown `/api/*`; `mode` joined onto
  `/api/repos`; `parse_ref` accepts ranges/trailing words; demo fixtures get real hunk headers.
- **Vietnamese:** glossary block pins loanwords (PR, repo, review, merge, commit, diff, patch,
  snapshot, claim, contract, caller, test, gate, docs, thread, pipeline, phase, log, trace,
  workspace, session, schema, parse, model, provider, token, API key, exit code, comment,
  ticket, CI); ~80 of 201 values rewritten meaning-first; status enums stay English.

## Decisions

1. No react-router / TanStack / i18next. The hand-rolled router gains query helpers + `<Link>`;
   one internal hook module (`useApi` with abort + stale-response guard, `usePoll` that stops
   when idle) replaces raw fetch-in-effect everywhere.
2. One new dependency pair: `@git-diff-view/react` + lowlight highlighter, confined to the lazy
   diff chunk.
3. Keep the visual identity (token layer, sans/mono split, hairlines) and every a11y invariant:
   glyph + word + colour, one h1 per route, keyboard reachability, `prefers-reduced-motion`,
   aria-hidden canvas with a text equivalent.
4. Findings keep the blocking-first priority (contracts → callers → claims → impact → docs →
   tests) that the old BLOCKING ledger encoded; it becomes the nav grouping + j/k order.
5. Sequencing: backend → foundation → management pages → workspace → Vietnamese rewrite →
   sweep. Conventional Commits, one per increment, on `feat/review-workspace`.

## Out of scope

SSE/websockets, React Router, GitHub write actions from the UI, review-pipeline/prompt/scoring
changes, SSR.

## Acceptance

- Full `pytest -q` and `npm test -- --run` green; `npm run build` clean; diff viewer in its own
  chunk; entry chunk not grown.
- `/repos/demo/app/pr/8` renders the workspace offline: inline cards on real hunks, the
  contract card reachable via `?finding=contract-0`, peek shows the workspace-unavailable state.
- A review started from the queue animates Running → sections re-sort without a reload, and
  polling stops when the run ends.
- The Vietnamese dashboard reads like a Vietnamese developer wrote it; status vocabulary stays
  English; both themes, EN↔VI, 375px smoke pass.
