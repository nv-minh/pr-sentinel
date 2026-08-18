import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { OpenPr, PrRecord, ReviewStatus } from '../api'
import {
  Empty, ErrorNotice, Eyebrow, GateBand, Ledger, Loading, Notice, PageSub, PageTitle, Row,
  StatusWord, Tile, Tiles, VerdictChips,
} from '../components'
import { useApi, usePoll } from '../hooks/useApi'
import { useT } from '../i18n'
import type { Key } from '../strings'
import { formatCost, formatScore } from '../status'
import { navigate, setQuery, useQuery } from '../router'
import { Button } from '@/components/ui/button'

type Section = 'running' | 'blocked' | 'warned' | 'passed' | 'not_scored'
  | 'not_reviewed' | 'draft'

const SECTIONS: Array<{ id: Section; label: Key }> = [
  { id: 'running', label: 'repo.sectionRunning' },
  { id: 'blocked', label: 'repo.sectionBlocked' },
  { id: 'warned', label: 'repo.sectionWarned' },
  { id: 'passed', label: 'repo.sectionPassed' },
  { id: 'not_scored', label: 'repo.sectionNotScored' },
  { id: 'not_reviewed', label: 'repo.sectionNotReviewed' },
  { id: 'draft', label: 'repo.sectionDraft' },
]

const GATE_FILTERS = ['pass', 'warn', 'fail', 'not_reviewed'] as const

interface QueueRow {
  pr: number
  title: string
  draft: boolean
  section: Section
  rec?: PrRecord
  open?: OpenPr
}

function bySection(open_prs: OpenPr[], prs: PrRecord[], busy: Set<number>): QueueRow[] {
  const byPr = new Map(prs.map((p) => [p.pr, p]))
  const rows: QueueRow[] = []
  const seen = new Set<number>()
  const gateSection = (rec?: PrRecord): Section =>
    rec?.gate === 'fail' ? 'blocked'
    : rec?.gate === 'warn' ? 'warned'
    : rec?.gate === 'pass' ? 'passed'
    : 'not_scored'
  for (const row of open_prs) {
    seen.add(row.pr)
    const rec = byPr.get(row.pr)
    const section: Section =
      row.status === 'reviewing' || busy.has(row.pr) ? 'running'
      : row.status === 'reviewed' ? gateSection(rec)
      : row.draft ? 'draft'
      : 'not_reviewed'
    rows.push({ pr: row.pr, title: row.title || rec?.title || '',
                draft: row.draft, section, rec, open: row })
  }
  // reviewed but no longer open (merged/closed) — history belongs in the queue
  for (const rec of prs) {
    if (!seen.has(rec.pr)) {
      rows.push({ pr: rec.pr, title: rec.title, draft: false,
                  section: busy.has(rec.pr) ? 'running' : gateSection(rec), rec })
    }
  }
  return rows
}

