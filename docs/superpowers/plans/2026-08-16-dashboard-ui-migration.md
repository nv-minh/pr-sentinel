# Dashboard UI/UX Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the PR Sentinel dashboard on Tailwind CSS v4 + shadcn/ui, and make a React Flow node graph of the review pipeline the way you navigate a run.

**Architecture:** The design tokens the current CSS already encodes (paper/ink/hairline, pass/warn/fail, sans for humans + mono for the machine) become CSS custom properties on `:root`, mapped onto shadcn/ui's token contract and exposed to Tailwind through `@theme inline`. Dark mode keeps its `data-theme` attribute, with Tailwind v4's dark variant repointed at it. Component primitives in `src/components.tsx` keep their current exported API so the four pages migrate one at a time. A new `metrics.pipeline_graph()` derives the pipeline's nodes and edges from the artifacts already in `sessions/` — no new state — and a lazily-loaded `@xyflow/react` view renders it, with node clicks driving the detail panel below.

**Tech Stack:** React 19, Vite 7, TypeScript 5.9, Tailwind CSS v4 (`@tailwindcss/vite`), shadcn/ui, `@xyflow/react` 12.x, vitest + jsdom. Backend: FastAPI, pytest.

**Spec:** `docs/superpowers/specs/2026-08-16-dashboard-ui-migration.md`

## Global Constraints

- **`web/ui/src/App.test.tsx` must keep passing unmodified** through every task. It selects on `.band-seg`, `.tab`, and rendered text. Those class names stay as semantic hooks on the new markup — they are the regression net for this migration. If a task genuinely cannot preserve one, stop and raise it rather than editing the assertion.
- **Status is never colour alone.** Every verdict renders glyph + word + colour (`status.ts` `GLYPH` / `TONE_COLOR`); the amber/red pair is not separable for deutan vision. This rule predates the migration.
- **Self-contained.** No CDN, no remote fonts, no external images. Everything ships from `web/ui/dist`.
- **Dark mode is attribute-driven:** `document.documentElement.dataset.theme` = `light` | `dark`, persisted under the existing `pr-sentinel-theme` localStorage key. Tailwind's `dark:` variant is redefined to match the attribute.
- **Ledger token names.** The palette custom properties are `--paper --surface --ink --ink-muted --hairline --hairline-strong --brand --brand-soft --pass --warn --fail --unknown`. Note the two renames from today's CSS: `--accent` → `--brand` and `--muted` → `--ink-muted`, because shadcn/ui claims `--accent` and `--muted` for its own contract. `--pass/--warn/--fail/--unknown` are unchanged, so `status.ts` needs no edit.
- **React Flow attribution stays.** Do not set `proOptions.hideAttribution` — removing it requires a paid licence.
- **`prefers-reduced-motion` disables edge animation** in the graph.
- **Build/test commands:** `cd web/ui && npm run build` (runs `tsc -b && vite build`) and `npm test -- --run`. Backend: `python -m pytest -q` from the repo root.
- **`package-lock.json` must be committed** with every dependency change — CI runs `npm ci`.
- **Commit style:** Conventional Commits.

## Dependency on the provider plan

Task 7 ports the provider panel that `docs/superpowers/plans/2026-08-16-multi-provider.md` adds to `Config.tsx`. **Run the provider plan first.** If it has not shipped, do Task 7 without the provider panel and add it when it lands — nothing else in this plan depends on it.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `web/ui/package.json`, `package-lock.json` | modify | Tailwind v4, shadcn deps, `@xyflow/react` |
| `web/ui/vite.config.ts` | modify | Tailwind plugin, `@` path alias |
| `web/ui/tsconfig.json` | modify | `baseUrl` + `paths` for `@/*` |
| `web/ui/components.json` | **create** | shadcn/ui CLI configuration |
| `web/ui/src/styles.css` | rewrite | Tailwind import, dark variant, ledger tokens, shadcn token mapping |
| `web/ui/src/lib/utils.ts` | **create** (by CLI) | `cn()` class merger |
| `web/ui/src/components/ui/*` | **create** (by CLI) | shadcn primitives |
| `web/ui/src/theme.ts` | **create** | `useTheme()` extracted from `App.tsx`, shared with the graph |
| `web/ui/src/App.tsx` | modify | Shell + masthead on Tailwind |
| `web/ui/src/components.tsx` | rewrite | Same exports, rebuilt on shadcn primitives |
| `web/ui/src/pages/Repos.tsx` | modify | Restyle, loading/empty states |
| `web/ui/src/pages/RepoDetail.tsx` | modify | Restyle, `--muted` → `--ink-muted` |
| `web/ui/src/pages/PrDetail.tsx` | rewrite | Graph-first layout, blocking-findings strip, node→tab wiring |
| `web/ui/src/pages/Config.tsx` | modify | Restyle + provider panel |
| `web/ui/src/graph/PipelineGraph.tsx` | **create** | React Flow canvas, layout, a11y text equivalent |
| `web/ui/src/graph/PhaseNode.tsx` | **create** | One phase node |
| `web/ui/src/graph/layout.ts` | **create** | Fixed node positions, node→tab map |
| `web/ui/src/api.ts` | modify | `PipelineGraph` types + `api.graph()` |
| `web/metrics.py` | modify | `pipeline_graph()` and its phase tables |
| `web/server.py` | modify | `GET .../pr/{n}/graph` |
| `tests/test_metrics.py` | modify | Graph derivation tests |
| `tests/test_server.py` | modify | Graph endpoint tests |
| `README.md` | modify | Dashboard section |

---

### Task 1: Tailwind v4, shadcn/ui, and the design tokens

**Files:**
- Modify: `web/ui/package.json`, `web/ui/vite.config.ts`, `web/ui/tsconfig.json`, `web/ui/src/styles.css`, `web/ui/src/App.tsx`
- Create: `web/ui/components.json`, `web/ui/src/theme.ts`, `web/ui/src/lib/utils.ts` (via CLI), `web/ui/src/components/ui/*` (via CLI)
- Test: `web/ui/src/App.test.tsx` (unchanged — it is the check)

**Interfaces:**
- Consumes: nothing
- Produces:
  - `web/ui/src/theme.ts` exports `useTheme(): [theme: 'light' | 'dark', toggle: () => void]`
  - `@/lib/utils` exports `cn(...inputs: ClassValue[]): string`
  - CSS custom properties listed in Global Constraints, available as Tailwind colours (`bg-paper`, `text-ink-muted`, `border-hairline`, `text-pass`, …)

- [ ] **Step 1: Install the dependencies**

```bash
cd web/ui
npm install -D tailwindcss@^4 @tailwindcss/vite@^4 @types/node
npm install class-variance-authority clsx tailwind-merge lucide-react
```

- [ ] **Step 2: Wire Tailwind and the path alias into Vite**

Replace `web/ui/vite.config.ts` with:

```ts
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The dashboard is served by FastAPI in production; in dev, proxy the API to it.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:6789' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
```

Add to `compilerOptions` in `web/ui/tsconfig.json`, after `"types": ["vite/client"]`:

```json
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
```

- [ ] **Step 3: Write the token stylesheet**

Replace the whole of `web/ui/src/styles.css` with:

