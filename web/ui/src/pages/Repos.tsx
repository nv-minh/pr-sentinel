import { useState } from 'react'
import { api } from '../api'
import type { RepoRecord } from '../api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import {
  Empty, ErrorNotice, GateBand, Loading, Notice, PageSub, PageTitle, VerdictChips,
} from '../components'
import { useApi } from '../hooks/useApi'
import { useT } from '../i18n'
import { Link, setQuery, useQuery } from '../router'
import { formatCost, formatScore } from '../status'

/** Two-step destructive button: first click arms it, the second fires.
 * Arming announces itself through the label and disarms after a pause. */
function ConfirmButton({ label, confirmLabel, ariaLabel, onConfirm }: {
  label: string
  confirmLabel: string
  ariaLabel: string
  onConfirm: () => void
}) {
  const [armed, setArmed] = useState(false)
  return (
    <Button
      variant="outline"
      size="sm"
      aria-label={ariaLabel}
      className={armed ? 'border-fail text-fail' : 'text-ink-muted'}
      onClick={() => {
        if (!armed) {
          setArmed(true)
          setTimeout(() => setArmed(false), 4000)
          return
        }
        setArmed(false)
        onConfirm()
      }}
      onBlur={() => setArmed(false)}
    >
      {armed ? confirmLabel : label}
    </Button>
  )
}

function RepoCard({ r, busy, onMode, onRemove }: {
  r: RepoRecord
  busy: boolean
  onMode: (repo: RepoRecord, mode: string) => void
  onRemove: (repo: RepoRecord) => void
}) {
  const t = useT()
  const full = `${r.owner}/${r.repo}`
  const mode = r.mode ?? 'unlisted'
  const nextMode = mode === 'auto' ? 'manual' : 'auto'
  return (
    <Card className="gap-3 rounded-sm border-hairline bg-surface py-4 shadow-none">
      <CardHeader className="gap-1 px-4">
        <div className="flex items-baseline justify-between gap-2">
          <Link to={`/repos/${full}`} className="min-w-0 truncate font-mono text-[15px] font-semibold no-underline hover:underline">
            {full}
          </Link>
          {/* `auto`/`manual` are the literal YAML modes — English by design. */}
          <Badge variant="outline" className="rounded-sm font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
            {mode}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-2 px-4">
        {r.has_data ? (
          <>
            <div className="font-mono text-xs tabular-nums text-ink-muted">
              {t('repos.prs', { n: r.prs_total })} · {t('repos.bugs', { n: r.bugs_total })} ·{' '}
              {t('repos.docErrors', { n: r.doc_errors_total })}
              {r.breaking_total ? ` · ${t('repos.breaking', { n: r.breaking_total })}` : ''}
              {r.test_gaps_total ? ` · ${t('repos.testGaps', { n: r.test_gaps_total })}` : ''}
            </div>
            <GateBand counts={r.gate_count} />
            <div className="flex items-baseline justify-between gap-2">
              <VerdictChips counts={r.verdict_count} />
              <span className="whitespace-nowrap font-mono text-xs tabular-nums text-ink-muted">
                {t('repos.verified', { score: formatScore(r.avg_verification_score) })} · {formatCost(r.cost_total)}
              </span>
            </div>
          </>
        ) : (
          <>
            <div>
              <Badge variant="secondary" className="rounded-sm font-mono text-[10px] uppercase tracking-[0.08em]">
                {t('repos.watched')}
              </Badge>
            </div>
            <p className="text-[13px] text-ink-muted">{t('repos.waitingMeta')}</p>
          </>
        )}
      </CardContent>
      <CardFooter className="justify-end gap-2 px-4">
        <Button
          variant="outline"
          size="sm"
          aria-label={t('config.modeAria', { repo: full })}
          title={t('config.modeAria', { repo: full })}
          disabled={busy}
          className="font-mono text-[11px] uppercase tracking-[0.08em]"
          onClick={() => onMode(r, nextMode)}
        >
          {mode} → {nextMode}
        </Button>
        <ConfirmButton
          label={t('config.remove')}
          confirmLabel={t('repos.removeConfirm')}
          ariaLabel={t('repos.removeAria', { repo: full })}
          onConfirm={() => onRemove(r)}
        />
      </CardFooter>
    </Card>
  )
}

