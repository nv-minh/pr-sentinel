// One evidence citation. Three behaviors by what the ref resolves to:
// unparseable → a plain mono chip; a file in the diff → jump the selection
// there; anything else → an inline peek that reads the workspace clone
// (gracefully unavailable for demo/CI sessions, which carry no clone).
import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { useT } from '../i18n'
import type { EvidenceRef } from './evidence'

const CHIP =
  'inline-block rounded-sm border border-hairline-strong px-[5px] py-px font-mono text-[11.5px]'

function Peek({ owner, repo, pr, path, start, end, onClose }: {
  owner: string; repo: string; pr: number
  path: string; start: number; end: number
  onClose: () => void
}) {
  const t = useT()
  const from = Math.max(1, start - 8)
  const slice = useApi(
    (signal) => api.prFile(owner, repo, pr, path, from, end + 8, signal),
    [owner, repo, pr, path, from, end],
  )
  return (
    <div className="w-full rounded-sm border border-hairline bg-surface px-3 py-2"
         onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="font-mono text-[11px] text-ink-muted">{path}</span>
        <button className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-muted hover:text-ink"
                onClick={onClose}>
          {t('ws.peekClose')}
        </button>
      </div>
      {slice.loading ? (
        <p className="font-mono text-[11px] text-ink-muted">{t('ws.peekLoading')}…</p>
      ) : slice.error || !slice.data ? (
        <p className="text-[12.5px] text-ink-muted">{t('ws.peekUnavailable')}</p>
      ) : (
        <ol start={slice.data.start}
            className="list-none overflow-x-auto font-mono text-[11.5px] leading-relaxed">
          {slice.data.lines.map((line, i) => {
            const n = slice.data!.start + i
            const hit = n >= start && n <= end
            return (
              <li key={n} className={hit ? 'bg-brand-soft' : ''}>
                <span className="mr-3 inline-block w-8 select-none text-right text-ink-muted">
                  {n}
                </span>
                <span className="whitespace-pre">{line}</span>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

export function EvidenceChip({ item, inDiff, owner, repo, pr, onJump }: {
  item: EvidenceRef
  inDiff: (path: string) => boolean
  owner: string
  repo: string
  pr: number
  onJump: (path: string, line: number) => void
}) {
  const t = useT()
  const [open, setOpen] = useState(false)
  if (!item.ref) {
    return <span className={`${CHIP} text-ink-muted`}>{item.raw}</span>
  }
  const { path, start, end } = item.ref
  if (inDiff(path)) {
    return (
      <button className={`${CHIP} text-ink hover:border-brand hover:text-brand`}
              aria-label={t('ws.jumpTo', { ref: item.raw })}
              onClick={() => onJump(path, start)}>
        {item.raw}
      </button>
    )
  }
  return (
    <>
      <button className={`${CHIP} text-ink hover:border-brand hover:text-brand`}
              aria-expanded={open}
              aria-label={t('ws.jumpTo', { ref: item.raw })}
              onClick={() => setOpen((v) => !v)}>
        {item.raw}
      </button>
      {open && (
        <Peek owner={owner} repo={repo} pr={pr} path={path} start={start} end={end}
              onClose={() => setOpen(false)} />
      )}
    </>
  )
}