```css
@import "tailwindcss";

/* The theme toggle writes data-theme on <html>. Tailwind v4 points `dark:` at
   prefers-color-scheme by default, so repoint it at the attribute — the user's
   explicit choice must win over the OS. */
@custom-variant dark (&:where([data-theme="dark"], [data-theme="dark"] *));

/* PR Sentinel is an evidence ledger, not a dashboard. The machine speaks in
   monospace (verdicts, metrics, file:line citations); humans speak in sans
   (titles, claim text, prose). Hairlines, not cards, so the eye reads down a
   column of evidence the way it reads a docket. */
:root {
  --paper: #fafaf8;
  --surface: #ffffff;
  --ink: #101828;
  --ink-muted: #5b6478;
  --hairline: #e4e5e1;
  --hairline-strong: #d2d4cf;
  --brand: #155e63;
  --brand-soft: #e5efee;

  --pass: #0e9f6e;
  --warn: #e5a50a;
  --fail: #d63a2f;
  --unknown: #7b7fd4;

  /* shadcn/ui's token contract, mapped onto the palette above so its
     components inherit the ledger look instead of bringing their own. */
  --background: var(--paper);
  --foreground: var(--ink);
  --card: var(--surface);
  --card-foreground: var(--ink);
  --popover: var(--surface);
  --popover-foreground: var(--ink);
  --primary: var(--brand);
  --primary-foreground: #ffffff;
  --secondary: var(--brand-soft);
  --secondary-foreground: var(--ink);
  --muted: var(--brand-soft);
  --muted-foreground: var(--ink-muted);
  --accent: var(--brand-soft);
  --accent-foreground: var(--ink);
  --destructive: var(--fail);
  --destructive-foreground: #ffffff;
  --border: var(--hairline);
  --input: var(--hairline-strong);
  --ring: var(--brand);
  --radius: 4px;
}

[data-theme="dark"] {
  --paper: #0e1117;
  --surface: #151a22;
  --ink: #e6e9ef;
  --ink-muted: #98a2b3;
  --hairline: #232a35;
  --hairline-strong: #313a48;
  --brand: #3fb6ae;
  --brand-soft: #16302f;

  --pass: #0f9e72;
  --warn: #b8880c;
  --fail: #e05540;
  --unknown: #767ed9;
}

/* `inline` because these reference custom properties that change per selector;
   without it Tailwind would freeze the light values into the utilities. */
@theme inline {
  --color-paper: var(--paper);
  --color-surface: var(--surface);
  --color-ink: var(--ink);
  --color-ink-muted: var(--ink-muted);
  --color-hairline: var(--hairline);
  --color-hairline-strong: var(--hairline-strong);
  --color-brand: var(--brand);
  --color-brand-soft: var(--brand-soft);

  --color-pass: var(--pass);
  --color-warn: var(--warn);
  --color-fail: var(--fail);
  --color-unknown: var(--unknown);

  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);

  --font-sans: ui-sans-serif, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;

  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-lg: 6px;
}

@layer base {
  * { border-color: var(--border); }

  html, body, #root { height: 100%; }

  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: var(--font-sans);
    font-size: 15px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  a { color: inherit; text-decoration: none; }
  a:hover { text-decoration: underline; }

  :focus-visible {
    outline: 2px solid var(--brand);
    outline-offset: 2px;
    border-radius: 2px;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

> Every rule from the old stylesheet that is *not* here — `.shell`, `.row`, `.tile`, `.tab`, `.band`, `.button`, … — is deliberately gone. Tasks 2–7 rebuild each one with Tailwind utilities. Between Task 1 and Task 7 the app is visually incomplete but must stay functional and test-green.

- [ ] **Step 4: Initialise shadcn/ui and pull in the primitives**

Create `web/ui/components.json`:

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

Then, from `web/ui`:

```bash
npx shadcn@latest add button badge card separator select tabs table skeleton tooltip scroll-area -y
```

This writes `src/lib/utils.ts` and `src/components/ui/*.tsx`. If the CLI offers to overwrite `src/styles.css`, **decline** — the file from Step 3 is the source of truth.

- [ ] **Step 5: Extract the theme hook**

Create `web/ui/src/theme.ts`:

```ts
import { useEffect, useState } from 'react'

export type Theme = 'light' | 'dark'

const KEY = 'pr-sentinel-theme'

function initial(): Theme {
  const stored = localStorage.getItem(KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** The theme, and a toggle. Written to <html data-theme> so CSS and React Flow
 *  read the same source. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initial)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(KEY, theme)
  }, [theme])
  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')]
}
```

- [ ] **Step 6: Rebuild the shell**

Replace `web/ui/src/App.tsx` with:

```tsx
import { Config } from './pages/Config'
import { PrDetail } from './pages/PrDetail'
import { RepoDetail } from './pages/RepoDetail'
import { Repos } from './pages/Repos'
import { navigate, useRoute } from './router'
import { useTheme } from './theme'

function link(path: string) {
  return {
    href: path,
    onClick: (e: React.MouseEvent) => { e.preventDefault(); navigate(path) },
  }
}

const NAV_LINK =
  'font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted ' +
  'hover:text-ink aria-[current=page]:text-ink'

export function App() {
  const route = useRoute()
  const [theme, toggleTheme] = useTheme()

  return (
    <div className="mx-auto max-w-[1120px] px-7 pb-24">
      <header className="mb-8 flex flex-wrap items-baseline gap-5 border-b border-hairline-strong pt-[22px] pb-[18px]">
        <a className="font-mono text-[13px] font-bold uppercase tracking-[0.14em] text-brand"
           {...link('/')}>
          PR Sentinel
        </a>
        <nav className="ml-auto flex items-center gap-[18px]">
          <a {...link('/')} className={NAV_LINK}
             aria-current={route.name === 'repos' ? 'page' : undefined}>
            Repos
          </a>
          <a {...link('/config')} className={NAV_LINK}
             aria-current={route.name === 'config' ? 'page' : undefined}>
            Config
          </a>
          <button
            className="rounded border border-hairline-strong px-[9px] py-1 font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted hover:border-ink-muted hover:text-ink"
            onClick={toggleTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </nav>
      </header>

      <main>
        {route.name === 'repos' && <Repos />}
        {route.name === 'config' && <Config />}
        {route.name === 'repo' && <RepoDetail owner={route.owner} repo={route.repo} />}
        {route.name === 'pr' && (
          <PrDetail owner={route.owner} repo={route.repo} pr={route.pr} />
        )}
      </main>
    </div>
  )
}
```

- [ ] **Step 7: Rename the two clashing tokens at their inline call sites**

`grep -rn "var(--muted)\|var(--accent)" src/` and replace `var(--muted)` with `var(--ink-muted)` and `var(--accent)` with `var(--brand)`. Expect hits in `pages/RepoDetail.tsx` and `pages/PrDetail.tsx` only — `status.ts` uses `--pass/--warn/--fail/--unknown`, which did not change.

- [ ] **Step 8: Verify the build and the existing tests**

Run: `cd web/ui && npm run build`
Expected: clean, no TypeScript errors

Run: `npm test -- --run`
Expected: PASS — all four `App.test.tsx` assertions still hold (the classes they select on live in the page components, which Task 1 has not touched)

- [ ] **Step 9: Commit**

```bash
cd ../.. && git add web/ui/package.json web/ui/package-lock.json web/ui/components.json \
  web/ui/vite.config.ts web/ui/tsconfig.json web/ui/src/styles.css web/ui/src/App.tsx \
  web/ui/src/theme.ts web/ui/src/lib web/ui/src/components/ui web/ui/src/pages
git commit -m "feat(ui): Tailwind v4 + shadcn/ui foundation and design tokens"
```

---

### Task 2: Component primitives on shadcn

**Files:**
- Rewrite: `web/ui/src/components.tsx`
- Test: `web/ui/src/App.test.tsx` (unchanged)

**Interfaces:**
- Consumes: `@/components/ui/*` and `cn()` from Task 1
- Produces: the **same exports as today**, so no page changes are needed in this task — `Mark`, `StatusWord`, `Tile`, `Eyebrow`, `GateBand`, `Row`, `Citations`, `Empty`, `Ledger`, `ToneDot`. Four new exports:
  - `Tiles({ children }: { children: ReactNode })` — the grid wrapper that `<div className="tiles">` used to be
  - `Loading({ label }: { label?: string })` — skeleton rows, `role="status"`
  - `ErrorNotice({ message }: { message: string })` — `role="alert"`
  - `Notice({ children, tone }: { children: ReactNode; tone?: 'info' | 'fail' })`

The class hooks `band-seg`, `row`, `tile` stay on the markup.

- [ ] **Step 1: Write the failing test**

Create `web/ui/src/components.test.tsx`:

```tsx
// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Empty, ErrorNotice, GateBand, Loading, Row, StatusWord, Tile } from './components'

let container: HTMLDivElement
let root: Root

function render(node: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  act(() => {
    root = createRoot(container)
    root.render(node)
  })
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('primitives', () => {
  it('renders a status as glyph and word, never colour alone', () => {
    render(<StatusWord status="FAIL" />)
    expect(container.textContent).toContain('FAIL')
  })

  it('marks an unknown status rather than dropping it', () => {
    render(<StatusWord status="" />)
    expect(container.textContent).toContain('UNKNOWN')
  })

  it('keeps the band-seg hook and one segment per non-empty bucket', () => {
    render(<GateBand counts={{ pass: 2, warn: 0, fail: 1, unknown: 0 }} />)
    expect(container.querySelectorAll('.band-seg')).toHaveLength(2)
    expect(container.textContent).toContain('Clear to merge')
  })

  it('says so when there is nothing to band', () => {
    render(<GateBand counts={undefined} />)
    expect(container.textContent).toContain('No scored reviews yet')
  })

  it('keeps a row clickable by keyboard', () => {
    let hits = 0
    render(<Row status="PASS" title="t" onClick={() => { hits += 1 }} />)
    const row = container.querySelector('.row') as HTMLElement
    expect(row.getAttribute('role')).toBe('button')
    expect(row.getAttribute('tabindex')).toBe('0')
    act(() => { row.click() })
    expect(hits).toBe(1)
  })

  it('renders a tile with its label and note', () => {
    render(<Tile label="Gate" value="fail" note="Blocked" />)
    expect(container.textContent).toContain('Gate')
    expect(container.textContent).toContain('Blocked')
  })

  it('renders empty, loading and error states', () => {
    render(<><Empty>nothing here</Empty><Loading /><ErrorNotice message="boom" /></>)
    expect(container.textContent).toContain('nothing here')
    expect(container.textContent).toContain('Loading')
    expect(container.textContent).toContain('boom')
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web/ui && npm test -- --run src/components.test.tsx`
Expected: FAIL — `components.tsx` exports no `Loading` or `ErrorNotice`

- [ ] **Step 3: Write the implementation**

Rewrite `web/ui/src/components.tsx`, keeping every existing export's signature:

```tsx
import type { ReactNode } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { GLYPH, TONE_COLOR, bandSegments, toneOf } from './status'
import type { Tone } from './status'

export function Mark({ status }: { status: string }) {
  const tone = toneOf(status)
  return (
    <span className="row-mark text-center font-mono text-[13px] font-bold leading-[1.6]"
          style={{ color: TONE_COLOR[tone] }} aria-hidden="true">
      {GLYPH[tone]}
    </span>
  )
}

export function StatusWord({ status }: { status: string }) {
  const tone = toneOf(status)
  return (
    <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]"
          style={{ color: TONE_COLOR[tone] }}>
      {status || 'UNKNOWN'}
    </span>
  )
}

export function Tile({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="tile bg-surface px-[18px] pt-4 pb-[18px]">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </div>
      <div className="mt-1.5 font-mono text-[30px] font-semibold tracking-[-0.02em] tabular-nums">
        {value}
      </div>
      {note ? <div className="mt-0.5 text-xs text-ink-muted">{note}</div> : null}
    </div>
  )
}

export function Tiles({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-px overflow-hidden rounded border border-hairline bg-hairline">
      {children}
    </div>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <h2 className="mt-10 mb-3 flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-muted after:h-px after:flex-1 after:bg-hairline after:content-['']">
      {children}
    </h2>
  )
}

/** The gate band: one horizontal bar segmented by merge decision. Each segment
 *  carries its own count, and the legend repeats glyph + word, so the reading
 *  never depends on telling amber from red. */
