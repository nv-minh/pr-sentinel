// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { setLang } from './i18n'
// PrDetail lazy-loads this module (`lazy(() => import('../graph/PipelineGraph'))`)
// on first mount. Importing it here too, eagerly, warms the same module-graph
// entry ahead of time so the PR route's flush loop below reliably observes it
// resolved, instead of racing a cold dynamic import.
import './graph/PipelineGraph'

// Local fixtures, deliberately minimal — just enough for each route's own
// controls to actually mount. App.test.tsx is frozen; these are not shared
// with it on purpose.

const CONFIG = {
  org: 'demo',
  interval_minutes: 15,
  post_comment: true,
  skip_human: false,
  auto_describe: false,
  docs_fix_pr: false,
  inline_suggestions: false,
  language: 'en',
  gate: { verification_score_min: 0.8 },
  provider: {
    name: 'anthropic',
    base_url: 'https://api.anthropic.com',
    model: 'claude-opus-4-6',
    claims_model: 'claude-haiku-4-5',
    structured_output: 'native',
    reports_cost: true,
    token_env: 'ANTHROPIC_API_KEY',
    token_present: true,
  },
  providers: ['anthropic', 'openai'],
  repos: [{ name: 'demo/app', mode: 'auto' }],
  config_path: '/etc/prsentinel.yml',
}

const REPO = {
  owner: 'demo', repo: 'app', prs_total: 2, bugs_total: 3, doc_errors_total: 1,
  breaking_total: 0, test_gaps_total: 0, cost_total: 0.12,
  avg_verification_score: 0.75, has_data: true,
  verdict_count: {}, gate_count: { pass: 1, warn: 0, fail: 1, unknown: 0 },
  prs: [],
  open_prs: [
    { pr: 8, title: 'Speed up checkout', draft: false, status: 'not_reviewed',
      rounds: null, bugs: null, doc_errors: null, unavailable: false },
    { pr: 9, title: 'Fix typo', draft: false, status: 'reviewed',
      rounds: 1, bugs: 0, doc_errors: 0, unavailable: false },
  ],
  open_questions: 0,
}

const PR = {
  reviewed: true, owner: 'demo', repo: 'app',
  pr: { pr: 8, title: 'Speed up checkout', author: 'dev2', base: 'main', head: 'perf/x',
        verdict: 'ACCURATE', gate: 'pass', verification_score: 0.9, business_risk: 'low',
        gate_reasons: [], cost_usd: 0.12, breaking: 0, test_gaps: 0, callers_at_risk: 0,
        claims_total: 1, bugs: 0, doc_errors: 0, open_questions: 0, rounds: 1,
        updated_at: '2026-08-16 22:00', failed: false },
  title: 'Speed up checkout',
  claims: [{ id: 'C1', text: 'Adds a pricing cache', category: 'perf', status: 'PASS',
             evidence: ['src/checkout/pricing.py:10'], note: '' }],
  docs: [], impact: [], callers: [], contracts: [], tests: [], threads: [],
  questions: [], answers: [], pruned: [],
  score: { gate: 'pass', verification_score: 0.9, business_risk: 'low', reasons: [] },
  usage: [], replies: [],
}

