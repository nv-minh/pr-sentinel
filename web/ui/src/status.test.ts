import { describe, expect, it } from 'vitest'
import { bandSegments, formatCost, formatScore, toneOf } from './status'
import { parse } from './router'

describe('toneOf', () => {
  it('maps every finding vocabulary to a tone', () => {
    expect(toneOf('PASS')).toBe('pass')
    expect(toneOf('FABRICATED')).toBe('fail')
    expect(toneOf('BREAKING_API_CHANGE')).toBe('fail')
    expect(toneOf('NEEDS_UPDATE')).toBe('warn')
    expect(toneOf('WEAK')).toBe('warn')
    expect(toneOf('STRONG')).toBe('pass')
  })

  it('falls back to unknown for anything unrecognised', () => {
    expect(toneOf('')).toBe('unknown')
    expect(toneOf(undefined)).toBe('unknown')
    expect(toneOf('BANANA')).toBe('unknown')
  })
})

describe('bandSegments', () => {
  it('keeps a fixed order so the band never repaints', () => {
    const segs = bandSegments({ fail: 1, pass: 2, warn: 1 })
    expect(segs.map((s) => s.key)).toEqual(['pass', 'warn', 'fail'])
    expect(segs[0].share).toBeCloseTo(0.5)
  })

  it('drops empty buckets and handles no data', () => {
    expect(bandSegments({ pass: 3, warn: 0 }).map((s) => s.key)).toEqual(['pass'])
    expect(bandSegments({})).toEqual([])
    expect(bandSegments(undefined)).toEqual([])
  })
})

describe('formatting', () => {
  it('renders scores as whole percentages and unknowns as a dash', () => {
    expect(formatScore(0.833)).toBe('83%')
    expect(formatScore(1)).toBe('100%')
    expect(formatScore(null)).toBe('—')
  })

  it('keeps small costs readable', () => {
    expect(formatCost(0)).toBe('$0')
    expect(formatCost(0.0042)).toBe('$0.0042')
    expect(formatCost(1.5)).toBe('$1.50')
  })
})

describe('router', () => {
  it('parses every dashboard path', () => {
    expect(parse('/')).toEqual({ name: 'repos' })
    expect(parse('/config')).toEqual({ name: 'config' })
    expect(parse('/repos/demo/app')).toEqual({ name: 'repo', owner: 'demo', repo: 'app' })
    expect(parse('/repos/demo/app/pr/7')).toEqual({
      name: 'pr', owner: 'demo', repo: 'app', pr: 7,
    })
  })

  it('falls back to the repo list for nonsense paths', () => {
    expect(parse('/repos/demo/app/pr/abc')).toEqual({
      name: 'repo', owner: 'demo', repo: 'app',
    })
    expect(parse('/nope')).toEqual({ name: 'repos' })
  })
})
