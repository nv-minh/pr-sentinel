// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it } from 'vitest'
import { cleanup, mount, setupTestEnv } from '../test/harness'
import { Markdown } from './Markdown'

beforeEach(setupTestEnv)
afterEach(cleanup)

const REPORT = `# Review PR #8 — Speed up checkout

- Author: dev2 | Base: main → Head: perf/price-cache
  - nested reason line
## Verdict: MISLEADING

| Claim | Status | Notes |
|---|---|---|
| C1 | Matches | first line<br>second line |
| C2 | **Mismatch** | uses \`price_for\` |

_Review cost: $0.3410_`

it('renders headings, bullets, tables and inline marks', async () => {
  const el = await mount(<Markdown source={REPORT} />)
  expect(el.querySelector('h2')?.textContent).toContain('Review PR #8')
  expect(el.querySelector('h3')?.textContent).toContain('Verdict: MISLEADING')
  expect(el.querySelectorAll('li').length).toBeGreaterThanOrEqual(2)
  const cells = Array.from(el.querySelectorAll('td')).map((c) => c.textContent)
  expect(cells).toContain('C1')
  // <br> inside a cell becomes a line break, not literal text
  expect(el.textContent).not.toContain('<br>')
  expect(el.textContent).toContain('second line')
  expect(el.querySelector('strong')?.textContent).toBe('Mismatch')
  expect(el.querySelector('code')?.textContent).toBe('price_for')
})

it('never injects markup — author-controlled text stays text', async () => {
  const el = await mount(
    <Markdown source={'## x\n\n**bold** <img src=x onerror=alert(1)> `code`'} />,
  )
  expect(el.querySelector('img')).toBeNull()
  expect(el.textContent).toContain('<img src=x onerror=alert(1)>')
})
