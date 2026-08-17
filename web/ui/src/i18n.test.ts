// @vitest-environment jsdom
import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { translate } from './i18n'

// i18n.ts holds `lang` in module scope, on purpose — same reason as
// theme.ts: one shared source of truth for every caller. That is correct for
// the running app, but Vitest isolates modules per *file*, not per `it()`:
// a static `import { useLang, useT } from './i18n'` at the top of this file
// would hand every test the same long-lived module instance, so language
// changes (and even the one-time detect() call) made by an earlier test
// would leak into the next one's "before anything happens" assertions.
// `translate` is pure — it takes `target: Lang` explicitly and never reads
// the module's mutable `lang` — so it is unaffected and stays a static
// import. `useLang`/`useT`, which do read that state, are re-imported fresh
// after `vi.resetModules()` in `beforeEach` so each test starts cold.
type I18nModule = typeof import('./i18n')
let i18n: I18nModule

function Reader({ id }: { id: string }) {
  const [lang] = i18n.useLang()
  return createElement('span', { 'data-testid': id }, lang)
}

function Greeter() {
  const t = i18n.useT()
  return createElement('span', { 'data-testid': 'greeting' }, t('nav.repos'))
}

function Switcher() {
  const [lang, setLang] = i18n.useLang()
  return createElement('button', {
    type: 'button',
    onClick: () => setLang(lang === 'vi' ? 'en' : 'vi'),
  }, 'switch')
}

let container: HTMLDivElement
let root: Root

beforeEach(async () => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
  document.documentElement.removeAttribute('lang')
  vi.stubGlobal('navigator', { language: 'en-US' })
  vi.resetModules()
  i18n = await import('./i18n')
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  vi.unstubAllGlobals()
})

function render(node: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  act(() => {
    root = createRoot(container)
    root.render(node)
  })
}

describe('translate', () => {
  it('returns the string for the requested language', () => {
    expect(translate('en', 'nav.repos')).toBe('Repos')
    expect(translate('vi', 'nav.repos')).toBe('Kho mã')
  })

  it('substitutes every occurrence of a named variable', () => {
    expect(translate('en', 'repos.bugs', { n: 6 })).toBe('6 bugs')
  })

  it('returns the raw string unchanged when no vars object is given at all', () => {
    expect(translate('en', 'repos.bugs')).toBe('{n} bugs')
  })

  it('leaves an unsupplied placeholder in place rather than printing undefined', () => {
    // A vars object that IS present, so this reaches the replace() callback's
    // `name in vars ? ... : match` guard — unlike the no-vars case above,
    // which returns before that callback ever runs.
    expect(translate('en', 'repos.bugs', {})).toBe('{n} bugs')
  })
})

describe('useLang', () => {
  it('is one shared source of truth: switching in one caller is observed by another', () => {
    render(createElement('div', null,
      createElement(Switcher),
      createElement(Reader, { id: 'a' }),
      createElement(Reader, { id: 'b' })))
    const readerA = () => container.querySelector('[data-testid="a"]')!.textContent
    const readerB = () => container.querySelector('[data-testid="b"]')!.textContent

    expect(readerA()).toBe('en')
    expect(readerB()).toBe('en')

    act(() => { (container.querySelector('button') as HTMLButtonElement).click() })

    expect(readerA()).toBe('vi')
    expect(readerB()).toBe('vi')
  })

  it('re-renders translated text when the language changes', () => {
    render(createElement('div', null,
      createElement(Switcher),
      createElement(Greeter)))
    const greeting = () => container.querySelector('[data-testid="greeting"]')!.textContent

    expect(greeting()).toBe('Repos')
    act(() => { (container.querySelector('button') as HTMLButtonElement).click() })
    expect(greeting()).toBe('Kho mã')
  })

  it('writes the choice to <html lang> and localStorage', () => {
    render(createElement('div', null, createElement(Switcher)))
    expect(document.documentElement.lang).toBe('en')

    act(() => { (container.querySelector('button') as HTMLButtonElement).click() })

    expect(document.documentElement.lang).toBe('vi')
    expect(localStorage.getItem('pr-sentinel-lang')).toBe('vi')
  })

  it('defaults to Vietnamese for a Vietnamese browser and English otherwise', () => {
    vi.stubGlobal('navigator', { language: 'vi-VN' })
    render(createElement('div', null, createElement(Reader, { id: 'a' })))
    expect(container.querySelector('[data-testid="a"]')!.textContent).toBe('vi')
  })
})
