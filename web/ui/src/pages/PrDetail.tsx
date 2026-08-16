import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { PrDetail as Detail, Pipeline, ReviewStatus } from '../api'
import {
  Citations, Empty, ErrorNotice, Eyebrow, Ledger, Loading, Notice, Row,
  StatusWord, Tile, Tiles,
} from '../components'
import { NODE_TAB } from '../graph/layout'
import { GATE_WORD, formatCost, formatScore } from '../status'

// React Flow is ~100 kB gzipped and only this route needs it.
const PipelineGraph = lazy(() => import('../graph/PipelineGraph'))

type TabKey =
  | 'claims' | 'docs' | 'impact' | 'callers' | 'contracts' | 'tests'
  | 'threads' | 'confirm' | 'context'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'claims', label: 'Claims' },
  { key: 'docs', label: 'Docs' },
  { key: 'impact', label: 'Impact' },
  { key: 'callers', label: 'Callers' },
  { key: 'contracts', label: 'Contracts' },
  { key: 'tests', label: 'Tests' },
  { key: 'threads', label: 'Threads' },
  { key: 'confirm', label: 'Confirm' },
  { key: 'context', label: 'Context' },
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
  label: string
  pick: (d: Detail) => { status: string; title: string; detail: string }[]
}[] = [
  { tab: 'contracts', label: 'Contract',
    pick: (d) => (d.contracts ?? [])
      .filter((c) => c.status !== 'COMPATIBLE')
      .map((c) => ({ status: c.status, title: c.path, detail: c.detail })) },
  { tab: 'callers', label: 'Caller',
    pick: (d) => (d.callers ?? [])
      .filter((c) => c.risk === 'BROKEN')
      .map((c) => ({ status: c.risk, title: c.symbol, detail: c.note })) },
  { tab: 'claims', label: 'Claim',
    pick: (d) => (d.claims ?? [])
      .filter((c) => c.status === 'FAIL')
      .map((c) => ({ status: c.status, title: c.text || c.id, detail: c.note })) },
  { tab: 'impact', label: 'Impact',
    pick: (d) => (d.impact ?? [])
      .filter((i) => i.impact === 'BROKEN')
      .map((i) => ({ status: i.impact, title: i.requirement, detail: i.detail })) },
  { tab: 'docs', label: 'Doc',
    pick: (d) => (d.docs ?? [])
      .filter((x) => x.status === 'WRONG' || x.status === 'FABRICATED')
      .map((x) => ({ status: x.status, title: x.path, detail: x.what })) },
  { tab: 'tests', label: 'Test',
    pick: (d) => (d.tests ?? [])
      .filter((t) => t.assertion_quality === 'MISSING')
      .map((t) => ({ status: t.assertion_quality, title: t.target, detail: t.note })) },
]

