// @vitest-environment jsdom
// Route-level behavior of the review workspace: nav grouping, selection via
// the URL query, right-pane tabs, and the poll-stops-when-idle contract.
import { act } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { setLang } from '../i18n'
import { cleanup, flush, mount, setupTestEnv } from '../test/harness'

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
  callers: [{ symbol: 'price_for(cart)', defined_at: 'src/checkout/pricing.py:41',
              callers: ['src/api/checkout.py:120', 'src/admin/quotes.py:57'],
              risk: 'BROKEN', note: 'cached' }],
  contracts: [{ kind: 'SCHEMA', path: 'db/migrations/0042.sql',
                status: 'SCHEMA_MIGRATION_RISK', detail: 'destructive drop' }],
  cross_pr: [], siblings: { scanned: 0, truncated: false, skipped: '', siblings: [] },
  tests: [], threads: [], questions: ['Should the TTL be configurable?'],
  answers: [{ question: 'Doc wrong?', kind: 'doc', answer: 'SKIPPED' }],
  pruned: [], score: { gate: 'fail', verification_score: 0.333, business_risk: 'high',
                       reasons: ['verification score 33% below 80%'] },
  usage: [{ phase: 'verify', session_id: 'v1', cost_usd: 0.3, num_turns: 12,
            duration_ms: 60000, model: 'claude-sonnet-5' }],
  replies: [],
}

const FILES = {
  files: [
    { filename: 'src/checkout/pricing.py', status: 'modified', additions: 4, deletions: 1,
      patch: '@@ -70,3 +72,4 @@\n def price_for(cart):\n     key = _cache_key(cart)\n+    total = _apply_discounts(cart)\n+    return total' },
    { filename: 'db/migrations/0042.sql', status: 'added', additions: 1, deletions: 0,
      patch: '@@ -0,0 +1,1 @@\n+DROP TABLE price_history;' },
  ],
  pruned: [], commits: [{ sha: 'abc', message: 'perf' }], threads: [],
  base_sha: 'b1', head_sha: 'h1',
}

const EXTRAS = { ticket: null, poc: null, patches: null, neutralized: null, description: null }
const GRAPH = { running: false, edges: [], nodes: [
  { id: 'snapshot', label: 'Snapshot', status: 'done', artifact: 'snapshot.json',
    cost_usd: null, duration_ms: null, model: '', metrics: [] },
  { id: 'verify', label: 'Verify', status: 'done', artifact: 'findings.json',
    cost_usd: 0.3, duration_ms: 60000, model: 'claude-sonnet-5', metrics: [] },
] }

let statusBody: Record<string, unknown> = { running: false, stale: false }
let calls: string[] = []

function stubFetch(overrides: Record<string, unknown> = {}) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    calls.push(url)
    if (url.includes('/pr/8/file?')) {
      if (url.includes('quotes.py')) {
        return { ok: true, json: async () => ({
          path: 'src/admin/quotes.py', start: 49, end: 69, total_lines: 90,
          lines: ['def quote_total(cart):', '    return price_for(cart)'],
        }) } as Response
      }
      return { ok: false, status: 404, statusText: 'Not Found',
               json: async () => ({ detail: 'workspace or file not available' }) } as Response
    }
    const body =
      url.includes('/review/status') ? statusBody
      : url.includes('/review/log') ? { log: 'phase: verify', running: statusBody.running }
      : url.endsWith('/files') ? (overrides.files ?? FILES)
      : url.endsWith('/extras') ? EXTRAS
      : url.endsWith('/trace') ? []
      : url.endsWith('/graph') ? GRAPH
      : url.endsWith('/report') ? { markdown: '# Review PR #8' }
      : url.endsWith('/pr/8') ? (overrides.pr ?? PR)
      : {}
    return { ok: true, json: async () => body } as Response
  }))
}

beforeEach(() => {
  setupTestEnv()
  vi.stubGlobal('ResizeObserver', class { observe() {}; unobserve() {}; disconnect() {} })
  statusBody = { running: false, stale: false }
  window.history.pushState({}, '', '/repos/demo/app/pr/8')
})
afterEach(() => {
  act(() => setLang('en'))
  cleanup()
  vi.useRealTimers()
})

it('groups nav findings blocking-first with the blast-radius order', async () => {
  stubFetch()
  const el = await mount(<App />)
  expect(el.textContent).toContain('Blocking (3)')
  const families = Array.from(el.querySelectorAll('[data-nav-family]'))
    .map((n) => n.getAttribute('data-nav-family'))
  expect(families.indexOf('contract')).toBeLessThan(families.indexOf('caller'))
  expect(families.indexOf('caller')).toBeLessThan(families.indexOf('claim'))
})

