# Spec — Dashboard UI/UX migration

**Date:** 2026-08-16
**Status:** agreed, ready to implement

## Problem

The dashboard works but reads like a log file. Concretely:

1. **The pipeline is invisible.** A review is seven phases with a branch and a
   loop (snapshot → describe → claims → verify → score → ask → report, plus doc
   remediation off verify and a reply loop back into it). The UI shows none of
   that — while a review runs you get a `<pre>` tail of `review.log`, and when it
   finishes you get numbers with no sense of what produced them.
2. **Findings are filed, not ranked.** `PrDetail` puts nine equal tabs across the
   top — Claims, Docs, Impact, Callers, Contracts, Tests, Threads, Confirm,
   Context. A blocking `SCHEMA_MIGRATION_RISK` sits three clicks away, indistinguishable
   in weight from an empty Threads tab.
3. **Everything is hand-rolled.** 375 lines of bespoke CSS, no component
   primitives, no loading or empty states beyond `Loading…`, no keyboard
   affordances, no focus management. Adding a control means writing a dropdown
   from scratch.

## What we are building

A migration of `web/ui` to **Tailwind CSS v4 + shadcn/ui**, and a **React Flow
(`@xyflow/react`) node graph** as the primary view of a review run.

### The graph

Each phase is a node carrying its own status, cost, duration, model and headline
counts. Clicking a node selects it and the panel below shows that phase's
detail — findings for verify, gate reasons for score, questions for ask, the
rendered report for report. So the graph is a **navigation surface**, not an
illustration: it is how you get to the evidence.

The pipeline is a genuine DAG, which is what makes the shape worth drawing:

```
                    ┌──────────┐
                    │ Replies  │──┐   (reply loop, --reply)
                    └──────────┘  │
                                  ▼
Snapshot ─▶ Describe ─▶ Claims ─▶ Verify ─▶ Score ─▶ Confirm ─▶ Report
                                     │                            ▲
                                     └────▶ Doc fixes ────────────┘
```

Backend support is a new `GET /api/repos/{owner}/{repo}/pr/{n}/graph` endpoint
that derives node status purely from the artifacts already on disk in
`sessions/` — no new state, no database, consistent with the rest of the app.

## Decisions

1. **Stack:** Tailwind CSS v4 (`@tailwindcss/vite`), shadcn/ui components copied
   into the repo, `@xyflow/react` 12.x. No component library lock-in, no CDN.
2. **Keep the existing router.** Four routes; `src/router.ts` stays.
3. **Keep the visual identity.** The current palette and the sans/mono split
   (humans speak in sans, the machine speaks in monospace) are the good part of
   today's design. The tokens are ported into `@theme` rather than replaced.
4. **Keep the existing test suite green.** `App.test.tsx` selects on `.band-seg`,
   `.tab`, and rendered text. Those hooks stay on the new markup, so the suite is
   a real regression net across the migration rather than something rewritten to
   match whatever was built.
5. **Accessibility is not negotiable.** Every status keeps glyph + word + colour
   (the amber/red pair is hard to separate for deutan vision) — that rule
   predates this migration and survives it. The graph gets a text equivalent for
   screen readers, and `prefers-reduced-motion` disables its animated edges.
6. **Dark mode stays attribute-driven.** The theme toggle writes
   `data-theme` on `<html>`; Tailwind v4's dark variant is repointed at that
   attribute instead of `prefers-color-scheme`.
7. **The graph is lazy-loaded.** React Flow is ~100 kB gzipped and only the PR
   detail route needs it.

## Node status model

Derived from files in `sessions/<owner>/<repo>/pr-<n>/`:

| status | meaning |
|---|---|
| `done` | the phase's artifact exists |
| `running` | `review.lock` holds a live PID and this is the first unfinished phase |
| `pending` | not run yet |
| `skipped` | not applicable to this review (a good PR body skips Describe; no fixable docs skips Doc fixes; no replies skips the reply loop) |
| `failed` | `report.md` begins with `# Review FAILED` |

Cost, duration and model come from `usage.json`, which already records one entry
per phase. Phases with no LLM call (snapshot, score, ask, report) simply carry no
cost.

## Out of scope

- Editing the graph. It is a read-only view of what happened; nodes are not
  draggable into a different pipeline.
- Replacing `src/router.ts` with React Router.
- Server-side rendering.
- Changing any review logic, scoring, or artifact format.

## Acceptance

- `npm run build` and `npm test -- --run` green; the four assertions in the
  existing `App.test.tsx` pass unmodified.
- `/repos/demo/app/pr/8` (the shipped demo session) renders the graph with
  Verify done, Score failed-gate, and Doc fixes skipped, and clicking Verify
  shows the contracts finding.
- A review started from the dashboard animates its node from `pending` to
  `running` to `done` without a page reload.
- Every interactive control is reachable by keyboard with a visible focus ring,
  in both themes.
- No network request leaves the page (no CDN fonts, no external assets).
