import { useEffect, useState } from 'react'
import { api } from '../api'
import type { RepoRecord } from '../api'
import { Empty, ErrorNotice, Eyebrow, Ledger, Loading, PageSub, PageTitle, Row } from '../components'
import { formatCost, formatScore } from '../status'
import { navigate } from '../router'

export function Repos() {
  const [repos, setRepos] = useState<RepoRecord[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.repos().then((d) => setRepos(d.repos)).catch((e) => setError(String(e.message)))
  }, [])

  if (error) return <ErrorNotice message={`Could not load repos — ${error}`} />
  if (!repos) return <Loading label="Loading repositories" />

  const reviewed = repos.filter((r) => r.has_data)
  const waiting = repos.filter((r) => !r.has_data)

  return (
    <>
      <PageTitle>Every claim, checked against the code.</PageTitle>
      <PageSub>
        {reviewed.length} repo{reviewed.length === 1 ? '' : 's'} reviewed ·{' '}
        {reviewed.reduce((n, r) => n + r.prs_total, 0)} pull requests on the record
      </PageSub>

      <Eyebrow>Reviewed repositories</Eyebrow>
      <Ledger>
        {reviewed.length === 0 ? (
          <Empty>
            No reviews yet. Run <code>python -m src.run owner/repo 123</code>, or add a repo
            on the Config page and let the poller pick it up.
          </Empty>
        ) : (
          reviewed.map((r) => (
            <Row
              key={`${r.owner}/${r.repo}`}
              status={r.gate_count?.fail ? 'FAIL' : r.gate_count?.warn ? 'PARTIAL' : 'PASS'}
              title={`${r.owner}/${r.repo}`}
              meta={
                <>
                  {r.prs_total} PR · {r.bugs_total} bugs · {r.doc_errors_total} doc errors
                  {r.breaking_total ? ` · ${r.breaking_total} breaking` : ''}
                  {r.test_gaps_total ? ` · ${r.test_gaps_total} test gaps` : ''}
                </>
              }
              right={
                <>
                  {formatScore(r.avg_verification_score)} verified<br />
                  {formatCost(r.cost_total)}
                </>
              }
              onClick={() => navigate(`/repos/${r.owner}/${r.repo}`)}
            />
          ))
        )}
      </Ledger>

      {waiting.length > 0 && (
        <>
          <Eyebrow>Watched, not yet reviewed</Eyebrow>
          <Ledger>
            {waiting.map((r) => (
              <Row
                key={`${r.owner}/${r.repo}`}
                status="UNVERIFIED"
                title={`${r.owner}/${r.repo}`}
                meta="Set to auto — the poller reviews its next open PR"
                right="AUTO"
                onClick={() => navigate(`/repos/${r.owner}/${r.repo}`)}
              />
            ))}
          </Ledger>
        </>
      )}
    </>
  )
}
