import { Mark, StatusWord } from '../components'
import { useT } from '../i18n'
import type { Key } from '../strings'
import { TONE_COLOR, toneOf } from '../status'
import type { Family, Finding } from './model'

export const FAMILY_LABEL: Record<Family, Key> = {
  contract: 'pr.blockContract',
  caller: 'pr.blockCaller',
  claim: 'pr.blockClaim',
  impact: 'pr.blockImpact',
  doc: 'pr.blockDoc',
  test: 'pr.blockTest',
  crosspr: 'pr.tabCrossPr',
  thread: 'pr.tabThreads',
}

export function FindingCard({ finding, selected, renderChips, children }: {
  finding: Finding
  selected: boolean
  /** Evidence chips renderer — plain chips now, interactive ones later. */
  renderChips: (finding: Finding) => React.ReactNode
  children?: React.ReactNode
}) {
  const t = useT()
  return (
    <article
      id={`finding-${finding.key}`}
      tabIndex={-1}
      data-selected={selected ? 'true' : undefined}
      className={`scroll-mt-16 border-l-2 bg-surface px-3.5 py-3 outline-none ${
        selected ? 'ring-2 ring-brand' : ''
      }`}
      style={{ borderLeftColor: TONE_COLOR[toneOf(finding.status)] }}
      aria-label={`${t(FAMILY_LABEL[finding.family])}: ${finding.title}`}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <Mark status={finding.status} />
        <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-muted">
          {t(FAMILY_LABEL[finding.family])}
        </span>
        <span className="min-w-0 break-words text-[14px] font-medium">{finding.title}</span>
        <StatusWord status={finding.status} />
        {finding.claim?.confidence != null && (
          <span className="font-mono text-[11px] tabular-nums text-ink-muted">
            {t('ws.confidence', { pct: `${Math.round(finding.claim.confidence * 100)}%` })}
          </span>
        )}
      </div>
      {finding.detail && (
        <p className="mt-1.5 max-w-[72ch] text-[13px] leading-relaxed text-ink-muted">
          {finding.detail}
        </p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-1">{renderChips(finding)}</div>
      {children}
    </article>
  )
}
