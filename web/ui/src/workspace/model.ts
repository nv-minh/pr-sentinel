// The workspace's pure core: findings normalized into one shape, anchored
// onto the diff, ordered for j/k navigation. No React, no fetch.
import type { PrDetail, PrExtras, SnapshotFile, SnapshotThread } from '../api'
import { parseEvidenceRef } from './evidence'
import type { EvidenceRef, ParsedRef } from './evidence'

/** DOM id for a file section — shared by the nav (scroll target) and the
 * lazy diff pane without importing across the chunk boundary. */
export const fileSlug = (path: string) => `file-${path.replace(/[^a-zA-Z0-9]+/g, '-')}`

export type Family =
  | 'contract' | 'caller' | 'claim' | 'impact' | 'doc' | 'test' | 'crosspr' | 'thread'

/** Blast-radius order — the same fixed priority the old BLOCKING ledger used:
 * an API-breaking change first, prose problems later. */
export const FAMILY_ORDER: Family[] =
  ['contract', 'caller', 'claim', 'impact', 'doc', 'test', 'crosspr', 'thread']

export interface Finding {
  /** `${family}-${i}` — stable per payload; the ?finding= deep-link value. */
  key: string
  family: Family
  status: string
  blocking: boolean
  title: string
  detail: string
  evidence: EvidenceRef[]
  /** Where the card renders: a diff line, a file header (start 0), or null. */
  anchor: ParsedRef | null
  claim?: { text: string; confidence?: number | null; category?: string }
  attachments?: { poc?: PrExtras['poc']; patches?: PrExtras['patches'] }
}

/** A path that may itself carry `:line` (real contract paths do). */
function fileAnchor(path: string): ParsedRef | null {
  if (!path) return null
  const parsed = parseEvidenceRef(path).ref
  return parsed ?? { path, start: 0, end: 0, annotation: '' }
}

function firstLineRef(evidence: EvidenceRef[]): ParsedRef | null {
  return evidence.find((e) => e.ref)?.ref ?? null
}

const normalize = (text: string) => text.replace(/\s+/g, ' ').trim().toLowerCase()

export function collectFindings(d: PrDetail, threads?: SnapshotThread[]): Finding[] {
  const out: Finding[] = []
  const push = (family: Family, f: Omit<Finding, 'key' | 'family'>) => {
    out.push({ ...f, family, key: '' })
  }

  for (const c of d.contracts ?? []) {
    push('contract', {
      status: c.status, blocking: c.status !== 'COMPATIBLE',
      title: c.path, detail: c.detail ?? '',
      evidence: [parseEvidenceRef(c.path)], anchor: fileAnchor(c.path),
    })
  }
  for (const c of d.callers ?? []) {
    push('caller', {
      status: c.risk, blocking: c.risk === 'BROKEN',
      title: c.symbol, detail: c.note ?? '',
      evidence: [c.defined_at, ...(c.callers ?? [])].filter(Boolean).map(parseEvidenceRef),
      anchor: parseEvidenceRef(c.defined_at ?? '').ref,
    })
  }
  for (const c of d.claims ?? []) {
    const evidence = (c.evidence ?? []).map(parseEvidenceRef)
    push('claim', {
      status: c.status, blocking: c.status === 'FAIL',
      title: c.text || c.id, detail: c.note ?? '',
      evidence, anchor: firstLineRef(evidence),
      claim: { text: c.text, confidence: c.confidence, category: c.category },
    })
  }
  for (const i of d.impact ?? []) {
    const paths: string[] = (i as { paths?: string[] }).paths ?? []
    push('impact', {
      status: i.impact, blocking: i.impact === 'BROKEN',
      title: i.requirement, detail: i.detail ?? '',
      evidence: paths.map(parseEvidenceRef), anchor: fileAnchor(paths[0] ?? ''),
    })
  }
  for (const x of d.docs ?? []) {
    push('doc', {
      status: x.status, blocking: x.status === 'WRONG' || x.status === 'FABRICATED',
      title: x.path, detail: x.what ?? '',
      evidence: [parseEvidenceRef(x.path)], anchor: fileAnchor(x.path),
    })
  }
  for (const tst of d.tests ?? []) {
    const filePart = (tst.target ?? '').split(':')[0]
    const cases = tst.uncovered_edge_cases ?? []
    const wheres = cases.map((e: { where?: string }) => e.where ?? '').filter(Boolean)
    push('test', {
      status: tst.assertion_quality, blocking: tst.assertion_quality === 'MISSING',
      title: tst.target,
      detail: [tst.note ?? '', ...cases.map((e) => `${e.case} → ${e.where}`)]
        .filter(Boolean).join('\n'),
      evidence: [tst.target, ...wheres].filter(Boolean).map(parseEvidenceRef),
      anchor: fileAnchor(filePart),
    })
  }
  for (const c of d.cross_pr ?? []) {
    const evidence = (c.evidence ?? []).map(parseEvidenceRef)
    push('crosspr', {
      status: c.status, blocking: false,
      title: `#${c.pr} ${c.symbol ?? ''}`.trim(), detail: c.detail ?? '',
      evidence, anchor: firstLineRef(evidence) ?? fileAnchor((c.paths ?? [])[0] ?? ''),
    })
  }
  for (const th of d.threads ?? []) {
    const text = normalize(th.text ?? '')
    const match = (threads ?? []).find((s) => {
      const body = normalize(s.body ?? '')
      return body && text && (body.includes(text) || text.includes(body))
    })
    push('thread', {
      status: th.status, blocking: false,
      title: th.text, detail: th.note ?? '',
      evidence: match?.path && match.line
        ? [parseEvidenceRef(`${match.path}:${match.line}`)] : [],
      anchor: match?.path && match.line
        ? { path: match.path, start: match.line, end: match.line, annotation: '' }
        : null,
    })
  }

  // stable keys per family, then blast-radius order
  const counters: Partial<Record<Family, number>> = {}
  for (const f of out) {
    const i = counters[f.family] ?? 0
    counters[f.family] = i + 1
    f.key = `${f.family}-${i}`
  }
  out.sort((a, b) => FAMILY_ORDER.indexOf(a.family) - FAMILY_ORDER.indexOf(b.family))
  return out
}

