// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useTheme } from './theme'

// Two independent components, each calling useTheme() on its own — exactly
// how App.tsx and PipelineGraph.tsx each call it today. This is the fixture
// that would fail against a plain useState-per-caller implementation: only
// the component that owns the toggle would ever see the new value.
function Reader({ id }: { id: string }) {
  const [theme] = useTheme()
  return <span data-testid={id}>{theme}</span>
}

function Toggler() {
  const [, toggle] = useTheme()
  return (
    <button type="button" onClick={toggle}>
      toggle
    </button>
  )
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
  delete document.documentElement.dataset.theme
  vi.stubGlobal('matchMedia', () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
  }))
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

describe('useTheme', () => {
  it('is one shared source of truth: toggling in one caller is observed by another', () => {
    render(
      <>
        <Toggler />
        <Reader id="a" />
        <Reader id="b" />
      </>,
    )
    const readerA = () => container.querySelector('[data-testid="a"]')!.textContent
    const readerB = () => container.querySelector('[data-testid="b"]')!.textContent

    // Both readers start in agreement.
    expect(readerB()).toBe(readerA())
    const before = readerA()

    const button = container.querySelector('button') as HTMLButtonElement
    act(() => { button.click() })

    // The toggle happened in a component neither reader owns — both must
    // still agree, and both must have actually changed.
    expect(readerA()).not.toBe(before)
    expect(readerB()).toBe(readerA())
  })

  it('writes the toggled value to <html data-theme> and localStorage', () => {
    render(
      <>
        <Toggler />
        <Reader id="a" />
      </>,
    )
    const before = document.documentElement.dataset.theme
    const button = container.querySelector('button') as HTMLButtonElement
    act(() => { button.click() })

    const after = document.documentElement.dataset.theme
    expect(after).not.toBe(before)
    expect(container.querySelector('[data-testid="a"]')!.textContent).toBe(after)
    expect(localStorage.getItem('pr-sentinel-theme')).toBe(after)
  })
})
