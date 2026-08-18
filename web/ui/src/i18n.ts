import { useCallback, useSyncExternalStore } from 'react'
import { TABLES, lookup, type Key, type Vars } from './strings'

export type Lang = 'en' | 'vi'

const KEY = 'pr-sentinel-lang'

function detect(): Lang {
  const stored = localStorage.getItem(KEY)
  if (stored === 'en' || stored === 'vi') return stored
  return navigator.language?.startsWith('vi') ? 'vi' : 'en'
}

// Module-level store, for the reason theme.ts:13-17 records: with a useState
// per caller, the header would switch language and the pages would not.
let lang: Lang | null = null
const listeners = new Set<() => void>()

function write(next: Lang) {
  // The counterpart to theme.ts writing <html data-theme>. Not bookkeeping: a
  // screen reader announcing Vietnamese under lang="en" mispronounces it.
  document.documentElement.lang = next
  localStorage.setItem(KEY, next)
}

function ensureInitialized(): Lang {
  if (lang === null) {
    lang = detect()
    write(lang)
  }
  return lang
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot(): Lang {
  return ensureInitialized()
}

/** Substitutes {name} placeholders. A placeholder with no matching variable is
 *  left as written rather than becoming "undefined" — a visible `{n}` is a bug
 *  report; the word "undefined" in the middle of a sentence is a mystery. */
export function translate(target: Lang, key: Key, vars?: Vars): string {
  const raw = TABLES[target][key]
  if (!vars) return raw
  return raw.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match)
}

/** Sets the current language. A standalone function rather than something
 *  only reachable through the hook, so tests can reset the module-level store
 *  from an `afterEach` without mounting a component. */
export function setLang(next: Lang) {
  lang = next
  write(next)
  listeners.forEach((listener) => listener())
}

/** The current language, and a setter. A setter rather than a toggle: a
 *  language is not binary, and a toggle would have to be rewritten the first
 *  time a third one is added. */
export function useLang(): [Lang, (next: Lang) => void] {
  return [useSyncExternalStore(subscribe, getSnapshot), setLang]
}

/** The translator, bound to the current language and re-created when it
 *  changes, so every component calling it re-renders on a switch. */
export function useT(): (key: Key, vars?: Vars) => string {
  const value = useSyncExternalStore(subscribe, getSnapshot)
  return useCallback((key: Key, vars?: Vars) => translate(value, key, vars), [value])
}

/** For server-supplied labels, which are looked up by a runtime string and
 *  fall back to what the server sent. See strings.ts `lookup`. */
export function useLookup(): (key: string, fallback: string) => string {
  const value = useSyncExternalStore(subscribe, getSnapshot)
  return useCallback((key: string, fallback: string) =>
    lookup(value, key, fallback), [value])
}
