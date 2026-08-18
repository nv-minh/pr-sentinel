import { useState } from 'react'
import { Button } from '@/components/ui/button'
import type { Pipeline, PrDetail, ReviewStatus } from '../api'
import { Notice, PageSub, PageTitle, StatusWord } from '../components'
import { STATUS_KEY, STATUS_TONE } from '../graph/layout'
import { useT } from '../i18n'
import { GLYPH, TONE_COLOR, formatScore } from '../status'
import type { Key } from '../strings'

export function Header({ owner, repo, pr, data, pipeline, running, lastRun, error,
                         onStart, onPhase }: {
  owner: string
  repo: string
  pr: number
  data: PrDetail
  pipeline: Pipeline | null
  running: boolean
  lastRun: ReviewStatus['last'] | undefined
  error: string
  onStart: (reply: boolean) => void
  onPhase: (id: string) => void
}) {
  const t = useT()
  const [showReasons, setShowReasons] = useState(false)
  const rec = data.pr
  const score = data.score ?? {}
  const gate = score.gate ?? 'unknown'
  const reasons = score.reasons ?? []

  return (
    <header>
      <PageTitle>
        <span className="font-mono text-[0.7em] text-ink-muted">#{pr}</span>{' '}
        {data.title || rec?.title || t('common.noTitle')}
      </PageTitle>
      <PageSub>
        {owner}/{repo} · {rec?.author ? `${t('pr.by', { author: rec.author })} · ` : ''}
        {rec?.base} ← {rec?.head} ·{' '}
        <a className="text-brand hover:underline"
           href={`https://github.com/${owner}/${repo}/pull/${pr}`}>
          {t('pr.openOnGitHub')}
        </a>
      </PageSub>

      {error && <Notice tone="fail">{error}</Notice>}

      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 border-y border-hairline py-2.5">
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-muted">
            {t('pr.tileGate')}
          </span>
          <StatusWord status={gate} />
          <span className="text-[13px] text-ink-muted">{t(`gate.${gate}` as Key)}</span>
        </span>
        <span className="font-mono text-xs tabular-nums text-ink-muted">
          {formatScore(score.verification_score ?? rec?.verification_score)} {t('pr.tileVerifiedNote')}
        </span>
        <span className="font-mono text-xs text-ink-muted">
          {t('pr.tileRisk')}: {score.business_risk ?? '—'}
        </span>
        {reasons.length > 0 && (
          <button
            className="font-mono text-xs text-brand underline-offset-2 hover:underline"
            aria-expanded={showReasons}
            onClick={() => setShowReasons((v) => !v)}
          >
            {showReasons ? t('ws.reasonsHide') : t('ws.reasonsToggle', { n: reasons.length })}
          </button>
        )}
        <span className="ml-auto flex items-center gap-2">
          <Button size="sm" onClick={() => onStart(false)} disabled={running}>
            {running ? t('pr.reviewing') : t('pr.reReview')}
          </Button>
          <Button size="sm" variant="outline" onClick={() => onStart(true)} disabled={running}>
            {t('pr.answerReplies')}
          </Button>
          {lastRun?.exit !== undefined && !running && (
            <span className="font-mono text-xs text-ink-muted">
              {t('pr.lastRun', { code: lastRun.exit, at: lastRun.finished_at ?? '' })}
            </span>
          )}
        </span>
      </div>

      {showReasons && reasons.length > 0 && (
        <Notice tone={gate === 'fail' ? 'fail' : 'info'}>
          {t('pr.whyGate')}
          <ul className="mt-1.5 list-disc space-y-0.5 pl-5">
            {reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </Notice>
      )}

      {pipeline?.nodes?.length ? (
        <div role="group" aria-label={t('ws.phaseStripLabel')}
             className="mb-4 flex flex-wrap items-center gap-1">
          {pipeline.nodes.map((node) => {
            const tone = STATUS_TONE[node.status]
            const word = t(STATUS_KEY[node.status])
            return (
              <button
                key={node.id}
                className="flex items-center gap-1 rounded-sm border border-hairline px-1.5 py-0.5 font-mono text-[10.5px] text-ink-muted hover:border-ink-muted hover:text-ink"
                aria-label={`${node.label}: ${word}`}
                title={`${node.label}: ${word}`}
                onClick={() => onPhase(node.id)}
              >
                <span aria-hidden="true" style={{ color: TONE_COLOR[tone] }}>{GLYPH[tone]}</span>
                {node.label}
              </button>
            )
          })}
        </div>
      ) : null}
    </header>
  )
}