export function GateBand({ counts }: { counts: Record<string, number> | undefined }) {
  const segments = bandSegments(counts)
  if (!segments.length) {
    return (
      <div className="my-2.5 flex h-[34px] gap-0.5">
        <div className="flex flex-1 items-center justify-center rounded-sm border border-dashed border-hairline-strong font-mono text-xs text-ink-muted">
          No scored reviews yet
        </div>
      </div>
    )
  }
  return (
    <>
      <div className="mt-1 mb-2.5 flex h-[34px] gap-0.5" role="img"
           aria-label={segments.map((s) => `${s.count} ${s.label}`).join(', ')}>
        {segments.map((seg) => (
          <div
            key={seg.key}
            className="band-seg flex min-w-0.5 items-center justify-center rounded-sm font-mono text-xs font-semibold text-white"
            style={{ flex: seg.share, background: TONE_COLOR[seg.key] }}
            title={`${seg.label}: ${seg.count}`}
          >
            {seg.share > 0.08 ? seg.count : ''}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-4 font-mono text-xs text-ink-muted">
        {segments.map((seg) => (
          <span className="flex items-center gap-[7px]" key={seg.key}>
            <ToneDot tone={seg.key} />
            {GLYPH[seg.key]} {seg.label} · {seg.count}
          </span>
        ))}
      </div>
    </>
  )
}

export function Row({
  status, title, meta, right, onClick,
}: {
  status: string
  title: ReactNode
  meta?: ReactNode
  right?: ReactNode
  onClick?: () => void
}) {
  const interactive = Boolean(onClick)
  return (
    <div
      className={`row grid grid-cols-[26px_minmax(0,1fr)_auto] items-start gap-3.5 border-b border-hairline px-0.5 py-[13px] hover:bg-brand-soft max-[620px]:grid-cols-[22px_minmax(0,1fr)] ${
        interactive ? 'cursor-pointer' : ''
      }`}
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.() } } : undefined}
    >
      <Mark status={status} />
      <div>
        <div className="text-[15px]">{title}</div>
        {meta ? (
          <div className="mt-[3px] break-words font-mono text-xs text-ink-muted">{meta}</div>
        ) : null}
      </div>
      {right ? (
        <div className="row-right whitespace-nowrap text-right font-mono text-xs tabular-nums text-ink-muted max-[620px]:col-start-2 max-[620px]:text-left">
          {right}
        </div>
      ) : null}
    </div>
  )
}

export function Citations({ items }: { items: string[] }) {
  if (!items?.length) return <span>no evidence cited</span>
  return (
    <>
      {items.map((item, i) => (
        <span className="mr-[5px] inline-block rounded-sm border border-hairline-strong px-[5px] py-px font-mono text-[11.5px] text-ink"
              key={`${item}-${i}`}>
          {item}
        </span>
      ))}
    </>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="border-b border-hairline px-0.5 py-[18px] text-sm text-ink-muted">
      {children}
    </div>
  )
}

export function Ledger({ children }: { children: ReactNode }) {
  return <div className="border-t border-hairline">{children}</div>
}

export function ToneDot({ tone }: { tone: Tone }) {
  return (
    <span className="size-2.5 flex-none rounded-sm"
          style={{ background: TONE_COLOR[tone] }} />
  )
}

/** Three skeleton rows: the page keeps its shape while the fetch lands, so the
 *  layout does not jump when it does. */
