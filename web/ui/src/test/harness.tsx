// Shared jsdom test harness — the createRoot/act pattern the older suites
// hand-roll per file (App.test.tsx, a11y.test.tsx), extracted for new tests.
// Old suites keep their local copies untouched; new tests import from here.
import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { vi } from 'vitest'

let container: HTMLDivElement | null = null
let root: Root | null = null

/** Call from beforeEach: act flag + the DOM stubs jsdom is missing. */
export function setupTestEnv() {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  vi.stubGlobal('matchMedia', () => ({
    matches: false, addEventListener() {}, removeEventListener() {},
  }))
  if (!Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = () => {}
  }
}

/** Mount a node and settle the first effects. Returns the container. */
export async function mount(node: ReactNode): Promise<HTMLDivElement> {
  container = document.createElement('div')
  document.body.appendChild(container)
  await act(async () => {
    root = createRoot(container as HTMLDivElement)
    root.render(node)
  })
  await flush()
  return container
}

/** Let queued microtasks, lazy chunks and re-renders settle. */
export async function flush(turns = 5) {
  await vi.dynamicImportSettled()
  for (let i = 0; i < turns; i++) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

/** Call from afterEach. */
export function cleanup() {
  act(() => root?.unmount())
  container?.remove()
  container = null
  root = null
  vi.unstubAllGlobals()
}
