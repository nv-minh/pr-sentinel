import { describe, expect, it } from 'vitest'
import { parseEvidenceRef } from './evidence'

describe('parseEvidenceRef — the grammar shared with src/annotations.py', () => {
  it('parses a plain file:line', () => {
    expect(parseEvidenceRef('src/checkout/pricing.py:74')).toEqual({
      raw: 'src/checkout/pricing.py:74',
      ref: { path: 'src/checkout/pricing.py', start: 74, end: 74, annotation: '' },
    })
  })

  it('parses a range with an annotation', () => {
    expect(parseEvidenceRef('src/repo_ref.py:1-36 (module with parse_repo)').ref)
      .toEqual({ path: 'src/repo_ref.py', start: 1, end: 36,
                 annotation: '(module with parse_repo)' })
  })

  it('parses a line with a bare trailing word', () => {
    expect(parseEvidenceRef('tests/test_x.py:7 test_name').ref)
      .toEqual({ path: 'tests/test_x.py', start: 7, end: 7, annotation: 'test_name' })
  })

  it('keeps last-colon semantics for windows-ish paths', () => {
    expect(parseEvidenceRef('C:/win/a.py:7').ref)
      .toEqual({ path: 'C:/win/a.py', start: 7, end: 7, annotation: '' })
  })

  it('returns a null ref for file:function and bare paths', () => {
    expect(parseEvidenceRef('tests/test_pricing.py:test_price_for').ref).toBeNull()
    expect(parseEvidenceRef('src/a.py').ref).toBeNull()
    expect(parseEvidenceRef('').ref).toBeNull()
    expect(parseEvidenceRef('src/a.py:12abc').ref).toBeNull()
  })
})