export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="space-y-2 py-4" role="status" aria-live="polite">
      <span className="sr-only">{label}…</span>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  )
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="my-4 border-l-2 border-fail py-2 pl-3 font-mono text-[12.5px] text-ink"
         role="alert">
      {message}
    </div>
  )
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'fail' }) {
  return (
    <div className={`my-4 border-l-2 py-2 pl-3 font-mono text-[12.5px] ${
      tone === 'fail' ? 'border-fail text-ink' : 'border-brand text-ink-muted'
    }`}>
      {children}
    </div>
  )
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm test -- --run`
Expected: PASS — both `components.test.tsx` and the untouched `App.test.tsx`

Run: `npm run build`
Expected: clean

- [ ] **Step 5: Commit**

```bash
git add web/ui/src/components.tsx web/ui/src/components.test.tsx
git commit -m "feat(ui): rebuild primitives on shadcn with loading and error states"
```

---

### Task 3: Repos and RepoDetail pages

**Files:**
- Modify: `web/ui/src/pages/Repos.tsx`, `web/ui/src/pages/RepoDetail.tsx`
- Test: `web/ui/src/App.test.tsx` (unchanged)

**Interfaces:**
- Consumes: `Tiles`, `Loading`, `ErrorNotice`, `Notice` from Task 2; `Button` from `@/components/ui/button`
- Produces: no new exports

- [ ] **Step 1: Restyle `Repos.tsx`**

Replace the bare `<h1 className="page-title">` / `<p className="page-sub">` markup with utilities, and swap the loading and error branches onto the new primitives:

```tsx
  if (error) return <ErrorNotice message={`Could not load repos — ${error}`} />
  if (!repos) return <Loading label="Loading repositories" />
```

Page heading pattern, used on every page from here on:

```tsx
      <h1 className="mb-1.5 text-[clamp(28px,4vw,40px)] font-[680] leading-[1.08] tracking-[-0.025em]">
        Every claim, checked against the code.
      </h1>
      <p className="mb-7 font-mono text-[12.5px] tracking-[0.02em] text-ink-muted">
        …
      </p>
```

Everything else in the file — the `reviewed` / `waiting` split, the `Row` props, the `navigate` calls — stays exactly as it is.

- [ ] **Step 2: Restyle `RepoDetail.tsx`**

Same treatment. Additionally:

- Wrap the six `<Tile>`s in `<Tiles>` instead of `<div className="tiles">`.
- Replace `<div className="toolbar">` with `className="my-2.5 flex flex-wrap items-center gap-2.5"`.
- Replace the `Review now` / `Re-review` `<button className="button button-quiet">` with shadcn `<Button variant="outline" size="sm">`.
- Replace the "GitHub is unreachable" `<div className="notice">` with `<Notice>`.
- Replace the remaining `var(--muted)` inline style on the `#{row.pr}` span with `className="font-mono text-ink-muted"`.

- [ ] **Step 3: Verify**

Run: `npm test -- --run`
Expected: PASS — `App.test.tsx` still finds `demo/app`, `6 bugs`, `50% verified`, and two `.band-seg` elements

Run: `npm run build`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add web/ui/src/pages/Repos.tsx web/ui/src/pages/RepoDetail.tsx
git commit -m "feat(ui): restyle the repo list and repo detail pages"
```

---

### Task 4: Pipeline graph API

**Files:**
- Modify: `web/metrics.py`, `web/server.py`
- Test: `tests/test_metrics.py`, `tests/test_server.py`

**Interfaces:**
- Consumes: `metrics._read_json`, `metrics._read_json_list`, `metrics.review_process_info` (all existing)
- Produces:
  - `metrics.PHASES`, `metrics.EDGES`, `metrics.ORDER`
  - `metrics.pipeline_graph(session_root: Path, owner: str, repo: str, n: int) -> dict | None` returning `{"nodes": [...], "edges": [{"source","target"}], "running": bool}`; each node is `{"id","label","status","artifact","cost_usd","duration_ms","model","metrics":[{"label","value"}]}` with `status` in `done | running | pending | skipped | failed`
  - `GET /api/repos/{owner}/{repo}/pr/{pr}/graph` returning that object, 404 when the session directory does not exist

- [ ] **Step 1: Write the failing test**

Append to `tests/test_metrics.py`:

```python
import json

from metrics import pipeline_graph


def _session(tmp_path, **files):
    d = tmp_path / "demo" / "app" / "pr-8"
    d.mkdir(parents=True)
    for name, body in files.items():
        name = name.replace("__", ".")
        (d / name).write_text(body if isinstance(body, str) else json.dumps(body))
    return d


def _by_id(graph):
    return {n["id"]: n for n in graph["nodes"]}


def test_graph_is_none_without_a_session(tmp_path):
    assert pipeline_graph(tmp_path, "demo", "app", 8) is None


def test_a_fresh_session_has_only_snapshot_done(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200, "files": [{"filename": "a.py"}]})
    nodes = _by_id(pipeline_graph(tmp_path, "demo", "app", 8))
    assert nodes["snapshot"]["status"] == "done"
    assert nodes["claims"]["status"] == "pending"
    assert nodes["snapshot"]["metrics"][0] == {"label": "files", "value": 1}


def test_a_long_pr_body_skips_describe(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    assert _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["describe"]["status"] == "skipped"


def test_a_thin_pr_body_leaves_describe_pending(tmp_path):
    _session(tmp_path, snapshot__json={"body": "too short"})
    assert _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["describe"]["status"] == "pending"


def test_remediate_is_skipped_when_no_doc_is_fixable(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"docs": [{"path": "README.md", "status": "MATCH"}]})
    assert _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["remediate"]["status"] == "skipped"


def test_remediate_is_pending_when_a_doc_is_stale(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"docs": [{"path": "README.md", "status": "STALE"}]})
    assert _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["remediate"]["status"] == "pending"


def test_the_reply_loop_is_skipped_until_it_runs(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    assert _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["followup"]["status"] == "skipped"


def test_usage_lands_on_the_phase_that_spent_it(tmp_path):
    _session(tmp_path,
             snapshot__json={"body": "x" * 200},
             findings__json={"claims": [{"id": "C1"}], "docs": []},
             usage__json=[{"phase": "verify", "cost_usd": 0.34, "duration_ms": 9100,
                           "model": "claude-sonnet-5", "num_turns": 12}])
    verify = _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["verify"]
    assert verify["status"] == "done"
    assert verify["cost_usd"] == 0.34
    assert verify["model"] == "claude-sonnet-5"
    assert {"label": "claims", "value": 1} in verify["metrics"]


def test_a_failed_report_is_marked_failed(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200},
             report__md="# Review FAILED\n\n- Error: boom\n")
    assert _by_id(pipeline_graph(tmp_path, "demo", "app", 8))["report"]["status"] == "failed"


def test_a_live_lock_marks_the_first_unfinished_phase_running(tmp_path, monkeypatch):
    import os

    d = _session(tmp_path, snapshot__json={"body": "x" * 200},
                 claims__json=[{"id": "C1"}])
    (d / "review.lock").write_text(json.dumps({"pid": os.getpid(),
                                               "started_at": "2026-08-16T10:00:00"}))
    graph = pipeline_graph(tmp_path, "demo", "app", 8)
    assert graph["running"] is True
    assert _by_id(graph)["verify"]["status"] == "running"


def test_edges_form_the_documented_dag(tmp_path):
    _session(tmp_path, snapshot__json={"body": "x" * 200})
    edges = {(e["source"], e["target"])
             for e in pipeline_graph(tmp_path, "demo", "app", 8)["edges"]}
    assert ("verify", "remediate") in edges     # doc-fix branch
    assert ("followup", "verify") in edges      # reply loop
    assert ("remediate", "report") in edges
```

Append to `tests/test_server.py`:

```python
def test_graph_endpoint_serves_the_demo_session(monkeypatch):
    from pathlib import Path

    # absolute, so the test does not depend on pytest's working directory
    demo_root = Path(__file__).resolve().parents[1] / "sessions"
    monkeypatch.setenv("PRS_SESSION_ROOT", str(demo_root))
    body = TestClient(app).get("/api/repos/demo/app/pr/8/graph").json()
    ids = [n["id"] for n in body["nodes"]]
    assert ids[0] == "snapshot" and "verify" in ids
    assert body["running"] is False


