import { Mark, StatusWord } from '../components'
import { useT } from '../i18n'
import type { Key } from '../strings'
import type { SnapshotFile } from '../api'
import { FAMILY_LABEL } from './FindingCard'
import { FAMILY_ORDER } from './model'
import type { AnchorPlan, Family, Finding } from './model'

const FAMILY_GROUP: Record<Family, Key> = {
  contract: 'pr.tabContracts',
  caller: 'pr.tabCallers',
  claim: 'pr.tabClaims',
  impact: 'pr.tabImpact',
  doc: 'pr.tabDocs',
  test: 'pr.tabTests',
  crosspr: 'pr.tabCrossPr',
  thread: 'pr.tabThreads',
}

export function NavPane({ findings, files, plan, selectedKey, viewed, onPick, onPickFile,
                          onToggleViewed }: {
  findings: Finding[]
  files: SnapshotFile[]
  plan: AnchorPlan
  selectedKey: string
  viewed: Set<string>
  onPick: (finding: Finding) => void
  onPickFile: (filename: string) => void
  onToggleViewed: (filename: string) => void
}) {
  const t = useT()
  const blocking = findings.filter((f) => f.blocking).length
  const countFor = (filename: string) => {
    const slot = plan.byFile.get(filename)
    if (!slot) return 0
    return slot.header.length +
      [...slot.byLine.values()].reduce((n, list) => n + list.length, 0)
  }
  return (
    <nav aria-label={t('ws.navFindings')} className="min-w-0 text-[13px]">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-muted">
          {t('ws.navFindings')}
        </span>
        {blocking > 0 && (
          <span className="rounded-sm border border-fail px-1.5 font-mono text-[10.5px] font-bold text-fail">
            {t('pr.blockingHeading', { n: blocking })}
          </span>
        )}
      </div>
      {findings.length === 0 && (
        <p className="text-xs text-ink-muted">{t('ws.noFindings')}</p>
      )}
      {FAMILY_ORDER.map((family) => {
        const group = findings.filter((f) => f.family === family)
        if (!group.length) return null
        return (
          <section key={family} data-nav-family={family} className="mb-3">
            <h2 className="mb-1 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-muted">
              {t(FAMILY_GROUP[family])} <span className="tabular-nums">{group.length}</span>
            </h2>
            <ul>
              {group.map((f) => (
                <li key={f.key}>
                  <button
                    className={`grid w-full grid-cols-[16px_minmax(0,1fr)] items-baseline gap-1.5 rounded-sm px-1 py-[3px] text-left hover:bg-brand-soft ${
                      selectedKey === f.key ? 'bg-brand-soft' : ''
                    }`}
                    aria-label={`${t(FAMILY_LABEL[family])}: ${f.title}`}
                    title={f.title}
                    onClick={() => onPick(f)}
                  >
                    <Mark status={f.status} />
                    <span className="truncate">
                      {f.title} <StatusWord status={f.status} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}

      <div className="mt-5 mb-2 flex items-baseline gap-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-muted">
          {t('ws.navFiles')}
        </span>
        {files.length > 0 && (
          <span className="font-mono text-[10.5px] tabular-nums text-ink-muted">
            {t('ws.filesViewed', { done: [...viewed].filter((v) =>
              files.some((f) => f.filename === v)).length, total: files.length })}
          </span>
        )}
      </div>
      {files.length === 0 && <p className="text-xs text-ink-muted">{t('files.empty')}</p>}
      <ul>
        {files.map((f) => {
          const n = countFor(f.filename)
          const isViewed = viewed.has(f.filename)
          return (
            <li key={f.filename} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-1">
              <button
                className="min-w-0 rounded-sm px-1 py-[3px] text-left font-mono text-[11.5px] hover:bg-brand-soft"
                title={f.filename}
                onClick={() => onPickFile(f.filename)}
              >
                <span className={`block truncate ${isViewed ? 'text-ink-muted line-through decoration-hairline-strong' : ''}`}>
                  {f.filename}
                </span>
                <span className="text-[10.5px] tabular-nums text-ink-muted">
                  <span className="text-pass">+{f.additions}</span>{' '}
                  <span className="text-fail">−{f.deletions}</span>
                  {n > 0 ? <> · {t('files.inFile', { n })}</> : null}
                </span>
              </button>
              <input
                type="checkbox"
                checked={isViewed}
                aria-label={t('files.markViewed', { path: f.filename })}
                onChange={() => onToggleViewed(f.filename)}
                className="accent-(--brand)"
              />
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
