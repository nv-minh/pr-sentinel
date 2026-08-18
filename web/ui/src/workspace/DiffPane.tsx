// The lazy chunk boundary: this module (and FileDiff) are the only importers
// of @git-diff-view — Repos/Config/queue never pay for it.
import '@git-diff-view/react/styles/diff-view.css'
import { useState } from 'react'
import type { ReactNode } from 'react'
import type { SnapshotFile } from '../api'
import { Empty, Eyebrow } from '../components'
import { useT } from '../i18n'
import { FileDiff } from './FileDiff'
import { fileSlug } from './model'
import type { AnchorPlan, Finding } from './model'

const MODE_KEY = 'pr-sentinel-diffmode'

export default function DiffPane({ files, plan, viewed, onToggleViewed, renderCard }: {
  files: SnapshotFile[]
  plan: AnchorPlan
  viewed: Set<string>
  onToggleViewed: (filename: string) => void
  renderCard: (finding: Finding) => ReactNode
}) {
  const t = useT()
  const [mode, setMode] = useState<'split' | 'unified'>(() =>
    localStorage.getItem(MODE_KEY) === 'split' ? 'split' : 'unified')
  const pick = (m: 'split' | 'unified') => {
    setMode(m)
    try { localStorage.setItem(MODE_KEY, m) } catch { /* convenience only */ }
  }

  if (files.length === 0 && plan.unanchored.length === 0) {
    return <Empty>{t('files.empty')}</Empty>
  }

  return (
    <div className="min-w-0">
      {files.length > 0 && (
        <div role="group" aria-label={t('files.diffModeLabel')}
             className="mb-2 flex justify-end gap-px font-mono text-[10.5px] uppercase tracking-[0.08em]">
          {(['unified', 'split'] as const).map((m) => (
            <button key={m} aria-pressed={mode === m}
                    className={`border border-hairline-strong px-2 py-0.5 first:rounded-l-sm last:rounded-r-sm ${
                      mode === m ? 'bg-brand-soft text-ink' : 'text-ink-muted hover:text-ink'
                    }`}
                    onClick={() => pick(m)}>
              {t(m === 'split' ? 'files.split' : 'files.unified')}
            </button>
          ))}
        </div>
      )}
      {files.map((f) => (
        <FileDiff key={f.filename} file={f}
                  anchors={plan.byFile.get(f.filename) ?? { header: [], byLine: new Map() }}
                  mode={mode} viewed={viewed.has(f.filename)}
                  onToggleViewed={onToggleViewed} renderCard={renderCard}
                  slug={fileSlug(f.filename)} />
      ))}
      {plan.unanchored.length > 0 && (
        <section className="mb-6">
          <Eyebrow>{t('files.unanchoredHeading')}</Eyebrow>
          <div className="grid gap-2">{plan.unanchored.map(renderCard)}</div>
        </section>
      )}
    </div>
  )
}
