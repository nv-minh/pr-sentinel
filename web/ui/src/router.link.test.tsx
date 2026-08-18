// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it } from 'vitest'
import { cleanup, mount, setupTestEnv } from './test/harness'
import { Link } from './router'

beforeEach(() => {
  setupTestEnv()
  window.history.replaceState({}, '', '/')
})
afterEach(cleanup)

it('Link renders a real href and navigates on a plain click', async () => {
  const el = await mount(<Link to="/repos/demo/app" query={{ q: 'x' }}>open</Link>)
  const a = el.querySelector('a') as HTMLAnchorElement
  expect(a.getAttribute('href')).toBe('/repos/demo/app?q=x')
  a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  expect(window.location.pathname).toBe('/repos/demo/app')
})

it('Link leaves modified clicks to the browser', async () => {
  const el = await mount(<Link to="/repos/demo/app">open</Link>)
  const a = el.querySelector('a') as HTMLAnchorElement
  a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, metaKey: true }))
  expect(window.location.pathname).toBe('/')
})
