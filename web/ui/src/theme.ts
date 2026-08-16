import { useSyncExternalStore } from 'react'

export type Theme = 'light' | 'dark'

const KEY = 'pr-sentinel-theme'

function detect(): Theme {
  const stored = localStorage.getItem(KEY)
  if (stored === 'light' || stored === 'dark') return stored
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

// Module-level store shared by every caller of useTheme. Before this, each
// call held its own useState, so toggling the theme in one component (the
// header button) never reached another (the graph's colorMode) — the graph
// kept reading whatever value it captured at mount. There is exactly one
// `theme` here, so there is exactly one thing to be out of sync with.
let theme: Theme | null = null
const listeners = new Set<() => void>()

function write(next: Theme) {
  document.documentElement.dataset.theme = next
  localStorage.setItem(KEY, next)
}

function ensureInitialized(): Theme {
  if (theme === null) {
    theme = detect()
    write(theme)
  }
  return theme
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): Theme {
  return ensureInitialized()
}

/** The theme, and a toggle. Written to <html data-theme> so CSS and React Flow
 *  read the same source. Backed by a module-level store (read through
 *  useSyncExternalStore) rather than per-component state, so every caller
 *  observes the same value and every caller re-renders when any caller
 *  toggles it. */
export function useTheme(): [Theme, () => void] {
  const value = useSyncExternalStore(subscribe, getSnapshot)
  const toggle = () => {
    theme = value === 'dark' ? 'light' : 'dark'
    write(theme)
    listeners.forEach((listener) => listener())
  }
  return [value, toggle]
}