def test_graph_endpoint_404s_for_an_unknown_pr(tmp_path, monkeypatch):
    monkeypatch.setenv("PRS_SESSION_ROOT", str(tmp_path))
    assert TestClient(app).get("/api/repos/demo/app/pr/999/graph").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_metrics.py -q`
Expected: FAIL — `ImportError: cannot import name 'pipeline_graph' from 'metrics'`

- [ ] **Step 3: Write the implementation**

In `web/metrics.py`, add the imports beside `from synthesize import _overall_verdict`:

```python
from describe import MIN_BODY_CHARS
from remediate import fixable_docs
```

Then append the phase tables and the function:

```python
# The pipeline, as the dashboard draws it. `optional` phases do not run on every
# review — a good PR body skips Describe, no fixable docs skips Doc fixes, and
# the reply loop only runs under `--reply`.
PHASES = (
    {"id": "snapshot", "label": "Snapshot", "artifact": "snapshot.json"},
    {"id": "describe", "label": "Describe", "artifact": "description.json"},
    {"id": "claims", "label": "Claims", "artifact": "claims.json"},
    {"id": "followup", "label": "Replies", "artifact": "replies.json"},
    {"id": "verify", "label": "Verify", "artifact": "findings.json"},
    {"id": "remediate", "label": "Doc fixes", "artifact": "patches.json"},
    {"id": "score", "label": "Score", "artifact": "score.json"},
    {"id": "ask", "label": "Confirm", "artifact": "answers.json"},
    {"id": "report", "label": "Report", "artifact": "report.md"},
)

EDGES = (
    ("snapshot", "describe"), ("describe", "claims"), ("claims", "verify"),
    ("followup", "verify"), ("verify", "score"), ("verify", "remediate"),
    ("score", "ask"), ("ask", "report"), ("remediate", "report"),
)

# The path a run actually walks, used to decide which node is the live one.
ORDER = ("snapshot", "describe", "claims", "verify", "score", "ask", "report")


def _phase_skipped(phase_id: str, snapshot: dict, findings: dict) -> bool:
    """Whether a missing artifact means 'not applicable' rather than 'not yet'."""
    if phase_id == "describe":
        return len((snapshot.get("body") or "").strip()) >= MIN_BODY_CHARS
    if phase_id == "remediate":
        return not fixable_docs(findings)
    if phase_id == "followup":
        return True  # only ever runs on --reply; its artifact is the only proof
    return False


def _phase_metrics(phase_id: str, session_dir: Path, snapshot: dict,
                   findings: dict, scores: dict) -> list[dict]:
    """The two or three numbers worth putting on the node itself."""
    if phase_id == "snapshot":
        return [{"label": "files", "value": len(snapshot.get("files") or [])},
                {"label": "commits", "value": len(snapshot.get("commits") or [])},
                {"label": "pruned", "value": len(snapshot.get("pruned") or [])}]
    if phase_id == "claims":
        return [{"label": "claims",
                 "value": len(_read_json_list(session_dir / "claims.json"))}]
    if phase_id == "verify":
        return [{"label": "claims", "value": len(findings.get("claims") or [])},
                {"label": "docs", "value": len(findings.get("docs") or [])},
                {"label": "callers",
                 "value": len(findings.get("callers_outside_diff") or [])},
                {"label": "contracts", "value": len(findings.get("contracts") or [])}]
    if phase_id == "score":
        value = scores.get("verification_score")
        return [{"label": "gate", "value": scores.get("gate") or "—"},
                {"label": "verified",
                 "value": f"{round(value * 100)}%" if value is not None else "—"}]
    if phase_id == "ask":
        answers = _read_json_list(session_dir / "answers.json")
        return [{"label": "answered",
                 "value": sum(1 for a in answers
                              if a.get("answer") not in ("SKIPPED", ""))},
                {"label": "open",
                 "value": sum(1 for a in answers
                              if a.get("answer") in ("SKIPPED", ""))}]
    if phase_id == "remediate":
        return [{"label": "patches",
                 "value": len(_read_json_list(session_dir / "patches.json"))}]
    if phase_id == "followup":
        return [{"label": "replies",
                 "value": len(_read_json_list(session_dir / "replies.json"))}]
    return []


def pipeline_graph(session_root: Path, owner: str, repo: str, n: int) -> dict | None:
    """The review pipeline for one PR, derived only from artifacts on disk.

    There is no run state to store: a phase is done because its file exists, and
    the live phase is the first one that has neither run nor been skipped.
    """
    session_dir = session_root / owner / repo / f"pr-{n}"
    if not session_dir.is_dir():
        return None
    snapshot = _read_json(session_dir / "snapshot.json") or {}
    findings = _read_json(session_dir / "findings.json") or {}
    scores = _read_json(session_dir / "score.json") or {}
    usage = {e.get("phase"): e
             for e in _read_json_list(session_dir / "usage.json")
             if isinstance(e, dict)}
    report = session_dir / "report.md"
    failed = report.exists() and report.read_text(
        errors="replace").startswith("# Review FAILED")
    running = review_process_info(session_dir) is not None

    nodes = []
    for phase in PHASES:
        phase_id = phase["id"]
        if (session_dir / phase["artifact"]).exists():
            status = "failed" if (phase_id == "report" and failed) else "done"
        elif _phase_skipped(phase_id, snapshot, findings):
            status = "skipped"
        else:
            status = "pending"
        spent = usage.get(phase_id) or {}
        nodes.append({
            "id": phase_id,
            "label": phase["label"],
            "status": status,
            "artifact": phase["artifact"],
            "cost_usd": spent.get("cost_usd"),
            "duration_ms": spent.get("duration_ms"),
            "model": spent.get("model", ""),
            "metrics": _phase_metrics(phase_id, session_dir, snapshot,
                                      findings, scores),
        })

    if running:
        by_id = {node["id"]: node for node in nodes}
        for phase_id in ORDER:
            if by_id[phase_id]["status"] == "pending":
                by_id[phase_id]["status"] = "running"
                break

    return {"nodes": nodes,
            "edges": [{"source": s, "target": t} for s, t in EDGES],
            "running": running}
```

In `web/server.py`, add the endpoint immediately after `api_report`:

```python
@app.get("/api/repos/{owner}/{repo}/pr/{pr}/graph")
def api_graph(owner: str, repo: str, pr: int):
    """The review pipeline as nodes and edges, for the dashboard's graph view."""
    graph = metrics.pipeline_graph(_session_root(), owner, repo, pr)
    if graph is None:
        raise HTTPException(status_code=404, detail="no session for this PR")
    return graph
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_metrics.py tests/test_server.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole backend suite**

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/metrics.py web/server.py tests/test_metrics.py tests/test_server.py
git commit -m "feat: derive the review pipeline graph from session artifacts"
```

---

### Task 5: The React Flow canvas

**Files:**
- Create: `web/ui/src/graph/layout.ts`, `web/ui/src/graph/PhaseNode.tsx`, `web/ui/src/graph/PipelineGraph.tsx`
- Create: `web/ui/src/graph/PipelineGraph.test.tsx`
- Modify: `web/ui/package.json`, `web/ui/src/api.ts`

**Interfaces:**
- Consumes: the graph endpoint from Task 4; `useTheme` from Task 1; `TONE_COLOR`/`GLYPH` from `status.ts`
- Produces:
  - `api.ts`: `PhaseStatus = 'done' | 'running' | 'pending' | 'skipped' | 'failed'`, `GraphNode`, `GraphEdge`, `Pipeline`, and `api.graph(owner, repo, pr)`
  - `graph/layout.ts`: `POSITION: Record<string, {x: number; y: number}>`, `STATUS_TONE: Record<PhaseStatus, Tone>`, `NODE_TAB: Record<string, TabKey>`
  - `graph/PhaseNode.tsx`: default-exported React Flow node component
  - `graph/PipelineGraph.tsx`: `<PipelineGraph pipeline={...} selected={...} onSelect={...} />` — **default export**, so `PrDetail` can `React.lazy()` it

- [ ] **Step 1: Install React Flow**

```bash
cd web/ui && npm install @xyflow/react
```

- [ ] **Step 2: Write the failing test**

Create `web/ui/src/graph/PipelineGraph.test.tsx`:

```tsx
// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PipelineGraph from './PipelineGraph'
import type { Pipeline } from '../api'

