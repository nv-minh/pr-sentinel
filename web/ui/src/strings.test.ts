import { describe, expect, it } from 'vitest'
import { TABLES, type Key } from './strings'

/** The `{name}` tokens in a translated string — order-independent, since
 *  a translation is free to reorder a sentence's parts. */
function placeholders(value: string): string[] {
  return [...value.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort()
}

const keys = Object.keys(TABLES.en) as Key[]

describe('TABLES placeholder parity', () => {
  // One assertion per key, not one assertion over the whole dictionary: a
  // single `expect(allEnSets).toEqual(allViSets)` across ~140 keys reports
  // only "expected Set to equal Set" and leaves whoever hits it to bisect the
  // dictionary by hand. Parametrising with the key names the failure in the
  // test's own title and gives a real per-string diff.
  it.each(keys)('%s: vi has the same {placeholders} as en', (key) => {
    expect(placeholders(TABLES.vi[key])).toEqual(placeholders(TABLES.en[key]))
  })
})
