# Vietnamese UI and Review-Output Language Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the dashboard a Vietnamese interface switchable per browser, and make the existing `language: vi` config actually reach every prompt that writes prose.

**Architecture:** Two independent settings. The interface language is a module-level store in `web/ui/src/i18n.ts`, read through `useSyncExternalStore`, backed by `localStorage` — the exact shape `theme.ts` already uses. The review-output language stays in `prsentinel.yml`, gains a write endpoint, and is threaded into the two prompt builders that never received it.

**Tech Stack:** React 19 + TypeScript (strict, `tsc -b` in the build), Vitest + jsdom, FastAPI, pytest, PyYAML. **No new dependencies in either project.**

**Spec:** `docs/superpowers/specs/2026-08-17-vietnamese-i18n.md`

## Global Constraints

- **No new npm or pip dependencies.** The i18n layer is hand-written.
- **English values are frozen strings.** Existing tests assert them verbatim (`App.test.tsx`, `components.test.tsx`, `PipelineGraph.test.tsx`). When you move a string into `strings.ts`, the English value must be byte-identical to what the component renders today, including trailing spaces and the `…` ellipsis character. Changing English copy is out of scope.
- **The status vocabulary is never translated.** `PASS`, `FAIL`, `PARTIAL`, `UNVERIFIED`, `MATCH`, `STALE`, `WRONG`, `FABRICATED`, `CHANGED`, `BROKEN`, `UNAFFECTED`, `RISK`, `SAFE`, `NEEDS_UPDATE`, `COMPATIBLE`, `BREAKING_API_CHANGE`, `SCHEMA_MIGRATION_RISK`, `STRONG`, `WEAK`, `MISSING`, `RESOLVED`, `STILL_VALID`, `FIXED`, `OUTDATED`, `ACCURATE`, `MISLEADING`, `NO_CLAIMS` render as-is in both languages. `StatusWord`'s `'UNKNOWN'` fallback is part of that vocabulary — leave it alone.
- **`status.ts` stays language-free.** It is a pure data module; no component of it may import from `i18n.ts` or `strings.ts`.
- **Dictionary type contract:** `const vi: Record<keyof typeof en, string>`, so a **missing** Vietnamese key is a `tsc -b` error (and `npm run build` runs `tsc -b` first). Do not add a comment claiming `typeof en` would "infer literal types and demand identical values" — that is false, disproved during implementation with a standalone `tsc --strict` run: `en` is declared without `as const`, so `typeof en` widens to `string` and both spellings reject a missing key equally.
- **`/api/*` response shapes are additive only.** The only change is one new key (`language`) on `GET /api/config` and one new endpoint. CI reads this JSON.
- **Config writes preserve comments.** Any new `prsentinel.yml` writer edits the raw text line, following `set_provider` (`src/autoreview_config.py:166-184`). Never `yaml.safe_dump` a whole config back.
- **Python style:** 4-space indent, ≤ 88 columns, tests named `test_<behaviour_in_a_sentence>`.
- **Commit style:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`).

**Verification commands** (used throughout):

```bash
# from the repo root, with .venv activated
pytest tests/ -q
# from web/ui
npm test -- --run
npm run build          # tsc -b && vite build — this is what catches a missing vi key
```

---

### Task 1: The locale store and the header switcher

**Files:**
- Create: `web/ui/src/i18n.ts`
- Create: `web/ui/src/strings.ts`
- Create: `web/ui/src/i18n.test.ts`
- Modify: `web/ui/src/App.tsx:15-58`
- Modify: `web/ui/index.html:2`

**Interfaces:**
- Consumes: nothing.
- Produces: `type Lang = 'en' | 'vi'`; `useLang(): [Lang, (next: Lang) => void]`; `useT(): (key: Key, vars?: Vars) => string`; `useLookup(): (key: string, fallback: string) => string`; `translate(lang: Lang, key: Key, vars?: Vars): string`; `type Key = keyof typeof en`; `type Vars = Record<string, string | number>`. Every later task adds keys to `strings.ts` and calls `useT()`.

- [ ] **Step 1: Write the failing test**

Create `web/ui/src/i18n.test.ts`. Note the `.ts` extension — it uses `React.createElement` rather than JSX so the file does not need to be `.tsx`; the fixture shape is lifted from `theme.test.tsx:11-50`, which is the working precedent for this exact store pattern.

```ts
// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useLang, useT, translate } from './i18n'

function Reader({ id }: { id: string }) {
  const [lang] = useLang()
  return createElement('span', { 'data-testid': id }, lang)
}

function Greeter() {
  const t = useT()
  return createElement('span', { 'data-testid': 'greeting' }, t('nav.repos'))
}

function Switcher() {
  const [lang, setLang] = useLang()
  return createElement('button', {
    type: 'button',
    onClick: () => setLang(lang === 'vi' ? 'en' : 'vi'),
  }, 'switch')
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
  document.documentElement.removeAttribute('lang')
  vi.stubGlobal('navigator', { language: 'en-US' })
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  vi.unstubAllGlobals()
})

function render(node: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  act(() => {
    root = createRoot(container)
    root.render(node)
  })
}

describe('translate', () => {
  it('returns the string for the requested language', () => {
    expect(translate('en', 'nav.repos')).toBe('Repos')
    expect(translate('vi', 'nav.repos')).toBe('Kho mã')
  })

  it('substitutes every occurrence of a named variable', () => {
    expect(translate('en', 'repos.bugs', { n: 6 })).toBe('6 bugs')
  })

  it('leaves an unsupplied placeholder in place rather than printing undefined', () => {
    expect(translate('en', 'repos.bugs')).toBe('{n} bugs')
  })
})

