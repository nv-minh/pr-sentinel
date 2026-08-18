# Spec — Vietnamese UI and review-output language

**Date:** 2026-08-17
**Status:** design approved, ready for an implementation plan

## Problem

A Vietnamese reviewer opens the dashboard and reads English. Every label, every
empty state, every `aria-label` in `web/ui/src` is a hardcoded English literal —
there is no locale layer at all, and no way to add one without touching every
component.

The review output is a different problem with a different shape. `prsentinel.yml`
already carries `language: en | vi`, and it already reaches three prompts. But it
does not reach the follow-up pass, so a repository configured for Vietnamese gets
a Vietnamese first review and English on every reply after it — the one place a
human is actually in a conversation with the agent. And nothing in the dashboard
shows the setting exists, so an operator has to know to open the YAML.

These are two settings, not one. A reviewer who reads Vietnamese may still need
the agent to write English into a public PR that an international team reads.

## What already exists

Worth stating plainly so the plan does not rebuild it:

- `language: en | vi` is defined and defaulted in `src/autoreview_config.py:19-21`
  and validated in `validate_config` (`autoreview_config.py:74-75`).
- It is threaded into three prompts: `src/verify.py:230-231` (findings notes and
  unresolved questions), `src/describe.py:84-86` (a drafted PR body), and
  `src/poc.py:103-105` (PoC test reasons).
- `src/verify.py:25` holds `LANGUAGES = {"en": "English", "vi": "Vietnamese"}` —
  the single map, to be imported rather than copied.
- `web/ui/src/theme.ts` is a working module-level store read through
  `useSyncExternalStore`. The i18n store is the same shape, for the same reason
  its comment gives at lines 13-17: per-component `useState` left the header and
  the graph disagreeing about the current value.

## Scope

Two independent settings:

1. **UI language** — per browser, `localStorage`, switched from the header.
   Never written to the config file, never sent to the server.
2. **Review-output language** — `prsentinel.yml`, applies to every review
   including CI runs. Readable and settable from the Config page.

**Non-goals**, named so a reader does not look for them:

- **Translating the status vocabulary.** `PASS`, `FAIL`, `STALE`, `BROKEN`,
  `NEEDS_UPDATE`, `BREAKING_API_CHANGE` and the rest stay English in the UI.
  They are enum values from the findings JSON schema; they appear verbatim in
  the comment posted to GitHub and in the artifacts CI reads. A translated UI
  label would no longer match the PR it describes.
- **Translating the GitHub summary markdown.** The section headings built in
  `src/synthesize.py:167-185` and `src/run.py:88` are template text, not model
  output. Their prose contents already follow `language` because they come from
  findings.
- **Translating the Jira comment framing** (`src/jira_report.py:22`). Same
  reasoning; its notes and questions already follow `language`.
- **Translating `new_snippet`** in doc patches. See "The remediate split" below.
- **A third language.** The interfaces are shaped so adding one is additive, but
  nothing beyond `en` and `vi` is built or tested here.
- **Server-side UI translation.** `/api/*` responses stay exactly as they are;
  they are the same JSON that CI consumes.

## Rejected alternatives

**`react-i18next`.** The standard choice, rejected on two counts. Its headline
features do not pay off here: Vietnamese has no plural forms, and the handful of
English count strings can be written neutrally. And its default behaviour is to
fall back silently to the key when a translation is missing — losing exactly the
guarantee the hand-rolled version buys (below). It would also add two
dependencies and a provider wrapper to a UI that hand-writes its router
(`router.ts`, 36 lines) and its theme store.

**One setting driving both.** Rejected: it forces a Vietnamese-reading operator
to publish Vietnamese review comments on a PR their international team reads,
and it makes changing the interface language a file write plus a server
round-trip.

**Per-component translation maps.** No way to verify completeness, and every
component invents its own key naming.

## Design

### 1. `web/ui/src/i18n.ts` — the locale store

Mirrors `theme.ts` exactly: one module-level variable, a `Set` of listeners, read
through `useSyncExternalStore` so every caller observes one value and every
caller re-renders when any caller changes it.

```ts
export type Lang = 'en' | 'vi'
export function useLang(): [Lang, (next: Lang) => void]
export function useT(): (key: Key, vars?: Record<string, string | number>) => string
```

- Key: `localStorage['pr-sentinel-lang']`.
- `detect()`: stored value if valid, else `navigator.language.startsWith('vi')
  ? 'vi' : 'en'`.
- `write(next)` sets `document.documentElement.lang = next`, the counterpart to
  `theme.ts` writing `data-theme`. This is a real accessibility requirement, not
  bookkeeping: a screen reader announcing Vietnamese text under `<html lang="en">`
  mispronounces it.
