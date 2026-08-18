// @vitest-environment jsdom
// Management behaviors of the repos home: mode switch, remove-with-confirm,
// add, search, watched state. Route-level content lives in App.test.tsx.
import { act } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { App } from '../App'
import { setLang } from '../i18n'
import { cleanup, flush, mount, setupTestEnv } from '../test/harness'

const CARD = {
  owner: 'demo', repo: 'app', prs_total: 2, bugs_total: 6, doc_errors_total: 3,
  breaking_total: 1, test_gaps_total: 2, cost_total: 0.62,
  avg_verification_score: 0.5, has_data: true, mode: 'auto',
  verdict_count: { ACCURATE: 0, PARTIAL: 1, MISLEADING: 1, NO_CLAIMS: 0 },
  gate_count: { pass: 0, warn: 1, fail: 1, unknown: 0 },
  prs: [], open_prs: [], open_questions: 1,
}
const OTHER = { ...CARD, owner: 'acme', repo: 'api', mode: 'manual' }
const WATCHED = {
  owner: 'demo', repo: 'later', prs_total: 0, bugs_total: 0, doc_errors_total: 0,
  breaking_total: 0, test_gaps_total: 0, cost_total: 0, has_data: false, mode: 'auto',
}

let calls: Array<{ url: string; method: string; body: string }>

function stubFetch(repos: unknown[]) {
  calls = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), method: init?.method ?? 'GET',
                 body: String(init?.body ?? '') })
    return { ok: true, json: async () => ({ repos, ok: true }) } as Response
  }))
}

beforeEach(() => {
  setupTestEnv()
  window.history.pushState({}, '', '/')
})
afterEach(() => {
  act(() => setLang('en'))
  cleanup()
})

it('switches a repo mode from the card', async () => {
  stubFetch([CARD])
  const el = await mount(<App />)
  const toggle = el.querySelector('[aria-label="Mode for demo/app"]') as HTMLButtonElement
  expect(toggle.textContent).toContain('auto')
  await act(async () => { toggle.click() })
  await flush()
  const post = calls.find((c) => c.url === '/api/config/repos/demo%2Fapp/mode')
  expect(post?.method).toBe('POST')
  expect(post?.body).toContain('"manual"')
  // and the list is refetched
  expect(calls.filter((c) => c.url === '/api/repos').length).toBeGreaterThan(1)
})

it('removes a repo only after the confirm step', async () => {
  stubFetch([CARD])
  const el = await mount(<App />)
  const remove = el.querySelector('[aria-label="Remove demo/app"]') as HTMLButtonElement
  await act(async () => { remove.click() })
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
  await act(async () => { remove.click() })
  await flush()
  const del = calls.find((c) => c.method === 'DELETE')
  expect(del?.url).toBe('/api/config/repos/demo%2Fapp')
})

it('adds a repo from the home page', async () => {
  stubFetch([])
  const el = await mount(<App />)
  const input = el.querySelector('input[name="add-repo"]') as HTMLInputElement
  const native = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value')!.set!
  await act(async () => {
    native.call(input, 'acme/api')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  const button = Array.from(el.querySelectorAll('button'))
    .find((b) => b.textContent === 'Watch repo') as HTMLButtonElement
  await act(async () => { button.click() })
  await flush()
  const post = calls.find((c) => c.url === '/api/config/repos')
  expect(post?.method).toBe('POST')
  expect(post?.body).toContain('acme/api')
})

it('filters the card grid by search text', async () => {
  stubFetch([CARD, OTHER])
  const el = await mount(<App />)
  expect(el.querySelectorAll('a[href^="/repos/"]').length).toBe(2)
  const search = el.querySelector('input[type="search"]') as HTMLInputElement
  const native = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value')!.set!
  await act(async () => {
    native.call(search, 'acme')
    search.dispatchEvent(new Event('input', { bubbles: true }))
  })
  const links = Array.from(el.querySelectorAll('a[href^="/repos/"]'))
  expect(links.length).toBe(1)
  expect(links[0].getAttribute('href')).toBe('/repos/acme/api')
})

it('shows a watched repo as watched, not zeroed', async () => {
  stubFetch([WATCHED])
  const el = await mount(<App />)
  expect(el.textContent).toContain('Watched')
  expect(el.querySelectorAll('.band-seg').length).toBe(0)
  expect(el.textContent).not.toContain('0% verified')
})
