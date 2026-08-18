import { Suspense, lazy, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import type { ReviewStatus } from '../api'
import { ErrorNotice, Loading, Notice, PageSub, PageTitle } from '../components'
import { useApi, usePoll } from '../hooks/useApi'
import { useT } from '../i18n'
import { EvidenceChip } from './EvidenceChip'
import { FindingCard } from './FindingCard'
import { Header } from './Header'
import { NavPane } from './NavPane'
import { RightPane } from './RightPane'
import { attachExtras, collectFindings, fileSlug, planAnchors } from './model'
import type { Finding } from './model'
import { useWorkspaceState } from './useWorkspaceState'
import { loadViewed, saveViewed } from './viewed'

/** Which selection a pipeline phase opens: the first finding of a family, or
 * a right-pane tab for phases whose output has no findings of its own. */
// The diff library rides in its own chunk, like the React Flow graph.
const DiffPane = lazy(() => import('./DiffPane'))

const NODE_TARGET: Record<string, { family?: Finding['family']; tab?: 'overview' | 'report' | 'run' }> = {
  snapshot: { tab: 'overview' },
  siblings: { family: 'crosspr' },
  describe: { tab: 'overview' },
  claims: { family: 'claim' },
  followup: { family: 'thread' },
  verify: { family: 'claim' },
  remediate: { family: 'doc' },
  poc: { family: 'impact' },
  score: { tab: 'overview' },
  ask: { tab: 'overview' },
  report: { tab: 'report' },
}

export function Workspace({ owner, repo, pr }: { owner: string; repo: string; pr: number }) {
  const t = useT()
  const state = useWorkspaceState()
  const detail = useApi((signal) => api.pr(owner, repo, pr, signal), [owner, repo, pr])
  const files = useApi(
    (signal) => api.prFiles(owner, repo, pr, signal).catch(() => null),
    [owner, repo, pr],
  )
  const extras = useApi(
    (signal) => api.prExtras(owner, repo, pr, signal).catch(() => null),
    [owner, repo, pr],
  )
  const graph = useApi(
    (signal) => api.graph(owner, repo, pr, signal).catch(() => null),
    [owner, repo, pr],
  )
  const statusOnce = useApi((signal) => api.reviewStatus(owner, repo, pr, signal),
                            [owner, repo, pr])
  const [optimisticRun, setOptimisticRun] = useState(false)
  const [actionError, setActionError] = useState('')
  const [navOpen, setNavOpen] = useState(true)
  const [selectedPhase, setSelectedPhase] = useState<string | null>(null)

  // Status: one snapshot on load, then a live poll only while running. The
  // poll's own answer feeds back into `runningKnown`, so it keeps itself
  // alive during a run and stops on the first not-running answer.
  const [runningKnown, setRunningKnown] = useState(false)
  const polled = usePoll(
    (signal) => api.reviewStatus(owner, repo, pr, signal),
    3000,
    optimisticRun || runningKnown,
  )
  const status: ReviewStatus | null = polled.data ?? statusOnce.data
  useEffect(() => {
    setRunningKnown(Boolean(status?.running))
  }, [status?.running])
  const running = optimisticRun || Boolean(status?.running)

  // When a run finishes, reload everything once.
  const prevRunning = useRef(false)
  useEffect(() => {
    const now = Boolean(status?.running)
    if (prevRunning.current && !now) {
      setOptimisticRun(false)
      detail.refetch(); files.refetch(); extras.refetch(); graph.refetch()
    }
    prevRunning.current = now
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.running])

  // Viewed marks, keyed by head sha.
  const headSha = files.data?.head_sha ?? ''
  const [viewed, setViewed] = useState<Set<string>>(new Set())
  useEffect(() => {
    setViewed(loadViewed(owner, repo, pr, headSha))
  }, [owner, repo, pr, headSha])
  const toggleViewed = (filename: string) => {
    setViewed((prev) => {
      const next = new Set(prev)
      if (next.has(filename)) next.delete(filename)
      else next.add(filename)
      saveViewed(owner, repo, pr, headSha, next)
      return next
    })
  }

  const startReview = async (reply: boolean) => {
    setActionError('')
    try {
      await api.startReview(owner, repo, pr, reply)
      setOptimisticRun(true)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : String(e))
    }
  }

  if (detail.error && !detail.data) return <ErrorNotice message={detail.error} />
  if (!detail.data) return <Loading label={t('pr.loading')} />
  const data = detail.data

  if (!data.reviewed) {
    return (
      <div className="mx-auto max-w-[860px]">
        <PageTitle>
          <span className="font-mono text-[0.7em] text-ink-muted">#{pr}</span>{' '}
          {data.title || data.pr?.title || t('common.noTitle')}
        </PageTitle>
        <PageSub>{owner}/{repo}</PageSub>
        {actionError && <Notice tone="fail">{actionError}</Notice>}
        <Notice>{t('pr.notReviewed')}</Notice>
        <Button onClick={() => startReview(false)} disabled={running}>
          {running ? t('pr.reviewing') : t('pr.reviewNow')}
        </Button>
      </div>
    )
  }

  const fileList = files.data?.files ?? []
  const findings = attachExtras(
    collectFindings(data, files.data?.threads ?? []),
    extras.data ?? null,
  )
  const plan = planAnchors(findings, fileList)

  const pick = (f: Finding) => {
    state.select({ finding: f.key, file: f.anchor?.path ?? null })
    document.getElementById(`finding-${f.key}`)?.scrollIntoView({ block: 'center' })
  }
  const pickFile = (filename: string) => {
    state.select({ file: filename, finding: null })
    document.getElementById(fileSlug(filename))?.scrollIntoView({ block: 'start' })
  }
  const onPhase = (id: string) => {
    setSelectedPhase(id)
    const target = NODE_TARGET[id]
    if (!target) return
    if (target.family) {
      const first = findings.find((f) => f.family === target.family)
      if (first) { pick(first); return }
    }
    state.select({ tab: target.tab ?? 'overview' })
  }

  const grid = navOpen
    ? 'min-[980px]:grid-cols-[270px_minmax(0,1fr)_370px]'
    : 'min-[980px]:grid-cols-[minmax(0,1fr)_370px]'

  const diffPaths = new Set(fileList.map((f) => f.filename))
  const jump = (path: string, _line: number) => {
    state.select({ file: path, finding: null })
    document.getElementById(fileSlug(path))?.scrollIntoView({ block: 'start' })
  }
  const renderChips = (f: Finding) => (
    f.evidence.length === 0
      ? <span className="font-mono text-[11px] text-ink-muted">{t('citations.none')}</span>
      : f.evidence.map((e, i) => (
          <EvidenceChip key={i} item={e} inDiff={(p) => diffPaths.has(p)}
                        owner={owner} repo={repo} pr={pr} onJump={jump} />
        ))
  )

  return (
    <>
      <Header owner={owner} repo={repo} pr={pr} data={data} pipeline={graph.data ?? null}
              running={running} lastRun={status?.last} error={actionError}
              onStart={startReview} onPhase={onPhase} />

      <div className={`grid grid-cols-1 items-start gap-6 ${grid}`}>
        <div className={navOpen ? '' : 'hidden'}>
          <button
            className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-muted hover:text-ink"
            onClick={() => setNavOpen(false)}
          >
            ← {t('ws.collapseNav')}
          </button>
          <NavPane findings={findings} files={fileList} plan={plan} selectedKey={state.finding}
                   viewed={viewed} onPick={pick} onPickFile={pickFile}
                   onToggleViewed={toggleViewed} />
        </div>
        {!navOpen && (
          <button
            className="fixed bottom-4 left-4 z-20 rounded-sm border border-hairline-strong bg-surface px-2 py-1 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-muted hover:text-ink"
            onClick={() => setNavOpen(true)}
          >
            {t('ws.expandNav')} →
          </button>
        )}

        <div className="min-w-0">
          <Suspense fallback={<Loading label={t('pr.loading')} />}>
            <DiffPane files={fileList} plan={plan} viewed={viewed}
                      onToggleViewed={toggleViewed}
                      renderCard={(f) => (
                        <FindingCard key={f.key} finding={f}
                                     selected={state.finding === f.key}
                                     renderChips={renderChips} />
                      )} />
          </Suspense>
        </div>

        <RightPane owner={owner} repo={repo} pr={pr} data={data} extras={extras.data ?? null}
                   pipeline={graph.data ?? null} status={status} running={running}
                   state={state} selectedPhase={selectedPhase} onPhase={onPhase} />
      </div>
    </>
  )
}
