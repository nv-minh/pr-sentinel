import { useEffect, useState } from 'react'
import { api } from '../api'
import type { RepoRecord } from '../api'
import { Empty, ErrorNotice, Eyebrow, Ledger, Loading, PageSub, PageTitle, Row } from '../components'
import { useT } from '../i18n'
import { formatCost, formatScore } from '../status'
import { navigate } from '../router'

export function Repos() {
  const t = useT()
  const [repos, setRepos] = useState<RepoRecord[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.repos().then((d) => setRepos(d.repos)).catch((e) => setError(String(e.message)))
  }, [])

  if (error) return <ErrorNotice message={t('repos.error', { detail: error })} />
  if (!repos) return <Loading label={t('repos.loading')} />

  const reviewed = repos.filter((r) => r.has_data)
  const waiting = repos.filter((r) => !r.has_data)

  return (
    <>
      <PageTitle>{t('repos.title')}</PageTitle>
      <PageSub>
        {reviewed.length === 1
          ? t('repos.subOne', { n: reviewed.length })
          : t('repos.subMany', { n: reviewed.length })} ·{' '}
        {t('repos.subPrs', { n: reviewed.reduce((n, r) => n + r.prs_total, 0) })}
      </PageSub>

      <Eyebrow>{t('repos.reviewedHeading')}</Eyebrow>
      <Ledger>
        {reviewed.length === 0 ? (
          <Empty>
            {t('repos.emptyBefore')}<code>python -m src.run owner/repo 123</code>
            {t('repos.emptyAfter')}
          </Empty>
        ) : (
          reviewed.map((r) => (
            <Row
              key={`${r.owner}/${r.repo}`}
              status={r.gate_count?.fail ? 'FAIL' : r.gate_count?.warn ? 'PARTIAL' : 'PASS'}
              title={`${r.owner}/${r.repo}`}
              meta={
                <>
                  {t('repos.prs', { n: r.prs_total })} · {t('repos.bugs', { n: r.bugs_total })} ·{' '}
                  {t('repos.docErrors', { n: r.doc_errors_total })}
                  {r.breaking_total ? ` · ${t('repos.breaking', { n: r.breaking_total })}` : ''}
                  {r.test_gaps_total ? ` · ${t('repos.testGaps', { n: r.test_gaps_total })}` : ''}
                </>
              }
              right={
                <>
                  {t('repos.verified', { score: formatScore(r.avg_verification_score) })}<br />
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
          <Eyebrow>{t('repos.waitingHeading')}</Eyebrow>
          <Ledger>
            {waiting.map((r) => (
              <Row
                key={`${r.owner}/${r.repo}`}
                status="UNVERIFIED"
                title={`${r.owner}/${r.repo}`}
                meta={t('repos.waitingMeta')}
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
