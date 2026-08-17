// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { Empty, ErrorNotice, GateBand, Loading, Row, StatusWord, Tile } from './components'
import { useLang } from './i18n'

let container: HTMLDivElement
let root: Root

function render(node: React.ReactNode) {
  container = document.createElement('div')
  document.body.appendChild(container)
  act(() => {
    root = createRoot(container)
    root.render(node)
  })
}

// Drives the real store the way the header does, rather than reaching into
// the module — the test stays blind to how the store is implemented.
function LangSwitcher() {
  const [, setLang] = useLang()
  return (
    <>
      <button type="button" data-testid="to-vi" onClick={() => setLang('vi')}>vi</button>
      <button type="button" data-testid="to-en" onClick={() => setLang('en')}>en</button>
    </>
  )
}

beforeEach(() => {
  ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true
  localStorage.clear()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
})

describe('primitives', () => {
  it('renders a status as glyph and word, never colour alone', () => {
    render(<StatusWord status="FAIL" />)
    expect(container.textContent).toContain('FAIL')
  })

  it('marks an unknown status rather than dropping it', () => {
    render(<StatusWord status="" />)
    expect(container.textContent).toContain('UNKNOWN')
  })

  it('keeps the band-seg hook and one segment per non-empty bucket', () => {
    render(<GateBand counts={{ pass: 2, warn: 0, fail: 1, unknown: 0 }} />)
    expect(container.querySelectorAll('.band-seg')).toHaveLength(2)
    expect(container.textContent).toContain('Clear to merge')
    const wrapper = container.querySelector('[role="img"]') as HTMLElement
    expect(wrapper).not.toBeNull()
    expect(wrapper.getAttribute('aria-label')).toBe('2 Clear to merge, 1 Blocked')
  })

  it('says so when there is nothing to band', () => {
    render(<GateBand counts={undefined} />)
    expect(container.textContent).toContain('No scored reviews yet')
  })

  it('translates the gate legend without translating the status vocabulary', () => {
    render(
      <>
        <LangSwitcher />
        <GateBand counts={{ pass: 2, fail: 1 }} />
      </>,
    )
    expect(container.textContent).toContain('Clear to merge')

    act(() => { (container.querySelector('[data-testid="to-vi"]') as HTMLButtonElement).click() })

    expect(container.textContent).toContain('Sẵn sàng merge')
    expect(container.textContent).toContain('Bị chặn')
    expect(container.textContent).not.toContain('Clear to merge')
    // The glyphs carry the reading when colour cannot; they are not words.
    expect(container.textContent).toContain('✓')

    // Switch back inside the test: the store is module-level, so leaving it on
    // 'vi' would hand the next test in this file a Vietnamese GateBand and
    // break the exact aria-label assertion at :45.
    act(() => { (container.querySelector('[data-testid="to-en"]') as HTMLButtonElement).click() })
    expect(container.textContent).toContain('Clear to merge')
  })

  it('keeps a row clickable by keyboard', () => {
    let hits = 0
    render(<Row status="PASS" title="t" onClick={() => { hits += 1 }} />)
    const row = container.querySelector('.row') as HTMLElement
    expect(row.getAttribute('role')).toBe('button')
    expect(row.getAttribute('tabindex')).toBe('0')
    act(() => { row.click() })
    expect(hits).toBe(1)
  })

  it('activates a row on keyboard Enter and Space, not just click', () => {
    let hits = 0
    render(<Row status="PASS" title="t" onClick={() => { hits += 1 }} />)
    const row = container.querySelector('.row') as HTMLElement
    act(() => {
      row.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    })
    expect(hits).toBe(1)
    act(() => {
      row.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }))
    })
    expect(hits).toBe(2)
  })

  it('does not let a nested control\'s keyboard activation bubble into the row\'s onClick', () => {
    let hits = 0
    render(
      <Row status="PASS" title="t" onClick={() => { hits += 1 }}
           right={<button type="button">Review now</button>} />,
    )
    const inner = container.querySelector('button') as HTMLButtonElement
    act(() => {
      inner.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }))
    })
    expect(hits).toBe(0)
    // the row itself must still activate on its own keydown — the guard
    // must not silently disable row activation altogether.
    const row = container.querySelector('.row') as HTMLElement
    act(() => {
      row.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }))
    })
    expect(hits).toBe(1)
  })

  it('renders a tile with its label and note', () => {
    render(<Tile label="Gate" value="fail" note="Blocked" />)
    expect(container.textContent).toContain('Gate')
    expect(container.textContent).toContain('Blocked')
  })

  it('renders empty, loading and error states', () => {
    render(<><Empty>nothing here</Empty><Loading /><ErrorNotice message="boom" /></>)
    expect(container.textContent).toContain('nothing here')
    expect(container.textContent).toContain('Loading')
    expect(container.textContent).toContain('boom')
    expect(container.querySelector('[role="status"]')).not.toBeNull()
    expect(container.querySelector('[role="alert"]')).not.toBeNull()
  })
})
