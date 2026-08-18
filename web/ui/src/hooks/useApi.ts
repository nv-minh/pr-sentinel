// The one data-fetch mechanism for pages: fetch-in-effect with abort on
// unmount, a stale-response guard, and a poll variant that stops when idle.
// Deliberately not TanStack Query — 13 endpoints and two poll sites don't
// justify a dependency (same reasoning as the hand-rolled router).
import { useCallback, useEffect, useRef, useState } from 'react'
import type { DependencyList } from 'react'

export interface ApiState<T> {
  /** Last successful payload; kept during refetches so the UI never flashes. */
  data: T | null
  /** '' when none. */
  error: string
  /** True only while the first request for the current deps is in flight. */
  loading: boolean
  refetch: () => void
}

export function useApi<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [bump, setBump] = useState(0)
  const run = useRef(0)

  // Route params changed → the old page's data must not linger; a refetch
  // (bump) keeps it so the page updates in place.
  useEffect(() => {
    setData(null)
    setLoading(true)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    const id = ++run.current
    const controller = new AbortController()
    fetcher(controller.signal).then(
      (value) => {
        if (controller.signal.aborted || id !== run.current) return
        setData(value)
        setError('')
        setLoading(false)
      },
      (e: unknown) => {
        if (controller.signal.aborted || id !== run.current) return
        setError(e instanceof Error ? e.message : String(e))
        setLoading(false)
      },
    )
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, bump])

  const refetch = useCallback(() => setBump((b) => b + 1), [])
  return { data, error, loading, refetch }
}

/** Chained-timeout poll: an immediate fetch when `active` flips true, the
 * next tick scheduled only after the previous settles (no overlap), errors
 * recorded but never fatal, and a full stop — timer cleared, request
 * aborted — the moment `active` is false or the component unmounts. */
export function usePoll<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
  active: boolean,
): { data: T | null; error: string } {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!active) return
    let timer: ReturnType<typeof setTimeout> | undefined
    let controller: AbortController | undefined
    let stopped = false

    const tick = async () => {
      controller = new AbortController()
      try {
        const value = await fetcher(controller.signal)
        if (!stopped && !controller.signal.aborted) {
          setData(value)
          setError('')
        }
      } catch (e) {
        if (!stopped && !controller.signal.aborted) {
          setError(e instanceof Error ? e.message : String(e))
        }
      }
      if (!stopped) timer = setTimeout(tick, intervalMs)
    }
    void tick()

    return () => {
      stopped = true
      if (timer !== undefined) clearTimeout(timer)
      controller?.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, intervalMs])

  return { data, error }
}