- A **setter**, not a toggle. `theme.ts` exposes a toggle because a theme is
  binary by nature; a language is not, and a toggle would have to be rewritten
  the first time a third language appears.
- Interpolation is a one-line `{name}` replacement. No ICU, no plural machinery.

### 2. `web/ui/src/strings.ts` — the dictionary

```ts
const en = { 'nav.repos': 'Repos', /* … */ }
const vi: Record<keyof typeof en, string> = { 'nav.repos': 'Kho mã', /* … */ }
```

The annotation makes a **missing** Vietnamese key a `tsc -b` error — and `tsc -b`
already runs as the first half of `npm run build`, so an incomplete translation
cannot reach a bundle.

(An earlier draft of this spec justified spelling it `Record<keyof typeof en,
string>` rather than `typeof en` on the grounds that `typeof en` would infer
literal types and demand identical values. That is wrong, and a reviewer
disproved it with a standalone `tsc --strict` run: because `en` is declared
without `as const`, `typeof en` widens each property to `string`, so differing
Vietnamese values compile fine either way. Both spellings reject a missing key
equally. The `Record` form is kept because it states the intent directly, not
because the alternative fails.)

Flat dotted keys, grouped by namespace: `nav.*`, `common.*`, `repos.*`,
`repo.*`, `pr.*`, `config.*`, `gate.*`, `graph.phase.*`, `graph.metric.*`,
`graph.status.*`.

### 3. Applying it

| File | Change |
|---|---|
| `App.tsx` | nav labels, theme button `aria-label`, plus a new `EN`/`VI` button beside the theme button, same styling, showing the *target* language |
| `components.tsx` | `Loading` (default `'Loading'`), `Empty`, `GateBand` (`'No scored reviews yet'`, its `aria-label` and `title`) |
| `pages/Repos.tsx`, `pages/RepoDetail.tsx`, `pages/PrDetail.tsx`, `pages/Config.tsx` | the bulk of the work; `PrDetail` and `Config` hold roughly half the strings between them |
| `graph/layout.ts` | `STATUS_WORD` (`done`/`running`/`failed`/`pending`/`skipped`) becomes `graph.status.*` keys |
| `graph/PhaseNode.tsx` | renders phase and metric labels through the lookup below |
| `graph/PipelineGraph.tsx` | the screen-reader equivalent list (`:102-122`) renders the same `node.label` and `STATUS_WORD` as the canvas nodes, and must translate identically — a mismatch here is worse than English, because a sighted user and a screen-reader user would be reading different words for the same phase |
| `index.html` | `<html lang>` becomes the initial value that `i18n.ts` overwrites at runtime |

Two boundary decisions:

**`status.ts` stays language-free.** `bandSegments()` currently returns a `label`
read from `GATE_WORD` (`status.ts:46-51`, `:80`). Drop `label` from `Segment`;
callers render `t(\`gate.${seg.key}\`)`. `status.ts` remains a pure data module
and `status.test.ts` never has to stand up a locale context. `GATE_WORD` moves
into `strings.ts` as `gate.pass` / `gate.warn` / `gate.fail` / `gate.unknown`.

**Graph labels are translated in the UI, keyed by the server's stable ids.**
`web/metrics.py:355-364` emits `label: "Snapshot" | "Doc fixes" | …` alongside a
stable `id`, and `metrics[].label` values (`files`, `claims`, `callers`,
`patches`, …). The UI looks these up as `graph.phase.<id>` and
`graph.metric.<label>`, leaving the API response untouched — it is the same JSON
CI reads.

The trade-off, stated rather than hidden: this one category is a **lookup with a
fallback to the server's English string**, not a total map, because its keys
arrive at runtime. A phase added to `metrics.py` without a matching dictionary
entry renders in English instead of failing the build. The cross-language test
below is what closes that gap.

### 4. Config page and the language endpoint

- `api_config()` (`web/server.py:131-158`) adds `"language": cfg.get("language")`.
- `POST /api/config/language` mirrors `api_set_provider` (`server.py:161-173`);
  a value outside `en|vi` is a 400.
- `autoreview_config.set_language(path, lang)` mirrors **`set_provider`
  (`autoreview_config.py:166-184`), not `set_repo_mode`.** `set_repo_mode` writes
  through `_write_atomic` → `yaml.safe_dump`, which rewrites the whole document
  and **deletes every comment in `prsentinel.yml`** — including the block that
  documents `language` itself. `set_provider` avoids this by regex-replacing the
  single `^provider:` line in the raw text, for the reason its docstring gives at
  lines 170-172. `set_language` does the same to `^language:`, appending the key
  if absent.
