// @vitest-environment jsdom
// The PR queue: section grouping, running-only polling, optimistic starts.
import { act } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { setLang } from '../i18n'
import { cleanup, flush, mount, setupTestEnv } from '../test/harness'

function rec(pr: number, gate: string, extra: Record<string, unknown> = {}) {
  return {
    pr, title: `PR ${pr}`, author: 'dev1', base: 'main', head: `feat/${pr}`,
    verdict: 'PARTIAL', gate, verification_score: 0.7, business_risk: 'low',
    gate_reasons: [], cost_usd: 0.2, breaking: 0, test_gaps: 0, callers_at_risk: 0,
    claims_total: 2, bugs: 1, doc_errors: 0, open_questions: 0, rounds: 1,
    updated_at: '2026-08-17 09:00', failed: false, ...extra,
  }
}

function open(pr: number, status: string, extra: Record<string, unknown> = {}) {
  return { pr, title: `PR ${pr}`, draft: false, status, rounds: 1, bugs: 1,
           doc_errors: 0, unavailable: false, ...extra }
}

const QUEUE = {
  owner: 'demo', repo: 'app', prs_total: 3, bugs_total: 3, doc_errors_total: 0,
  breaking_total: 0, test_gaps_total: 0, cost_total: 0.6,
  avg_verification_score: 0.7, has_data: true,
  verdict_count: { ACCURATE: 1, PARTIAL: 2, MISLEADING: 0, NO_CLAIMS: 0 },
  gate_count: { pass: 1, warn: 1, fail: 1, unknown: 0 },
  prs: [rec(5, 'fail'), rec(4, 'pass'), rec(3, 'warn', { open_questions: 2 })],
  open_prs: [
    open(7, 'reviewing', { started_at: '2026-08-18T12:00:00' }),
    open(6, 'not_reviewed', { rounds: null, bugs: null, doc_errors: null }),
    open(5, 'reviewed'), open(4, 'reviewed'), open(3, 'reviewed'),
    open(2, 'not_reviewed', { draft: true, rounds: null, bugs: null, doc_errors: null }),
  ],
  open_questions: 2,
}

const SETTLED = {
  ...QUEUE,
  open_prs: QUEUE.open_prs.map((r) => (r.pr === 7 ? { ...r, status: 'reviewed' } : r)),
}

let calls: Array<{ url: string; method: string }>

function stubFetch(repoBodies: unknown[], statusBody: unknown = { running: true }) {
  calls = []
  let repoHits = 0
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, method: init?.method ?? 'GET' })
    const body =
      url.includes('/review/status') ? statusBody
      : url.includes('/review') ? { ok: true }
      : url.endsWith('/demo/app')
        ? repoBodies[Math.min(repoHits++, repoBodies.length - 1)]
      : {}
    return { ok: true, json: async () => body } as Response
  }))
}

beforeEach(() => {
  setupTestEnv()
  window.history.pushState({}, '', '/repos/demo/app')
})
afterEach(() => {
  act(() => setLang('en'))
  cleanup()
  vi.useRealTimers()
})

function sectionOf(el: HTMLElement, pr: number): string {
  // walk backwards from the row to the nearest section heading
  const row = Array.from(el.querySelectorAll('.row'))
    .find((r) => r.textContent?.includes(`#${pr}`)) as HTMLElement
  expect(row, `row #${pr}`).toBeTruthy()
  let node: Element | null = row.closest('[data-section]')
  return node?.getAttribute('data-section') ?? ''
}

it('groups PRs into sections by state', async () => {
  stubFetch([QUEUE])
  const el = await mount(<App />)
  expect(sectionOf(el, 7)).toBe('running')
  expect(sectionOf(el, 5)).toBe('blocked')
  expect(sectionOf(el, 3)).toBe('warned')
  expect(sectionOf(el, 4)).toBe('passed')
  expect(sectionOf(el, 6)).toBe('not_reviewed')
  expect(sectionOf(el, 2)).toBe('draft')
})

it('polls review status only while a PR is running', async () => {
  vi.useFakeTimers()
  stubFetch([QUEUE])
  await mount(<App />)
  const before = calls.filter((c) => c.url.includes('/review/status')).length
  await act(async () => { vi.advanceTimersByTime(8000) })
  await act(async () => {})
  expect(calls.filter((c) => c.url.includes('/review/status')).length)
    .toBeGreaterThan(before)
  cleanup()

  stubFetch([SETTLED])
  await mount(<App />)
  await act(async () => { vi.advanceTimersByTime(8000) })
  expect(calls.filter((c) => c.url.includes('/review/status')).length).toBe(0)
})

it('reloads the repo once when the running review finishes', async () => {
  vi.useFakeTimers()
  stubFetch([QUEUE, SETTLED], { running: false })
  const el = await mount(<App />)
  await act(async () => { vi.advanceTimersByTime(4000) })
  await flush()
  expect(calls.filter((c) => c.url.endsWith('/demo/app')).length).toBe(2)
  expect(sectionOf(el, 7)).toBe('not_scored') // reviewed, but no stored record yet
})

it('moves a row to Running when Review is clicked', async () => {
  stubFetch([QUEUE])
  const el = await mount(<App />)
  const row = Array.from(el.querySelectorAll('.row'))
    .find((r) => r.textContent?.includes('#6')) as HTMLElement
  const button = Array.from(row.querySelectorAll('button'))
    .find((b) => b.textContent === 'Review now') as HTMLButtonElement
  await act(async () => { button.click() })
  await flush()
  expect(calls.some((c) => c.method === 'POST' && c.url.includes('/pr/6/review'))).toBe(true)
  expect(sectionOf(el, 6)).toBe('running')
})

it('starts a reply review from a row with open questions', async () => {
  stubFetch([QUEUE])
  const el = await mount(<App />)
  const row = Array.from(el.querySelectorAll('.row'))
    .find((r) => r.textContent?.includes('#3')) as HTMLElement
  const button = Array.from(row.querySelectorAll('button'))
    .find((b) => b.textContent === 'Answer replies') as HTMLButtonElement
  await act(async () => { button.click() })
  await flush()
  expect(calls.some((c) => c.method === 'POST' && c.url.includes('/pr/3/review?reply=true')))
    .toBe(true)
})

it('filters rows by gate', async () => {
  stubFetch([QUEUE])
  const el = await mount(<App />)
  const chip = Array.from(el.querySelectorAll('button'))
    .find((b) => b.getAttribute('data-gate-filter') === 'fail') as HTMLButtonElement
  await act(async () => { chip.click() })
  const rows = Array.from(el.querySelectorAll('.row')).map((r) => r.textContent ?? '')
  expect(rows.some((r) => r.includes('#5'))).toBe(true)
  expect(rows.some((r) => r.includes('#4'))).toBe(false)
  expect(rows.some((r) => r.includes('#6'))).toBe(false)
})
