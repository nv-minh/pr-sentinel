// @vitest-environment jsdom
import { act } from 'react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, flush, mount, setupTestEnv } from '../test/harness'
import { useApi, usePoll } from './useApi'

beforeEach(() => setupTestEnv())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

function ApiProbe({ fetcher, dep = 0 }: {
  fetcher: (signal: AbortSignal) => Promise<string>
  dep?: number
}) {
  const { data, error, loading, refetch } = useApi(fetcher, [dep])
  return (
    <div>
      <span data-testid="data">{data ?? ''}</span>
      <span data-testid="error">{error}</span>
      <span data-testid="loading">{String(loading)}</span>
      <button type="button" onClick={refetch}>refetch</button>
    </div>
  )
}

it('useApi loads data and clears loading', async () => {
  const el = await mount(<ApiProbe fetcher={async () => 'hello'} />)
  expect(el.querySelector('[data-testid="data"]')?.textContent).toBe('hello')
  expect(el.querySelector('[data-testid="loading"]')?.textContent).toBe('false')
})

it('useApi aborts the in-flight request on unmount', async () => {
  let seen: AbortSignal | null = null
  const el = await mount(
    <ApiProbe fetcher={(signal) => { seen = signal; return new Promise(() => {}) }} />,
  )
  expect(el).toBeTruthy()
  cleanup()
  expect(seen && (seen as AbortSignal).aborted).toBe(true)
})

it('useApi ignores a stale response after a refetch', async () => {
  const resolvers: Array<(v: string) => void> = []
  const fetcher = () => new Promise<string>((r) => resolvers.push(r))
  const el = await mount(<ApiProbe fetcher={fetcher} />)
  ;(el.querySelector('button') as HTMLButtonElement).click()
  await flush()
  expect(resolvers.length).toBe(2)
  await act(async () => { resolvers[1]('fresh') })
  await act(async () => { resolvers[0]('stale') })
  await flush()
  expect(el.querySelector('[data-testid="data"]')?.textContent).toBe('fresh')
})

it('useApi reports the error message and recovers on refetch', async () => {
  let fail = true
  const fetcher = async () => {
    if (fail) throw new Error('boom')
    return 'ok'
  }
  const el = await mount(<ApiProbe fetcher={fetcher} />)
  expect(el.querySelector('[data-testid="error"]')?.textContent).toBe('boom')
  fail = false
  await act(async () => { (el.querySelector('button') as HTMLButtonElement).click() })
  await flush()
  expect(el.querySelector('[data-testid="data"]')?.textContent).toBe('ok')
  expect(el.querySelector('[data-testid="error"]')?.textContent).toBe('')
})

function PollProbe({ fetcher, active }: {
  fetcher: (signal: AbortSignal) => Promise<string>
  active: boolean
}) {
  const { data } = usePoll(fetcher, 3000, active)
  return <span data-testid="data">{data ?? ''}</span>
}

it('usePoll polls only while active', async () => {
  vi.useFakeTimers()
  const calls = vi.fn(async () => 'tick')
  await mount(<PollProbe fetcher={calls} active={false} />)
  await act(async () => { vi.advanceTimersByTime(10_000) })
  expect(calls).not.toHaveBeenCalled()
  cleanup()

  const el2 = await mount(<PollProbe fetcher={calls} active={true} />)
  await act(async () => {})
  expect(calls).toHaveBeenCalledTimes(1)
  await act(async () => { vi.advanceTimersByTime(3000) })
  await act(async () => {})
  expect(calls).toHaveBeenCalledTimes(2)
  expect(el2.querySelector('[data-testid="data"]')?.textContent).toBe('tick')
})

it('usePoll survives a failing tick and keeps polling', async () => {
  vi.useFakeTimers()
  let n = 0
  const fetcher = async () => {
    n++
    if (n === 1) throw new Error('flaky')
    return 'recovered'
  }
  const el = await mount(<PollProbe fetcher={fetcher} active={true} />)
  await act(async () => {})
  await act(async () => { vi.advanceTimersByTime(3000) })
  await act(async () => {})
  expect(n).toBe(2)
  expect(el.querySelector('[data-testid="data"]')?.textContent).toBe('recovered')
})
