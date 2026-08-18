// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest'
import { buildPath, navigate, parseQuery, setQuery } from './router'

beforeEach(() => {
  window.history.replaceState({}, '', '/')
})

describe('query helpers', () => {
  it('parses and serialises query params round-trip', () => {
    const path = buildPath('/repos/demo/app', { q: 'auth review', sort: 'spend' })
    const [, search] = path.split('?')
    expect(parseQuery('?' + search)).toEqual({ q: 'auth review', sort: 'spend' })
  })

  it('buildPath omits empty values and the bare question mark', () => {
    expect(buildPath('/x', { q: '', sort: 'name' })).toBe('/x?sort=name')
    expect(buildPath('/x', {})).toBe('/x')
    expect(buildPath('/x')).toBe('/x')
  })

  it('setQuery merges, deletes null keys, and uses replaceState by default', () => {
    window.history.replaceState({}, '', '/repos/demo/app?q=a&sort=spend')
    const before = window.history.length
    setQuery({ q: 'b', sort: null })
    expect(window.location.search).toBe('?q=b')
    expect(window.history.length).toBe(before)
  })

  it('setQuery can push a history entry when asked', () => {
    window.history.replaceState({}, '', '/x')
    setQuery({ finding: 'claim-0' }, { replace: false })
    expect(window.location.search).toBe('?finding=claim-0')
  })

  it('navigate accepts a query object', () => {
    navigate('/repos/demo/app', { q: 'auth' })
    expect(window.location.pathname).toBe('/repos/demo/app')
    expect(window.location.search).toBe('?q=auth')
  })
})
