// @vitest-environment jsdom
import { beforeEach, expect, it } from 'vitest'
import { loadViewed, saveViewed } from './viewed'

beforeEach(() => localStorage.clear())

it('persists viewed files per PR', () => {
  saveViewed('demo', 'app', 8, 'h1', new Set(['a.py', 'b.py']))
  expect(loadViewed('demo', 'app', 8, 'h1')).toEqual(new Set(['a.py', 'b.py']))
})

it('resets when the head sha changes — old marks are stale', () => {
  saveViewed('demo', 'app', 8, 'h1', new Set(['a.py']))
  expect(loadViewed('demo', 'app', 8, 'h2')).toEqual(new Set())
})

it('is empty for an unknown PR and survives garbage', () => {
  expect(loadViewed('demo', 'app', 9, 'h1')).toEqual(new Set())
  localStorage.setItem('pr-sentinel-viewed:demo/app/9', 'not json')
  expect(loadViewed('demo', 'app', 9, 'h1')).toEqual(new Set())
})
