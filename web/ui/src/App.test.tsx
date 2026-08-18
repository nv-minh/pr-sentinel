// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

const REPO = {
  owner: 'demo', repo: 'app', prs_total: 2, bugs_total: 6, doc_errors_total: 3,
  breaking_total: 1, test_gaps_total: 2, cost_total: 0.6265,
  avg_verification_score: 0.5, has_data: true,
  verdict_count: { ACCURATE: 0, PARTIAL: 1, MISLEADING: 1, NO_CLAIMS: 0 },
  gate_count: { pass: 0, warn: 1, fail: 1, unknown: 0 },
  prs: [], open_prs: [], open_questions: 1,
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

function mockFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const body =
      url === '/api/repos' ? { repos: [REPO] }
      : url.includes('/review/status') ? { running: false, stale: false }
      : url.endsWith('/pr/8') ? PR
      : url.endsWith('/demo/app') ? REPO
      : {}
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
  await act(async () => { await Promise.resolve() })
}

beforeEach(() => {
  // react's act() needs to know it is running inside a test renderer
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('fetch', mockFetch())
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {}, removeEventListener() {} }))
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  vi.unstubAllGlobals()
})

describe('App', () => {
  it('renders the repo ledger', async () => {
    await render('/')
    expect(container.textContent).toContain('demo/app')
    expect(container.textContent).toContain('6 bugs')
    expect(container.textContent).toContain('50% verified')
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
    expect(container.textContent).toContain('verification score 33% below 80%')
  })

  it('switches to the contracts tab', async () => {
    await render('/repos/demo/app/pr/8')
    const tabs = Array.from(container.querySelectorAll('.tab')) as HTMLButtonElement[]
    const contracts = tabs.find((t) => t.textContent?.startsWith('Contracts'))!
    await act(async () => { contracts.click() })
    expect(container.textContent).toContain('db/migrations/0042.sql')
    expect(container.textContent).toContain('SCHEMA_MIGRATION_RISK')
  })

  it('switches to the cross-PR tab', async () => {
    await render('/repos/demo/app/pr/8')
    const tabs = Array.from(container.querySelectorAll('.tab')) as HTMLButtonElement[]
    const crosspr = tabs.find((t) => t.textContent?.startsWith('Cross-PR'))!
    await act(async () => { crosspr.click() })
    expect(container.textContent).toContain('createInvoice')
    expect(container.textContent).toContain('#456')
  })
})