/** New-side [start, end] ranges from `@@ -a,b +c,d @@` headers. The strict
 * regex is deliberate: a degenerate patch ("@@\n+x") yields no ranges, so its
 * findings all fall back to the file header — same rule the raw-pre fallback
 * uses in the diff pane. */
export function newLineRanges(patch: string): Array<[number, number]> {
  const ranges: Array<[number, number]> = []
  const re = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/gm
  let m: RegExpExecArray | null
  while ((m = re.exec(patch ?? '')) !== null) {
    const start = Number(m[1])
    const count = m[2] === undefined ? 1 : Number(m[2])
    ranges.push([start, start + Math.max(count - 1, 0)])
  }
  return ranges
}

export interface FileAnchors {
  header: Finding[]
  byLine: Map<number, Finding[]>
}

export interface AnchorPlan {
  byFile: Map<string, FileAnchors>
  unanchored: Finding[]
  /** j/k order: per file — header cards, then lines ascending — then unanchored. */
  orderedKeys: string[]
}

export function planAnchors(findings: Finding[], files: SnapshotFile[]): AnchorPlan {
  const byFile = new Map<string, FileAnchors>()
  const ranges = new Map<string, Array<[number, number]>>()
  for (const f of files) {
    byFile.set(f.filename, { header: [], byLine: new Map() })
    ranges.set(f.filename, newLineRanges(f.patch))
  }
  const unanchored: Finding[] = []
  for (const finding of findings) {
    const a = finding.anchor
    const slot = a ? byFile.get(a.path) : undefined
    if (!a || !slot) {
      unanchored.push(finding)
      continue
    }
    const inHunk = a.start > 0 &&
      (ranges.get(a.path) ?? []).some(([lo, hi]) => a.start >= lo && a.start <= hi)
    if (inHunk) {
      const list = slot.byLine.get(a.start) ?? []
      list.push(finding)
      slot.byLine.set(a.start, list)
    } else {
      slot.header.push(finding)
    }
  }
  const orderedKeys: string[] = []
  for (const f of files) {
    const slot = byFile.get(f.filename)!
    for (const finding of slot.header) orderedKeys.push(finding.key)
    for (const line of [...slot.byLine.keys()].sort((x, y) => x - y)) {
      for (const finding of slot.byLine.get(line)!) orderedKeys.push(finding.key)
    }
  }
  for (const finding of unanchored) orderedKeys.push(finding.key)
  return { byFile, unanchored, orderedKeys }
}

/** Attach PoC tests and doc patches to the findings they were written for.
 * PoC entries are drafted from poc.broken(findings), which walks impact
 * BROKEN then callers BROKEN in order — zip by index, leftovers unattached
 * (the Overview tab lists every extra regardless). Doc patches match their
 * doc finding by path. */
export function attachExtras(findings: Finding[], extras: PrExtras | null): Finding[] {
  if (!extras) return findings
  const next = findings.map((f) => ({ ...f }))
  const brokenOrder = [
    ...next.filter((f) => f.family === 'impact' && f.status === 'BROKEN'),
    ...next.filter((f) => f.family === 'caller' && f.status === 'BROKEN'),
  ]
  for (const [i, poc] of (extras.poc ?? []).entries()) {
    const owner = brokenOrder[i]
    if (!owner) break
    owner.attachments = { ...owner.attachments, poc: [...(owner.attachments?.poc ?? []), poc] }
  }
  for (const patch of extras.patches ?? []) {
    const owner = next.find((f) => f.family === 'doc' && f.title === patch.path)
    if (!owner) continue
    owner.attachments = {
      ...owner.attachments,
      patches: [...(owner.attachments?.patches ?? []), patch],
    }
  }
  return next
}