const PIPELINE: Pipeline = {
  running: false,
  edges: [
    { source: 'snapshot', target: 'claims' },
    { source: 'claims', target: 'verify' },
  ],
  nodes: [
    { id: 'snapshot', label: 'Snapshot', status: 'done', artifact: 'snapshot.json',
      cost_usd: null, duration_ms: null, model: '',
      metrics: [{ label: 'files', value: 3 }] },
    { id: 'claims', label: 'Claims', status: 'done', artifact: 'claims.json',
      cost_usd: 0.01, duration_ms: 2000, model: 'claude-haiku-4-5-20251001',
      metrics: [{ label: 'claims', value: 2 }] },
    { id: 'verify', label: 'Verify', status: 'running', artifact: 'findings.json',
      cost_usd: null, duration_ms: null, model: '', metrics: [] },
  ],
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  // React Flow measures its container; jsdom reports zeroes without this.
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
  vi.stubGlobal('matchMedia', () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
  }))
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

describe('PipelineGraph', () => {
  it('mirrors every phase in a text equivalent for screen readers', () => {
    render(<PipelineGraph pipeline={PIPELINE} selected={null} onSelect={() => {}} />)
    const list = container.querySelector('[data-testid="pipeline-text"]')!
    expect(list.textContent).toContain('Snapshot')
    expect(list.textContent).toContain('done')
    expect(list.textContent).toContain('Verify')
    expect(list.textContent).toContain('running')
  })

  it('lets the text equivalent select a phase, so the graph is not the only way in', () => {
    const picked: string[] = []
    render(<PipelineGraph pipeline={PIPELINE} selected={null}
                          onSelect={(id) => picked.push(id)} />)
    const button = container.querySelector('[data-phase="claims"]') as HTMLButtonElement
    act(() => { button.click() })
    expect(picked).toEqual(['claims'])
  })
})
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm test -- --run src/graph/PipelineGraph.test.tsx`
Expected: FAIL — `Cannot find module './PipelineGraph'`

- [ ] **Step 4: Add the API types and call**

Append to `web/ui/src/api.ts`:

```ts
export type PhaseStatus = 'done' | 'running' | 'pending' | 'skipped' | 'failed'

export interface GraphNode {
  id: string
  label: string
  status: PhaseStatus
  artifact: string
  cost_usd: number | null
  duration_ms: number | null
  model: string
  metrics: { label: string; value: string | number }[]
}

export interface GraphEdge {
  source: string
  target: string
}

export interface Pipeline {
  nodes: GraphNode[]
  edges: GraphEdge[]
  running: boolean
}
```

and inside the `api` object, after `report`:

```ts
  graph: (owner: string, repo: string, pr: number) =>
    request<Pipeline>(`/api/repos/${owner}/${repo}/pr/${pr}/graph`),
```

- [ ] **Step 5: Write the layout table**

Create `web/ui/src/graph/layout.ts`:

```ts
import type { PhaseStatus } from '../api'
import type { Tone } from '../status'

/** Hand-placed, not auto-laid-out: nine fixed phases in a shape that reads
 *  left-to-right, with the reply loop above the spine and the doc-fix branch
 *  below it. A layout engine would only make this move around between runs. */
export const POSITION: Record<string, { x: number; y: number }> = {
  snapshot: { x: 0, y: 130 },
  describe: { x: 185, y: 130 },
  claims: { x: 370, y: 130 },
  followup: { x: 370, y: 0 },
  verify: { x: 555, y: 130 },
  score: { x: 740, y: 130 },
  remediate: { x: 740, y: 262 },
  ask: { x: 925, y: 130 },
  report: { x: 1110, y: 196 },
}

export const STATUS_TONE: Record<PhaseStatus, Tone> = {
  done: 'pass',
  running: 'warn',
  failed: 'fail',
  pending: 'unknown',
  skipped: 'unknown',
}

export const STATUS_WORD: Record<PhaseStatus, string> = {
  done: 'done',
  running: 'running',
  failed: 'failed',
  pending: 'pending',
  skipped: 'skipped',
}

/** Which detail tab a node opens. Phases with no tab of their own land on the
 *  nearest one that actually shows their output. */
export const NODE_TAB: Record<string, string> = {
  snapshot: 'context',
  describe: 'context',
  claims: 'claims',
  followup: 'threads',
  verify: 'claims',
  remediate: 'docs',
  score: 'claims',
  ask: 'confirm',
  report: 'claims',
}
```

- [ ] **Step 6: Write the node component**

Create `web/ui/src/graph/PhaseNode.tsx`:

```tsx
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { GraphNode } from '../api'
import { GLYPH, TONE_COLOR, formatCost } from '../status'
import { STATUS_TONE, STATUS_WORD } from './layout'

export type PhaseNodeData = GraphNode & { selected: boolean }

