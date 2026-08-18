import { useEffect, useRef } from 'react'
import { api } from '../api'
import type { PrDetail, ReviewStatus } from '../api'
import { Empty, Eyebrow } from '../components'
import { useApi } from '../hooks/useApi'
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table'
import { usePoll } from '../hooks/useApi'
import { useT } from '../i18n'
import { formatCost } from '../status'

export function RunTab({ owner, repo, pr, data, status, running }: {
  owner: string
  repo: string
  pr: number
  data: PrDetail
  status: ReviewStatus | null
  running: boolean
}) {
  const t = useT()
  const log = usePoll(
    (signal) => api.reviewLog(owner, repo, pr, signal),
    3000,
    running,
  )
  const pre = useRef<HTMLPreElement>(null)
  const atBottom = useRef(true)

  // Follow the tail, but stop the moment the reader scrolls up.
  useEffect(() => {
    const el = pre.current
    if (el && atBottom.current) el.scrollTop = el.scrollHeight
  }, [log.data])

  return (
    <div className="grid gap-1">
      {running ? (
        <>
          <Eyebrow>{t('run.liveHeading')}</Eyebrow>
          <pre
            ref={pre}
            onScroll={(e) => {
              const el = e.currentTarget
              atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24
            }}
            className="max-h-[340px] overflow-auto rounded border border-hairline bg-surface px-3.5 py-3 font-mono text-xs whitespace-pre-wrap text-ink-muted"
          >
            {log.data?.log || t('pr.starting')}
          </pre>
          {status?.elapsed_seconds != null && (
            <span className="font-mono text-xs text-ink-muted">
              {t('run.elapsed', { t: `${status.elapsed_seconds}s` })}
            </span>
          )}
        </>
      ) : (
        <p className="text-[13px] text-ink-muted">
          {t('run.idle')}
          {status?.last?.exit !== undefined && (
            <> · <span className="font-mono text-xs">
              {t('pr.lastRun', { code: status.last.exit, at: status.last.finished_at ?? '' })}
            </span></>
          )}
        </p>
      )}

      <Trace owner={owner} repo={repo} pr={pr} />

      <Eyebrow>{t('run.costHeading')}</Eyebrow>
      {data.usage?.length ? (
        <div className="overflow-x-auto">
          <Table className="font-mono text-xs">
            <TableHeader>
              <TableRow>
                <TableHead>{t('run.colPhase')}</TableHead>
                <TableHead>{t('run.colModel')}</TableHead>
                <TableHead className="text-right">{t('run.colTurns')}</TableHead>
                <TableHead className="text-right">{t('run.colDuration')}</TableHead>
                <TableHead className="text-right">{t('run.colCost')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.usage.map((u, i) => (
                <TableRow key={i}>
                  <TableCell>{u.phase}</TableCell>
                  <TableCell>{u.model}</TableCell>
                  <TableCell className="text-right tabular-nums">{u.num_turns ?? '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {u.duration_ms != null ? `${Math.round(u.duration_ms / 1000)}s` : '—'}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatCost(u.cost_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <Empty>{t('run.idle')}</Empty>
      )}
    </div>
  )
}

/** The agent's tool-call timeline, phase by phase — what the reviewer read,
 * grepped and ran before concluding. Only verify/followup mirror transcripts,
 * and old sessions carry none, so absence is normal. */
function Trace({ owner, repo, pr }: { owner: string; repo: string; pr: number }) {
  const t = useT()
  const trace = useApi((signal) => api.prTrace(owner, repo, pr, signal), [owner, repo, pr])
  return (
    <>
      <Eyebrow>{t('trace.heading')}</Eyebrow>
      {!trace.data?.length ? (
        <p className="text-[12.5px] text-ink-muted">{t('trace.empty')}</p>
      ) : (
        trace.data.map((phase) => (
          <section key={phase.session_id} className="mb-2">
            <h3 className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-muted">
              {phase.phase}
            </h3>
            <ol className="grid gap-0.5 border-l border-hairline pl-3">
              {phase.events.map((event, i) => (
                <li key={i} className={`text-[12px] leading-relaxed ${
                  event.type === 'tool' ? 'font-mono text-ink' : 'text-ink-muted'
                }`}>
                  {event.type === 'tool'
                    ? <><span aria-hidden="true">⚙ </span>{event.tool} — {event.summary}</>
                    : event.summary}
                </li>
              ))}
            </ol>
          </section>
        ))
      )}
    </>
  )
}
