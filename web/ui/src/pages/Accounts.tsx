import { useCallback, useEffect, useState } from 'react'
import type { GithubAccount, GithubPr, GithubRepo } from '../api'
import { api } from '../api'
import {
  Empty, Eyebrow, Ledger, Loading, Notice, PageSub, PageTitle, Row,
} from '../components'
import { useT } from '../i18n'
import type { Key } from '../strings'
import { navigate } from '../router'
import { Button } from '@/components/ui/button'

const STATUS_KEY: Record<string, Key> = {
  reviewed: 'repo.statusReviewed',
  reviewing: 'repo.statusReviewing',
  not_reviewed: 'repo.statusNotReviewed',
}

export function Accounts() {
  const t = useT()
  const [accounts, setAccounts] = useState<GithubAccount[] | null>(null)
  const [ghAvailable, setGhAvailable] = useState(true)
  const [repos, setRepos] = useState<GithubRepo[] | null>(null)
  const [truncated, setTruncated] = useState(false)
  const [fetching, setFetching] = useState(false)
  const [token, setToken] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [open, setOpen] = useState<string>('')
  const [watched, setWatched] = useState<string[]>([])

  /** The whole point of the page: connecting an account fetches its projects
   *  without a second click, and switching accounts refetches. */
  const loadRepos = useCallback(async () => {
    setFetching(true)
    try {
      const data = await api.githubRepos()
      setRepos(data.repos)
      setTruncated(data.truncated)
      setError('')
    } catch (e) {
      // Left null, not []: an empty list renders "nothing open", which would
      // contradict the error notice this sets.
      setRepos(null)
      setError(String((e as Error).message))
    } finally {
      setFetching(false)
    }
  }, [])

  const loadAccounts = useCallback(async () => {
    const data = await api.githubAccounts()
    setAccounts(data.accounts)
    setGhAvailable(data.gh_available)
    return data
  }, [])

  useEffect(() => {
    loadAccounts()
      .then((data) => { if (data.active) loadRepos() })
      .catch((e) => { setAccounts([]); setError(String(e.message)) })
  }, [loadAccounts, loadRepos])

  const act = async (label: string, fn: () => Promise<unknown>) => {
    setBusy(label)
    try {
      await fn()
      setError('')
      const data = await loadAccounts()
      if (data.active) await loadRepos()
      else setRepos(null)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy('')
    }
  }

  const watch = async (name: string) => {
    setBusy(`watch:${name}`)
    try {
      await api.addRepo(name, 'auto')
      setWatched((prev) => [...prev, name])
      setError('')
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy('')
    }
  }

  const connect = () =>
    act('connect', async () => {
      await api.addGithubAccount(token.trim())
      setToken('')
    })

  const review = async (repo: GithubRepo, pr: number) => {
    setBusy(`review:${repo.owner}/${repo.repo}#${pr}`)
    try {
      await api.startReview(repo.owner, repo.repo, pr)
      navigate(`/repos/${repo.owner}/${repo.repo}/pr/${pr}`)
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy('')
    }
  }

  if (!accounts) return <Loading label={t('accounts.loading')} />

  const active = accounts.find((a) => a.active)
  const withPrs = (repos ?? []).filter((r) => r.open_pr_count > 0)
  const idle = (repos ?? []).filter((r) => r.open_pr_count === 0)

  return (
    <>
      <PageTitle>{t('accounts.title')}</PageTitle>
      <PageSub>{t('accounts.sub')}</PageSub>

      {error && <Notice tone="fail">{error}</Notice>}
      {!ghAvailable && <Notice tone="fail">{t('accounts.noGhCli')}</Notice>}

      <Eyebrow>{t('accounts.connectHeading')}</Eyebrow>
      <div className="my-2.5 flex flex-wrap items-center gap-2.5">
        <input
          type="password"
          autoComplete="off"
          className="w-[320px] max-w-full rounded border border-input bg-surface px-2 py-1.5 font-mono text-xs text-ink"
          value={token}
          placeholder={t('accounts.tokenPlaceholder')}
          aria-label={t('accounts.tokenAria')}
          onChange={(e) => setToken(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && token.trim()) connect() }}
        />
        <Button disabled={!token.trim() || busy === 'connect'} onClick={connect}>
          {busy === 'connect' ? t('accounts.connecting') : t('accounts.connect')}
        </Button>
      </div>
      <Notice>{t('accounts.tokenNote')}</Notice>

      <Eyebrow>{t('accounts.accountsHeading')}</Eyebrow>
      <Ledger>
        {accounts.length === 0 ? (
          <Empty>{t('accounts.noAccounts')}</Empty>
        ) : (
          accounts.map((a) => (
            <Row
              key={a.login}
              status={a.active ? 'PASS' : 'UNVERIFIED'}
              title={a.login}
              meta={a.active ? t('accounts.activeMeta') : t('accounts.idleMeta')}
              right={
                <>
                  {!a.active && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={Boolean(busy)}
                      onClick={() => act(`switch:${a.login}`,
                        () => api.setActiveGithubAccount(a.login))}
                    >
                      {t('accounts.use')}
                    </Button>
                  )}{' '}
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={Boolean(busy)}
                    onClick={() => act(`remove:${a.login}`,
                      () => api.removeGithubAccount(a.login))}
                  >
                    {t('accounts.disconnect')}
                  </Button>
                </>
              }
            />
          ))
        )}
      </Ledger>

      {active && (
        <>
          <Eyebrow>{t('accounts.projectsHeading')}</Eyebrow>
          {repos === null ? (
            // null means "no list to show": either still fetching, or the
            // fetch failed and the error notice above is already saying so.
            fetching ? <Loading label={t('accounts.fetching')} /> : null
          ) : (
            <>
              <div className="my-2.5 flex flex-wrap items-center gap-2.5">
                <Button variant="outline" size="sm" disabled={fetching}
                        onClick={loadRepos}>
                  {t('accounts.refresh')}
                </Button>
                <span className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted">
                  {t('accounts.summary', {
                    login: active.login,
                    repos: withPrs.length,
                    prs: withPrs.reduce((n, r) => n + r.open_pr_count, 0),
                  })}
                </span>
              </div>
              {truncated && (
                <Notice>{t('accounts.listTruncated', { n: (repos ?? []).length })}</Notice>
              )}
              <Ledger>
                {withPrs.length === 0 ? (
                  <Empty>{t('accounts.noOpenPrs')}</Empty>
                ) : (
                  withPrs.map((r) => {
                    const name = `${r.owner}/${r.repo}`
                    const expanded = open === name
                    return (
                      <div key={name}>
                        <Row
                          status={r.reviewed_count === r.open_pr_count ? 'PASS' : 'PARTIAL'}
                          title={name}
                          meta={
                            <>
                              {t('accounts.repoOpen', { n: r.open_pr_count })} ·{' '}
                              {t('accounts.repoReviewed', { n: r.reviewed_count })}
                              {r.private ? ` · ${t('accounts.private')}` : ''}
                              {r.truncated ? ` · ${t('accounts.repoTruncated', { n: r.prs.length })}` : ''}
                            </>
                          }
                          right={
                            <>
                              {expanded ? t('accounts.hide') : t('accounts.show')}{' '}
                              <Button
                                variant="outline"
                                size="sm"
                                disabled={busy === `watch:${name}` || watched.includes(name)}
                                onClick={(e) => { e.stopPropagation(); watch(name) }}
                              >
                                {watched.includes(name)
                                  ? t('accounts.watching')
                                  : t('accounts.watch')}
                              </Button>
                            </>
                          }
                          expanded={expanded}
                          onClick={() => setOpen(expanded ? '' : name)}
                        />
                        {expanded && (
                          <div className="border-l-2 border-hairline-strong pl-3.5">
                            {r.prs.map((pr: GithubPr) => (
                              <Row
                                key={pr.pr}
                                status={pr.status === 'reviewed' ? 'PASS' : 'UNVERIFIED'}
                                title={
                                  <>
                                    <span className="font-mono text-ink-muted">#{pr.pr}</span>{' '}
                                    {pr.title || t('common.noTitle')}
                                    {pr.draft ? ` · ${t('repo.draft')}` : ''}
                                  </>
                                }
                                meta={
                                  <>
                                    {STATUS_KEY[pr.status] ? t(STATUS_KEY[pr.status]) : pr.status}
                                    {pr.author ? ` · ${pr.author}` : ''}
                                    {pr.status === 'reviewed'
                                      ? ` · ${t('repo.prBugs', { n: pr.bugs ?? 0 })}`
                                      : ''}
                                  </>
                                }
                                right={
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={busy === `review:${name}#${pr.pr}`
                                      || pr.status === 'reviewing'}
                                    onClick={(e) => { e.stopPropagation(); review(r, pr.pr) }}
                                  >
                                    {pr.status === 'reviewed'
                                      ? t('repo.reReview')
                                      : t('repo.reviewNow')}
                                  </Button>
                                }
                                onClick={() =>
                                  navigate(`/repos/${r.owner}/${r.repo}/pr/${pr.pr}`)}
                              />
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })
                )}
              </Ledger>

              {idle.length > 0 && (
                <>
                  <Eyebrow>{t('accounts.idleHeading')}</Eyebrow>
                  <Ledger>
                    {idle.map((r) => (
                      <Row
                        key={`${r.owner}/${r.repo}`}
                        status="UNVERIFIED"
                        title={`${r.owner}/${r.repo}`}
                        meta={t('accounts.noPrsMeta')}
                        onClick={() => navigate(`/repos/${r.owner}/${r.repo}`)}
                      />
                    ))}
                  </Ledger>
                </>
              )}
            </>
          )}
        </>
      )}
    </>
  )
}
