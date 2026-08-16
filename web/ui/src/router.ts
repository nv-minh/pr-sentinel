import { useEffect, useState } from 'react'

export type Route =
  | { name: 'repos' }
  | { name: 'config' }
  | { name: 'repo'; owner: string; repo: string }
  | { name: 'pr'; owner: string; repo: string; pr: number }

export function parse(pathname: string): Route {
  const parts = pathname.split('/').filter(Boolean)
  if (parts[0] === 'config') return { name: 'config' }
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

export function navigate(path: string): void {
  window.history.pushState({}, '', path)
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
