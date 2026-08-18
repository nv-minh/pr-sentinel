import type { ReactNode } from 'react'
import { Skeleton } from '@/components/ui/skeleton'
import { useT } from './i18n'
import { GLYPH, TONE_COLOR, bandSegments, toneOf } from './status'
import type { Tone } from './status'
import type { Key } from './strings'

export function Mark({ status }: { status: string }) {
  const tone = toneOf(status)
  return (
    <span className="row-mark text-center font-mono text-[13px] font-bold leading-[1.6]"
          style={{ color: TONE_COLOR[tone] }} aria-hidden="true">
      {GLYPH[tone]}
    </span>
  )
}

export function StatusWord({ status }: { status: string }) {
  const tone = toneOf(status)
  return (
    <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]"
          style={{ color: TONE_COLOR[tone] }}>
      {status || 'UNKNOWN'}
    </span>
  )
}

/** Non-zero verdict counts as toned mono chips — shared by the repo cards
 * and the PR queue header. */
export function VerdictChips({ counts }: { counts: Record<string, number> | undefined }) {
  const entries = Object.entries(counts ?? {}).filter(([, n]) => n > 0)
  if (!entries.length) return null
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] tabular-nums">
      {entries.map(([verdict, n]) => (
        <span key={verdict} className="whitespace-nowrap text-ink-muted">
          {n} <StatusWord status={verdict} />
        </span>
      ))}
    </div>
  )
}

export function Tile({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="tile bg-surface px-[18px] pt-4 pb-[18px]">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-muted">
        {label}
      </div>
      <div className="mt-1.5 font-mono text-[30px] font-semibold tracking-[-0.02em] tabular-nums">
        {value}
      </div>
      {note ? <div className="mt-0.5 text-xs text-ink-muted">{note}</div> : null}
    </div>
  )
}

export function Tiles({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(150px,1fr))] gap-px overflow-hidden rounded border border-hairline bg-hairline">
      {children}
    </div>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return (
    <h2 className="mt-10 mb-3 flex items-center gap-2.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-muted after:h-px after:flex-1 after:bg-hairline after:content-['']">
      {children}
    </h2>
  )
}

export function PageTitle({ children }: { children: ReactNode }) {
  return (
    <h1 className="mb-1.5 text-[clamp(28px,4vw,40px)] font-[680] leading-[1.08] tracking-[-0.025em]">
      {children}
    </h1>
  )
}

export function PageSub({ children }: { children: ReactNode }) {
  return (
    <p className="mb-7 font-mono text-[12.5px] tracking-[0.02em] text-ink-muted">
      {children}
    </p>
  )
}

/** The gate band: one horizontal bar segmented by merge decision. Each segment
 *  carries its own count, and the legend repeats glyph + word, so the reading
 *  never depends on telling amber from red. */
export function GateBand({ counts }: { counts: Record<string, number> | undefined }) {
  const t = useT()
  const segments = bandSegments(counts)
  const word = (seg: { key: Tone }) => t(`gate.${seg.key}` as Key)
  if (!segments.length) {
    return (
      <div className="my-2.5 flex h-[34px] gap-0.5">
        <div className="flex flex-1 items-center justify-center rounded-sm border border-dashed border-hairline-strong font-mono text-xs text-ink-muted">
          {t('band.empty')}
        </div>
      </div>
    )
  }
  return (
    <>
      <div className="mt-1 mb-2.5 flex h-[34px] gap-0.5" role="img"
           aria-label={segments.map((s) => `${s.count} ${word(s)}`).join(', ')}>
        {segments.map((seg) => (
          <div
            key={seg.key}
            className="band-seg flex min-w-0.5 items-center justify-center rounded-sm font-mono text-xs font-semibold text-white"
            style={{ flex: seg.share, background: TONE_COLOR[seg.key] }}
            title={`${word(seg)}: ${seg.count}`}
          >
            {seg.share > 0.08 ? seg.count : ''}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-4 font-mono text-xs text-ink-muted">
        {segments.map((seg) => (
          <span className="flex items-center gap-[7px]" key={seg.key}>
            <ToneDot tone={seg.key} />
            {GLYPH[seg.key]} {word(seg)} · {seg.count}
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
      className={`row grid grid-cols-[26px_minmax(0,1fr)_auto] items-start gap-3.5 border-b border-hairline px-0.5 py-[13px] hover:bg-brand-soft max-[620px]:grid-cols-[22px_minmax(0,1fr)] ${
        interactive ? 'cursor-pointer' : ''
      }`}
      onClick={onClick}
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onKeyDown={interactive ? (e) => {
        if (e.target !== e.currentTarget) return
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.() }
      } : undefined}
    >
      <Mark status={status} />
      <div>
        <div className="text-[15px]">{title}</div>
        {meta ? (
          <div className="mt-[3px] break-words font-mono text-xs text-ink-muted">{meta}</div>
        ) : null}
      </div>
      {right ? (
        <div className="row-right whitespace-nowrap text-right font-mono text-xs tabular-nums text-ink-muted max-[620px]:col-start-2 max-[620px]:text-left">
          {right}
        </div>
      ) : null}
    </div>
  )
}

export function Citations({ items }: { items: string[] }) {
  const t = useT()
  if (!items?.length) return <span>{t('citations.none')}</span>
  return (
    <>
      {items.map((item, i) => (
        <span className="mr-[5px] inline-block rounded-sm border border-hairline-strong px-[5px] py-px font-mono text-[11.5px] text-ink"
              key={`${item}-${i}`}>
          {item}
        </span>
      ))}
    </>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="border-b border-hairline px-0.5 py-[18px] text-sm text-ink-muted">
      {children}
    </div>
  )
}

export function Ledger({ children }: { children: ReactNode }) {
  return <div className="border-t border-hairline">{children}</div>
}

export function ToneDot({ tone }: { tone: Tone }) {
  return (
    <span className="size-2.5 flex-none rounded-sm"
          style={{ background: TONE_COLOR[tone] }} />
  )
}

/** Three skeleton rows: the page keeps its shape while the fetch lands, so the
 *  layout does not jump when it does. */
export function Loading({ label }: { label?: string }) {
  const t = useT()
  return (
    <div className="space-y-2 py-4" role="status" aria-live="polite">
      <span className="sr-only">{label ?? t('common.loading')}…</span>
      <Skeleton className="h-6 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  )
}

export function ErrorNotice({ message }: { message: ReactNode }) {
  return (
    <div className="my-4 border-l-2 border-fail py-2 pl-3 font-mono text-[12.5px] text-ink"
         role="alert">
      {message}
    </div>
  )
}

export function Notice({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'fail' }) {
  return (
    <div className={`my-4 border-l-2 py-2 pl-3 font-mono text-[12.5px] ${
      tone === 'fail' ? 'border-fail text-ink' : 'border-brand text-ink-muted'
    }`} role={tone === 'fail' ? 'alert' : undefined}>
      {children}
    </div>
  )
}
