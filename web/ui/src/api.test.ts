// @vitest-environment jsdom
import { afterEach, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => vi.unstubAllGlobals())

function stubFetch() {
  const calls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    calls.push(String(input))
    return { ok: true, json: async () => ({}) } as Response
  }))
  return calls
}

it('workspace endpoints hit their documented paths', async () => {
  const calls = stubFetch()
  await api.prFiles('o', 'r', 5)
  await api.prFile('o', 'r', 5, 'src/a b.py', 2, 9)
  await api.prExtras('o', 'r', 5)
  await api.prTrace('o', 'r', 5)
  expect(calls).toEqual([
    '/api/repos/o/r/pr/5/files',
    '/api/repos/o/r/pr/5/file?path=src%2Fa%20b.py&start=2&end=9',
    '/api/repos/o/r/pr/5/extras',
    '/api/repos/o/r/pr/5/trace',
  ])
})

it('every method forwards an abort signal', async () => {
  const seen: Array<AbortSignal | undefined> = []
  vi.stubGlobal('fetch', vi.fn(async (_: RequestInfo | URL, init?: RequestInit) => {
    seen.push(init?.signal ?? undefined)
    return { ok: true, json: async () => ({ repos: [] }) } as Response
  }))
  const ctrl = new AbortController()
  await api.repos(ctrl.signal)
  await api.prFiles('o', 'r', 5, ctrl.signal)
  expect(seen.every((s) => s === ctrl.signal)).toBe(true)
})