// Nodes with real ids, so PipelineGraph actually mounts and its phase
// buttons come under test too — the alternative (leaving /graph unmocked, so
// `pipeline?.nodes?.length` is falsy and PrDetail shows the "no pipeline
// data" notice instead) is a smaller fixture, but it is exactly the gap this
// finding is about: it would keep PipelineGraph's phase buttons permanently
// untested. Mocking real nodes is the more valuable choice, so that's what
// this does.
const GRAPH = {
  running: false,
  edges: [{ source: 'snapshot', target: 'claims' }],
  nodes: [
    { id: 'snapshot', label: 'Snapshot', status: 'done', artifact: 'snapshot.json',
      cost_usd: null, duration_ms: null, model: '', metrics: [] },
    { id: 'claims', label: 'Claims', status: 'done', artifact: 'claims.json',
      cost_usd: 0.01, duration_ms: 1200, model: 'claude-haiku-4-5', metrics: [] },
  ],
}

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body =
      url === '/api/config' ? CONFIG
      : url.endsWith('/pr/8/graph') ? GRAPH
      : url.includes('/pr/8/review/status') ? { running: false, stale: false }
      : url.includes('/pr/8/review/log') ? { log: '', running: false }
      : url.endsWith('/pr/8/files')
        ? { files: [], pruned: [], commits: [], threads: [], base_sha: '', head_sha: 'h1' }
      : url.endsWith('/pr/8/extras')
        ? { ticket: null, poc: null, patches: null, neutralized: null, description: null }
      : url.endsWith('/pr/8/trace') ? []
      : url.endsWith('/pr/8') ? PR
      : url.endsWith('/demo/app') ? REPO
      : { repos: [] } // '/api/repos', for the empty repo-list route
    return { ok: true, json: async () => body } as Response
  })
}

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
  // One microtask isn't enough for the PR route: api.pr, api.graph and
  // api.reviewStatus each resolve on their own tick, and PipelineGraph is
  // lazy-loaded on top of that. A few real-timer turns settles all of it;
  // it's a harmless no-op extra wait for the simpler routes. Kept inside one
  // act(...) call (rather than one per turn) so the lazy import's own
  // suspense resolution — which can land in the gap between two separate
  // act() calls — stays inside act's tracking the whole time.
  await act(async () => {
    for (let i = 0; i < 5; i += 1) {
      await new Promise((r) => setTimeout(r, 0))
    }
  })
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  localStorage.removeItem('pr-sentinel-lang')
  vi.stubGlobal('fetch', mockFetch())
  vi.stubGlobal('matchMedia', () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
  }))
  // React Flow (mounted via PipelineGraph on the PR route) measures its
  // container; jsdom reports zeroes without this stub.
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  vi.unstubAllGlobals()
})

// Runs whether or not the test body above threw, so a Vietnamese switch that
// never reaches its own switch-back (a failed assertion mid-test) still
// cannot leak into the next test in this file or any file after it.
afterEach(() => act(() => setLang('en')))

function unnamedButtons(): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('button')).filter(
    (b) => !(b.textContent ?? '').trim() && !b.getAttribute('aria-label'))
}

describe('accessibility basics', () => {
  it('gives every button an accessible name', async () => {
    await render('/')
    expect(unnamedButtons()).toEqual([])
  })

  it('exposes exactly one h1 per page', async () => {
    await render('/')
    expect(container.querySelectorAll('h1')).toHaveLength(1)
  })

  it('sets the theme attribute on the document element', async () => {
    await render('/')
    expect(['light', 'dark']).toContain(document.documentElement.dataset.theme)
  })

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

  // The '/' route above only ever mounts the header's theme toggle — an
  // empty repo list renders no buttons of its own. That single route was
  // the whole a11y suite before this fix, so it only ever inspected one
  // already-compliant button and one already-compliant h1. These three
  // routes are what actually puts PrDetail's ten tabs, PipelineGraph's
  // phase buttons, RepoDetail's Review button and Config's SelectTriggers
  // under test.
  const routes: { path: string; label: string }[] = [
    { path: '/config', label: 'config' },
    { path: '/repos/demo/app', label: 'repo detail' },
    { path: '/repos/demo/app/pr/8', label: 'pr detail' },
  ]

  for (const { path, label } of routes) {
    it(`gives every button an accessible name on the ${label} route`, async () => {
      await render(path)
      expect(unnamedButtons()).toEqual([])
    })

    it(`exposes exactly one h1 on the ${label} route`, async () => {
      await render(path)
      expect(container.querySelectorAll('h1')).toHaveLength(1)
    })
  }
})
