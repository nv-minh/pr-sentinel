// Evidence refs arrive as free text — real reviews write `src/a.py:74`,
// `src/repo_ref.py:1-36 (module …)`, `tests/test_x.py:7 test_name` and plain
// `file:function` targets. This grammar is shared with src/annotations.py's
// parse_ref: path ':' digits ('-' digits)? (whitespace annotation)?
const REF_RE = /^(.+?):(\d+)(?:-(\d+))?(?:\s+(\S.*))?$/

export interface ParsedRef {
  path: string
  start: number
  end: number
  annotation: string
}

export interface EvidenceRef {
  raw: string
  /** null when no line number could be read — rendered as a plain chip. */
  ref: ParsedRef | null
}

export function parseEvidenceRef(raw: string): EvidenceRef {
  const match = REF_RE.exec((raw ?? '').trim())
  if (!match) return { raw, ref: null }
  const start = Number(match[2])
  return {
    raw,
    ref: {
      path: match[1],
      start,
      end: match[3] ? Number(match[3]) : start,
      annotation: match[4] ?? '',
    },
  }
}
