// A deliberately small renderer for report.md's fixed grammar (see
// synthesize.build_report): #/##/### headings, "-" bullets with 2-space
// nesting, GFM pipe tables whose cells may carry literal <br> breaks,
// **bold**, `code`, _italics_ and <details>/<summary> blocks. Everything is
// built as JSX text nodes — the report embeds PR-author-controlled prose, so
// there is no innerHTML anywhere; unknown markup renders as visible text.
// Headings shift down one level (h1 → h2): the workspace already has the h1.
import { Fragment } from 'react'
import type { ReactNode } from 'react'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g

function inline(text: string): ReactNode {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className="rounded-sm bg-brand-soft px-1 font-mono text-[0.92em]">{part.slice(1, -1)}</code>
    }
    if (part.startsWith('_') && part.endsWith('_') && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>
    }
    return <Fragment key={i}>{part}</Fragment>
  })
}

function cell(text: string): ReactNode {
  const parts = text.split(/<br\s*\/?>/i)
  return parts.map((part, i) => (
    <Fragment key={i}>
      {i > 0 && <br />}
      {inline(part.trim())}
    </Fragment>
  ))
}

const isDivider = (line: string) => /^\|[\s:|-]+\|$/.test(line.trim())
const isRow = (line: string) => line.trim().startsWith('|') && line.trim().endsWith('|')
const cells = (line: string) => line.trim().slice(1, -1).split('|').map((c) => c.trim())

export function Markdown({ source }: { source: string }) {
  const lines = source.split('\n')
  const out: ReactNode[] = []
  let i = 0
  let key = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (!trimmed) { i++; continue }

    const heading = /^(#{1,3}) (.*)$/.exec(trimmed)
    if (heading) {
      const level = heading[1].length
      const text = inline(heading[2])
      out.push(level === 1
        ? <h2 key={key++} className="mt-4 mb-2 text-[17px] font-semibold">{text}</h2>
        : level === 2
          ? <h3 key={key++} className="mt-4 mb-1.5 font-mono text-[12px] font-bold uppercase tracking-[0.1em] text-ink-muted">{text}</h3>
          : <h4 key={key++} className="mt-3 mb-1 text-[13.5px] font-semibold">{text}</h4>)
      i++
      continue
    }

    if (trimmed.startsWith('- ')) {
      const items: Array<{ depth: number; text: string }> = []
      while (i < lines.length && lines[i].trim().startsWith('- ')) {
        const depth = /^(\s*)/.exec(lines[i])![1].length >= 2 ? 1 : 0
        items.push({ depth, text: lines[i].trim().slice(2) })
        i++
      }
      out.push(
        <ul key={key++} className="mb-2 list-disc space-y-0.5 pl-5 text-[13px]">
          {items.map((item, j) => (
            <li key={j} className={item.depth ? 'ml-4 list-[circle]' : ''}>
              {inline(item.text)}
            </li>
          ))}
        </ul>,
      )
      continue
    }

    if (isRow(trimmed) && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const head = cells(trimmed)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && isRow(lines[i].trim()) && !isDivider(lines[i])) {
        rows.push(cells(lines[i].trim()))
        i++
      }
      out.push(
        <div key={key++} className="mb-3 overflow-x-auto">
          <Table className="text-xs">
            <TableHeader>
              <TableRow>
                {head.map((h, j) => <TableHead key={j}>{inline(h)}</TableHead>)}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row, j) => (
                <TableRow key={j}>
                  {row.map((c, k) => <TableCell key={k} className="align-top">{cell(c)}</TableCell>)}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>,
      )
      continue
    }

    if (trimmed === '<details>' || trimmed === '</details>') { i++; continue }
    const summary = /^<summary>(.*)<\/summary>$/.exec(trimmed)
    if (summary) {
      out.push(<h4 key={key++} className="mt-3 mb-1 text-[13.5px] font-semibold">{inline(summary[1])}</h4>)
      i++
      continue
    }

    if (trimmed.startsWith('```')) {
      const buf: string[] = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        buf.push(lines[i])
        i++
      }
      i++
      out.push(
        <pre key={key++} className="mb-2 overflow-x-auto rounded border border-hairline bg-surface px-3 py-2 font-mono text-xs whitespace-pre-wrap">
          {buf.join('\n')}
        </pre>,
      )
      continue
    }

    out.push(<p key={key++} className="mb-2 max-w-[80ch] text-[13px] leading-relaxed">{inline(trimmed)}</p>)
    i++
  }

  return <div data-report>{out}</div>
}
