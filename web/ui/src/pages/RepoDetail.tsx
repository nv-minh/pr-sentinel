import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { RepoRecord } from '../api'
import {
  Empty, ErrorNotice, Eyebrow, GateBand, Ledger, Loading, Notice, PageSub, PageTitle, Row, Tile,
  Tiles,
} from '../components'
import { formatCost, formatScore } from '../status'
import { navigate } from '../router'
import { Button } from '@/components/ui/button'

const STATUS_LABEL: Record<string, string> = {
  reviewed: 'Reviewed',
  reviewing: 'Reviewing now',
  not_reviewed: 'Not reviewed',
}

export function RepoDetail({ owner, repo }: { owner: string; repo: string }) {
  const [data, setData] = useState<RepoRecord | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  const load = useCallback(() => {
    api.repo(owner, repo).then(setData).catch((e) => setError(String(e.message)))
  }, [owner, repo])

  useEffect(load, [load])

  const review = async (pr: number) => {
    setBusy(pr)
    try {
      await api.startReview(owner, repo, pr)
      navigate(`/repos/${owner}/${repo}/pr/${pr}`)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(null)
    }
  }

  if (error && !data) return <ErrorNotice message={error} />
  if (!data) return <Loading label="Loading repository" />

  const byPr = new Map(data.prs.map((p) => [p.pr, p]))
  const unavailable = data.open_prs.some((row) => row.unavailable)

  return (
    <>
      <PageTitle>{owner}/{repo}</PageTitle>
      <PageSub>
        <a className="text-brand hover:underline" href={`https://github.com/${owner}/${repo}`}>
          github.com/{owner}/{repo}
        </a>
      </PageSub>

      {error && <Notice tone="fail">{error}</Notice>}

      <Tiles>
        <Tile label="PRs reviewed" value={data.prs_total} />
        <Tile label="Verified" value={formatScore(data.avg_verification_score)}
              note="claims backed by file:line" />
        <Tile label="Bugs" value={data.bugs_total} note="failed claims + broken impact" />
        <Tile label="Doc errors" value={data.doc_errors_total} />
        <Tile label="Breaking" value={data.breaking_total} note="API + schema contracts" />
        <Tile label="Spent" value={formatCost(data.cost_total)} />
      </Tiles>

      <Eyebrow>Merge decisions</Eyebrow>
      <GateBand counts={data.gate_count} />

      <Eyebrow>Open pull requests</Eyebrow>
      {unavailable && (
        <Notice>
          GitHub is unreachable — showing pull requests from stored reviews only.
        </Notice>
      )}
      <Ledger>
        {data.open_prs.length === 0 ? (
          <Empty>No open pull requests.</Empty>
        ) : (
          data.open_prs.map((row) => {
            const rec = byPr.get(row.pr)
            return (
              <Row
                key={row.pr}
                status={rec?.gate ? rec.gate : row.status === 'reviewed' ? 'PASS' : 'UNVERIFIED'}
                title={
                  <>
                    <span className="font-mono text-ink-muted">
                      #{row.pr}
                    </span>{' '}
                    {row.title || '(no title)'} {row.draft ? '· draft' : ''}
                  </>
                }
                meta={
                  <>
                    {STATUS_LABEL[row.status]}
                    {row.rounds ? ` · ${row.rounds} round${row.rounds > 1 ? 's' : ''}` : ''}
                    {rec ? ` · ${rec.bugs} bugs · ${rec.doc_errors} doc errors` : ''}
                    {rec?.breaking ? ` · ${rec.breaking} breaking` : ''}
                  </>
                }
                right={
                  <>
                    {rec ? formatScore(rec.verification_score) : '—'}{' '}
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy === row.pr || row.status === 'reviewing'}
                      onClick={(e) => { e.stopPropagation(); review(row.pr) }}
                    >
                      {row.status === 'reviewed' ? 'Re-review' : 'Review now'}
                    </Button>
                  </>
                }
                onClick={() => navigate(`/repos/${owner}/${repo}/pr/${row.pr}`)}
              />
            )
          })
        )}
      </Ledger>
    </>
  )
}
