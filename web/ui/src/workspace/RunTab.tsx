import { useEffect, useRef } from 'react'
import { api } from '../api'
import type { PrDetail, ReviewStatus } from '../api'
import { Empty, Eyebrow } from '../components'
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
