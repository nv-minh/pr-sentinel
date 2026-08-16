/* Status vocabulary. Every status ships as glyph + word + color — never colour
   alone, because the amber/red pair is hard to separate for deutan vision. */

export type Tone = 'pass' | 'warn' | 'fail' | 'unknown'

export const TONE_COLOR: Record<Tone, string> = {
  pass: 'var(--pass)',
  warn: 'var(--warn)',
  fail: 'var(--fail)',
  unknown: 'var(--unknown)',
}

export const GLYPH: Record<Tone, string> = {
  pass: '✓',
  warn: '!',
  fail: '✕',
  unknown: '?',
}

const TONES: Record<string, Tone> = {
  // claim verdicts
  PASS: 'pass', FAIL: 'fail', PARTIAL: 'warn', UNVERIFIED: 'unknown',
  // documentation
  MATCH: 'pass', STALE: 'warn', WRONG: 'fail', FABRICATED: 'fail',
  // requirement impact
  UNAFFECTED: 'pass', CHANGED: 'warn', RISK: 'warn', BROKEN: 'fail',
  // callers outside the diff
  SAFE: 'pass', NEEDS_UPDATE: 'warn',
  // contracts
  COMPATIBLE: 'pass', BREAKING_API_CHANGE: 'fail', SCHEMA_MIGRATION_RISK: 'fail',
  // test integrity
  STRONG: 'pass', WEAK: 'warn', MISSING: 'fail',
  // review threads
  RESOLVED: 'pass', FIXED: 'pass', OUTDATED: 'unknown', STILL_VALID: 'warn',
  // overall verdict
  ACCURATE: 'pass', MISLEADING: 'fail', NO_CLAIMS: 'unknown',
  // gate
  pass: 'pass', warn: 'warn', fail: 'fail',
}

export function toneOf(status: string | undefined | null): Tone {
  if (!status) return 'unknown'
  return TONES[status] ?? 'unknown'
}

export const GATE_WORD: Record<string, string> = {
  pass: 'Clear to merge',
  warn: 'Merge with care',
  fail: 'Blocked',
  unknown: 'Not scored',
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function formatCost(value: number | null | undefined): string {
  if (!value) return '$0'
  return value < 0.01 ? `$${value.toFixed(4)}` : `$${value.toFixed(2)}`
}

export interface Segment {
  key: Tone
  label: string
  count: number
  share: number
}

/** Gate counts → band segments, largest share first is NOT applied: the order
 *  is fixed (pass → warn → fail → unknown) so a repo's band never repaints
 *  itself when one bucket changes. Empty buckets are dropped. */
export function bandSegments(counts: Record<string, number> | undefined): Segment[] {
  const order: Tone[] = ['pass', 'warn', 'fail', 'unknown']
  const total = order.reduce((sum, key) => sum + (counts?.[key] ?? 0), 0)
  if (!total) return []
  return order
    .map((key) => ({
      key,
      label: GATE_WORD[key],
      count: counts?.[key] ?? 0,
      share: (counts?.[key] ?? 0) / total,
    }))
    .filter((seg) => seg.count > 0)
}