describe('useLang', () => {
  it('is one shared source of truth: switching in one caller is observed by another', () => {
    render(createElement('div', null,
      createElement(Switcher),
      createElement(Reader, { id: 'a' }),
      createElement(Reader, { id: 'b' })))
    const readerA = () => container.querySelector('[data-testid="a"]')!.textContent
    const readerB = () => container.querySelector('[data-testid="b"]')!.textContent

    expect(readerA()).toBe('en')
    expect(readerB()).toBe('en')

    act(() => { (container.querySelector('button') as HTMLButtonElement).click() })

    expect(readerA()).toBe('vi')
    expect(readerB()).toBe('vi')
  })

  it('re-renders translated text when the language changes', () => {
    render(createElement('div', null,
      createElement(Switcher),
      createElement(Greeter)))
    const greeting = () => container.querySelector('[data-testid="greeting"]')!.textContent

    expect(greeting()).toBe('Repos')
    act(() => { (container.querySelector('button') as HTMLButtonElement).click() })
    expect(greeting()).toBe('Kho mã')
  })

  it('writes the choice to <html lang> and localStorage', () => {
    render(createElement('div', null, createElement(Switcher)))
    expect(document.documentElement.lang).toBe('en')

    act(() => { (container.querySelector('button') as HTMLButtonElement).click() })

    expect(document.documentElement.lang).toBe('vi')
    expect(localStorage.getItem('pr-sentinel-lang')).toBe('vi')
  })

  it('defaults to Vietnamese for a Vietnamese browser and English otherwise', () => {
    vi.stubGlobal('navigator', { language: 'vi-VN' })
    render(createElement('div', null, createElement(Reader, { id: 'a' })))
    expect(container.querySelector('[data-testid="a"]')!.textContent).toBe('vi')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web/ui && npm test -- --run src/i18n.test.ts
```

Expected: FAIL — `Failed to resolve import "./i18n"`.

- [ ] **Step 3: Create the dictionary**

Create `web/ui/src/strings.ts`. This task seeds it with the header keys plus the two keys the tests above reach for; later tasks append to the same two objects.

```ts
/* The interface dictionary. English is the source of truth for the key set:
   `vi` is typed as Record<keyof typeof en, string>, so a key added here and
   forgotten there is a `tsc -b` error, and `npm run build` runs tsc first.

   Status vocabulary (PASS, STALE, BREAKING_API_CHANGE …) is absent on purpose:
   those are enum values from the findings schema, they appear verbatim in the
   comment posted to GitHub, and a translated dashboard label would no longer
   match the pull request it describes. */

const en = {
  'nav.repos': 'Repos',
  'nav.config': 'Config',
  'nav.themeLight': 'Light',
  'nav.themeDark': 'Dark',
  'nav.themeSwitchToLight': 'Switch to light theme',
  'nav.themeSwitchToDark': 'Switch to dark theme',
  'nav.langSwitchToVi': 'Chuyển giao diện sang tiếng Việt',
  'nav.langSwitchToEn': 'Switch interface to English',
  'repos.bugs': '{n} bugs',
}

const vi: Record<keyof typeof en, string> = {
  'nav.repos': 'Kho mã',
  'nav.config': 'Cấu hình',
  'nav.themeLight': 'Sáng',
  'nav.themeDark': 'Tối',
  'nav.themeSwitchToLight': 'Chuyển sang giao diện sáng',
  'nav.themeSwitchToDark': 'Chuyển sang giao diện tối',
  'nav.langSwitchToVi': 'Chuyển giao diện sang tiếng Việt',
  'nav.langSwitchToEn': 'Switch interface to English',
  'repos.bugs': '{n} lỗi',
}

export type Key = keyof typeof en
export type Vars = Record<string, string | number>

// Annotated rather than inferred so TABLES[lang][key] is `string`, not the
// union of en's literal types with vi's `string`.
export const TABLES: Record<'en' | 'vi', Record<Key, string>> = { en, vi }

/** Phase and metric labels arrive from the server at runtime (see
 *  web/metrics.py PHASES), so unlike everything above they cannot be a total
 *  map checked by the compiler. An id with no entry falls back to the server's
 *  English string. tests/test_ui_strings.py is what stops that going unnoticed. */
export function lookup(lang: 'en' | 'vi', key: string, fallback: string): string {
  const table = TABLES[lang] as Record<string, string | undefined>
  return table[key] ?? fallback
}
```

- [ ] **Step 4: Create the store**

Create `web/ui/src/i18n.ts`:

```ts
import { useCallback, useSyncExternalStore } from 'react'
import { TABLES, lookup, type Key, type Vars } from './strings'

export type Lang = 'en' | 'vi'

const KEY = 'pr-sentinel-lang'

function detect(): Lang {
  const stored = localStorage.getItem(KEY)
  if (stored === 'en' || stored === 'vi') return stored
  return navigator.language?.startsWith('vi') ? 'vi' : 'en'
}

// Module-level store, for the reason theme.ts:13-17 records: with a useState
// per caller, the header would switch language and the pages would not.
let lang: Lang | null = null
const listeners = new Set<() => void>()

function write(next: Lang) {
  // The counterpart to theme.ts writing <html data-theme>. Not bookkeeping: a
  // screen reader announcing Vietnamese under lang="en" mispronounces it.
  document.documentElement.lang = next
  localStorage.setItem(KEY, next)
}

function ensureInitialized(): Lang {
  if (lang === null) {
    lang = detect()
    write(lang)
  }
  return lang
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): Lang {
  return ensureInitialized()
}

/** Substitutes {name} placeholders. A placeholder with no matching variable is
 *  left as written rather than becoming "undefined" — a visible `{n}` is a bug
 *  report; the word "undefined" in the middle of a sentence is a mystery. */
export function translate(target: Lang, key: Key, vars?: Vars): string {
  const raw = TABLES[target][key]
  if (!vars) return raw
  return raw.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match)
}

/** The current language, and a setter. A setter rather than a toggle: a
 *  language is not binary, and a toggle would have to be rewritten the first
 *  time a third one is added. */
export function useLang(): [Lang, (next: Lang) => void] {
  const value = useSyncExternalStore(subscribe, getSnapshot)
  const set = useCallback((next: Lang) => {
    lang = next
    write(next)
    listeners.forEach((listener) => listener())
  }, [])
  return [value, set]
}

/** The translator, bound to the current language and re-created when it
 *  changes, so every component calling it re-renders on a switch. */
export function useT(): (key: Key, vars?: Vars) => string {
  const value = useSyncExternalStore(subscribe, getSnapshot)
  return useCallback((key: Key, vars?: Vars) => translate(value, key, vars), [value])
}

/** For server-supplied labels, which are looked up by a runtime string and
 *  fall back to what the server sent. See strings.ts `lookup`. */
export function useLookup(): (key: string, fallback: string) => string {
  const value = useSyncExternalStore(subscribe, getSnapshot)
  return useCallback((key: string, fallback: string) =>
    lookup(value, key, fallback), [value])
}
```

- [ ] **Step 5: Run the test to verify it passes**

```bash
cd web/ui && npm test -- --run src/i18n.test.ts
```

Expected: PASS, 7 tests.

- [ ] **Step 6: Wire the header and add the language button**

In `web/ui/src/App.tsx`, add the imports:

```tsx
import { useLang, useT } from './i18n'
```

Inside `App()`, after `const [theme, toggleTheme] = useTheme()`:

```tsx
  const [lang, setLang] = useLang()
  const t = useT()
```

Replace the two nav anchors' text and the theme button (`App.tsx:31-45`) with:

```tsx
          <a {...link('/')} className={NAV_LINK}
             aria-current={route.name === 'repos' ? 'page' : undefined}>
            {t('nav.repos')}
          </a>
          <a {...link('/config')} className={NAV_LINK}
             aria-current={route.name === 'config' ? 'page' : undefined}>
            {t('nav.config')}
          </a>
          <button
            className="rounded border border-hairline-strong px-[9px] py-1 font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted hover:border-ink-muted hover:text-ink"
            onClick={() => setLang(lang === 'vi' ? 'en' : 'vi')}
            aria-label={lang === 'vi' ? t('nav.langSwitchToEn') : t('nav.langSwitchToVi')}
          >
            {lang === 'vi' ? 'EN' : 'VI'}
          </button>
          <button
            className="rounded border border-hairline-strong px-[9px] py-1 font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted hover:border-ink-muted hover:text-ink"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? t('nav.themeSwitchToLight') : t('nav.themeSwitchToDark')}
          >
            {theme === 'dark' ? t('nav.themeLight') : t('nav.themeDark')}
          </button>
```

The language button's own label is the language code, never translated — `EN` and `VI` are how a reader who cannot read the current interface finds the way out.

In `web/ui/index.html:2`, leave `<html lang="en">` as written; `i18n.ts` overwrites it on first render. No edit needed — this step exists so you confirm it rather than change it.

- [ ] **Step 7: Assert the switcher in the accessibility suite**

`a11y.test.tsx` already proves every button has an accessible name on four routes (`unnamedButtons()`, `:150-152`), so the new button is covered by construction. What is not yet covered is the document language. Add one test to `web/ui/src/a11y.test.tsx`, immediately after `it('sets the theme attribute on the document element', …)` (`:165-168`):

```tsx
  it('declares the document language and updates it when the switcher is used', async () => {
    await render('/')
    expect(['en', 'vi']).toContain(document.documentElement.lang)

    const button = Array.from(container.querySelectorAll('button'))
      .find((b) => ['EN', 'VI'].includes((b.textContent ?? '').trim())) as HTMLButtonElement
    expect(button).toBeDefined()

    const before = document.documentElement.lang
    await act(async () => { button.click() })

    // A screen reader pronounces the page by this attribute; a Vietnamese
    // interface under lang="en" is read out in the wrong phonology.
    expect(document.documentElement.lang).not.toBe(before)
    expect(button.getAttribute('aria-label')).toBeTruthy()
  })
```

Be accurate about what this leaves behind: `localStorage.removeItem('pr-sentinel-lang')` in `beforeEach` clears the *persisted* value, but the module-level store keeps whatever the click set for the rest of the file — vitest isolates modules per file, not per test. That is harmless here because every other assertion in `a11y.test.tsx` is structural (button names, `h1` counts, roles) and none reads English copy. Add the `beforeEach` line anyway so the file starts from a known persisted state; do not try to reach into the store to reset it.

- [ ] **Step 8: Verify the whole UI suite and the build**

```bash
cd web/ui && npm test -- --run && npm run build
```

Expected: all suites PASS (`App.test.tsx` still finds `Repos`/`Config` because the English values are unchanged), build succeeds.

- [ ] **Step 9: Commit**

```bash
git add web/ui/src/i18n.ts web/ui/src/strings.ts web/ui/src/i18n.test.ts web/ui/src/App.tsx web/ui/src/a11y.test.tsx
git commit -m "feat(ui): a per-browser interface language store and header switcher"
```

---

### Task 2: Shared components and the status.ts boundary

**Files:**
- Modify: `web/ui/src/status.ts:46-51,63-85`
- Modify: `web/ui/src/components.tsx:75-111,152-164,187-196`
- Modify: `web/ui/src/strings.ts`
- Test: `web/ui/src/components.test.tsx` (must pass unchanged), `web/ui/src/status.test.ts` (must pass unchanged)

**Interfaces:**
- Consumes: `useT` from Task 1.
- Produces: `Segment` without its `label` field — `{ key: Tone; count: number; share: number }`. `GATE_WORD` is deleted from `status.ts`; anything that wants a gate word calls `t('gate.pass' | 'gate.warn' | 'gate.fail' | 'gate.unknown')`. Task 4 depends on this, since `PrDetail.tsx:172` imports `GATE_WORD` today.

- [ ] **Step 1: Write the failing test**

Add to `web/ui/src/components.test.tsx`'s imports (the file currently imports `act` from `react` and its helpers from `vitest` at `:2-5`):

```tsx
import { useLang } from './i18n'
```

Add a switcher fixture next to the existing `render` helper (`:10-17`):

```tsx
// Drives the real store the way the header does, rather than reaching into
// the module — the test stays blind to how the store is implemented.
function LangSwitcher() {
  const [, setLang] = useLang()
  return (
    <>
      <button type="button" data-testid="to-vi" onClick={() => setLang('vi')}>vi</button>
      <button type="button" data-testid="to-en" onClick={() => setLang('en')}>en</button>
    </>
  )
}
```

Then add this test inside the existing `describe('primitives', …)` block, after the `'says so when there is nothing to band'` test (`:48-51`):

```tsx
  it('translates the gate legend without translating the status vocabulary', () => {
    render(
      <>
        <LangSwitcher />
        <GateBand counts={{ pass: 2, fail: 1 }} />
      </>,
    )
    expect(container.textContent).toContain('Clear to merge')

    act(() => { (container.querySelector('[data-testid="to-vi"]') as HTMLButtonElement).click() })

    expect(container.textContent).toContain('Sẵn sàng merge')
    expect(container.textContent).toContain('Bị chặn')
    expect(container.textContent).not.toContain('Clear to merge')
    // The glyphs carry the reading when colour cannot; they are not words.
    expect(container.textContent).toContain('✓')

    // Switch back inside the test: the store is module-level, so leaving it on
    // 'vi' would hand the next test in this file a Vietnamese GateBand and
    // break the exact aria-label assertion at :45.
    act(() => { (container.querySelector('[data-testid="to-en"]') as HTMLButtonElement).click() })
    expect(container.textContent).toContain('Clear to merge')
  })
```

Also add `localStorage.clear()` to this file's `beforeEach` (`:19-21`), so a value left by another suite cannot start it in Vietnamese.

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd web/ui && npm test -- --run src/components.test.tsx
```

Expected: FAIL — the Vietnamese string is absent because `GateBand` still reads `GATE_WORD`.

- [ ] **Step 3: Add the keys**

Append to `en` in `web/ui/src/strings.ts`:

```ts
  'gate.pass': 'Clear to merge',
  'gate.warn': 'Merge with care',
  'gate.fail': 'Blocked',
  'gate.unknown': 'Not scored',
  'band.empty': 'No scored reviews yet',
  'common.loading': 'Loading',
  'common.yes': 'yes',
  'common.no': 'no',
  'common.noTitle': '(no title)',
  'citations.none': 'no evidence cited',
```

and to `vi`:

```ts
  'gate.pass': 'Sẵn sàng merge',
  'gate.warn': 'Merge có cân nhắc',
  'gate.fail': 'Bị chặn',
  'gate.unknown': 'Chưa chấm điểm',
  'band.empty': 'Chưa có review nào được chấm điểm',
  'common.loading': 'Đang tải',
  'common.yes': 'có',
  'common.no': 'không',
  'common.noTitle': '(không có tiêu đề)',
  'citations.none': 'không có bằng chứng nào được dẫn',
```

- [ ] **Step 4: Strip the language out of status.ts**

In `web/ui/src/status.ts`, delete the `GATE_WORD` constant (lines 46-51), drop `label` from the `Segment` interface, and drop it from the mapped object:

```ts
export interface Segment {
  key: Tone
  count: number
  share: number
}

/** Gate counts → band segments, largest share first is NOT applied: the order
 *  is fixed (pass → warn → fail → unknown) so a repo's band never repaints
 *  itself when one bucket changes. Empty buckets are dropped.
 *
 *  Returns the tone key, not a word: this module is pure data, and the words
 *  live in strings.ts so they can be translated without dragging a locale
 *  context into every consumer of bandSegments. */
export function bandSegments(counts: Record<string, number> | undefined): Segment[] {
  const order: Tone[] = ['pass', 'warn', 'fail', 'unknown']
  const total = order.reduce((sum, key) => sum + (counts?.[key] ?? 0), 0)
  if (!total) return []
  return order
    .map((key) => ({
      key,
      count: counts?.[key] ?? 0,
      share: (counts?.[key] ?? 0) / total,
    }))
    .filter((seg) => seg.count > 0)
}
```

- [ ] **Step 5: Translate the shared components**

In `web/ui/src/components.tsx`, add `import { useT } from './i18n'`, then:

`GateBand` (replacing lines 75-111) — note each `seg.label` becomes `t(\`gate.${seg.key}\`)`:

```tsx
export function GateBand({ counts }: { counts: Record<string, number> | undefined }) {
  const t = useT()
  const segments = bandSegments(counts)
  const word = (seg: { key: Tone }) => t(`gate.${seg.key}` as Key)
  if (!segments.length) {
    return (
      <div className="my-2.5 flex h-[34px] gap-0.5">
        <div className="flex flex-1 items-center justify-center rounded-sm border border-dashed border-hairline-strong font-mono text-xs text-ink-muted">
          {t('band.empty')}
        </div>
      </div>
    )
  }
  return (
    <>
      <div className="mt-1 mb-2.5 flex h-[34px] gap-0.5" role="img"
           aria-label={segments.map((s) => `${s.count} ${word(s)}`).join(', ')}>
        {segments.map((seg) => (
          <div
            key={seg.key}
            className="band-seg flex min-w-0.5 items-center justify-center rounded-sm font-mono text-xs font-semibold text-white"
            style={{ flex: seg.share, background: TONE_COLOR[seg.key] }}
            title={`${word(seg)}: ${seg.count}`}
          >
            {seg.share > 0.08 ? seg.count : ''}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-4 font-mono text-xs text-ink-muted">
        {segments.map((seg) => (
          <span className="flex items-center gap-[7px]" key={seg.key}>
            <ToneDot tone={seg.key} />
            {GLYPH[seg.key]} {word(seg)} · {seg.count}
          </span>
        ))}
      </div>
    </>
  )
}
```

Add `import type { Key } from './strings'` for the `as Key` assertion above. The assertion is safe because all four `gate.*` keys exist; it is needed because TypeScript cannot narrow a template literal against the key union on its own.

`Citations` (line 153):

```tsx
export function Citations({ items }: { items: string[] }) {
  const t = useT()
  if (!items?.length) return <span>{t('citations.none')}</span>
```

`Loading` (lines 187-196) — the default moves from a parameter default to the dictionary, so callers that pass a label are unaffected:

```tsx
export function Loading({ label }: { label?: string }) {
  const t = useT()
  return (
    <div className="space-y-2 py-4" role="status" aria-live="polite">
      <span className="sr-only">{label ?? t('common.loading')}…</span>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  )
}
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd web/ui && npm test -- --run && npm run build
```

Expected: PASS. `status.test.ts` needs no edit — it only asserts `key` and `share`, never `label`. `components.test.tsx:42` still finds `'Clear to merge'` because English is the default in jsdom.

- [ ] **Step 7: Commit**

```bash
git add web/ui/src/status.ts web/ui/src/components.tsx web/ui/src/strings.ts web/ui/src/components.test.tsx
git commit -m "feat(ui): translate the shared components and keep status.ts language-free"
```

---

### Task 3: The repo list and repo detail pages

**Files:**
- Modify: `web/ui/src/pages/Repos.tsx`
- Modify: `web/ui/src/pages/RepoDetail.tsx`
- Modify: `web/ui/src/strings.ts`

**Interfaces:**
- Consumes: `useT` from Task 1; `Loading` with an optional label from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Add the keys**

Append to `en`:

```ts
  'repos.error': 'Could not load repos — {detail}',
  'repos.loading': 'Loading repositories',
  'repos.title': 'Every claim, checked against the code.',
  'repos.subOne': '{n} repo reviewed',
  'repos.subMany': '{n} repos reviewed',
  'repos.subPrs': '{n} pull requests on the record',
  'repos.reviewedHeading': 'Reviewed repositories',
  'repos.emptyBefore': 'No reviews yet. Run ',
  'repos.emptyAfter': ', or add a repo on the Config page and let the poller pick it up.',
  'repos.prs': '{n} PR',
  'repos.docErrors': '{n} doc errors',
  'repos.breaking': '{n} breaking',
  'repos.testGaps': '{n} test gaps',
  'repos.verified': '{score} verified',
  'repos.waitingHeading': 'Watched, not yet reviewed',
  'repos.waitingMeta': 'Set to auto — the poller reviews its next open PR',
  'repo.loading': 'Loading repository',
  'repo.statusReviewed': 'Reviewed',
  'repo.statusReviewing': 'Reviewing now',
  'repo.statusNotReviewed': 'Not reviewed',
  'repo.tilePrs': 'PRs reviewed',
  'repo.tileVerified': 'Verified',
  'repo.tileVerifiedNote': 'claims backed by file:line',
  'repo.tileBugs': 'Bugs',
  'repo.tileBugsNote': 'failed claims + broken impact',
  'repo.tileDocErrors': 'Doc errors',
  'repo.tileBreaking': 'Breaking',
  'repo.tileBreakingNote': 'API + schema contracts',
  'repo.tileSpent': 'Spent',
  'repo.gateHeading': 'Merge decisions',
  'repo.openPrsHeading': 'Open pull requests',
  'repo.unreachable': 'GitHub is unreachable — showing pull requests from stored reviews only.',
  'repo.noOpenPrs': 'No open pull requests.',
  'repo.draft': 'draft',
  'repo.roundOne': '{n} round',
  'repo.roundMany': '{n} rounds',
  'repo.prBugs': '{n} bugs',
  'repo.prDocErrors': '{n} doc errors',
  'repo.prBreaking': '{n} breaking',
  'repo.reReview': 'Re-review',
  'repo.reviewNow': 'Review now',
```

`repos.subOne`/`subMany` and `repo.roundOne`/`roundMany` exist because English needs the plural distinction the components make today with a ternary. Vietnamese uses the same string for both — the `Record<keyof typeof en, string>` type allows duplicate values.

Append to `vi`:

```ts
  'repos.error': 'Không tải được danh sách kho mã — {detail}',
  'repos.loading': 'Đang tải danh sách kho mã',
  'repos.title': 'Mọi tuyên bố đều được đối chiếu với code.',
  'repos.subOne': '{n} kho mã đã review',
  'repos.subMany': '{n} kho mã đã review',
  'repos.subPrs': '{n} pull request trong hồ sơ',
  'repos.reviewedHeading': 'Kho mã đã review',
  'repos.emptyBefore': 'Chưa có review nào. Chạy ',
  'repos.emptyAfter': ', hoặc thêm một kho mã ở trang Cấu hình rồi để bộ quét tự nhận.',
  'repos.prs': '{n} PR',
  'repos.docErrors': '{n} lỗi tài liệu',
  'repos.breaking': '{n} phá vỡ tương thích',
  'repos.testGaps': '{n} lỗ hổng test',
  'repos.verified': '{score} đã xác minh',
  'repos.waitingHeading': 'Đang theo dõi, chưa review',
  'repos.waitingMeta': 'Đặt chế độ auto — bộ quét sẽ review PR mở tiếp theo',
  'repo.loading': 'Đang tải kho mã',
  'repo.statusReviewed': 'Đã review',
  'repo.statusReviewing': 'Đang review',
  'repo.statusNotReviewed': 'Chưa review',
  'repo.tilePrs': 'PR đã review',
  'repo.tileVerified': 'Đã xác minh',
  'repo.tileVerifiedNote': 'tuyên bố có dẫn file:line',
  'repo.tileBugs': 'Lỗi',
  'repo.tileBugsNote': 'tuyên bố sai + tác động hỏng',
  'repo.tileDocErrors': 'Lỗi tài liệu',
  'repo.tileBreaking': 'Phá vỡ tương thích',
  'repo.tileBreakingNote': 'hợp đồng API + schema',
  'repo.tileSpent': 'Đã chi',
  'repo.gateHeading': 'Quyết định merge',
  'repo.openPrsHeading': 'Pull request đang mở',
  'repo.unreachable': 'Không kết nối được GitHub — chỉ hiện pull request từ review đã lưu.',
  'repo.noOpenPrs': 'Không có pull request nào đang mở.',
  'repo.draft': 'nháp',
  'repo.roundOne': '{n} vòng',
  'repo.roundMany': '{n} vòng',
  'repo.prBugs': '{n} lỗi',
  'repo.prDocErrors': '{n} lỗi tài liệu',
  'repo.prBreaking': '{n} phá vỡ tương thích',
  'repo.reReview': 'Review lại',
  'repo.reviewNow': 'Review ngay',
```

- [ ] **Step 2: Translate `Repos.tsx`**

Add `import { useT } from '../i18n'` and `const t = useT()` as the first line of the component. Then replace the rendered strings. The `meta` and `right` blocks must keep producing the same English text — `App.test.tsx:80-82` asserts `'6 bugs'` and `'50% verified'`:

```tsx
  if (error) return <ErrorNotice message={t('repos.error', { detail: error })} />
  if (!repos) return <Loading label={t('repos.loading')} />
```

```tsx
      <PageTitle>{t('repos.title')}</PageTitle>
      <PageSub>
        {reviewed.length === 1
          ? t('repos.subOne', { n: reviewed.length })
          : t('repos.subMany', { n: reviewed.length })} ·{' '}
        {t('repos.subPrs', { n: reviewed.reduce((n, r) => n + r.prs_total, 0) })}
      </PageSub>

      <Eyebrow>{t('repos.reviewedHeading')}</Eyebrow>
      <Ledger>
        {reviewed.length === 0 ? (
          <Empty>
            {t('repos.emptyBefore')}<code>python -m src.run owner/repo 123</code>
            {t('repos.emptyAfter')}
          </Empty>
        ) : (
```

The row's `meta` and `right`:

```tsx
              meta={
                <>
                  {t('repos.prs', { n: r.prs_total })} · {t('repos.bugs', { n: r.bugs_total })} ·{' '}
                  {t('repos.docErrors', { n: r.doc_errors_total })}
                  {r.breaking_total ? ` · ${t('repos.breaking', { n: r.breaking_total })}` : ''}
                  {r.test_gaps_total ? ` · ${t('repos.testGaps', { n: r.test_gaps_total })}` : ''}
                </>
              }
              right={
                <>
                  {t('repos.verified', { score: formatScore(r.avg_verification_score) })}<br />
                  {formatCost(r.cost_total)}
                </>
              }
```

and the waiting section:

```tsx
          <Eyebrow>{t('repos.waitingHeading')}</Eyebrow>
```
```tsx
                meta={t('repos.waitingMeta')}
```

- [ ] **Step 3: Translate `RepoDetail.tsx`**

The module-level `STATUS_LABEL` map (`RepoDetail.tsx:12-16`) becomes a key map, because a module constant cannot call a hook:

```tsx
const STATUS_KEY: Record<string, Key> = {
  reviewed: 'repo.statusReviewed',
  reviewing: 'repo.statusReviewing',
  not_reviewed: 'repo.statusNotReviewed',
}
```

with `import { useT } from '../i18n'` and `import type { Key } from '../strings'`. Inside the component add `const t = useT()`, then:

```tsx
  if (!data) return <Loading label={t('repo.loading')} />
```
```tsx
        <Tile label={t('repo.tilePrs')} value={data.prs_total} />
        <Tile label={t('repo.tileVerified')} value={formatScore(data.avg_verification_score)}
              note={t('repo.tileVerifiedNote')} />
        <Tile label={t('repo.tileBugs')} value={data.bugs_total} note={t('repo.tileBugsNote')} />
        <Tile label={t('repo.tileDocErrors')} value={data.doc_errors_total} />
        <Tile label={t('repo.tileBreaking')} value={data.breaking_total}
              note={t('repo.tileBreakingNote')} />
        <Tile label={t('repo.tileSpent')} value={formatCost(data.cost_total)} />
      </Tiles>

      <Eyebrow>{t('repo.gateHeading')}</Eyebrow>
      <GateBand counts={data.gate_count} />

      <Eyebrow>{t('repo.openPrsHeading')}</Eyebrow>
      {unavailable && <Notice>{t('repo.unreachable')}</Notice>}
      <Ledger>
        {data.open_prs.length === 0 ? (
          <Empty>{t('repo.noOpenPrs')}</Empty>
        ) : (
```

the row's title, meta and button:

```tsx
                    {row.title || t('common.noTitle')} {row.draft ? `· ${t('repo.draft')}` : ''}
```
```tsx
                meta={
                  <>
                    {t(STATUS_KEY[row.status])}
                    {row.rounds
                      ? ` · ${row.rounds > 1
                          ? t('repo.roundMany', { n: row.rounds })
                          : t('repo.roundOne', { n: row.rounds })}`
                      : ''}
                    {rec ? ` · ${t('repo.prBugs', { n: rec.bugs })} · ${t('repo.prDocErrors', { n: rec.doc_errors })}` : ''}
                    {rec?.breaking ? ` · ${t('repo.prBreaking', { n: rec.breaking })}` : ''}
                  </>
                }
```
```tsx
                      {row.status === 'reviewed' ? t('repo.reReview') : t('repo.reviewNow')}
```

- [ ] **Step 4: Run the tests and the build**

```bash
cd web/ui && npm test -- --run && npm run build
```

Expected: PASS. If `tsc` complains that `t(STATUS_KEY[row.status])` may be `undefined`, that is a real pre-existing hole — `row.status` is a server string. Guard it: `{STATUS_KEY[row.status] ? t(STATUS_KEY[row.status]) : row.status}`.

- [ ] **Step 5: Commit**

```bash
git add web/ui/src/pages/Repos.tsx web/ui/src/pages/RepoDetail.tsx web/ui/src/strings.ts
git commit -m "feat(ui): translate the repo list and repo detail pages"
```

---

### Task 4: The PR detail page

**Files:**
- Modify: `web/ui/src/pages/PrDetail.tsx`
- Modify: `web/ui/src/strings.ts`

**Interfaces:**
- Consumes: `useT` from Task 1; the removal of `GATE_WORD` from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Add the keys**

Append to `en`:

```ts
  'pr.loading': 'Loading the PR',
  'pr.by': 'by {author}',
  'pr.openOnGitHub': 'open on GitHub',
  'pr.notReviewed': 'This pull request has not been reviewed yet.',
  'pr.reviewing': 'Reviewing…',
  'pr.reviewNow': 'Review now',
  'pr.reReview': 'Re-review',
  'pr.answerReplies': 'Answer replies',
  'pr.tileGate': 'Gate',
  'pr.tileVerified': 'Verified',
  'pr.tileVerifiedNote': 'claims with file:line',
  'pr.tileVerdict': 'Verdict',
  'pr.tileVerdictNote': 'PR description vs code',
  'pr.tileRisk': 'Business risk',
  'pr.tileRounds': 'Rounds',
  'pr.tileCost': 'Cost',
  'pr.pipelineHeading': 'Pipeline',
  'pr.pipelineLoading': 'Loading the pipeline',
  'pr.noPipeline': 'No pipeline data for this review yet.',
  'pr.whyGate': 'Why this gate:',
  'pr.lastRun': 'last run exit {code} · {at}',
  'pr.inProgressHeading': 'Review in progress',
  'pr.starting': 'starting…',
  'pr.blockingHeading': 'Blocking ({n})',
  'pr.tabClaims': 'Claims',
  'pr.tabDocs': 'Docs',
  'pr.tabImpact': 'Impact',
  'pr.tabCallers': 'Callers',
  'pr.tabContracts': 'Contracts',
  'pr.tabTests': 'Tests',
  'pr.tabThreads': 'Threads',
  'pr.tabConfirm': 'Confirm',
  'pr.tabContext': 'Context',
  'pr.blockContract': 'Contract',
  'pr.blockCaller': 'Caller',
  'pr.blockClaim': 'Claim',
  'pr.blockImpact': 'Impact',
  'pr.blockDoc': 'Doc',
  'pr.blockTest': 'Test',
  'pr.emptyClaims': 'The description made no verifiable claims.',
  'pr.emptyDocs': 'No documentation related to this change was found.',
  'pr.emptyImpact': 'No requirement was traced to this change.',
  'pr.emptyCallers': 'Nothing outside this diff calls the changed code.',
  'pr.emptyContracts': 'No API, schema, type or proto contract was touched.',
  'pr.emptyTests': 'No test coverage was assessed for this change.',
  'pr.emptyThreads': 'No review comments to re-check.',
  'pr.emptyConfirm': 'The reviewer had no questions for a human.',
  'pr.emptyContext': 'The whole diff went into the review — nothing was trimmed.',
  'pr.uncovered': 'uncovered: {case} → {where}',
  'pr.answered': 'answered: {answer}',
  'pr.dropped': 'dropped',
  'pr.trimmed': 'patch trimmed',
  'pr.repliesHeading': 'Replies answered',
```

Append to `vi`:

```ts
  'pr.loading': 'Đang tải PR',
  'pr.by': 'bởi {author}',
  'pr.openOnGitHub': 'mở trên GitHub',
  'pr.notReviewed': 'Pull request này chưa được review.',
  'pr.reviewing': 'Đang review…',
  'pr.reviewNow': 'Review ngay',
  'pr.reReview': 'Review lại',
  'pr.answerReplies': 'Trả lời phản hồi',
  'pr.tileGate': 'Cổng merge',
  'pr.tileVerified': 'Đã xác minh',
  'pr.tileVerifiedNote': 'tuyên bố có file:line',
  'pr.tileVerdict': 'Kết luận',
  'pr.tileVerdictNote': 'mô tả PR đối chiếu code',
  'pr.tileRisk': 'Rủi ro nghiệp vụ',
  'pr.tileRounds': 'Số vòng',
  'pr.tileCost': 'Chi phí',
  'pr.pipelineHeading': 'Quy trình',
  'pr.pipelineLoading': 'Đang tải quy trình',
  'pr.noPipeline': 'Chưa có dữ liệu quy trình cho review này.',
  'pr.whyGate': 'Vì sao có kết quả này:',
  'pr.lastRun': 'lần chạy trước thoát {code} · {at}',
  'pr.inProgressHeading': 'Đang review',
  'pr.starting': 'đang khởi động…',
  'pr.blockingHeading': 'Chặn merge ({n})',
  'pr.tabClaims': 'Tuyên bố',
  'pr.tabDocs': 'Tài liệu',
  'pr.tabImpact': 'Tác động',
  'pr.tabCallers': 'Nơi gọi',
  'pr.tabContracts': 'Hợp đồng',
  'pr.tabTests': 'Test',
  'pr.tabThreads': 'Thảo luận',
  'pr.tabConfirm': 'Xác nhận',
  'pr.tabContext': 'Ngữ cảnh',
  'pr.blockContract': 'Hợp đồng',
  'pr.blockCaller': 'Nơi gọi',
  'pr.blockClaim': 'Tuyên bố',
  'pr.blockImpact': 'Tác động',
  'pr.blockDoc': 'Tài liệu',
  'pr.blockTest': 'Test',
  'pr.emptyClaims': 'Mô tả không đưa ra tuyên bố nào kiểm chứng được.',
  'pr.emptyDocs': 'Không tìm thấy tài liệu nào liên quan tới thay đổi này.',
  'pr.emptyImpact': 'Không truy được yêu cầu nào tới thay đổi này.',
  'pr.emptyCallers': 'Không có chỗ nào ngoài diff này gọi tới code đã đổi.',
  'pr.emptyContracts': 'Không đụng tới hợp đồng API, schema, kiểu hay proto nào.',
  'pr.emptyTests': 'Chưa đánh giá độ phủ test cho thay đổi này.',
  'pr.emptyThreads': 'Không có comment review nào cần kiểm tra lại.',
  'pr.emptyConfirm': 'Reviewer không có câu hỏi nào cho người.',
  'pr.emptyContext': 'Toàn bộ diff đã vào review — không cắt bỏ gì.',
  'pr.uncovered': 'chưa phủ: {case} → {where}',
  'pr.answered': 'đã trả lời: {answer}',
  'pr.dropped': 'đã bỏ',
  'pr.trimmed': 'đã cắt bớt patch',
  'pr.repliesHeading': 'Phản hồi đã trả lời',
```

- [ ] **Step 2: Convert the two module-level tables to key tables**

`TABS` (`PrDetail.tsx:19-29`) and `BLOCKING` (`:38-67`) are module constants, so they hold keys, not words:

```tsx
const TABS: { key: TabKey; label: Key }[] = [
  { key: 'claims', label: 'pr.tabClaims' },
  { key: 'docs', label: 'pr.tabDocs' },
  { key: 'impact', label: 'pr.tabImpact' },
  { key: 'callers', label: 'pr.tabCallers' },
  { key: 'contracts', label: 'pr.tabContracts' },
  { key: 'tests', label: 'pr.tabTests' },
  { key: 'threads', label: 'pr.tabThreads' },
  { key: 'confirm', label: 'pr.tabConfirm' },
  { key: 'context', label: 'pr.tabContext' },
]
```

In `BLOCKING`, change the type annotation's `label: string` to `label: Key` and each entry's label to its key — `'Contract'` → `'pr.blockContract'`, `'Caller'` → `'pr.blockCaller'`, `'Claim'` → `'pr.blockClaim'`, `'Impact'` → `'pr.blockImpact'`, `'Doc'` → `'pr.blockDoc'`, `'Test'` → `'pr.blockTest'`. Leave the explanatory comment at `:31-37` intact — it explains the fixed category order, which this change does not touch.

Add the imports:

```tsx
import { useT } from '../i18n'
import type { Key } from '../strings'
```

and drop `GATE_WORD` from the `../status` import (it no longer exists after Task 2), leaving `import { formatCost, formatScore } from '../status'`.

- [ ] **Step 3: Translate the body**

Add `const t = useT()` at the top of `PrDetail()`, then:

```tsx
  if (!data) return <Loading label={t('pr.loading')} />
```

Header:

```tsx
        {data.title || rec?.title || t('common.noTitle')}
      </PageTitle>
      <PageSub>
        {owner}/{repo} · {rec?.author ? `${t('pr.by', { author: rec.author })} · ` : ''}
        {rec?.base} ← {rec?.head} ·{' '}
        <a className="text-brand hover:underline" href={`https://github.com/${owner}/${repo}/pull/${pr}`}>
          {t('pr.openOnGitHub')}
        </a>
      </PageSub>
```

Unreviewed branch:

```tsx
          <Notice>{t('pr.notReviewed')}</Notice>
          <Button onClick={() => startReview(false)} disabled={status?.running}>
            {status?.running ? t('pr.reviewing') : t('pr.reviewNow')}
          </Button>
```

Tiles — note the gate note now comes from the dictionary instead of `GATE_WORD`:

```tsx
            <Tile label={t('pr.tileGate')} value={<StatusWord status={gate} />}
                  note={t(`gate.${gate}` as Key)} />
            <Tile label={t('pr.tileVerified')} value={formatScore(score.verification_score ?? rec?.verification_score)}
                  note={t('pr.tileVerifiedNote')} />
            <Tile label={t('pr.tileVerdict')} value={<StatusWord status={rec?.verdict ?? ''} />}
                  note={t('pr.tileVerdictNote')} />
            <Tile label={t('pr.tileRisk')} value={score.business_risk ?? '—'} />
            <Tile label={t('pr.tileRounds')} value={rec?.rounds ?? 1} />
            <Tile label={t('pr.tileCost')} value={formatCost(rec?.cost_usd)} />
```

`gate` is `score.gate ?? 'unknown'` — one of `pass`/`warn`/`fail`/`unknown`, so all four `gate.*` keys exist. If a malformed `score.json` produces something else, `translate` returns `undefined` and the note renders empty; that is the same blank the old `GATE_WORD[gate]` produced, so behaviour is unchanged.

Pipeline, gate reasons, action row, log:

```tsx
          <Eyebrow>{t('pr.pipelineHeading')}</Eyebrow>
          {pipeline?.nodes?.length ? (
            <Suspense fallback={<Loading label={t('pr.pipelineLoading')} />}>
```
```tsx
          ) : (
            <Notice>{t('pr.noPipeline')}</Notice>
          )}
```
```tsx
              {t('pr.whyGate')}
```
```tsx
            <Button onClick={() => startReview(false)} disabled={status?.running}>
              {status?.running ? t('pr.reviewing') : t('pr.reReview')}
            </Button>
            <Button variant="outline" onClick={() => startReview(true)} disabled={status?.running}>
              {t('pr.answerReplies')}
            </Button>
            {status?.last?.exit !== undefined && !status.running && (
              <span className="font-mono text-xs text-ink-muted">
                {t('pr.lastRun', { code: status.last.exit, at: status.last.finished_at })}
              </span>
            )}
```
```tsx
              <Eyebrow>{t('pr.inProgressHeading')}</Eyebrow>
```
```tsx
                {log || t('pr.starting')}
```

Blocking strip:

```tsx
              <Eyebrow>{t('pr.blockingHeading', { n: blocking.length })}</Eyebrow>
```
```tsx
                    right={t(item.label)}
```

**Three shadowing renames.** The translator is `t`, and three existing `.map()` callbacks already bind `t` as their parameter. Each must be renamed, and the new name must not collide with the state variable `tab` either.

Tabs (`:250-260`) — the callback parameter becomes `item`, and `aria-selected` keeps comparing the *state* `tab` to the item's key:

```tsx
            {TABS.map((item) => (
              <button
                key={item.key}
                role="tab"
                className="tab border-b-2 border-transparent px-2.5 py-2 font-mono text-xs uppercase tracking-[0.06em] text-ink-muted aria-selected:border-brand aria-selected:text-ink"
                aria-selected={tab === item.key}
                onClick={() => setTab(item.key)}
              >
                {t(item.label)} <span className="tabular-nums">{counts[item.key]}</span>
              </button>
            ))}
```

Tests tab (`:307-318`) — `data.tests.map((t) => …)` becomes `test`, the inner `e` is untouched:

```tsx
            {tab === 'tests' && (data.tests?.length
              ? data.tests.map((test, i) => (
                  <Row key={i} status={test.assertion_quality}
                       title={<>{test.target} <StatusWord status={test.assertion_quality} /></>}
                       meta={
                         test.uncovered_edge_cases?.length
                           ? test.uncovered_edge_cases.map((e, j) => (
                               <div key={j}>{t('pr.uncovered', { case: e.case, where: e.where })}</div>))
                           : test.note
                       } />
                ))
              : <Empty>{t('pr.emptyTests')}</Empty>)}
```

Threads tab (`:320-326`) — `data.threads.map((t) => …)` becomes `thread`:

```tsx
            {tab === 'threads' && (data.threads?.length
              ? data.threads.map((thread, i) => (
                  <Row key={i} status={thread.status}
                       title={<>{thread.text} <StatusWord status={thread.status} /></>}
                       meta={thread.note} />
                ))
              : <Empty>{t('pr.emptyThreads')}</Empty>)}
```

Replace the remaining empty states with `t('pr.emptyClaims')`, `t('pr.emptyDocs')`, `t('pr.emptyImpact')`, `t('pr.emptyCallers')`, `t('pr.emptyContracts')`, `t('pr.emptyConfirm')`, `t('pr.emptyContext')`. In the confirm tab replace `` meta={`answered: ${a.answer}`} `` with `` meta={t('pr.answered', { answer: a.answer })} ``. In the context tab replace `right={p.dropped ? 'dropped' : 'patch trimmed'}` with `right={p.dropped ? t('pr.dropped') : t('pr.trimmed')}`. Replace the replies heading with `{t('pr.repliesHeading')}`.

- [ ] **Step 4: Run the tests and the build**

```bash
cd web/ui && npm test -- --run && npm run build
```

Expected: PASS. `App.test.tsx:103` finds the contracts tab by `textContent?.startsWith('Contracts')` — that still holds because the English value is unchanged.

- [ ] **Step 5: Commit**

```bash
git add web/ui/src/pages/PrDetail.tsx web/ui/src/strings.ts
git commit -m "feat(ui): translate the PR detail page"
```

---

### Task 5: Pipeline graph labels and the completeness test

**Files:**
- Modify: `web/ui/src/graph/layout.ts:29-35`
- Modify: `web/ui/src/graph/PhaseNode.tsx`
- Modify: `web/ui/src/graph/PipelineGraph.tsx:102-122`
- Modify: `web/ui/src/strings.ts`
- Create: `tests/test_ui_strings.py`

**Interfaces:**
- Consumes: `useT`, `useLookup` from Task 1.
- Produces: `STATUS_KEY: Record<PhaseStatus, Key>` exported from `layout.ts`, replacing `STATUS_WORD`.

- [ ] **Step 1: Write the failing cross-language test**

Create `tests/test_ui_strings.py`. This is the guard for the one lookup that the TypeScript compiler cannot check, because its keys arrive from the server at runtime:

```python
"""The dashboard translates phase and metric labels by the ids web/metrics.py
emits. Those ids reach the UI at runtime, so the compiler cannot check them the
way it checks the rest of the dictionary — this test does it instead. A phase
added to metrics.py without a Vietnamese label fails here rather than silently
rendering English on a Vietnamese dashboard.
"""
import re
from pathlib import Path

from web.metrics import PHASES

STRINGS = Path(__file__).resolve().parents[1] / "web" / "ui" / "src" / "strings.ts"

# Every metric label _phase_metrics() can emit, kept here as the assertion's
# expectation: adding one to metrics.py means adding it here and translating it.
METRIC_LABELS = {"files", "commits", "pruned", "claims", "docs", "callers",
                 "contracts", "gate", "verified", "answered", "open", "patches",
                 "tests", "replies"}


def _keys() -> set[str]:
    text = STRINGS.read_text(encoding="utf-8")
    return set(re.findall(r"'([\w.]+)':", text))


def test_every_pipeline_phase_has_a_translated_label():
    keys = _keys()
    missing = [p["id"] for p in PHASES if f"graph.phase.{p['id']}" not in keys]
    assert not missing, f"untranslated pipeline phases: {missing}"


def test_every_phase_metric_has_a_translated_label():
    keys = _keys()
    missing = sorted(m for m in METRIC_LABELS if f"graph.metric.{m}" not in keys)
    assert not missing, f"untranslated phase metrics: {missing}"


def test_the_metric_label_list_still_matches_metrics_py():
    """If _phase_metrics() grows a label, this fails before the two above do,
    pointing at the real edit rather than at a stale expectation."""
    source = (Path(__file__).resolve().parents[1] / "web" / "metrics.py").read_text()
    body = source.split("def _phase_metrics(")[1].split("\ndef ")[0]
    found = set(re.findall(r'"label": "(\w+)"', body))
    assert found == METRIC_LABELS
```

The spec named `ORDER` as the source of phase ids; `PHASES` is used instead because it is the superset — `followup` is a rendered node that `ORDER` omits, and leaving it untranslated is exactly the bug this test exists to catch.

- [ ] **Step 2: Run it to verify it fails**

```bash
pytest tests/test_ui_strings.py -q
```

Expected: FAIL — `untranslated pipeline phases: ['snapshot', 'describe', …]`.

- [ ] **Step 3: Add the keys**

Append to `en`:

```ts
  'graph.statusDone': 'done',
  'graph.statusRunning': 'running',
  'graph.statusFailed': 'failed',
  'graph.statusPending': 'pending',
  'graph.statusSkipped': 'skipped',
  'graph.phase.snapshot': 'Snapshot',
  'graph.phase.describe': 'Describe',
  'graph.phase.claims': 'Claims',
  'graph.phase.followup': 'Replies',
  'graph.phase.verify': 'Verify',
  'graph.phase.remediate': 'Doc fixes',
  'graph.phase.poc': 'PoC tests',
  'graph.phase.score': 'Score',
  'graph.phase.ask': 'Confirm',
  'graph.phase.report': 'Report',
  'graph.metric.files': 'files',
  'graph.metric.commits': 'commits',
  'graph.metric.pruned': 'pruned',
  'graph.metric.claims': 'claims',
  'graph.metric.docs': 'docs',
  'graph.metric.callers': 'callers',
  'graph.metric.contracts': 'contracts',
  'graph.metric.gate': 'gate',
  'graph.metric.verified': 'verified',
  'graph.metric.answered': 'answered',
  'graph.metric.open': 'open',
  'graph.metric.patches': 'patches',
  'graph.metric.tests': 'tests',
  'graph.metric.replies': 'replies',
```

Append to `vi`:

```ts
  'graph.statusDone': 'xong',
  'graph.statusRunning': 'đang chạy',
  'graph.statusFailed': 'lỗi',
  'graph.statusPending': 'chờ',
  'graph.statusSkipped': 'bỏ qua',
  'graph.phase.snapshot': 'Ảnh chụp',
  'graph.phase.describe': 'Mô tả',
  'graph.phase.claims': 'Tuyên bố',
  'graph.phase.followup': 'Phản hồi',
  'graph.phase.verify': 'Xác minh',
  'graph.phase.remediate': 'Sửa tài liệu',
  'graph.phase.poc': 'Test PoC',
  'graph.phase.score': 'Chấm điểm',
  'graph.phase.ask': 'Xác nhận',
  'graph.phase.report': 'Báo cáo',
  'graph.metric.files': 'tệp',
  'graph.metric.commits': 'commit',
  'graph.metric.pruned': 'đã cắt',
  'graph.metric.claims': 'tuyên bố',
  'graph.metric.docs': 'tài liệu',
  'graph.metric.callers': 'nơi gọi',
  'graph.metric.contracts': 'hợp đồng',
  'graph.metric.gate': 'cổng',
  'graph.metric.verified': 'đã xác minh',
  'graph.metric.answered': 'đã trả lời',
  'graph.metric.open': 'còn mở',
  'graph.metric.patches': 'bản vá',
  'graph.metric.tests': 'test',
  'graph.metric.replies': 'phản hồi',
```

- [ ] **Step 4: Run the Python test to verify it passes**

```bash
pytest tests/test_ui_strings.py -q
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Swap `STATUS_WORD` for `STATUS_KEY`**

In `web/ui/src/graph/layout.ts`, replace the `STATUS_WORD` constant (lines 29-35):

```ts
import type { Key } from '../strings'

export const STATUS_KEY: Record<PhaseStatus, Key> = {
  done: 'graph.statusDone',
  running: 'graph.statusRunning',
  failed: 'graph.statusFailed',
  pending: 'graph.statusPending',
  skipped: 'graph.statusSkipped',
}
```

- [ ] **Step 6: Translate both graph renderers**

In `web/ui/src/graph/PhaseNode.tsx`, swap the import of `STATUS_WORD` for `STATUS_KEY`, add `import { useT, useLookup } from '../i18n'`, and inside the component:

```tsx
  const t = useT()
  const lookup = useLookup()
```

then the label, status word and metric labels:

```tsx
        <span className="text-sm font-semibold">
          {lookup(`graph.phase.${node.id}`, node.label)}
        </span>
```
```tsx
        {t(STATUS_KEY[node.status])}
```
```tsx
            <div key={m.label} className="flex justify-between gap-2">
              <dt>{lookup(`graph.metric.${m.label}`, m.label)}</dt>
              <dd className="tabular-nums text-ink">{m.value}</dd>
            </div>
```

`node.id` must exist on `PhaseNodeData` — it does, via `GraphNode` (`api.ts:131` region). Confirm with `tsc`.

In `web/ui/src/graph/PipelineGraph.tsx`, make the same two substitutions in the screen-reader list (`:102-122`). This list and the canvas node must translate identically: a sighted reader and a screen-reader reader seeing different words for the same phase is worse than leaving both in English.

```tsx
              {lookup(`graph.phase.${node.id}`, node.label)}{' '}
              <span style={{ color: TONE_COLOR[STATUS_TONE[node.status]] }}>
                {GLYPH[STATUS_TONE[node.status]]} {t(STATUS_KEY[node.status])}
              </span>
```

Add `const t = useT()` and `const lookup = useLookup()` to that component too, and update its `../graph/layout` import.

- [ ] **Step 7: Run the full UI suite and the build**

```bash
cd web/ui && npm test -- --run && npm run build
```

Expected: PASS. `PipelineGraph.test.tsx:62-77` asserts `'Snapshot'`, `'Claims'`, `'Verify'`, `'done'`, `'running'` — all unchanged English values.

- [ ] **Step 8: Commit**

```bash
git add web/ui/src/graph web/ui/src/strings.ts tests/test_ui_strings.py
git commit -m "feat(ui): translate pipeline phase and metric labels, guarded by a completeness test"
```

---

### Task 6: Writing the review-output language to prsentinel.yml

**Files:**
- Modify: `src/autoreview_config.py` (add `set_language` after `set_provider`, ends line 184)
- Modify: `web/server.py:20-22` (imports), `:143-158` (config payload), after `:173` (new endpoint)
- Test: `tests/test_autoreview_config.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `set_language(path: Path, language: str) -> dict`; `GET /api/config` gains `"language": "en" | "vi"`; `POST /api/config/language` with body `{"language": "vi"}` returns `{"ok": True, "language": "vi"}`. Task 7 calls both.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_autoreview_config.py`, and add `set_language` to its import at line 4-5:

```python
def test_set_language_writes_only_the_selection(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "language: en\nrepos:\n  app: auto\n")
    cfg = set_language(path, "vi")
    assert cfg["language"] == "vi"
    assert load_config(path)["language"] == "vi"
    assert load_config(path)["repos"] == {"app": "auto"}


def test_set_language_preserves_comments_and_formatting(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", (
        "# PR Sentinel configuration.\n"
        "# The language the model writes its output in. en | vi\n"
        "language: en\n"
        "interval_minutes: 2   # fast loop\n"
        "repos:\n"
        "  app: auto\n"))
    set_language(path, "vi")
    out = path.read_text()
    assert "# PR Sentinel configuration." in out
    assert "# The language the model writes its output in. en | vi" in out
    assert "# fast loop" in out
    assert "language: vi" in out
    assert "language: en" not in out


def test_set_language_adds_the_key_when_missing(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "repos:\n  app: auto\n")
    assert set_language(path, "vi")["language"] == "vi"
    assert load_config(path)["language"] == "vi"


def test_set_language_rejects_an_unsupported_language(tmp_path):
    path = _write(tmp_path / "prsentinel.yml", "language: en\nrepos:\n  app: auto\n")
    with pytest.raises(ValueError, match="language"):
        set_language(path, "fr")
    assert path.read_text().count("language: en") == 1
```

Append to `tests/test_server.py`, in the config section after `test_api_config_missing_file_404`:

```python
def test_api_config_reports_the_review_language(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch,
            "org: sample-org\nlanguage: vi\nrepos:\n  sample-app: auto\n")
    monkeypatch.setattr("gh.run_gh", lambda args, **kw: [])
    assert TestClient(app).get("/api/config").json()["language"] == "vi"


def test_api_set_language(tmp_path, monkeypatch):
    cfg_path = _config(tmp_path, monkeypatch)
    assert TestClient(app).post("/api/config/language",
                                json={"language": "vi"}).status_code == 200
    assert load_config(cfg_path)["language"] == "vi"


def test_api_set_language_rejects_an_unsupported_language(tmp_path, monkeypatch):
    cfg_path = _config(tmp_path, monkeypatch)
    r = TestClient(app).post("/api/config/language", json={"language": "fr"})
    assert r.status_code == 400
    assert load_config(cfg_path)["language"] == "en"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
pytest tests/test_autoreview_config.py tests/test_server.py -q
```

Expected: FAIL — `ImportError: cannot import name 'set_language'`.

- [ ] **Step 3: Implement `set_language`**

In `src/autoreview_config.py`, directly after `set_provider` (which ends at line 184):

```python
def set_language(path: Path, language: str) -> dict:
    """Switch the language the model writes its output in.

    Edits the one top-level `language:` line in the raw text, the way
    set_provider does, so the operator's comments and ordering survive. A yaml
    round-trip through _write_atomic would rewrite the whole document and delete
    every comment in the file — including the block that documents this key.
    """
    if language not in ("en", "vi"):
        raise ValueError("language must be 'en' or 'vi'")
    text = path.read_text() if path.exists() else ""
    if re.search(r"(?m)^language:", text):
        text = re.sub(r"(?m)^language:[ \t]*.*$",
                      lambda _m: f"language: {language}", text, count=1)
    elif text.strip():
        text = text.rstrip("\n") + f"\nlanguage: {language}\n"
    else:
        text = f"language: {language}\n"
    _write_text_atomic(path, text)
    return load_config(path)
```

The value is checked before the write so a bad request cannot leave a file that `load_config` then refuses to read. `re` is already imported at the top of the module.

- [ ] **Step 4: Expose it over HTTP**

In `web/server.py`, extend the import at lines 21-22:

```python
from autoreview_config import (auto_repos, list_repos, remove_repo,
                               set_language, set_provider, set_repo_mode)
```

(keep the existing member list; add `set_language` in alphabetical position).

Add `"language": cfg.get("language"),` to the `api_config()` return dict, next to `"default_mode"`.

Add the endpoint after `api_set_provider` (which ends at line 173):

```python
@app.post("/api/config/language")
def api_set_language(payload: dict):
    """Set the language the review writes its prose in. Fixed labels stay English."""
    path = _require_config()
    language = (payload.get("language") or "").strip()
    try:
        set_language(path, language)
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "language": language}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/test_autoreview_config.py tests/test_server.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/autoreview_config.py web/server.py tests/test_autoreview_config.py tests/test_server.py
git commit -m "feat(web): read and write the review-output language over the config API"
```

---

### Task 7: The Config page language block, and the README

**Files:**
- Modify: `web/ui/src/api.ts:169-207`
- Modify: `web/ui/src/pages/Config.tsx`
- Modify: `web/ui/src/strings.ts`
- Modify: `README.md:267`

**Interfaces:**
- Consumes: `GET /api/config`'s `language` field and `POST /api/config/language` from Task 6; `useLang`, `useT` from Task 1.
- Produces: `api.setLanguage(language: string)`.

- [ ] **Step 1: Add the keys**

Append to `en`:

```ts
  'config.errorAfter': ' — create ',
  'config.errorMid': ' next to the repo, or point ',
  'config.errorEnd': ' at it.',
  'config.loading': 'Loading configuration',
  'config.title': 'What the poller watches',
  'config.tileOrg': 'Org',
  'config.tilePollEvery': 'Poll every',
  'config.tileGateAt': 'Gate at',
  'config.tileGateNote': 'minimum verification score',
  'config.tilePostsComments': 'Posts comments',
  'config.tileDocPrs': 'Writes doc PRs',
  'config.tileRewritesBody': 'Rewrites PR body',
  'config.providerHeading': 'Model provider',
  'config.noKeyBefore': 'No key for ',
  'config.noKeyMid': ' — set ',
  'config.noKeyAfter': ' in ',
  'config.noKeyEnd': '. Reviews will refuse to start until it is there.',
  'config.tileProvider': 'Provider',
  'config.tileDeepDive': 'Deep dive',
  'config.tileClaims': 'Claims',
  'config.tileSchema': 'Schema',
  'config.schemaEnforced': 'enforced',
  'config.schemaPrompted': 'prompted',
  'config.schemaEnforcedNote': 'the API validates the JSON',
  'config.schemaPromptedNote': 'the reply is parsed and repaired',
  'config.tileKey': 'Key',
  'config.keySet': 'set',
  'config.keyMissing': 'missing',
  'config.tileCosts': 'Costs',
  'config.costsTracked': 'tracked',
  'config.costsUnknown': 'unknown',
  'config.costsUnknownNote': 'budget caps do not apply',
  'config.tokensNote': 'tokens are read from the environment only',
  'config.languageHeading': 'Language',
  'config.uiLanguage': 'Interface',
  'config.uiLanguageNote': 'this browser only — it does not change what the agent writes',
  'config.reviewLanguage': 'Review output',
  'config.reviewLanguageNote': 'written to the config file; applies to every review, including CI',
  'config.languageFootnote': 'Status codes (PASS, STALE, BROKEN…) stay English so the dashboard matches the comment posted on GitHub.',
  'config.uiLanguageAria': 'Interface language',
  'config.reviewLanguageAria': 'Review output language',
  'config.reposHeading': 'Repositories',
  'config.repoPlaceholderOrg': 'repo-name or owner/repo',
  'config.repoPlaceholder': 'owner/repo',
  'config.watchRepo': 'Watch repo',
  'config.noRepos': 'No repositories configured yet.',
  'config.modeAuto': 'Reviewed automatically',
  'config.modeManual': 'Reviewed only when you ask',
  'config.modeUnlisted': 'Not configured',
  'config.modeAria': 'Mode for {repo}',
  'config.remove': 'Remove',
  'lang.en': 'English',
  'lang.vi': 'Tiếng Việt',
```

`lang.vi` is `'Tiếng Việt'` in **both** tables, and `lang.en` is `'English'` in both — a language's name in a picker is written in that language, so a reader can find their own.

Append to `vi`:

```ts
  'config.errorAfter': ' — tạo ',
  'config.errorMid': ' cạnh kho mã, hoặc trỏ ',
  'config.errorEnd': ' tới nó.',
  'config.loading': 'Đang tải cấu hình',
  'config.title': 'Bộ quét đang theo dõi những gì',
  'config.tileOrg': 'Tổ chức',
  'config.tilePollEvery': 'Chu kỳ quét',
  'config.tileGateAt': 'Ngưỡng cổng',
  'config.tileGateNote': 'điểm xác minh tối thiểu',
  'config.tilePostsComments': 'Đăng comment',
  'config.tileDocPrs': 'Mở PR sửa tài liệu',
  'config.tileRewritesBody': 'Viết lại mô tả PR',
  'config.providerHeading': 'Nhà cung cấp model',
  'config.noKeyBefore': 'Chưa có khoá cho ',
  'config.noKeyMid': ' — đặt ',
  'config.noKeyAfter': ' trong ',
  'config.noKeyEnd': '. Review sẽ không chạy cho tới khi có khoá.',
  'config.tileProvider': 'Nhà cung cấp',
  'config.tileDeepDive': 'Phân tích sâu',
  'config.tileClaims': 'Tuyên bố',
  'config.tileSchema': 'Schema',
  'config.schemaEnforced': 'bắt buộc',
  'config.schemaPrompted': 'nhắc qua prompt',
  'config.schemaEnforcedNote': 'API tự kiểm tra JSON',
  'config.schemaPromptedNote': 'phản hồi được phân tích và sửa lại',
  'config.tileKey': 'Khoá',
  'config.keySet': 'đã có',
  'config.keyMissing': 'thiếu',
  'config.tileCosts': 'Chi phí',
  'config.costsTracked': 'có theo dõi',
  'config.costsUnknown': 'không rõ',
  'config.costsUnknownNote': 'không áp được hạn mức ngân sách',
  'config.tokensNote': 'token chỉ đọc từ biến môi trường',
  'config.languageHeading': 'Ngôn ngữ',
  'config.uiLanguage': 'Giao diện',
  'config.uiLanguageNote': 'chỉ trình duyệt này — không đổi thứ agent viết ra',
  'config.reviewLanguage': 'Output review',
  'config.reviewLanguageNote': 'ghi vào file cấu hình; áp dụng cho mọi review, kể cả CI',
  'config.languageFootnote': 'Mã trạng thái (PASS, STALE, BROKEN…) luôn giữ tiếng Anh để dashboard khớp với comment đăng trên GitHub.',
  'config.uiLanguageAria': 'Ngôn ngữ giao diện',
  'config.reviewLanguageAria': 'Ngôn ngữ output review',
  'config.reposHeading': 'Kho mã',
  'config.repoPlaceholderOrg': 'tên-kho hoặc owner/repo',
  'config.repoPlaceholder': 'owner/repo',
  'config.watchRepo': 'Theo dõi kho',
  'config.noRepos': 'Chưa cấu hình kho mã nào.',
  'config.modeAuto': 'Tự động review',
  'config.modeManual': 'Chỉ review khi bạn yêu cầu',
  'config.modeUnlisted': 'Chưa cấu hình',
  'config.modeAria': 'Chế độ cho {repo}',
  'config.remove': 'Bỏ theo dõi',
  'lang.en': 'English',
  'lang.vi': 'Tiếng Việt',
```

- [ ] **Step 2: Add the API call**

In `web/ui/src/api.ts`, after `setProvider`:

```ts
  setLanguage: (language: string) =>
    request<any>('/api/config/language', {
      method: 'POST',
      body: JSON.stringify({ language }),
    }),
```

- [ ] **Step 3: Translate the Config page and add the language block**

In `web/ui/src/pages/Config.tsx`, add `language: string` to `ConfigState` (after `interval_minutes`), add the imports:

```tsx
import { useLang, useT } from '../i18n'
```

and inside the component, after the existing state:

```tsx
  const [uiLang, setUiLang] = useLang()
  const t = useT()
```

Replace the rendered strings — the error notice's embedded `<code>` elements are spanned by the three-part keys:

```tsx
  if (error && !cfg) {
    return (
      <ErrorNotice
        message={<>{error}{t('config.errorAfter')}<code>prsentinel.yml</code>
          {t('config.errorMid')}<code>PRSENTINEL_CONFIG</code>{t('config.errorEnd')}</>}
      />
    )
  }
  if (!cfg) return <Loading label={t('config.loading')} />
```

```tsx
      <PageTitle>{t('config.title')}</PageTitle>
```
```tsx
        <Tile label={t('config.tileOrg')} value={cfg.org || '—'} />
        <Tile label={t('config.tilePollEvery')} value={`${cfg.interval_minutes}m`} />
        <Tile label={t('config.tileGateAt')} value={`${Math.round(cfg.gate.verification_score_min * 100)}%`}
              note={t('config.tileGateNote')} />
        <Tile label={t('config.tilePostsComments')} value={cfg.post_comment ? t('common.yes') : t('common.no')} />
        <Tile label={t('config.tileDocPrs')} value={cfg.docs_fix_pr ? t('common.yes') : t('common.no')} />
        <Tile label={t('config.tileRewritesBody')} value={cfg.auto_describe ? t('common.yes') : t('common.no')} />
```

```tsx
      <Eyebrow>{t('config.providerHeading')}</Eyebrow>
      {!cfg.provider.token_present && (
        <Notice tone="fail">
          {t('config.noKeyBefore')}<code>{cfg.provider.name}</code>
          {t('config.noKeyMid')}<code>{cfg.provider.token_env}</code>
          {t('config.noKeyAfter')}<code>.env</code>{t('config.noKeyEnd')}
        </Notice>
      )}
```

Then the provider tiles (`config.tileProvider`, `config.tileDeepDive`, `config.tileClaims`, `config.tileSchema` with `config.schemaEnforced`/`config.schemaPrompted` and their notes, `config.tileKey` with `config.keySet`/`config.keyMissing`, `config.tileCosts` with `config.costsTracked`/`config.costsUnknown` and `config.costsUnknownNote`), the provider select's `aria-label={t('config.providerHeading')}`, and `{t('config.tokensNote')}`.

Insert the new language block immediately after the provider block and before `<Eyebrow>{t('config.reposHeading')}</Eyebrow>`:

```tsx
      <Eyebrow>{t('config.languageHeading')}</Eyebrow>
      <div className="my-2.5 flex flex-wrap items-start gap-6">
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-muted">
            {t('config.uiLanguage')}
          </span>
          <Select value={uiLang} onValueChange={(next) => setUiLang(next as 'en' | 'vi')}>
            <SelectTrigger className="w-[150px] font-mono text-xs"
                           aria-label={t('config.uiLanguageAria')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en" className="font-mono text-xs">{t('lang.en')}</SelectItem>
              <SelectItem value="vi" className="font-mono text-xs">{t('lang.vi')}</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-ink-muted">{t('config.uiLanguageNote')}</span>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-muted">
            {t('config.reviewLanguage')}
          </span>
          <Select value={cfg.language}
                  onValueChange={(next) => act(() => api.setLanguage(next))}>
            <SelectTrigger className="w-[150px] font-mono text-xs"
                           aria-label={t('config.reviewLanguageAria')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en" className="font-mono text-xs">{t('lang.en')}</SelectItem>
              <SelectItem value="vi" className="font-mono text-xs">{t('lang.vi')}</SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-ink-muted">{t('config.reviewLanguageNote')}</span>
        </div>
      </div>
      <Notice>{t('config.languageFootnote')}</Notice>
```

The two selects are `w-[150px]` rather than the provider select's `w-[180px]` because their content is two short words; if a Vietnamese label clips, widen the class — never truncate the word.

Finally the repositories block: `{t('config.reposHeading')}`, `placeholder={cfg.org ? t('config.repoPlaceholderOrg') : t('config.repoPlaceholder')}`, `{t('config.watchRepo')}`, `<Empty>{t('config.noRepos')}</Empty>`, the three mode descriptions, `aria-label={t('config.modeAria', { repo: r.name })}`, and `{t('config.remove')}`.

- [ ] **Step 4: Run the tests and the build**

```bash
cd web/ui && npm test -- --run && npm run build
```

Expected: PASS. `a11y.test.tsx`'s fixture `CONFIG` object has no `language` field, so `cfg.language` is `undefined` there and the Select renders empty — harmless for the assertions that file makes (it checks roles and labels), but add `language: 'en'` to that fixture at `a11y.test.tsx:16-37` so the control has a real value.

- [ ] **Step 5: Update the README**

`README.md:267` currently reads (check the exact wording before editing):

> `prsentinel.yml` holds the rest. `language: en | vi` (default `en`) sets the language the model writes its output in — notes, unresolved questions, drafted…

Extend that paragraph so it names all five prompts and states the separation:

```markdown
`language: en | vi` (default `en`) sets the language the model writes its prose
in — findings notes, unresolved questions, drafted descriptions, PoC test
reasons, follow-up replies and the reason attached to a documentation fix. Fixed
labels stay English: the status vocabulary (`PASS`, `STALE`, `BREAKING_API_CHANGE`
…) is a schema enum that CI reads, and a documentation patch keeps the language
of the document it edits. Set it from the dashboard's Config page or in the file.

The dashboard's own language is a **separate** setting, stored per browser and
switched from the header. Reading a Vietnamese dashboard does not make the agent
write Vietnamese into a public pull request, and it is never written to
`prsentinel.yml`.
```

- [ ] **Step 6: Commit**

```bash
git add web/ui/src/api.ts web/ui/src/pages/Config.tsx web/ui/src/strings.ts web/ui/src/a11y.test.tsx README.md
git commit -m "feat(ui): translate the config page and expose both language settings"
```

---

### Task 8: The review-output language reaches the last two prompts

**Files:**
- Modify: `src/threads.py:17` (import), `:126-159` (`build_followup_prompt`), `:162-200` (`run_followup`)
- Modify: `src/remediate.py:58-77` (`build_prompt`), `:79-94` (`draft_patches`)
- Test: `tests/test_threads.py`, `tests/test_remediate.py`

**Interfaces:**
- Consumes: `LANGUAGES` from `src/verify.py:25` — the one map, imported rather than copied. `verify` imports only `agent` and `untrusted`, so neither import creates a cycle.
- Produces: `build_followup_prompt(replies, new_commits, previous_findings=None, found=None, language="en")`; `build_prompt(docs, found=None, language="en")` in `remediate`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_threads.py`:

```python
def test_a_vietnamese_follow_up_prompts_for_vietnamese_output():
    prompt = build_followup_prompt([{"source": "conversation", "author": "dev1",
                                     "body": "ok", "path": None}], [], language="vi")
    assert "Vietnamese" in prompt


def test_an_english_follow_up_prompt_is_unchanged_by_the_default():
    replies = [{"source": "conversation", "author": "dev1", "body": "ok", "path": None}]
    assert build_followup_prompt(replies, []) == build_followup_prompt(replies, [],
                                                                       language="en")


def test_run_followup_forwards_the_language(tmp_path):
    (tmp_path / "verify-meta.json").write_text(json.dumps({"session_id": "sess-9"}))
    transcript = FileSessionStore(tmp_path).path_for({"session_id": "sess-9"})
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(json.dumps({"type": "user", "uuid": "a"}) + "\n")
    captured = {}

    def runner(prompt, **kw):
        captured["prompt"] = prompt
        return AgentResult(data=dict(FINDINGS), session_id="s", cost_usd=0.0,
                           num_turns=1, duration_ms=1)

    run_followup({"model": "m", "language": "vi"}, tmp_path / "ws", tmp_path,
                 {"head_sha": "sha2"},
                 [{"source": "conversation", "author": "dev1", "body": "ok",
                   "path": None}], [], runner=runner)
    assert "Vietnamese" in captured["prompt"]
```

Append to `tests/test_remediate.py`, adding `build_prompt` to its import at line 4-6:

```python
def test_a_vietnamese_doc_fix_translates_the_reason_but_not_the_document():
    prompt = build_prompt(fixable_docs(FINDINGS), language="vi")
    assert "Vietnamese" in prompt
    # The replacement text is pasted into the file through a GitHub suggestion
    # block. Translating it would rewrite the README in another language.
    assert "new_snippet" in prompt
    lowered = prompt.lower()
    assert "same language as the document" in lowered or "document's own language" in lowered


def test_an_english_doc_fix_prompt_is_unchanged_by_the_default():
    docs = fixable_docs(FINDINGS)
    assert build_prompt(docs) == build_prompt(docs, language="en")


def test_draft_patches_forwards_the_language(tmp_path):
    captured = {}

    def runner(prompt, **kw):
        captured["prompt"] = prompt
        return AgentResult(data={"patches": [PATCH]}, session_id="s", cost_usd=0.0,
                           num_turns=1, duration_ms=1)

    draft_patches(FINDINGS, {"model": "m", "language": "vi"}, tmp_path / "ws",
                  tmp_path, runner=runner)
    assert "Vietnamese" in captured["prompt"]
```

- [ ] **Step 2: Run them to verify they fail**

```bash
pytest tests/test_threads.py tests/test_remediate.py -q
```

Expected: FAIL — `build_followup_prompt() got an unexpected keyword argument 'language'`.

- [ ] **Step 3: Thread the language through `threads.py`**

Extend the import at line 17:

```python
from verify import FINDINGS_SCHEMA, LANGUAGES, SYSTEM_PROMPT, validate_findings
```

Change the signature and the return. The function currently ends `return f"""…""".strip()`; assign it first so the sentence can be appended, matching `verify.py:229-232` exactly:

```python
def build_followup_prompt(replies: list[dict], new_commits: list[dict],
                          previous_findings: dict | None = None,
                          found: list[str] | None = None,
                          language: str = "en") -> str:
```

```python
    prompt = f"""
The author replied to your review. The workspace is now at the latest commit.
...
current code.
""".strip()
    if language not in ("", "en"):
        name = LANGUAGES.get(language, language)
        prompt += f"\n\nWrite every note, detail and question in {name}."
    return prompt
```

In `run_followup`, pass it at the call site:

```python
        build_followup_prompt(replies, new_commits, previous_findings=carried,
                              found=found, language=cfg.get("language", "en")),
```

- [ ] **Step 4: Thread the language through `remediate.py`, with the split instruction**

Add the import:

```python
from verify import LANGUAGES
```

Then the signature and the appended paragraph. This is **not** the sentence `verify.py` uses — the distinction between the reason and the replacement text is the whole point:

```python
def build_prompt(docs: list[dict], found: list[str] | None = None,
                 language: str = "en") -> str:
    # `what` is the review agent's account of a doc, written from repository
    # content — second-hand, but the same provenance as the text it describes.
    listed = untrusted.block(
        "Doc findings",
        "\n".join(f"- {d['path']} ({d['status']}): {d.get('what', '')}" for d in docs),
        found=found)
    prompt = f"""
A review found these documentation files out of sync with the code:

{listed}

For each one: read the file, read the code it describes, and produce the minimal
text replacement that makes the doc true. Copy `old_snippet` exactly as it
appears in the file so it can be replaced programmatically — if you cannot
reproduce it exactly, skip that file rather than guessing.
""".strip()
    if language not in ("", "en"):
        name = LANGUAGES.get(language, language)
        # Deliberately split: `new_snippet` is pasted into the file through a
        # GitHub suggestion block, so translating it would rewrite the document
        # in a language its readers did not choose.
        prompt += (f"\n\nWrite `why` in {name}. Write `old_snippet` and "
                   f"`new_snippet` in the same language as the document itself — "
                   f"never translate the documentation text you are replacing.")
    return prompt
```

In `draft_patches`, pass it:

```python
        build_prompt(docs, found=found, language=cfg.get("language", "en")),
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
pytest tests/test_threads.py tests/test_remediate.py -q
```

Expected: PASS.

- [ ] **Step 6: Run the whole Python suite**

```bash
pytest tests/ -q
```

Expected: PASS — no regression in `test_run.py` or `test_e2e.py`, which drive both modules through the full pipeline.

- [ ] **Step 7: Commit**

```bash
git add src/threads.py src/remediate.py tests/test_threads.py tests/test_remediate.py
git commit -m "fix: honour the configured language in follow-up replies and doc fixes"
```

---

## Definition of done

Run both gates from a clean tree and confirm each one passes before calling the work finished:

```bash
cd /Users/abc/Desktop/pr-sentinel && pytest tests/ -q
cd web/ui && npm test -- --run && npm run build
```

Then confirm by hand, with the dev server running (`cd web/ui && npm run dev`):

1. The header shows `VI`; clicking it turns the dashboard Vietnamese and `<html lang>` becomes `vi`. Reloading keeps it.
2. The status codes on a PR page (`PASS`, `BREAKING_API_CHANGE`, …) are still English.
3. The Config page's two language selects are independent: switching **Interface** does not touch `prsentinel.yml`; switching **Review output** rewrites the one `language:` line and leaves every comment in the file intact (`git diff prsentinel.yml` should show a one-line change).

## Notes for the executor

- **Do not translate by changing English copy.** If an English string reads awkwardly, leave it — three test files assert these strings verbatim, and rewording is a separate change.
- **When `tsc` reports a missing key in `vi`, that is the safety net working.** Add the translation; never widen the type to silence it.
- Vietnamese renders longer than English. Where a fixed width clips a label (`w-[110px]`, `w-[150px]`, `w-[180px]`, the `w-[160px]` phase node), widen the class. Do not shorten the word into an abbreviation a reader has to decode.
