// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { setLang } from './i18n'

const REPO = {
  owner: 'demo', repo: 'app', prs_total: 2, bugs_total: 6, doc_errors_total: 3,
  breaking_total: 1, test_gaps_total: 2, cost_total: 0.6265,
  avg_verification_score: 0.5, has_data: true,
  verdict_count: { ACCURATE: 0, PARTIAL: 1, MISLEADING: 1, NO_CLAIMS: 0 },
  gate_count: { pass: 0, warn: 1, fail: 1, unknown: 0 },
  prs: [], open_prs: [], open_questions: 1, mode: 'auto',
}

// A repo detail fixture with an open PR, used only by the Vietnamese
// RepoDetail test below: the shared REPO fixture's open_prs is empty, which
// is enough for the English tests but leaves nothing to exercise the
// interpolated round/bugs text in a PR row's meta line.
const REPO_WITH_OPEN_PR = {
  ...REPO,
  open_prs: [
    { pr: 9, title: 'Add caching', draft: false, status: 'reviewed' as const,
      rounds: 2, bugs: 3, doc_errors: 1, unavailable: false },
  ],
  prs: [
    { pr: 9, title: 'Add caching', author: 'dev1', base: 'main', head: 'feat/cache',
      verdict: 'ACCURATE', gate: 'pass' as const, verification_score: 0.8, business_risk: 'low',
      gate_reasons: [], cost_usd: 0.1, breaking: 0, test_gaps: 0, callers_at_risk: 0,
      claims_total: 2, bugs: 3, doc_errors: 1, open_questions: 0, rounds: 2,
      updated_at: '2026-08-17 09:00' },
  ],
}

const PR = {
  reviewed: true, owner: 'demo', repo: 'app',
  pr: { pr: 8, title: 'Speed up checkout', author: 'dev2', base: 'main',
        head: 'perf/x', verdict: 'MISLEADING', gate: 'fail', verification_score: 0.333,
        business_risk: 'high', gate_reasons: [], cost_usd: 0.34, breaking: 1,
        test_gaps: 1, callers_at_risk: 1, claims_total: 3, bugs: 4, doc_errors: 2,
        open_questions: 1, rounds: 1, updated_at: '2026-08-16 22:00', failed: false },
  title: 'Speed up checkout',
  claims: [{ id: 'C2', text: 'No behaviour change', category: 'perf', status: 'FAIL',
             evidence: ['src/checkout/pricing.py:74'], note: 'discounts bypass the cache' }],
  docs: [], impact: [],
  callers: [{ symbol: 'price_for(cart)', defined_at: 'a.py:41',
              callers: ['src/api/checkout.py:120'], risk: 'BROKEN', note: '' }],
  contracts: [{ kind: 'SCHEMA', path: 'db/migrations/0042.sql',
                status: 'SCHEMA_MIGRATION_RISK', detail: 'destructive drop' }],
  cross_pr: [{ pr: 456, status: 'SEMANTIC_CONFLICT', symbol: 'createInvoice',
               paths: ['src/payment/invoice.py'],
               evidence: ['src/payment/invoice.py:42'],
               detail: 'renames a symbol this PR calls', confidence: 0.9 }],
  siblings: { scanned: 12, truncated: false, skipped: '', siblings: [] },
  tests: [], threads: [], questions: [], answers: [], pruned: [],
  score: { gate: 'fail', verification_score: 0.333, business_risk: 'high',
           reasons: ['verification score 33% below 80%'] },
  usage: [], replies: [],
}

// Snapshot slice for the workspace's diff pane. The pricing patch's hunk
// covers new-side lines 72-75, so the claim evidence at :74 anchors inline.
const PR_FILES = {
  files: [
    { filename: 'src/checkout/pricing.py', status: 'modified', additions: 3, deletions: 0,
      patch: '@@ -70,3 +72,4 @@\n def price_for(cart):\n     key = _cache_key(cart)\n+    total = _apply_discounts(cart)\n+    return total' },
    { filename: 'db/migrations/0042.sql', status: 'added', additions: 1, deletions: 0,
      patch: '@@ -0,0 +1,1 @@\n+DROP TABLE price_history;' },
  ],
  pruned: [], commits: [], threads: [], base_sha: 'b1', head_sha: 'h1',
}
const PR_EXTRAS = { ticket: null, poc: null, patches: null, neutralized: null, description: null }

// Config route fixture, used only by the Vietnamese Config test below: no
// other test in this file navigates to /config.
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

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body =
      url === '/api/repos' ? { repos: [REPO] }
      : url === '/api/config' ? CONFIG
      : url.includes('/review/status') ? { running: false, stale: false }
      : url.endsWith('/pr/8/files') ? PR_FILES
      : url.endsWith('/pr/8/extras') ? PR_EXTRAS
      : url.endsWith('/pr/8/trace') ? []
      : url.endsWith('/pr/8/graph') ? {}
      : url.endsWith('/pr/8') ? PR
      : url.endsWith('/demo/app') ? REPO
      : {}
    return { ok: true, json: async () => body } as Response
  })
}

function mockFetchWithOpenPr() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body =
      url === '/api/repos' ? { repos: [REPO_WITH_OPEN_PR] }
      : url.includes('/review/status') ? { running: false, stale: false }
      : url.endsWith('/demo/app') ? REPO_WITH_OPEN_PR
      : {}
    return { ok: true, json: async () => body } as Response
  })
}