export function Repos() {
  const t = useT()
  const repos = useApi((signal) => api.repos(signal).then((d) => d.repos), [])
  const query = useQuery()
  const [newRepo, setNewRepo] = useState('')
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  const act = async (run: () => Promise<unknown>) => {
    setBusy(true)
    setActionError('')
    try {
      await run()
      repos.refetch()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (repos.error) return <ErrorNotice message={t('repos.error', { detail: repos.error })} />
  if (repos.loading || !repos.data) return <Loading label={t('repos.loading')} />

  const q = (query.q ?? '').toLowerCase()
  const sort = query.sort || 'prs'
  const shown = repos.data
    .filter((r) => `${r.owner}/${r.repo}`.toLowerCase().includes(q))
    .sort((a, b) =>
      sort === 'spend' ? b.cost_total - a.cost_total
      : sort === 'name' ? `${a.owner}/${a.repo}`.localeCompare(`${b.owner}/${b.repo}`)
      : b.prs_total - a.prs_total)
  const reviewed = repos.data.filter((r) => r.has_data)

  return (
    <>
      <PageTitle>{t('repos.title')}</PageTitle>
      <PageSub>
        {reviewed.length === 1
          ? t('repos.subOne', { n: reviewed.length })
          : t('repos.subMany', { n: reviewed.length })} ·{' '}
        {t('repos.subPrs', { n: reviewed.reduce((n, r) => n + r.prs_total, 0) })}
      </PageSub>

      <div className="mb-4 flex flex-wrap items-center gap-2" role="search">
        <input
          type="search"
          aria-label={t('repos.searchAria')}
          placeholder={t('repos.searchPlaceholder')}
          defaultValue={query.q ?? ''}
          onInput={(e) => setQuery({ q: e.currentTarget.value || null })}
          className="h-8 w-56 max-w-full rounded-sm border border-hairline-strong bg-surface px-2.5 font-mono text-xs outline-none focus-visible:border-brand"
        />
        <Select value={sort} onValueChange={(v) => setQuery({ sort: v === 'prs' ? null : v })}>
          <SelectTrigger size="sm" aria-label={t('repos.sortAria')} className="w-36 rounded-sm font-mono text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="prs">{t('repos.sortPrs')}</SelectItem>
            <SelectItem value="spend">{t('repos.sortSpend')}</SelectItem>
            <SelectItem value="name">{t('repos.sortName')}</SelectItem>
          </SelectContent>
        </Select>
        <span className="mx-1 hidden h-5 w-px bg-hairline-strong sm:block" aria-hidden="true" />
        <input
          name="add-repo"
          aria-label={t('repos.addAria')}
          placeholder={t('config.repoPlaceholderOrg')}
          value={newRepo}
          onInput={(e) => setNewRepo(e.currentTarget.value)}
          className="h-8 w-56 max-w-full rounded-sm border border-hairline-strong bg-surface px-2.5 font-mono text-xs outline-none focus-visible:border-brand"
        />
        <Button
          variant="outline"
          size="sm"
          disabled={busy || !newRepo.trim()}
          onClick={() => act(() => api.addRepo(newRepo.trim(), 'auto')).then(() => setNewRepo(''))}
        >
          {t('config.watchRepo')}
        </Button>
      </div>

      {actionError && <Notice tone="fail">{actionError}</Notice>}

      {shown.length === 0 ? (
        <Empty>
          {t('repos.emptyBefore')}<code>python -m src.run owner/repo 123</code>
          {t('repos.emptyAfter')}
        </Empty>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3">
          {shown.map((r) => (
            <RepoCard
              key={`${r.owner}/${r.repo}`}
              r={r}
              busy={busy}
              onMode={(repo, mode) => act(() => api.setMode(`${repo.owner}/${repo.repo}`, mode))}
              onRemove={(repo) => act(() => api.removeRepo(`${repo.owner}/${repo.repo}`))}
            />
          ))}
        </div>
      )}
    </>
  )
}
