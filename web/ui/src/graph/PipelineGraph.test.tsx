// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PipelineGraph from './PipelineGraph'
import type { Pipeline } from '../api'

const PIPELINE: Pipeline = {
  running: false,
  edges: [
    { source: 'snapshot', target: 'claims' },
    { source: 'claims', target: 'verify' },
  ],
  nodes: [
    { id: 'snapshot', label: 'Snapshot', status: 'done', artifact: 'snapshot.json',
      cost_usd: null, duration_ms: null, model: '',
      metrics: [{ label: 'files', value: 3 }] },
    { id: 'claims', label: 'Claims', status: 'done', artifact: 'claims.json',
      cost_usd: 0.01, duration_ms: 2000, model: 'claude-haiku-4-5-20251001',
      metrics: [{ label: 'claims', value: 2 }] },
    { id: 'verify', label: 'Verify', status: 'running', artifact: 'findings.json',
      cost_usd: null, duration_ms: null, model: '', metrics: [] },
  ],
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  // React Flow measures its container; jsdom reports zeroes without this.
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    unobserve() {}
    disconnect() {}
  })
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

describe('PipelineGraph', () => {
  it('mirrors every phase in a text equivalent for screen readers', () => {
    render(<PipelineGraph pipeline={PIPELINE} selected={null} onSelect={() => {}} />)
    const list = container.querySelector('[data-testid="pipeline-text"]')!
    expect(list.textContent).toContain('Snapshot')
    expect(list.textContent).toContain('done')
    expect(list.textContent).toContain('Verify')
    expect(list.textContent).toContain('running')
  })

  it('lets the text equivalent select a phase, so the graph is not the only way in', () => {
    const picked: string[] = []
    render(<PipelineGraph pipeline={PIPELINE} selected={null}
                          onSelect={(id) => picked.push(id)} />)
    const button = container.querySelector('[data-phase="claims"]') as HTMLButtonElement
    act(() => { button.click() })
    expect(picked).toEqual(['claims'])
  })
})