- The value is validated before the write, so a bad request cannot leave a file
  that `load_config` then refuses to read.
- `api.ts` gains `language` on `ConfigState` and a `setLanguage` call.
- The Config page gains a **Language** block holding both controls side by side,
  labelled so the difference is unmissable: *Interface* (this browser only,
  shares state with the header button) and *Review output* (written to
  `prsentinel.yml`, applies to every review including CI). A note records that
  status codes stay English so the UI matches the comment on GitHub.

### 5. The two prompts that never received `language`

**`threads.py` — the follow-up pass.** `build_followup_prompt`
(`threads.py:126-159`) takes a `language` parameter and appends the same
sentence `verify.py:230-231` appends; `run_followup` passes
`cfg.get("language", "en")`. `LANGUAGES` comes from the existing
`from verify import …` line (`threads.py:17`) — one map, not two.

**`remediate.py` — the doc-patch pass.** `build_prompt`
(`remediate.py:58-77`) takes `language`, and its instruction must be **split**
rather than reusing verify's sentence verbatim:

- `why` — the model's account of what the code actually does — follows the
  configured language.
- `new_snippet` — **always the documentation's own language.** It is pasted
  straight into the file through a GitHub suggestion block. A prompt that says
  "write everything in Vietnamese" will translate the README and commit it.

`draft_patches` passes `cfg.get("language", "en")`.

## Testing

**Python (pytest)** — following `tests/test_verify.py:284-301`:

- `build_followup_prompt(language="vi")` contains `Vietnamese`; `language="en"`
  does not add a language sentence.
- `run_followup` forwards `cfg["language"]` to the prompt builder.
- `remediate.build_prompt(language="vi")` contains both the language instruction
  **and** the instruction to keep `new_snippet` in the document's language.
- `set_language` rewrites the key and **leaves the file's comments intact**
  (assert on the raw text, not the parsed dict); rejects `fr`.
- `GET /api/config` returns `language`; `POST /api/config/language` with `fr`
  returns 400.

**Cross-language completeness test (pytest).** Read `web/ui/src/strings.ts` as
text and assert every id in `web/metrics.py`'s `ORDER` has a `graph.phase.<id>`
key. It lives on the Python side because `metrics.py` is the source of truth for
the phase list: adding a phase there without translating it fails a test instead
of silently rendering English.

**UI (vitest)** — following `theme.test.tsx`:

- `i18n.test.ts`: the store is shared across two components; `useLang` persists
  to `localStorage`; `document.documentElement.lang` follows the value.
- `a11y.test.tsx`: the language button has an `aria-label`, and `<html lang>`
  changes when it is pressed.
- No test asserts dictionary completeness for `en`/`vi` — `tsc -b` does that.

## Documentation

`README.md:267` already documents `language: en | vi`. Extend it to say the
dashboard exposes it, and that the interface language is a separate, per-browser
setting that does not affect what the agent writes.

The same list of what `language` reaches is duplicated in two more places: the
`#` block above the `language:` key in `prsentinel.yml`, and the `#` block above
the `DEFAULTS["language"]` entry in `src/autoreview_config.py`. All three —
`README.md:267`, `prsentinel.yml` and `src/autoreview_config.py` — must be kept
in sync whenever what `language` covers changes.

## Files touched

**New:** `web/ui/src/i18n.ts`, `web/ui/src/strings.ts`, `web/ui/src/i18n.test.ts`.

**Modified:** `web/ui/src/{App,components}.tsx`, `web/ui/src/pages/*.tsx` (4),
`web/ui/src/graph/{layout.ts,PhaseNode.tsx,PipelineGraph.tsx}`,
`web/ui/src/status.ts`, `web/ui/src/api.ts`,
`web/ui/src/{App,a11y,components}.test*`,
`web/ui/src/graph/PipelineGraph.test.tsx`,
`web/server.py`, `src/autoreview_config.py`, `src/threads.py`,
`src/remediate.py`, `tests/*`, `README.md`.

## Risks

- **Translation drift in the graph lookup** — mitigated by the cross-language
  test, bounded by an English fallback rather than a crash.
- **Layout under longer Vietnamese strings.** Vietnamese runs longer than English
  for the same label, and several surfaces are fixed-width — the `160px` phase
  node (`PhaseNode.tsx`), the `110px` mode select and `180px` provider select
  (`Config.tsx:101,157`), and the uppercase mono nav. Translations are chosen to
  fit; where they cannot, the width gives rather than the word being truncated.
- **`set_language` is a regex edit on operator-authored YAML.** The same
  exposure `set_provider` already carries. Bounded by validating before writing
  and re-loading after.
