import type { ReactNode } from 'react'
import { GLYPH, TONE_COLOR, bandSegments, toneOf } from './status'
import type { Tone } from './status'

export function Mark({ status }: { status: string }) {
  const tone = toneOf(status)
  return (
    <span className="row-mark" style={{ color: TONE_COLOR[tone] }} aria-hidden="true">
      {GLYPH[tone]}
    </span>
  )
}

export function StatusWord({ status }: { status: string }) {
  const tone = toneOf(status)
  return (
    <span className="status-word" style={{ color: TONE_COLOR[tone] }}>
      {status || 'UNKNOWN'}
    </span>
  )
}

export function Tile({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {note ? <div className="tile-note">{note}</div> : null}
    </div>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <h2 className="eyebrow">{children}</h2>
}

/** The gate band: one horizontal bar segmented by merge decision. Each segment
 *  carries its own count, and the legend repeats glyph + word, so the reading
 *  never depends on telling amber from red. */
export function GateBand({ counts }: { counts: Record<string, number> | undefined }) {
  const segments = bandSegments(counts)
  if (!segments.length) {
    return <div className="band"><div className="band-empty">No scored reviews yet</div></div>
  }
  return (
    <>
      <div className="band" role="img" aria-label={segments
        .map((s) => `${s.count} ${s.label}`).join(', ')}>
        {segments.map((seg) => (
          <div
            key={seg.key}
            className="band-seg"
            style={{ flex: seg.share, background: TONE_COLOR[seg.key] }}
            title={`${seg.label}: ${seg.count}`}
          >
            {seg.share > 0.08 ? seg.count : ''}
          </div>
        ))}
      </div>
      <div className="legend">
        {segments.map((seg) => (
          <span className="legend-item" key={seg.key}>
            <span className="swatch" style={{ background: TONE_COLOR[seg.key] }} />
            {GLYPH[seg.key]} {seg.label} · {seg.count}
          </span>
        ))}
      </div>
    </>
  )
}

export function Row({
  status, title, meta, right, onClick,
}: {
  status: string
  title: ReactNode
  meta?: ReactNode
  right?: ReactNode
  onClick?: () => void
}) {
  const interactive = Boolean(onClick)
  return (
    <div
      className="row"
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => { if (e.key === 'Enter') onClick?.() } : undefined}
      style={interactive ? { cursor: 'pointer' } : undefined}
    >
      <Mark status={status} />
      <div>
        <div className="row-title">{title}</div>
        {meta ? <div className="row-meta">{meta}</div> : null}
      </div>
      {right ? <div className="row-right">{right}</div> : null}
    </div>
  )
}

export function Citations({ items }: { items: string[] }) {
  if (!items?.length) return <span>no evidence cited</span>
  return (
    <>
      {items.map((item, i) => (
        <span className="cite" key={`${item}-${i}`}>{item}</span>
      ))}
    </>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>
}

export function Ledger({ children }: { children: ReactNode }) {
  return <div className="ledger">{children}</div>
}

export function ToneDot({ tone }: { tone: Tone }) {
  return <span className="swatch" style={{ background: TONE_COLOR[tone] }} />
}
