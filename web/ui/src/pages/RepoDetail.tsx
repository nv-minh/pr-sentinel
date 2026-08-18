import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { RepoRecord } from '../api'
import {
  Empty, ErrorNotice, Eyebrow, GateBand, Ledger, Loading, Notice, PageSub, PageTitle, Row, Tile,
  Tiles,
} from '../components'
import { useT } from '../i18n'
import type { Key } from '../strings'
import { formatCost, formatScore } from '../status'
import { navigate } from '../router'
import { Button } from '@/components/ui/button'

const STATUS_KEY: Record<string, Key> = {
  reviewed: 'repo.statusReviewed',
  reviewing: 'repo.statusReviewing',
  not_reviewed: 'repo.statusNotReviewed',
}

export function RepoDetail({ owner, repo }: { owner: string; repo: string }) {
  const t = useT()
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
  if (!data) return <Loading label={t('repo.loading')} />

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

      <Eyebrow>{t('repo.openPrsHeading')}</Eyebrow>
      {unavailable && <Notice>{t('repo.unreachable')}</Notice>}
      <Ledger>
        {data.open_prs.length === 0 ? (
          <Empty>{t('repo.noOpenPrs')}</Empty>
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
                    {row.title || t('common.noTitle')} {row.draft ? `· ${t('repo.draft')}` : ''}
                  </>
                }
                meta={
                  <>
                    {STATUS_KEY[row.status] ? t(STATUS_KEY[row.status]) : row.status}
                    {row.rounds
                      ? ` · ${row.rounds > 1
                          ? t('repo.roundMany', { n: row.rounds })
                          : t('repo.roundOne', { n: row.rounds })}`
                      : ''}
                    {rec ? ` · ${t('repo.prBugs', { n: rec.bugs })} · ${t('repo.prDocErrors', { n: rec.doc_errors })}` : ''}
                    {rec?.breaking ? ` · ${t('repo.prBreaking', { n: rec.breaking })}` : ''}
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
                      {row.status === 'reviewed' ? t('repo.reReview') : t('repo.reviewNow')}
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
