import { useState } from 'react'
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
      {finding.attachments?.poc?.map((poc, i) => (
        <Attachment key={`poc-${i}`} heading={t('extras.pocHeading')}
                    badge={poc.framework} copyText={poc.test_code}>
          <pre className="overflow-x-auto rounded border border-hairline bg-paper px-3 py-2 font-mono text-[11.5px] whitespace-pre-wrap">
            {poc.test_code}
          </pre>
          <p className="mt-1 text-[12.5px] text-ink-muted">
            <span className="font-mono text-[10.5px] uppercase tracking-[0.08em]">{t('extras.pocWhy')}:</span>{' '}
            {poc.why_it_fails}
          </p>
        </Attachment>
      ))}
      {finding.attachments?.patches?.map((patch, i) => (
        <Attachment key={`patch-${i}`} heading={t('extras.patchHeading')}
                    badge={patch.path} copyText={patch.new_snippet}>
          <div className="grid gap-1.5">
            <div className="border-l-2 border-fail">
              <span className="ml-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-muted">{t('extras.patchOld')}</span>
              <pre className="ml-2 overflow-x-auto font-mono text-[11.5px] whitespace-pre-wrap text-ink-muted">{patch.old_snippet}</pre>
            </div>
            <div className="border-l-2 border-pass">
              <span className="ml-2 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-muted">{t('extras.patchNew')}</span>
              <pre className="ml-2 overflow-x-auto font-mono text-[11.5px] whitespace-pre-wrap">{patch.new_snippet}</pre>
            </div>
          </div>
          {patch.why && <p className="mt-1 text-[12.5px] text-ink-muted">{patch.why}</p>}
        </Attachment>
      ))}
      {children}
    </article>
  )
}

/** A generated artifact riding on a finding: a PoC test or a doc fix, with a
 * copy button so the author can act on it — never applied automatically. */
function Attachment({ heading, badge, copyText, children }: {
  heading: string
  badge?: string
  copyText: string
  children: React.ReactNode
}) {
  const t = useT()
  const [copied, setCopied] = useState(false)
  return (
    <div className="mt-2.5 rounded-sm border border-hairline bg-surface px-3 py-2.5">
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="font-mono text-[10.5px] font-bold uppercase tracking-[0.1em] text-ink-muted">
          {heading}
        </span>
        {badge && <span className="font-mono text-[10.5px] text-ink-muted">{badge}</span>}
        <button
          className="ml-auto rounded-sm border border-hairline-strong px-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-muted hover:text-ink"
          onClick={() => {
            void navigator.clipboard?.writeText(copyText)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
          }}
        >
          {copied ? t('extras.copied') : t('extras.copy')}
        </button>
        <span aria-live="polite" className="sr-only">{copied ? t('extras.copied') : ''}</span>
      </div>
      {children}
    </div>
  )
}
