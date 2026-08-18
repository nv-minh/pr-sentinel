import { useEffect, useState, type MouseEvent, type ReactNode } from 'react'

export type Route =
  | { name: 'repos' }
  | { name: 'config' }
  | { name: 'github' }
  | { name: 'repo'; owner: string; repo: string }
  | { name: 'pr'; owner: string; repo: string; pr: number }

export type Query = Record<string, string>

export function parse(pathname: string): Route {
  const parts = pathname.split('/').filter(Boolean)
  if (parts[0] === 'config') return { name: 'config' }
  if (parts[0] === 'github') return { name: 'github' }
  if (parts[0] === 'repos' && parts.length >= 3) {
    const [, owner, repo] = parts
    if (parts[3] === 'pr' && parts[4]) {
      const pr = Number(parts[4])
      if (Number.isFinite(pr)) return { name: 'pr', owner, repo, pr }
    }
    return { name: 'repo', owner, repo }
  }
  return { name: 'repos' }
}

export function parseQuery(search: string): Query {
  const query: Query = {}
  for (const [key, value] of new URLSearchParams(search)) {
    if (value) query[key] = value
  }
  return query
}

export function buildPath(pathname: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value) params.set(key, value)
  }
  const search = params.toString()
  return search ? `${pathname}?${search}` : pathname
}

export function navigate(path: string, query?: Query): void {
  window.history.pushState({}, '', buildPath(path, query))
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** Merge a patch into the current query; null/'' deletes a key. Replaces the
 * history entry by default — filters must not spam history; pass
 * `{replace: false}` for selections the back button should undo. */
export function setQuery(patch: Record<string, string | null>,
                         opts?: { replace?: boolean }): void {
  const query = parseQuery(window.location.search)
  for (const [key, value] of Object.entries(patch)) {
    if (value) query[key] = value
    else delete query[key]
  }
  const path = buildPath(window.location.pathname, query)
  if (opts?.replace === false) window.history.pushState({}, '', path)
  else window.history.replaceState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.pathname))
  useEffect(() => {
    const update = () => setRoute(parse(window.location.pathname))
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])
  return route
}

export function useQuery(): Query {
  const [query, set] = useState(() => parseQuery(window.location.search))
  useEffect(() => {
    const update = () => set(parseQuery(window.location.search))
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])
  return query
}

/** An <a> with a real href (open-in-new-tab works) that routes plain clicks
 * through the SPA history instead of a full page load. */
export function Link({ to, query, className, children, ...rest }: {
  to: string
  query?: Query
  className?: string
  children: ReactNode
  'aria-label'?: string
  'aria-current'?: 'page' | undefined
  title?: string
}) {
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
    e.preventDefault()
    navigate(to, query)
  }
  return (
    <a href={buildPath(to, query)} className={className} onClick={onClick} {...rest}>
      {children}
    </a>
  )
}
