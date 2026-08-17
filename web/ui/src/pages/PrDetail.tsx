import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { PrDetail as Detail, Pipeline, ReviewStatus } from '../api'
import {
  Citations, Empty, ErrorNotice, Eyebrow, Ledger, Loading, Notice, PageSub, PageTitle, Row,
  StatusWord, Tile, Tiles,
} from '../components'
import { NODE_TAB } from '../graph/layout'
import { useT } from '../i18n'
import { formatCost, formatScore } from '../status'
import type { Key } from '../strings'

// React Flow is ~100 kB gzipped and only this route needs it.
const PipelineGraph = lazy(() => import('../graph/PipelineGraph'))

type TabKey =
  | 'claims' | 'docs' | 'impact' | 'callers' | 'contracts' | 'tests'
  | 'threads' | 'confirm' | 'context'

const TABS: { key: TabKey; label: Key }[] = [
  { key: 'claims', label: 'pr.tabClaims' },
  { key: 'docs', label: 'pr.tabDocs' },
  { key: 'impact', label: 'pr.tabImpact' },
  { key: 'callers', label: 'pr.tabCallers' },
  { key: 'contracts', label: 'pr.tabContracts' },
  { key: 'tests', label: 'pr.tabTests' },
  { key: 'threads', label: 'pr.tabThreads' },
  { key: 'confirm', label: 'pr.tabConfirm' },
  { key: 'context', label: 'pr.tabContext' },
]

/** Every finding severe enough to block a merge. All seven blocking statuses
 *  share the same 'fail' tone (see status.ts) — there is no severity field to
 *  sort by, so this is a fixed category order, not a computed one: contracts
 *  and callers first, since an API-breaking change has the widest blast
 *  radius, then claims, impact, docs, tests. Each row answers "why" and links
 *  straight to the tab that has the detail — the point being that a blocking
 *  risk should never be three clicks away. */
const BLOCKING: {
  tab: TabKey
  label: Key
  pick: (d: Detail) => { status: string; title: string; detail: string }[]
}[] = [
  { tab: 'contracts', label: 'pr.blockContract',
    pick: (d) => (d.contracts ?? [])
      .filter((c) => c.status !== 'COMPATIBLE')
      .map((c) => ({ status: c.status, title: c.path, detail: c.detail })) },
  { tab: 'callers', label: 'pr.blockCaller',
    pick: (d) => (d.callers ?? [])
      .filter((c) => c.risk === 'BROKEN')
      .map((c) => ({ status: c.risk, title: c.symbol, detail: c.note })) },
  { tab: 'claims', label: 'pr.blockClaim',
    pick: (d) => (d.claims ?? [])
      .filter((c) => c.status === 'FAIL')
      .map((c) => ({ status: c.status, title: c.text || c.id, detail: c.note })) },
  { tab: 'impact', label: 'pr.blockImpact',
    pick: (d) => (d.impact ?? [])
      .filter((i) => i.impact === 'BROKEN')
      .map((i) => ({ status: i.impact, title: i.requirement, detail: i.detail })) },
  { tab: 'docs', label: 'pr.blockDoc',
    pick: (d) => (d.docs ?? [])
      .filter((x) => x.status === 'WRONG' || x.status === 'FABRICATED')
      .map((x) => ({ status: x.status, title: x.path, detail: x.what })) },
  { tab: 'tests', label: 'pr.blockTest',
    pick: (d) => (d.tests ?? [])
      .filter((t) => t.assertion_quality === 'MISSING')
      .map((t) => ({ status: t.assertion_quality, title: t.target, detail: t.note })) },
]

