import type { PhaseStatus } from '../api'
import type { Tone } from '../status'

/** Hand-placed, not auto-laid-out: eleven fixed phases in a shape that reads
 *  left-to-right, with the reply loop above the spine, the sibling scan below
 *  the spine on the left as an input to Verify, and the doc-fix and PoC-test
 *  branches below it on the right as outputs. A layout engine would only make
 *  this move around between runs. */
export const POSITION: Record<string, { x: number; y: number }> = {
  snapshot: { x: 0, y: 130 },
  siblings: { x: 185, y: 262 },
  describe: { x: 185, y: 130 },
  claims: { x: 370, y: 130 },
  followup: { x: 370, y: 0 },
  verify: { x: 555, y: 130 },
  score: { x: 740, y: 130 },
  remediate: { x: 740, y: 262 },
  poc: { x: 925, y: 262 },
  ask: { x: 925, y: 130 },
  report: { x: 1110, y: 196 },
}

export const STATUS_TONE: Record<PhaseStatus, Tone> = {
  done: 'pass',
  running: 'warn',
  failed: 'fail',
  pending: 'unknown',
  skipped: 'unknown',
}

export const STATUS_WORD: Record<PhaseStatus, string> = {
  done: 'done',
  running: 'running',
  failed: 'failed',
  pending: 'pending',
  skipped: 'skipped',
}

/** Which detail tab a node opens. Phases with no tab of their own land on the
 *  nearest one that actually shows their output. */
export const NODE_TAB: Record<string, string> = {
  snapshot: 'context',
  siblings: 'crosspr',
  describe: 'context',
  claims: 'claims',
  followup: 'threads',
  verify: 'claims',
  remediate: 'docs',
  poc: 'tests',
  score: 'claims',
  ask: 'confirm',
  report: 'claims',
}
