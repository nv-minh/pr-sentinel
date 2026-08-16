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
    expect(list.querySelectorAll('[data-phase]')).toHaveLength(PIPELINE.nodes.length)
    expect(list.textContent).toContain('Snapshot')
    expect(list.textContent).toContain('done')
    expect(list.textContent).toContain('Claims')
    expect(list.textContent).toContain('Verify')
    expect(list.textContent).toContain('running')
  })

  it('renders a status glyph alongside the word in the text equivalent, not colour alone', () => {
    render(<PipelineGraph pipeline={PIPELINE} selected={null} onSelect={() => {}} />)
    const list = container.querySelector('[data-testid="pipeline-text"]')!
    // 'done' -> tone 'pass' -> glyph '✓'; 'running' -> tone 'warn' -> glyph '!'
    expect(list.textContent).toContain('✓')
    expect(list.textContent).toContain('!')
    // the words must still be present and intact alongside the glyphs
    expect(list.textContent).toContain('done')
    expect(list.textContent).toContain('running')
  })

  it('keeps the canvas free of focusable elements while it is aria-hidden', () => {
    render(<PipelineGraph pipeline={PIPELINE} selected={null} onSelect={() => {}} />)
    const hidden = container.querySelector('[aria-hidden="true"]')!
    // Covers every natively- or explicitly-focusable tag/attribute combo, not
    // just [tabindex="0"] and <button> — React Flow's attribution anchor
    // (<a href>) is real and stays in the DOM for licence reasons, so this
    // must also exclude anything explicitly opted out via tabindex="-1"
    // (which is exactly what PipelineGraph.tsx does for that anchor).
    // Without the wider selector, the next focusable element of a different
    // tag (an <a>, an <input>, ...) would slip through unnoticed, just like
    // the attribution link did.
    const candidates = hidden.querySelectorAll(
      '[tabindex="0"], button, a[href], input, select, textarea, [contenteditable]',
    )
    const focusable = Array.from(candidates).filter((el) => el.getAttribute('tabindex') !== '-1')
    expect(focusable).toHaveLength(0)
    // Regression: <MiniMap> was removed because it occluded two phase nodes.
    // Re-adding it should fail this test rather than slip back in silently.
    expect(container.querySelector('.react-flow__minimap')).toBeNull()
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