export function PrDetail({ owner, repo, pr }: { owner: string; repo: string; pr: number }) {
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
      setStatus({ running: true, stale: false })
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  if (error) return <ErrorNotice message={error} />
  if (!data) return <Loading label="Loading the PR" />

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
      <h1 className="mb-1.5 text-[clamp(28px,4vw,40px)] font-[680] leading-[1.08] tracking-[-0.025em]">
        <span className="font-mono text-ink-muted text-[0.7em]">
          #{pr}
        </span>{' '}
        {data.title || rec?.title || '(no title)'}
      </h1>
      <p className="mb-7 font-mono text-[12.5px] tracking-[0.02em] text-ink-muted">
        {owner}/{repo} · {rec?.author ? `by ${rec.author} · ` : ''}
        {rec?.base} ← {rec?.head} ·{' '}
        <a className="text-brand hover:underline" href={`https://github.com/${owner}/${repo}/pull/${pr}`}>
          open on GitHub
        </a>
      </p>

      {!data.reviewed ? (
        <>
          <Notice>This pull request has not been reviewed yet.</Notice>
          <Button onClick={() => startReview(false)} disabled={status?.running}>
            {status?.running ? 'Reviewing…' : 'Review now'}
          </Button>
        </>
      ) : (
        <>
          <Tiles>
            <Tile label="Gate" value={<StatusWord status={gate} />} note={GATE_WORD[gate]} />
            <Tile label="Verified" value={formatScore(score.verification_score ?? rec?.verification_score)}
                  note="claims with file:line" />
            <Tile label="Verdict" value={<StatusWord status={rec?.verdict ?? ''} />}
                  note="PR description vs code" />
            <Tile label="Business risk" value={score.business_risk ?? '—'} />
            <Tile label="Rounds" value={rec?.rounds ?? 1} />
            <Tile label="Cost" value={formatCost(rec?.cost_usd)} />
          </Tiles>

          <Eyebrow>Pipeline</Eyebrow>
          {pipeline?.nodes?.length ? (
            <Suspense fallback={<Loading label="Loading the pipeline" />}>
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
            <Notice>No pipeline data for this review yet.</Notice>
          )}

          {score.reasons && score.reasons.length > 0 && (
            <Notice tone={gate === 'fail' ? 'fail' : 'info'}>
              Why this gate:
              <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
                {score.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </Notice>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={() => startReview(false)} disabled={status?.running}>
              {status?.running ? 'Reviewing…' : 'Re-review'}
            </Button>
            <Button variant="outline" onClick={() => startReview(true)} disabled={status?.running}>
              Answer replies
            </Button>
            {status?.last?.exit !== undefined && !status.running && (
              <span className="font-mono text-xs text-ink-muted">
                last run exit {status.last.exit} · {status.last.finished_at}
              </span>
            )}
          </div>

          {status?.running && (
            <>
              <Eyebrow>Review in progress</Eyebrow>
              <pre className="max-h-[260px] overflow-auto rounded border border-hairline bg-surface px-3.5 py-3 font-mono text-xs whitespace-pre-wrap text-ink-muted">
                {log || 'starting…'}
              </pre>
            </>
          )}

          {blocking.length > 0 && (
            <>
              <Eyebrow>Blocking ({blocking.length})</Eyebrow>
              <Ledger>
                {blocking.map((item, i) => (
                  <Row
                    key={`${item.tab}-${i}`}
                    status={item.status}
                    title={<>{item.title} <StatusWord status={item.status} /></>}
                    meta={item.detail}
                    right={item.label}
                    onClick={() => setTab(item.tab)}
                  />
                ))}
              </Ledger>
            </>
          )}

          <div className="tabs mt-7 mb-1 flex flex-wrap gap-1 border-b border-hairline-strong" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                className="tab border-b-2 border-transparent px-2.5 py-2 font-mono text-xs uppercase tracking-[0.06em] text-ink-muted aria-selected:border-brand aria-selected:text-ink"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
              >
                {t.label} <span className="tabular-nums">{counts[t.key]}</span>
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
              : <Empty>The description made no verifiable claims.</Empty>)}

            {tab === 'docs' && (data.docs?.length
              ? data.docs.map((d, i) => (
                  <Row key={i} status={d.status}
                       title={<>{d.path} <StatusWord status={d.status} /></>}
                       meta={d.what} />
                ))
              : <Empty>No documentation related to this change was found.</Empty>)}

            {tab === 'impact' && (data.impact?.length
              ? data.impact.map((it, i) => (
                  <Row key={i} status={it.impact}
                       title={<>{it.requirement} <StatusWord status={it.impact} /></>}
                       meta={it.detail}
                       right={[it.requirement_source, it.area].filter(Boolean).join(' · ')} />
                ))
              : <Empty>No requirement was traced to this change.</Empty>)}

            {tab === 'callers' && (data.callers?.length
              ? data.callers.map((c, i) => (
                  <Row key={i} status={c.risk}
                       title={<>{c.symbol} <StatusWord status={c.risk} /></>}
                       meta={<><Citations items={c.callers} /> {c.note}</>}
                       right={c.defined_at} />
                ))
              : <Empty>Nothing outside this diff calls the changed code.</Empty>)}

            {tab === 'contracts' && (data.contracts?.length
              ? data.contracts.map((c, i) => (
                  <Row key={i} status={c.status}
                       title={<>{c.path} <StatusWord status={c.status} /></>}
                       meta={c.detail} right={c.kind} />
                ))
              : <Empty>No API, schema, type or proto contract was touched.</Empty>)}

            {tab === 'tests' && (data.tests?.length
              ? data.tests.map((t, i) => (
                  <Row key={i} status={t.assertion_quality}
                       title={<>{t.target} <StatusWord status={t.assertion_quality} /></>}
                       meta={
                         t.uncovered_edge_cases?.length
                           ? t.uncovered_edge_cases.map((e, j) => (
                               <div key={j}>uncovered: {e.case} → {e.where}</div>))
                           : t.note
                       } />
                ))
              : <Empty>No test coverage was assessed for this change.</Empty>)}

            {tab === 'threads' && (data.threads?.length
              ? data.threads.map((t, i) => (
                  <Row key={i} status={t.status}
                       title={<>{t.text} <StatusWord status={t.status} /></>}
                       meta={t.note} />
                ))
              : <Empty>No review comments to re-check.</Empty>)}

            {tab === 'confirm' && (data.answers?.length
              ? data.answers.map((a, i) => (
                  <Row key={i} status={a.answer === 'SKIPPED' ? 'UNVERIFIED' : 'PASS'}
                       title={a.question} meta={`answered: ${a.answer}`} right={a.kind} />
                ))
              : <Empty>The reviewer had no questions for a human.</Empty>)}

            {tab === 'context' && (data.pruned?.length
              ? data.pruned.map((p, i) => (
                  <Row key={i} status={p.dropped ? 'UNVERIFIED' : 'PARTIAL'}
                       title={p.filename} meta={p.reason}
                       right={p.dropped ? 'dropped' : 'patch trimmed'} />
                ))
              : <Empty>The whole diff went into the review — nothing was trimmed.</Empty>)}
          </Ledger>

          {data.replies && data.replies.length > 0 && (
            <>
              <Eyebrow>Replies answered</Eyebrow>
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