export function PrDetail({ owner, repo, pr }: { owner: string; repo: string; pr: number }) {
  const t = useT()
  const [data, setData] = useState<Detail | null>(null)
  const [status, setStatus] = useState<ReviewStatus | null>(null)
  const [log, setLog] = useState('')
  const [tab, setTab] = useState<TabKey>('claims')
  const [error, setError] = useState('')
  const [pipeline, setPipeline] = useState<Pipeline | null>(null)
  const [phase, setPhase] = useState<string | null>(null)

  const load = useCallback(() => {
    api.pr(owner, repo, pr).then(setData).catch((e) => setError(String(e.message)))
  }, [owner, repo, pr])

  const loadGraph = useCallback(() => {
    api.graph(owner, repo, pr).then(setPipeline).catch(() => setPipeline(null))
  }, [owner, repo, pr])

  useEffect(load, [load])
  useEffect(loadGraph, [loadGraph])

  // While a review runs, follow its log and the pipeline graph; reload the
  // page data (and the graph) when it finishes.
  useEffect(() => {
    let running = true
    const tick = async () => {
      try {
        const s = await api.reviewStatus(owner, repo, pr)
        setStatus((prev) => {
          if (prev?.running && !s.running) { load(); loadGraph() }
          return s
        })
        if (s.running) {
          const l = await api.reviewLog(owner, repo, pr)
          setLog(l.log)
          loadGraph()
        }
      } catch {
        /* the dashboard keeps working even if one poll fails */
      }
      if (running) setTimeout(tick, 3000)
    }
    tick()
    return () => { running = false }
  }, [owner, repo, pr, load, loadGraph])

  const startReview = async (reply = false) => {
    try {
      await api.startReview(owner, repo, pr, reply)
      setError('')
      setStatus({ running: true, stale: false })
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  if (error && !data) return <ErrorNotice message={error} />
  if (!data) return <Loading label={t('pr.loading')} />

  const rec = data.pr
  const score = data.score ?? {}
  const gate = score.gate ?? 'unknown'
  const counts: Record<TabKey, number> = {
    claims: data.claims?.length ?? 0,
    docs: data.docs?.length ?? 0,
    impact: data.impact?.length ?? 0,
    callers: data.callers?.length ?? 0,
    contracts: data.contracts?.length ?? 0,
    tests: data.tests?.length ?? 0,
    threads: data.threads?.length ?? 0,
    confirm: data.answers?.length ?? 0,
    context: data.pruned?.length ?? 0,
  }
  const blocking = BLOCKING.flatMap((group) =>
    group.pick(data).map((item) => ({ ...item, ...group })))

  return (
    <>
      <PageTitle>
        <span className="font-mono text-ink-muted text-[0.7em]">
          #{pr}
        </span>{' '}
        {data.title || rec?.title || t('common.noTitle')}
      </PageTitle>
      <PageSub>
        {owner}/{repo} · {rec?.author ? `${t('pr.by', { author: rec.author })} · ` : ''}
        {rec?.base} ← {rec?.head} ·{' '}
        <a className="text-brand hover:underline" href={`https://github.com/${owner}/${repo}/pull/${pr}`}>
          {t('pr.openOnGitHub')}
        </a>
      </PageSub>

      {error && <Notice tone="fail">{error}</Notice>}

      {!data.reviewed ? (
        <>
          <Notice>{t('pr.notReviewed')}</Notice>
          <Button onClick={() => startReview(false)} disabled={status?.running}>
            {status?.running ? t('pr.reviewing') : t('pr.reviewNow')}
          </Button>
        </>
      ) : (
        <>
          <Tiles>
            <Tile label={t('pr.tileGate')} value={<StatusWord status={gate} />} note={t(`gate.${gate}` as Key)} />
            <Tile label={t('pr.tileVerified')} value={formatScore(score.verification_score ?? rec?.verification_score)}
                  note={t('pr.tileVerifiedNote')} />
            <Tile label={t('pr.tileVerdict')} value={<StatusWord status={rec?.verdict ?? ''} />}
                  note={t('pr.tileVerdictNote')} />
            <Tile label={t('pr.tileRisk')} value={score.business_risk ?? '—'} />
            <Tile label={t('pr.tileRounds')} value={rec?.rounds ?? 1} />
            <Tile label={t('pr.tileCost')} value={formatCost(rec?.cost_usd)} />
          </Tiles>

          <Eyebrow>{t('pr.pipelineHeading')}</Eyebrow>
          {pipeline?.nodes?.length ? (
            <Suspense fallback={<Loading label={t('pr.pipelineLoading')} />}>
              <PipelineGraph
                pipeline={pipeline}
                selected={phase}
                onSelect={(id) => {
                  setPhase(id)
                  const next = NODE_TAB[id]
                  if (next) setTab(next as TabKey)
                }}
              />
            </Suspense>
          ) : (
            <Notice>{t('pr.noPipeline')}</Notice>
          )}

          {score.reasons && score.reasons.length > 0 && (
            <Notice tone={gate === 'fail' ? 'fail' : 'info'}>
              {t('pr.whyGate')}
              <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
                {score.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </Notice>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => startReview(false)} disabled={status?.running}>
              {status?.running ? t('pr.reviewing') : t('pr.reReview')}
            </Button>
            <Button variant="outline" onClick={() => startReview(true)} disabled={status?.running}>
              {t('pr.answerReplies')}
            </Button>
            {status?.last?.exit !== undefined && !status.running && (
              <span className="font-mono text-xs text-ink-muted">
                {t('pr.lastRun', { code: status.last.exit, at: status.last.finished_at ?? '' })}
              </span>
            )}
          </div>

          {status?.running && (
            <>
              <Eyebrow>{t('pr.inProgressHeading')}</Eyebrow>
              <pre className="max-h-[260px] overflow-auto rounded border border-hairline bg-surface px-3.5 py-3 font-mono text-xs whitespace-pre-wrap text-ink-muted">
                {log || t('pr.starting')}
              </pre>
            </>
          )}

          {blocking.length > 0 && (
            <>
              <Eyebrow>{t('pr.blockingHeading', { n: blocking.length })}</Eyebrow>
              <Ledger>
                {blocking.map((item, i) => (
                  <Row
                    key={`${item.tab}-${i}`}
                    status={item.status}
                    title={<>{item.title} <StatusWord status={item.status} /></>}
                    meta={item.detail}
                    right={t(item.label)}
                    onClick={() => setTab(item.tab)}
                  />
                ))}
              </Ledger>
            </>
          )}

          <div className="tabs mt-7 mb-1 flex flex-wrap gap-1 border-b border-hairline-strong" role="tablist">
            {TABS.map((item) => (
              <button
                key={item.key}
                role="tab"
                className="tab border-b-2 border-transparent px-2.5 py-2 font-mono text-xs uppercase tracking-[0.06em] text-ink-muted aria-selected:border-brand aria-selected:text-ink"
                aria-selected={tab === item.key}
                onClick={() => setTab(item.key)}
              >
                {t(item.label)} <span className="tabular-nums">{counts[item.key]}</span>
              </button>
            ))}
          </div>

          <Ledger>
            {tab === 'claims' && (data.claims?.length
              ? data.claims.map((c) => (
                  <Row key={c.id} status={c.status}
                       title={<>{c.text || c.id} <StatusWord status={c.status} /></>}
                       meta={<Citations items={c.evidence} />}
                       right={c.category} />
                ))
              : <Empty>{t('pr.emptyClaims')}</Empty>)}

            {tab === 'docs' && (data.docs?.length
              ? data.docs.map((d, i) => (
                  <Row key={i} status={d.status}
                       title={<>{d.path} <StatusWord status={d.status} /></>}
                       meta={d.what} />
                ))
              : <Empty>{t('pr.emptyDocs')}</Empty>)}

            {tab === 'impact' && (data.impact?.length
              ? data.impact.map((it, i) => (
                  <Row key={i} status={it.impact}
                       title={<>{it.requirement} <StatusWord status={it.impact} /></>}
                       meta={it.detail}
                       right={[it.requirement_source, it.area].filter(Boolean).join(' · ')} />
                ))
              : <Empty>{t('pr.emptyImpact')}</Empty>)}

            {tab === 'callers' && (data.callers?.length
              ? data.callers.map((c, i) => (
                  <Row key={i} status={c.risk}
                       title={<>{c.symbol} <StatusWord status={c.risk} /></>}
                       meta={<><Citations items={c.callers} /> {c.note}</>}
                       right={c.defined_at} />
                ))
              : <Empty>{t('pr.emptyCallers')}</Empty>)}

            {tab === 'contracts' && (data.contracts?.length
              ? data.contracts.map((c, i) => (
                  <Row key={i} status={c.status}
                       title={<>{c.path} <StatusWord status={c.status} /></>}
                       meta={c.detail} right={c.kind} />
                ))
              : <Empty>{t('pr.emptyContracts')}</Empty>)}

            {tab === 'tests' && (data.tests?.length
              ? data.tests.map((test, i) => (
                  <Row key={i} status={test.assertion_quality}
                       title={<>{test.target} <StatusWord status={test.assertion_quality} /></>}
                       meta={
                         test.uncovered_edge_cases?.length
                           ? test.uncovered_edge_cases.map((e, j) => (
                               <div key={j}>{t('pr.uncovered', { case: e.case, where: e.where })}</div>))
                           : test.note
                       } />
                ))
              : <Empty>{t('pr.emptyTests')}</Empty>)}

            {tab === 'threads' && (data.threads?.length
              ? data.threads.map((thread, i) => (
                  <Row key={i} status={thread.status}
                       title={<>{thread.text} <StatusWord status={thread.status} /></>}
                       meta={thread.note} />
                ))
              : <Empty>{t('pr.emptyThreads')}</Empty>)}

            {tab === 'confirm' && (data.answers?.length
              ? data.answers.map((a, i) => (
                  <Row key={i} status={a.answer === 'SKIPPED' ? 'UNVERIFIED' : 'PASS'}
                       title={a.question} meta={t('pr.answered', { answer: a.answer })} right={a.kind} />
                ))
              : <Empty>{t('pr.emptyConfirm')}</Empty>)}

            {tab === 'context' && (data.pruned?.length
              ? data.pruned.map((p, i) => (
                  <Row key={i} status={p.dropped ? 'UNVERIFIED' : 'PARTIAL'}
                       title={p.filename} meta={p.reason}
                       right={p.dropped ? t('pr.dropped') : t('pr.trimmed')} />
                ))
              : <Empty>{t('pr.emptyContext')}</Empty>)}
          </Ledger>

          {data.replies && data.replies.length > 0 && (
            <>
              <Eyebrow>{t('pr.repliesHeading')}</Eyebrow>
              <Ledger>
                {data.replies.map((r, i) => (
                  <Row key={i} status="PASS" title={r.body}
                       meta={`${r.author} · ${r.source}`} right={r.created_at?.slice(0, 10)} />
                ))}
              </Ledger>
            </>
          )}
        </>
      )}
    </>
  )
}
