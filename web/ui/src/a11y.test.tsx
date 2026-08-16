// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

let container: HTMLDivElement
let root: Root

async function render(path: string) {
  window.history.pushState({}, '', path)
  container = document.createElement('div')
  document.body.appendChild(container)
  await act(async () => {
    root = createRoot(container)
    root.render(<App />)
  })
  await act(async () => { await Promise.resolve() })
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ repos: [] }) })))
  vi.stubGlobal('matchMedia', () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
  }))
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  vi.unstubAllGlobals()
})

describe('accessibility basics', () => {
  it('gives every button an accessible name', async () => {
    await render('/')
    const unnamed = Array.from(container.querySelectorAll('button')).filter(
      (b) => !(b.textContent ?? '').trim() && !b.getAttribute('aria-label'))
    expect(unnamed).toEqual([])
  })

  it('exposes exactly one h1 per page', async () => {
    await render('/')
    expect(container.querySelectorAll('h1')).toHaveLength(1)
  })

  it('sets the theme attribute on the document element', async () => {
    await render('/')
    expect(['light', 'dark']).toContain(document.documentElement.dataset.theme)
  })
})