export default function PhaseNode({ data }: NodeProps) {
  const node = data as unknown as PhaseNodeData
  const tone = STATUS_TONE[node.status]
  const dim = node.status === 'pending' || node.status === 'skipped'

  return (
    <div
      className={`w-[160px] rounded border bg-surface px-3 py-2.5 text-left shadow-sm ${
        node.selected ? 'border-brand ring-2 ring-brand' : 'border-hairline-strong'
      } ${dim ? 'opacity-60' : ''}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-hairline-strong" />
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">{node.label}</span>
        <span className="font-mono text-[11px] font-bold" style={{ color: TONE_COLOR[tone] }}>
          {GLYPH[tone]}
        </span>
      </div>
      <div className="font-mono text-[10px] uppercase tracking-[0.12em]"
           style={{ color: TONE_COLOR[tone] }}>
        {STATUS_WORD[node.status]}
      </div>
      {node.metrics.length > 0 && (
        <dl className="mt-1.5 space-y-0.5 font-mono text-[10.5px] text-ink-muted">
          {node.metrics.map((m) => (
            <div key={m.label} className="flex justify-between gap-2">
              <dt>{m.label}</dt>
              <dd className="tabular-nums text-ink">{m.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {node.cost_usd !== null && (
        <div className="mt-1.5 border-t border-hairline pt-1 font-mono text-[10px] text-ink-muted">
          {formatCost(node.cost_usd)}
          {node.duration_ms ? ` · ${Math.round(node.duration_ms / 1000)}s` : ''}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-hairline-strong" />
    </div>
  )
}
```

- [ ] **Step 7: Write the canvas**

Create `web/ui/src/graph/PipelineGraph.tsx`:

```tsx
import { useMemo } from 'react'
import {
  Background, Controls, MiniMap, ReactFlow, type Edge, type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { Pipeline } from '../api'
import { TONE_COLOR } from '../status'
import { useTheme } from '../theme'
import PhaseNode from './PhaseNode'
import { POSITION, STATUS_TONE, STATUS_WORD } from './layout'

const nodeTypes = { phase: PhaseNode }

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** The pipeline as a graph, plus a text equivalent underneath it.
 *
 *  The canvas is aria-hidden: a pan-and-zoom surface is not navigable with a
 *  screen reader, so the list below carries the same information and the same
 *  ability to select a phase. */
export default function PipelineGraph({
  pipeline, selected, onSelect,
}: {
  pipeline: Pipeline
  selected: string | null
  onSelect: (id: string) => void
}) {
  const [theme] = useTheme()
  const still = prefersReducedMotion()

  const nodes: Node[] = useMemo(
    () => pipeline.nodes.map((node) => ({
      id: node.id,
      type: 'phase',
      position: POSITION[node.id] ?? { x: 0, y: 0 },
      data: { ...node, selected: node.id === selected },
      draggable: false,
      connectable: false,
      selectable: true,
    })),
    [pipeline.nodes, selected],
  )

  const edges: Edge[] = useMemo(() => {
    const status = new Map(pipeline.nodes.map((n) => [n.id, n.status]))
    return pipeline.edges.map((edge) => {
      const target = status.get(edge.target)
      const live = target === 'running'
      const faded = target === 'pending' || target === 'skipped'
      return {
        id: `${edge.source}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        animated: live && !still,
        style: {
          stroke: live ? TONE_COLOR.warn : 'var(--hairline-strong)',
          strokeWidth: live ? 2 : 1,
          opacity: faded ? 0.45 : 1,
        },
      }
    })
  }, [pipeline.edges, pipeline.nodes, still])

  return (
    <div>
      <div className="h-[380px] rounded border border-hairline bg-paper" aria-hidden="true">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          onNodeClick={(_, node) => onSelect(node.id)}
          minZoom={0.4}
          maxZoom={1.4}
        >
          <Background gap={18} size={1} color="var(--hairline)" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable
                   nodeColor={(n) => TONE_COLOR[STATUS_TONE[(n.data as { status: Pipeline['nodes'][number]['status'] }).status]]} />
        </ReactFlow>
      </div>

      <ol className="mt-3 flex flex-wrap gap-1.5" data-testid="pipeline-text">
        {pipeline.nodes.map((node) => (
          <li key={node.id}>
            <button
              type="button"
              data-phase={node.id}
              onClick={() => onSelect(node.id)}
              aria-pressed={node.id === selected}
              className={`rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-[0.06em] ${
                node.id === selected
                  ? 'border-brand text-ink'
                  : 'border-hairline-strong text-ink-muted hover:text-ink'
              }`}
            >
              {node.label}{' '}
              <span style={{ color: TONE_COLOR[STATUS_TONE[node.status]] }}>
                {STATUS_WORD[node.status]}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `npm test -- --run`
Expected: PASS

Run: `npm run build`
Expected: clean

- [ ] **Step 9: Commit**

```bash
git add web/ui/package.json web/ui/package-lock.json web/ui/src/api.ts web/ui/src/graph
git commit -m "feat(ui): React Flow pipeline graph with a screen-reader equivalent"
```

---

### Task 6: PrDetail rebuilt around the graph

**Files:**
- Rewrite: `web/ui/src/pages/PrDetail.tsx`
- Test: `web/ui/src/App.test.tsx` (unchanged — it must still pass)

**Interfaces:**
- Consumes: `api.graph` and `PipelineGraph` from Task 5; `NODE_TAB` from `graph/layout.ts`; primitives from Task 2
- Produces: no new exports

Three changes on top of a restyle:

1. **The graph goes first**, lazily loaded, polled on the same 3-second tick that already follows `review/status`.
2. **A blocking-findings strip** above the tabs: every `FAIL`, `BROKEN`, `WRONG`, `FABRICATED`, `BREAKING_API_CHANGE`, `SCHEMA_MIGRATION_RISK` and `MISSING` finding, most severe first, each linking to its tab. This is the answer to "a blocking migration risk is three clicks away".
3. **Node clicks drive the tab** through `NODE_TAB`.

The nine-tab strip stays, with its `.tab` class and `{label} {count}` content — `App.test.tsx` clicks the Contracts tab and asserts on its content.

- [ ] **Step 1: Add the graph state**

Replace the import block at the top of the file with:

```tsx
import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { PrDetail as Detail, Pipeline, ReviewStatus } from '../api'
import {
  Citations, Empty, ErrorNotice, Eyebrow, Ledger, Loading, Notice, Row,
  StatusWord, Tile, Tiles,
} from '../components'
import { NODE_TAB } from '../graph/layout'
import { GATE_WORD, formatCost, formatScore } from '../status'

// React Flow is ~100 kB gzipped and only this route needs it.
const PipelineGraph = lazy(() => import('../graph/PipelineGraph'))
```

Then, alongside the existing state:

```tsx
  const [pipeline, setPipeline] = useState<Pipeline | null>(null)
  const [phase, setPhase] = useState<string | null>(null)

  const loadGraph = useCallback(() => {
    api.graph(owner, repo, pr).then(setPipeline).catch(() => setPipeline(null))
  }, [owner, repo, pr])

  useEffect(loadGraph, [loadGraph])
```

and inside the existing polling `tick()`, after `setLog(l.log)`:

```tsx
          loadGraph()
```

plus `loadGraph()` in the branch that fires when a run finishes (next to the existing `load()`).

Add `loadGraph` to that effect's dependency array.

- [ ] **Step 2: Render the graph**

Immediately below the gate tiles and above the toolbar:

```tsx
          <Eyebrow>Pipeline</Eyebrow>
          {pipeline ? (
            <Suspense fallback={<Loading label="Loading the pipeline" />}>
              <PipelineGraph
                pipeline={pipeline}
                selected={phase}
                onSelect={(id) => {
                  setPhase(id)
                  const next = NODE_TAB[id]
                  if (next) setTab(next as TabKey)
                }}
              />
            </Suspense>
          ) : (
            <Notice>No pipeline data for this review yet.</Notice>
          )}
```

- [ ] **Step 3: Add the blocking-findings strip**

Above the `<div className="tabs">` block:

```tsx
const BLOCKING: { tab: TabKey; label: string; pick: (d: Detail) => { status: string; title: string; detail: string }[] }[] = [
  { tab: 'contracts', label: 'Contract',
    pick: (d) => (d.contracts ?? [])
      .filter((c) => c.status !== 'COMPATIBLE')
      .map((c) => ({ status: c.status, title: c.path, detail: c.detail })) },
  { tab: 'callers', label: 'Caller',
    pick: (d) => (d.callers ?? [])
      .filter((c) => c.risk === 'BROKEN')
      .map((c) => ({ status: c.risk, title: c.symbol, detail: c.note })) },
  { tab: 'claims', label: 'Claim',
    pick: (d) => (d.claims ?? [])
      .filter((c) => c.status === 'FAIL')
      .map((c) => ({ status: c.status, title: c.text || c.id, detail: c.note })) },
  { tab: 'impact', label: 'Impact',
    pick: (d) => (d.impact ?? [])
      .filter((i) => i.impact === 'BROKEN')
      .map((i) => ({ status: i.impact, title: i.requirement, detail: i.detail })) },
  { tab: 'docs', label: 'Doc',
    pick: (d) => (d.docs ?? [])
      .filter((x) => x.status === 'WRONG' || x.status === 'FABRICATED')
      .map((x) => ({ status: x.status, title: x.path, detail: x.what })) },
  { tab: 'tests', label: 'Test',
    pick: (d) => (d.tests ?? [])
      .filter((t) => t.assertion_quality === 'MISSING')
      .map((t) => ({ status: t.assertion_quality, title: t.target, detail: t.note })) },
]
```

and the markup:

```tsx
          {(() => {
            const blocking = BLOCKING.flatMap((group) =>
              group.pick(data).map((item) => ({ ...item, ...group })))
            if (!blocking.length) return null
            return (
              <>
                <Eyebrow>Blocking ({blocking.length})</Eyebrow>
                <Ledger>
                  {blocking.map((item, i) => (
                    <Row
                      key={`${item.tab}-${i}`}
                      status={item.status}
                      title={<>{item.title} <StatusWord status={item.status} /></>}
                      meta={item.detail}
                      right={item.label}
                      onClick={() => setTab(item.tab)}
                    />
                  ))}
                </Ledger>
              </>
            )
          })()}
```

- [ ] **Step 4: Restyle the rest**

- `<div className="tabs">` → `className="tabs mt-7 mb-1 flex flex-wrap gap-1 border-b border-hairline-strong"` (the `tabs` name is kept for readability; the `.tab` class on the buttons is what the test needs)
- each tab button → `className="tab border-b-2 border-transparent px-2.5 py-2 font-mono text-xs uppercase tracking-[0.06em] text-ink-muted aria-selected:border-brand aria-selected:text-ink"`
- `<div className="tiles">` → `<Tiles>`
- `<pre className="log">` → `className="max-h-[260px] overflow-auto rounded border border-hairline bg-surface px-3.5 py-3 font-mono text-xs whitespace-pre-wrap text-ink-muted"`
- `.notice` / `.notice-fail` → `<Notice>` / `<Notice tone="fail">`
- `.button` / `.button-quiet` → shadcn `<Button>` / `<Button variant="outline">`
- the `#{pr}` and `var(--muted)` inline styles → `className="font-mono text-ink-muted"`

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm test -- --run`
Expected: PASS — in particular `switches to the contracts tab`, which clicks a `.tab` whose text starts with `Contracts` and then asserts `db/migrations/0042.sql` and `SCHEMA_MIGRATION_RISK` are on screen. Note the demo PR has a blocking contract, so that text now also appears in the Blocking strip — the assertion is `toContain`, so it still holds.

Run: `npm run build`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add web/ui/src/pages/PrDetail.tsx
git commit -m "feat(ui): graph-first PR detail with a blocking-findings strip"
```

---

### Task 7: Config page

**Files:**
- Modify: `web/ui/src/pages/Config.tsx`
- Test: `web/ui/src/App.test.tsx` (unchanged)

**Interfaces:**
- Consumes: primitives from Task 2; `Select` from `@/components/ui/select`; `ProviderInfo` and `api.setProvider` from the multi-provider plan (Task 8 there)
- Produces: no new exports

- [ ] **Step 1: Restyle**

Both this step and the next need shadcn's select, so add the import once:

```tsx
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Empty, ErrorNotice, Eyebrow, Ledger, Loading, Notice, Row, Tile, Tiles,
} from '../components'
```

- Page heading and sub-line use the Task 3 pattern.
- `<div className="tiles">` → `<Tiles>`.
- `<div className="toolbar">` → `className="my-2.5 flex flex-wrap items-center gap-2.5"`.
- The repo-name `<input type="text">` → `className="rounded border border-input bg-surface px-2 py-1.5 font-mono text-xs text-ink"`.
- `Watch repo` and `Remove` → shadcn `<Button>` / `<Button variant="outline" size="sm">`.
- The per-repo `auto`/`manual` `<select>` → shadcn `<Select>`.
- Loading and error branches → `<Loading />` and `<ErrorNotice />`.

- [ ] **Step 2: Port the provider panel**

The multi-provider plan added a provider panel to this page against the old CSS classes. Rebuild it on the new primitives, keeping every field and every line of copy:

```tsx
      <Eyebrow>Model provider</Eyebrow>
      {!cfg.provider.token_present && (
        <Notice tone="fail">
          No key for <code>{cfg.provider.name}</code> — set{' '}
          <code>{cfg.provider.token_env}</code> in <code>.env</code>. Reviews will
          refuse to start until it is there.
        </Notice>
      )}
      <Tiles>
        <Tile label="Provider" value={cfg.provider.name} note={cfg.provider.base_url} />
        <Tile label="Deep dive" value={cfg.provider.model} />
        <Tile label="Claims" value={cfg.provider.claims_model} />
        <Tile
          label="Schema"
          value={cfg.provider.structured_output === 'native' ? 'enforced' : 'prompted'}
          note={cfg.provider.structured_output === 'native'
            ? 'the API validates the JSON'
            : 'the reply is parsed and repaired'}
        />
        <Tile label="Key" value={cfg.provider.token_present ? 'set' : 'missing'}
              note={cfg.provider.token_env} />
        <Tile label="Costs" value={cfg.provider.reports_cost ? 'tracked' : 'unknown'}
              note={cfg.provider.reports_cost ? '' : 'budget caps do not apply'} />
      </Tiles>
      <div className="my-2.5 flex flex-wrap items-center gap-2.5">
        <Select value={cfg.provider.name}
                onValueChange={(name) => act(() => api.setProvider(name))}>
          <SelectTrigger className="w-[180px] font-mono text-xs" aria-label="Model provider">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {cfg.providers.map((name) => (
              <SelectItem key={name} value={name} className="font-mono text-xs">
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted">
          tokens are read from the environment only
        </span>
      </div>
```

The tile values render long model IDs, so give `.tile-value`'s replacement a smaller size here if `deepseek-v4-flash` wraps badly — `<Tile>` takes any `ReactNode`, so wrap the string in `<span className="text-base">` rather than changing the primitive.

If the multi-provider plan has not shipped, skip this step and leave a `TODO(provider)` comment naming that plan.

- [ ] **Step 3: Verify**

Run: `npm test -- --run && npm run build`
Expected: PASS, clean

- [ ] **Step 4: Commit**

```bash
git add web/ui/src/pages/Config.tsx
git commit -m "feat(ui): restyle the config page and its provider panel"
```

---

### Task 8: Polish, accessibility, and documentation

**Files:**
- Modify: `web/ui/src/pages/*.tsx` (touch-ups only), `web/ui/index.html`, `README.md`
- Test: `web/ui/src/App.test.tsx`, and a new `web/ui/src/a11y.test.tsx`

**Interfaces:**
- Consumes: everything above
- Produces: no new exports

- [ ] **Step 1: Write the failing test**

Create `web/ui/src/a11y.test.tsx`:

```tsx
// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

let container: HTMLDivElement
let root: Root

async function render(path: string) {
  window.history.pushState({}, '', path)
  container = document.createElement('div')
  document.body.appendChild(container)
  await act(async () => {
    root = createRoot(container)
    root.render(<App />)
  })
  await act(async () => { await Promise.resolve() })
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ repos: [] }) })))
  vi.stubGlobal('matchMedia', () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
  }))
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  vi.unstubAllGlobals()
})

describe('accessibility basics', () => {
  it('gives every button an accessible name', async () => {
    await render('/')
    const unnamed = Array.from(container.querySelectorAll('button')).filter(
      (b) => !(b.textContent ?? '').trim() && !b.getAttribute('aria-label'))
    expect(unnamed).toEqual([])
  })

  it('exposes exactly one h1 per page', async () => {
    await render('/')
    expect(container.querySelectorAll('h1')).toHaveLength(1)
  })

  it('sets the theme attribute on the document element', async () => {
    await render('/')
    expect(['light', 'dark']).toContain(document.documentElement.dataset.theme)
  })
})
```

- [ ] **Step 2: Run it and fix what it finds**

Run: `npm test -- --run src/a11y.test.tsx`
Expected: it may fail on an icon-only button somewhere — add the missing `aria-label` at the call site.

- [ ] **Step 3: Manual pass**

Serve the app and walk it in both themes:

```bash
(cd web/ui && npm run build)
PRS_SESSION_ROOT=sessions python -m web.server
```

At `http://127.0.0.1:6789/repos/demo/app/pr/8`, check each of:
- Tab from the top of the page to the bottom: every control takes focus, with a visible ring, in the order it is read.
- Toggle the theme: no unreadable text, and the graph's own colours flip with it.
- Narrow the window to 380 px: nothing overflows horizontally; the graph scrolls inside its own box.
- Turn on "Reduce motion" at the OS level and reload: no animated edges.
- Stop the server mid-page-load: the page shows `ErrorNotice`, not a blank screen.

- [ ] **Step 4: Update the README**

Replace the **Dashboard** section's last paragraph with:

```markdown
A read-only ledger over `sessions/` — no database. Repo list → repo detail
(KPIs, merge-decision band, open PRs) → PR detail, which opens on the review
pipeline as a graph: Snapshot → Describe → Claims → Verify → Score → Confirm →
Report, with the doc-fix branch off Verify and the reply loop back into it. Each
node carries its own status, cost and headline counts; clicking one opens that
phase's evidence below. Blocking findings are listed above the tabs, most severe
first. Reviews started from the dashboard run in the background and the graph
follows them live.
```

- [ ] **Step 5: Full verification**

Run: `python -m pytest -q`
Expected: PASS

Run: `cd web/ui && npm run build && npm test -- --run`
Expected: clean build, all suites PASS

- [ ] **Step 6: Commit**

```bash
cd ../.. && git add web/ui/src README.md
git commit -m "feat(ui): accessibility pass and dashboard documentation"
```

---

## Notes for whoever executes this

- **Between Task 1 and Task 7 the app looks half-built.** That is by design: Task 1 deletes the old stylesheet, and each page gets its utilities back in its own task. Do not batch the visual work into one commit to avoid the awkward middle — the point of the sequence is that each page is independently reviewable.
- **If `App.test.tsx` fails, the markup lost a hook, not the test.** Put `.band-seg` / `.tab` / `.row` back rather than editing the assertion.
- **React Flow in jsdom needs `ResizeObserver`.** It is stubbed in `PipelineGraph.test.tsx`; any new test that mounts the graph needs the same stub.