it('selects a contract finding from the nav and records it in the URL', async () => {
  stubFetch()
  const el = await mount(<App />)
  const item = Array.from(el.querySelectorAll('[data-nav-family="contract"] button'))
    .find((b) => b.textContent?.includes('0042.sql')) as HTMLButtonElement
  await act(async () => { item.click() })
  await flush()
  expect(window.location.search).toContain('finding=contract-0')
  const card = el.querySelector('#finding-contract-0') as HTMLElement
  expect(card.textContent).toContain('SCHEMA_MIGRATION_RISK')
  expect(card.textContent).toContain('destructive drop')
  expect(card.getAttribute('data-selected')).toBe('true')
})

it('switches right-pane tabs through the URL query', async () => {
  stubFetch()
  const el = await mount(<App />)
  const runTab = Array.from(el.querySelectorAll('[role="tab"]'))
    .find((b) => b.textContent === 'Run') as HTMLButtonElement
  // Radix activates a tab on pointer-down, not click
  await act(async () => {
    runTab.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }))
    runTab.click()
  })
  await flush()
  expect(window.location.search).toContain('tab=run')
  expect(el.textContent).toContain('claude-sonnet-5') // usage table
})

it('renders the diff text with the finding card anchored inside its file section', async () => {
  stubFetch()
  const el = await mount(<App />)
  const section = el.querySelector('#file-src-checkout-pricing-py') as HTMLElement
  expect(section).toBeTruthy()
  // the changed line itself is visible (diff table, or raw-patch fallback)
  expect(section.textContent).toContain('_apply_discounts')
  // and the finding card renders inside that file's section
  expect(section.querySelector('#finding-claim-0')).toBeTruthy()
})

it('falls back to raw patch text when hunk headers cannot be parsed', async () => {
  stubFetch({ files: { ...FILES, files: [
    { filename: 'src/checkout/pricing.py', status: 'modified', additions: 1, deletions: 0,
      patch: '@@\n+CACHE_TTL = 300' },
  ] } })
  const el = await mount(<App />)
  const pre = el.querySelector('#file-src-checkout-pricing-py pre') as HTMLElement
  expect(pre.textContent).toContain('+CACHE_TTL = 300')
  expect(el.textContent).toContain('hunk headers could not be parsed')
})

it('peeks workspace code from a chip pointing outside the diff', async () => {
  stubFetch()
  const el = await mount(<App />)
  // the caller card cites src/api/checkout.py:120 — not a changed file
  const chip = Array.from(el.querySelectorAll('#finding-caller-0 button'))
    .find((b) => b.textContent?.includes('src/api/checkout.py:120')) as HTMLButtonElement
  expect(chip).toBeTruthy()
  await act(async () => { chip.click() })
  await flush()
  // the demo mock has no workspace → graceful unavailable state
  expect(el.textContent).toContain('open on GitHub instead')
})

it('shows fetched source lines in the peek when the workspace has the file', async () => {
  stubFetch()
  const el = await mount(<App />)
  const chip = Array.from(el.querySelectorAll('#finding-caller-0 button'))
    .find((b) => b.textContent?.includes('src/admin/quotes.py:57')) as HTMLButtonElement
  await act(async () => { chip.click() })
  await flush()
  expect(el.textContent).toContain('def quote_total')
})

it('navigates to the file when a chip points inside the diff', async () => {
  stubFetch()
  const el = await mount(<App />)
  const chip = Array.from(el.querySelectorAll('#finding-caller-0 button'))
    .find((b) => b.textContent?.includes('src/checkout/pricing.py:41')) as HTMLButtonElement
  await act(async () => { chip.click() })
  expect(window.location.search).toContain('file=src%2Fcheckout%2Fpricing.py')
})

it('polls status only while a review runs and stops when it ends', async () => {
  vi.useFakeTimers()
  stubFetch()
  await mount(<App />)
  const count = () => calls.filter((u) => u.includes('/review/status')).length
  const before = count()
  await act(async () => { vi.advanceTimersByTime(9000) })
  await act(async () => {})
  expect(count()).toBe(before) // idle → no polling

  cleanup()
  statusBody = { running: true }
  stubFetch()
  await mount(<App />)
  const start = count()
  await act(async () => { vi.advanceTimersByTime(3000) })
  await act(async () => {})
  expect(count()).toBeGreaterThan(start) // running → polls
})

it('keeps the simple screen for a not-reviewed PR', async () => {
  stubFetch({ pr: { reviewed: false, owner: 'demo', repo: 'app',
                    pr: { pr: 8, title: 'New PR', author: 'dev', base: 'main', head: 'x' } } })
  const el = await mount(<App />)
  expect(el.textContent).toContain('This pull request has not been reviewed yet.')
  const buttons = Array.from(el.querySelectorAll('button')).map((b) => b.textContent)
  expect(buttons).toContain('Review now')
})