export function RepoDetail({ owner, repo }: { owner: string; repo: string }) {
  const t = useT()
  const query = useQuery()
  const repoApi = useApi((signal) => api.repo(owner, repo, signal), [owner, repo])
  const [busy, setBusy] = useState<Set<number>>(new Set())
  const [actionError, setActionError] = useState('')

  const data = repoApi.data
  const rows = data ? bySection(data.open_prs ?? [], data.prs ?? [], busy) : []
  const runningPrs = rows.filter((r) => r.section === 'running').map((r) => r.pr)
  const runningRef = useRef(runningPrs)
  runningRef.current = runningPrs

  // Poll cheap, disk-only status for the running PRs — never the gh-backed
  // repo endpoint — and stop entirely the moment nothing runs.
  const statuses = usePoll(
    (signal) => Promise.all(runningRef.current.map((n) =>
      api.reviewStatus(owner, repo, n, signal).then((st) => [n, st] as const))),
    4000,
    runningPrs.length > 0,
  )

  // One repo refetch (one gh hit) when every polled run has finished.
  const refetch = repoApi.refetch
  useEffect(() => {
    const settled = statuses.data as Array<readonly [number, ReviewStatus]> | null
    if (settled?.length && settled.every(([, st]) => !st.running)) {
      setBusy(new Set())
      refetch()
    }
  }, [statuses.data, refetch])

  const start = async (pr: number, reply = false) => {
    setActionError('')
    setBusy((prev) => new Set(prev).add(pr))
    try {
      await api.startReview(owner, repo, pr, reply)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
      setBusy((prev) => {
        const next = new Set(prev)
        next.delete(pr)
        return next
      })
    }
  }

  if (repoApi.error && !data) return <ErrorNotice message={repoApi.error} />
  if (!data) return <Loading label={t('repo.loading')} />

  const q = (query.q ?? '').toLowerCase()
  const gate = query.gate ?? ''
  const shown = rows.filter((r) => {
    const hay = `#${r.pr} ${r.title} ${r.rec?.author ?? ''}`.toLowerCase()
    if (q && !hay.includes(q)) return false
    if (!gate) return true
    if (gate === 'not_reviewed') return r.section === 'not_reviewed' || r.section === 'draft'
    return r.rec?.gate === gate
  })
  const unavailable = (data.open_prs ?? []).some((row) => row.unavailable)

  return (
    <>
      <PageTitle>{owner}/{repo}</PageTitle>
      <PageSub>
        <a className="text-brand hover:underline" href={`https://github.com/${owner}/${repo}`}>
          github.com/{owner}/{repo}
        </a>
      </PageSub>

      {actionError && <Notice tone="fail">{actionError}</Notice>}

      <Tiles>
        <Tile label={t('repo.tilePrs')} value={data.prs_total} />
        <Tile label={t('repo.tileVerified')} value={formatScore(data.avg_verification_score)}
              note={t('repo.tileVerifiedNote')} />
        <Tile label={t('repo.tileBugs')} value={data.bugs_total} note={t('repo.tileBugsNote')} />
        <Tile label={t('repo.tileDocErrors')} value={data.doc_errors_total} />
        <Tile label={t('repo.tileBreaking')} value={data.breaking_total}
              note={t('repo.tileBreakingNote')} />
        <Tile label={t('repo.tileSpent')} value={formatCost(data.cost_total)} />
      </Tiles>

      <Eyebrow>{t('repo.gateHeading')}</Eyebrow>
      <GateBand counts={data.gate_count} />
      <VerdictChips counts={data.verdict_count} />

      <div className="mt-5 mb-3 flex flex-wrap items-center gap-2">
        <input
          type="search"
          aria-label={t('repo.searchAria')}
          placeholder={t('repo.searchPlaceholder')}
          defaultValue={query.q ?? ''}
          onInput={(e) => setQuery({ q: e.currentTarget.value || null })}
          className="h-8 w-64 max-w-full rounded-sm border border-hairline-strong bg-surface px-2.5 font-mono text-xs outline-none focus-visible:border-brand"
        />
        <div role="group" aria-label={t('repo.gateFilterAria')} className="flex gap-1">
          <Button variant={gate === '' ? 'secondary' : 'ghost'} size="sm"
                  data-gate-filter="" className="font-mono text-[11px]"
                  onClick={() => setQuery({ gate: null })}>
            {t('repo.gateFilterAll')}
          </Button>
          {GATE_FILTERS.map((g) => (
            <Button key={g} variant={gate === g ? 'secondary' : 'ghost'} size="sm"
                    data-gate-filter={g} className="font-mono text-[11px] uppercase tracking-[0.06em]"
                    onClick={() => setQuery({ gate: g === gate ? null : g })}>
              {g === 'not_reviewed' ? t('repo.sectionNotReviewed') : g}
            </Button>
          ))}
        </div>
      </div>

      {unavailable && <Notice>{t('repo.unreachable')}</Notice>}

      {shown.length === 0 ? (
        <Empty>{t('repo.noOpenPrs')}</Empty>
      ) : (
        SECTIONS.map(({ id, label }) => {
          const group = shown.filter((r) => r.section === id)
          if (!group.length) return null
          return (
            <section key={id} data-section={id}>
              <Eyebrow>{t(label)}</Eyebrow>
              <Ledger>
                {group.map((r) => <QueueRowView key={r.pr} r={r} owner={owner} repo={repo}
                                                busy={busy.has(r.pr)} onStart={start} />)}
              </Ledger>
            </section>
          )
        })
      )}
    </>
  )
}

function QueueRowView({ r, owner, repo, busy, onStart }: {
  r: QueueRow
  owner: string
  repo: string
  busy: boolean
  onStart: (pr: number, reply?: boolean) => void
}) {
  const t = useT()
  const rec = r.rec
  const running = r.section === 'running'
  const status =
    running ? 'RUNNING'
    : rec?.gate ? rec.gate
    : r.open?.status === 'reviewed' ? 'PASS'
    : 'UNVERIFIED'
  const stop = (e: { stopPropagation: () => void }) => e.stopPropagation()
  return (
    <Row
      status={status}
      title={
        <>
          <span className="font-mono text-ink-muted">#{r.pr}</span>{' '}
          {r.title || t('common.noTitle')} {r.draft ? `· ${t('repo.draft')}` : ''}
        </>
      }
      meta={
        <>
          {running ? t('repo.statusReviewing')
            : rec ? <>{rec.verdict ? <StatusWord status={rec.verdict} /> : t('repo.statusReviewed')}</>
            : r.open?.status === 'reviewed' ? t('repo.statusReviewed')
            : t('repo.statusNotReviewed')}
          {rec?.author ? ` · ${rec.author}` : ''}
          {r.open?.rounds
            ? ` · ${r.open.rounds > 1
                ? t('repo.roundMany', { n: r.open.rounds })
                : t('repo.roundOne', { n: r.open.rounds })}`
            : ''}
          {rec ? ` · ${t('repo.prBugs', { n: rec.bugs })} · ${t('repo.prDocErrors', { n: rec.doc_errors })}` : ''}
          {rec?.breaking ? ` · ${t('repo.prBreaking', { n: rec.breaking })}` : ''}
        </>
      }
      right={
        <span className="flex items-center justify-end gap-1.5 max-[620px]:justify-start">
          {rec ? <>{formatScore(rec.verification_score)} · {formatCost(rec.cost_usd)}</> : null}
          {!running && (
            <Button variant="outline" size="sm" disabled={busy}
                    onClick={(e) => { stop(e); onStart(r.pr) }}>
              {rec || r.open?.status === 'reviewed' ? t('repo.reReview') : t('repo.reviewNow')}
            </Button>
          )}
          {!running && rec && rec.open_questions > 0 && (
            <Button variant="outline" size="sm" disabled={busy}
                    onClick={(e) => { stop(e); onStart(r.pr, true) }}>
              {t('repo.answerReplies')}
            </Button>
          )}
        </span>
      }
      onClick={() => navigate(`/repos/${owner}/${repo}/pr/${r.pr}`)}
    />
  )
}
