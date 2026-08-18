import { describe, expect, it } from 'vitest'
import type { PrDetail, PrExtras, SnapshotFile, SnapshotThread } from '../api'
import { FAMILY_ORDER, attachExtras, collectFindings, newLineRanges, planAnchors } from './model'

const PATCH = [
  '@@ -70,3 +70,6 @@',
  ' def _compute_total(cart):',
  '     subtotal = sum(...)',
  '+    total = _apply_discounts(cart, subtotal)',
  '+    _price_cache[key] = total',
  '+    return total',
  ' # end',
].join('\n')

const FILES: SnapshotFile[] = [
  { filename: 'src/checkout/pricing.py', status: 'modified', additions: 3, deletions: 0,
    patch: PATCH },
  { filename: 'docs/checkout.md', status: 'modified', additions: 1, deletions: 0,
    patch: '@@ -1,1 +1,2 @@\n context\n+cached per customer' },
]

const THREADS: SnapshotThread[] = [
  { path: 'src/checkout/pricing.py', line: 72, author: 'rev',
    body: 'Does this handle a reused discount code?', resolved: false, outdated: false },
]

const DETAIL = {
  claims: [
    { id: 'C1', text: 'Caches prices', category: 'perf', status: 'FAIL',
      evidence: ['src/checkout/pricing.py:72', 'db/x.sql:1'], note: 'discounts bypass' },
    { id: 'C2', text: 'Covered by tests', category: 'test', status: 'PASS',
      evidence: ['tests/test_pricing.py:12'], note: '' },
  ],
  docs: [{ path: 'docs/checkout.md', status: 'FABRICATED', what: 'per-customer key' }],
  impact: [{ requirement: 'Discounts apply', impact: 'BROKEN', area: 'payment',
             paths: ['src/checkout/pricing.py'], detail: 'stale within TTL' }],
  callers: [{ symbol: 'price_for(cart)', defined_at: 'src/checkout/pricing.py:71',
              callers: ['src/api/checkout.py:120'], risk: 'BROKEN', note: 'cached' }],
  contracts: [{ kind: 'SCHEMA', path: 'db/x.sql', status: 'SCHEMA_MIGRATION_RISK',
                detail: 'no down migration' }],
  cross_pr: [],
  tests: [{ target: 'tests/test_pricing.py:test_price_for', assertion_quality: 'MISSING',
            uncovered_edge_cases: [], note: 'no cache test' }],
  threads: [{ text: 'Does this handle a reused discount code?', status: 'STILL_VALID', note: '' }],
} as unknown as PrDetail

describe('newLineRanges', () => {
  it('reads new-side ranges from hunk headers', () => {
    expect(newLineRanges(PATCH)).toEqual([[70, 75]])
  })
  it('is empty for degenerate patches without a real header', () => {
    expect(newLineRanges('@@\n+CACHE_TTL = 300')).toEqual([])
    expect(newLineRanges('')).toEqual([])
  })
})

describe('collectFindings', () => {
  it('walks families in blast-radius order and keeps the blocking predicates', () => {
    const findings = collectFindings(DETAIL, THREADS)
    expect(FAMILY_ORDER).toEqual(
      ['contract', 'caller', 'claim', 'impact', 'doc', 'test', 'crosspr', 'thread'])
    const families = findings.map((f) => f.family)
    expect(families.indexOf('contract')).toBeLessThan(families.indexOf('claim'))
    const blocking = findings.filter((f) => f.blocking).map((f) => `${f.family}:${f.title}`)
    expect(blocking).toContain('contract:db/x.sql')
    expect(blocking).toContain('caller:price_for(cart)')
    expect(blocking).toContain('claim:Caches prices')
    expect(blocking).toContain('impact:Discounts apply')
    expect(blocking).toContain('doc:docs/checkout.md')
    expect(blocking).toContain('test:tests/test_pricing.py:test_price_for')
    expect(blocking).not.toContain('claim:Covered by tests')
  })

  it('anchors a thread finding through the matching snapshot thread', () => {
    const thread = collectFindings(DETAIL, THREADS).find((f) => f.family === 'thread')!
    expect(thread.anchor).toEqual({ path: 'src/checkout/pricing.py', start: 72, end: 72,
                                    annotation: '' })
  })
})

describe('planAnchors', () => {
  const findings = collectFindings(DETAIL, THREADS)
  const plan = planAnchors(findings, FILES)

  it('buckets an in-hunk ref onto its line', () => {
    const pricing = plan.byFile.get('src/checkout/pricing.py')!
    const lines = [...pricing.byLine.keys()]
    expect(lines).toContain(72) // C1 evidence + thread
    expect(pricing.byLine.get(72)!.some((f) => f.family === 'claim')).toBe(true)
  })

  it('sends an out-of-hunk ref to the file header', () => {
    const pricing = plan.byFile.get('src/checkout/pricing.py')!
    // caller defined_at :71 is a context line — in-hunk; impact has no line → header
    expect(pricing.header.some((f) => f.family === 'impact')).toBe(true)
  })

  it('sends refs to files outside the diff to unanchored', () => {
    expect(plan.unanchored.some((f) => f.family === 'contract')).toBe(true) // db/x.sql not in diff
    expect(plan.unanchored.some((f) => f.family === 'test')).toBe(true)
  })

  it('orders keys document-first: file order, header before lines, then unanchored', () => {
    const keys = plan.orderedKeys
    const idx = (k: string) => keys.indexOf(k)
    const impact = findings.find((f) => f.family === 'impact')!.key
    const claim = findings.find((f) => f.family === 'claim' && f.blocking)!.key
    const doc = findings.find((f) => f.family === 'doc')!.key
    const contract = findings.find((f) => f.family === 'contract')!.key
    expect(idx(impact)).toBeLessThan(idx(claim))   // header before in-line, same file
    expect(idx(claim)).toBeLessThan(idx(doc))      // first file before second file
    expect(idx(doc)).toBeLessThan(idx(contract))   // diff files before unanchored
    expect(keys.length).toBe(findings.length)
  })

  it('treats every finding in a degenerate-patch file as header-anchored', () => {
    const degenerate = [{ filename: 'src/checkout/pricing.py', status: 'modified',
                          additions: 1, deletions: 0, patch: '@@\n+CACHE_TTL' }]
    const p = planAnchors(findings, degenerate as SnapshotFile[])
    const pricing = p.byFile.get('src/checkout/pricing.py')!
    expect([...pricing.byLine.keys()]).toEqual([])
    expect(pricing.header.length).toBeGreaterThan(0)
  })
})

describe('attachExtras', () => {
  it('attaches a poc to its broken finding and a doc patch to its doc finding', () => {
    const extras = {
      ticket: null, neutralized: null, description: null,
      poc: [{ target: 'tests/test_pricing.py', framework: 'pytest',
              test_code: 'def test(): ...', why_it_fails: 'stale price' }],
      patches: [{ path: 'docs/checkout.md', old_snippet: 'per customer', new_snippet: 'per cart',
                  line_hint: 2, why: 'no such key' }],
    } as PrExtras
    const findings = attachExtras(collectFindings(DETAIL, THREADS), extras)
    const claim = findings.find((f) => f.family === 'claim' && f.blocking)!
    const doc = findings.find((f) => f.family === 'doc')!
    const pocOwners = findings.filter((f) => f.attachments?.poc?.length)
    expect(pocOwners.length).toBe(1) // exactly one owner — no duplicate cards
    expect(doc.attachments?.patches?.[0].new_snippet).toBe('per cart')
    expect(claim.family).toBe('claim')
  })
})