// Flips the header's real language button — the same element the user
// clicks — rather than reaching into the i18n module, so this stays blind to
// how the store is implemented (same reasoning as components.test.tsx's
// LangSwitcher, applied to the switcher the app actually ships).
function clickLangToggle() {
  const btn = Array.from(container.querySelectorAll('button'))
    .find((b) => b.textContent === 'VI' || b.textContent === 'EN') as HTMLButtonElement
  act(() => { btn.click() })
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
  await vi.dynamicImportSettled() // lazy chunks: PipelineGraph, DiffPane
  await act(async () => { await Promise.resolve() })
  await act(async () => { await Promise.resolve() })
}

beforeEach(() => {
  // react's act() needs to know it is running inside a test renderer
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('fetch', mockFetch())
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
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

describe('App', () => {
  it('renders the repo card grid with a link and a mode badge', async () => {
    await render('/')
    const link = container.querySelector('a[href="/repos/demo/app"]')
    expect(link?.textContent).toContain('demo/app')
    expect(container.textContent).toContain('6 bugs')
    expect(container.textContent).toContain('50% verified')
    expect(container.textContent).toContain('auto') // the literal YAML mode
  })

  it('renders the gate band with a legend on the repo page', async () => {
    await render('/repos/demo/app')
    expect(container.querySelectorAll('.band-seg')).toHaveLength(2)
    expect(container.textContent).toContain('Merge with care')
    expect(container.textContent).toContain('Blocked')
  })

  it('renders a blocked PR with its evidence and reasons', async () => {
    await render('/repos/demo/app/pr/8')
    expect(container.textContent).toContain('Speed up checkout')
    expect(container.textContent).toContain('No behaviour change')
    expect(container.textContent).toContain('src/checkout/pricing.py:74')
    // gate reasons sit behind the header toggle now
    const toggle = Array.from(container.querySelectorAll('button'))
      .find((b) => b.textContent?.startsWith('Show reasons')) as HTMLButtonElement
    await act(async () => { toggle.click() })
    expect(container.textContent).toContain('verification score 33% below 80%')
  })

  it('selects a contract finding from the nav', async () => {
    await render('/repos/demo/app/pr/8')
    const item = Array.from(
      container.querySelectorAll('[data-nav-family="contract"] button'),
    ).find((b) => b.textContent?.includes('0042.sql')) as HTMLButtonElement
    await act(async () => { item.click() })
    expect(window.location.search).toContain('finding=contract-0')
    expect(container.textContent).toContain('db/migrations/0042.sql')
    expect(container.textContent).toContain('SCHEMA_MIGRATION_RISK')
  })

  it('renders the repo ledger in Vietnamese, with numbers landing inside their sentence', async () => {
    await render('/')
    expect(container.textContent).toContain('6 bugs')

    clickLangToggle()

    expect(container.textContent).toContain('6 lỗi') // repos.bugs, interpolated
    expect(container.textContent).toContain('50% đã xác minh') // repos.verified, interpolated
    // config.modeAria, interpolated with the repo name — the mode control
    // lives on the repo card now that Config lost its repo table.
    expect(container.querySelector('[aria-label="Chế độ cho demo/app"]')).toBeTruthy()
    expect(container.textContent).not.toContain('6 bugs')

    // Switch back inside the test: `lang` is module-level (see i18n.ts), so
    // leaving it on 'vi' would hand the next test in this file a Vietnamese
    // App and break its English assertions.
    clickLangToggle()
    expect(container.textContent).toContain('6 bugs')
    expect(container.textContent).toContain('50% verified')
  })

  it('renders the repo detail page in Vietnamese, with a round count landing inside its sentence', async () => {
    vi.stubGlobal('fetch', mockFetchWithOpenPr())
    await render('/repos/demo/app')
    expect(container.textContent).toContain('Merge decisions')

    clickLangToggle()

    expect(container.textContent).toContain('Quyết định merge')
    expect(container.textContent).toContain('2 vòng') // repo.roundMany, interpolated
    expect(container.textContent).toContain('3 lỗi') // repo.prBugs, interpolated
    expect(container.textContent).not.toContain('Merge decisions')

    clickLangToggle()
    expect(container.textContent).toContain('Merge decisions')
  })

  it('renders the PR detail page in Vietnamese, with the blocking count landing inside its sentence', async () => {
    await render('/repos/demo/app/pr/8')
    expect(container.textContent).toContain('Blocking (3)')

    clickLangToggle()

    expect(container.textContent).toContain('Chặn merge (3)') // pr.blockingHeading, interpolated
    // pr.tileGate is the loanword 'Gate' now — assert a VI-only string instead
    expect(container.textContent).toContain('Xem lý do') // ws.reasonsToggle
    expect(container.textContent).not.toContain('Blocking (3)')

    clickLangToggle()
    expect(container.textContent).toContain('Blocking (3)')
  })

  it('renders the config page in Vietnamese', async () => {
    await render('/config')
    expect(container.textContent).toContain('What the poller watches')
    expect(container.textContent).toContain('Model provider')

    clickLangToggle()

    expect(container.textContent).toContain('PR Sentinel đang theo dõi những gì')
    expect(container.textContent).toContain('Nhà cung cấp model')
    expect(container.textContent).not.toContain('What the poller watches')

    clickLangToggle()
    expect(container.textContent).toContain('What the poller watches')
  })

  it('selects a cross-PR finding from the nav', async () => {
    await render('/repos/demo/app/pr/8')
    const item = Array.from(
      container.querySelectorAll('[data-nav-family="crosspr"] button'),
    ).find((b) => b.textContent?.includes('#456')) as HTMLButtonElement
    await act(async () => { item.click() })
    expect(container.textContent).toContain('createInvoice')
    expect(container.textContent).toContain('renames a symbol this PR calls')
  })
})
