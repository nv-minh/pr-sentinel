import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { PrDetail as Detail, ReviewStatus } from '../api'
import { Citations, Empty, Eyebrow, Ledger, Row, StatusWord, Tile } from '../components'
import { GATE_WORD, formatCost, formatScore } from '../status'

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

export function PrDetail({ owner, repo, pr }: { owner: string; repo: string; pr: number }) {
  const [data, setData] = useState<Detail | null>(null)
  const [status, setStatus] = useState<ReviewStatus | null>(null)
  const [log, setLog] = useState('')
  const [tab, setTab] = useState<TabKey>('claims')
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.pr(owner, repo, pr).then(setData).catch((e) => setError(String(e.message)))
  }, [owner, repo, pr])

  useEffect(load, [load])

  // While a review runs, follow its log; reload the page data when it finishes.
  useEffect(() => {
    let running = true
    const tick = async () => {
      try {
        const s = await api.reviewStatus(owner, repo, pr)
        setStatus((prev) => {
          if (prev?.running && !s.running) load()
          return s
        })
        if (s.running) {
          const l = await api.reviewLog(owner, repo, pr)
          setLog(l.log)
        }
      } catch {
        /* the dashboard keeps working even if one poll fails */
      }
      if (running) setTimeout(tick, 3000)
    }
    tick()
    return () => { running = false }
  }, [owner, repo, pr, load])

  const startReview = async (reply = false) => {
    try {
      await api.startReview(owner, repo, pr, reply)
      setStatus({ running: true, stale: false })
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  if (error) return <div className="notice notice-fail">{error}</div>
  if (!data) return <div className="page-sub">Loading…</div>

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

  return (
    <>
      <h1 className="page-title">
        <span className="font-mono text-ink-muted text-[0.7em]">
          #{pr}
        </span>{' '}
        {data.title || rec?.title || '(no title)'}
      </h1>
      <p className="page-sub">
        {owner}/{repo} · {rec?.author ? `by ${rec.author} · ` : ''}
        {rec?.base} ← {rec?.head} ·{' '}
        <a className="linkish" href={`https://github.com/${owner}/${repo}/pull/${pr}`}>
          open on GitHub
        </a>
      </p>

      {!data.reviewed ? (
        <>
          <div className="notice">This pull request has not been reviewed yet.</div>
          <button className="button" onClick={() => startReview(false)}
                  disabled={status?.running}>
            {status?.running ? 'Reviewing…' : 'Review now'}
          </button>
        </>
      ) : (
        <>
          <div className="tiles">
            <Tile label="Gate" value={<StatusWord status={gate} />} note={GATE_WORD[gate]} />
            <Tile label="Verified" value={formatScore(score.verification_score ?? rec?.verification_score)}
                  note="claims with file:line" />
            <Tile label="Verdict" value={<StatusWord status={rec?.verdict ?? ''} />}
                  note="PR description vs code" />
            <Tile label="Business risk" value={score.business_risk ?? '—'} />
            <Tile label="Rounds" value={rec?.rounds ?? 1} />
            <Tile label="Cost" value={formatCost(rec?.cost_usd)} />
          </div>

          {score.reasons && score.reasons.length > 0 && (
            <div className={gate === 'fail' ? 'notice notice-fail' : 'notice'}>
              Why this gate:
              <ul className="reasons">
                {score.reasons.map((r, i) => <li key={i}>{r}</li>)}
              </ul>
            </div>
          )}

          <div className="toolbar">
            <button className="button" onClick={() => startReview(false)}
                    disabled={status?.running}>
              {status?.running ? 'Reviewing…' : 'Re-review'}
            </button>
            <button className="button button-quiet" onClick={() => startReview(true)}
                    disabled={status?.running}>
              Answer replies
            </button>
            {status?.last?.exit !== undefined && !status.running && (
              <span className="linkish">
                last run exit {status.last.exit} · {status.last.finished_at}
              </span>
            )}
          </div>

          {status?.running && (
            <>
              <Eyebrow>Review in progress</Eyebrow>
              <pre className="log">{log || 'starting…'}</pre>
            </>
          )}

          <div className="tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.key}
                role="tab"
                className="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
              >
                {t.label} <span className="tab-count">{counts[t.key]}</span>
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
