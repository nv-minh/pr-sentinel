// One file's diff: sticky header, the GitHub-style DiffView with finding
// cards attached to their lines, and an honest fallback ladder — empty patch
// → note, truncation → banner, unparseable hunks or a render crash → the raw
// patch text. All @git-diff-view contact lives in this module and DiffPane.
import { Component, useMemo } from 'react'
import type { ReactNode } from 'react'
import { DiffFile, DiffModeEnum, DiffView } from '@git-diff-view/react'
import { highlighter } from '@git-diff-view/lowlight'
import type { SnapshotFile } from '../api'
import { useT } from '../i18n'
import { useTheme } from '../theme'
import type { FileAnchors, Finding } from './model'

const TRUNCATED = /\n?… patch truncated: (\d+) more lines\s*$/
const HUNK = /^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@/m

const LANG: Record<string, string> = {
  ts: 'typescript', tsx: 'tsx', js: 'javascript', jsx: 'jsx', mjs: 'javascript',
  py: 'python', rb: 'ruby', go: 'go', rs: 'rust', java: 'java', kt: 'kotlin',
  css: 'css', scss: 'scss', html: 'xml', xml: 'xml', json: 'json',
  yml: 'yaml', yaml: 'yaml', md: 'markdown', sql: 'sql', sh: 'shell', bash: 'shell',
  swift: 'swift', c: 'c', h: 'c', cpp: 'cpp', cs: 'csharp', php: 'php', dart: 'dart',
}

function langOf(filename: string): string {
  const ext = filename.split('.').pop() ?? ''
  return LANG[ext] ?? 'plaintext'
}

/** A crash inside the diff library must degrade to the raw patch, never take
 * the workspace down. */
class DiffBoundary extends Component<{ fallback: ReactNode; children: ReactNode },
                                     { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

export function FileDiff({ file, anchors, mode, viewed, onToggleViewed, renderCard, slug }: {
  file: SnapshotFile
  anchors: FileAnchors
  mode: 'split' | 'unified'
  viewed: boolean
  onToggleViewed: (filename: string) => void
  renderCard: (finding: Finding) => ReactNode
  slug: string
}) {
  const t = useT()
  const [theme] = useTheme()
  const truncated = TRUNCATED.exec(file.patch)
  const cleaned = file.patch.replace(TRUNCATED, '')

  const diffFile = useMemo(() => {
    if (!cleaned || !HUNK.test(cleaned)) return null
    try {
      const lang = langOf(file.filename)
      // GitHub's `patch` field carries bare hunks; the parser needs the
      // ---/+++ file headers a real git diff would have.
      const oldName = file.status === 'added' ? '/dev/null' : `a/${file.filename}`
      const newName = file.status === 'removed' ? '/dev/null' : `b/${file.filename}`
      const withHeader = `--- ${oldName}\n+++ ${newName}\n${cleaned}`
      const df = new DiffFile('', '', file.filename, '', [withHeader], lang, lang)
      df.initTheme(theme)
      df.initRaw()
      df.buildSplitDiffLines()
      df.buildUnifiedDiffLines()
      if (df.diffLineLength === 0) return null
      return df
    } catch {
      return null
    }
  }, [cleaned, file.filename, file.status, theme])

  const extendData = useMemo(() => {
    const byLine: Record<string, { data: Finding[] }> = {}
    for (const [line, list] of anchors.byLine) byLine[String(line)] = { data: list }
    return { newFile: byLine }
  }, [anchors])

  const count = anchors.header.length +
    [...anchors.byLine.values()].reduce((n, list) => n + list.length, 0)

  const rawFallback = (
    <>
      <p className="mt-2 font-mono text-[11px] text-ink-muted">{t('files.rawPatch')}</p>
      <pre className="mt-1 overflow-x-auto rounded border border-hairline bg-surface px-3 py-2 font-mono text-xs whitespace-pre-wrap text-ink-muted">
        {file.patch}
      </pre>
      {[...anchors.byLine.values()].flat().length > 0 && (
        <div className="mt-2 grid gap-2">
          {[...anchors.byLine.values()].flat().map(renderCard)}
        </div>
      )}
    </>
  )

  return (
    <section id={slug} className="mb-6 scroll-mt-4">
      <p className="sr-only">
        {t('files.summary', { path: file.filename, added: file.additions,
                              deleted: file.deletions, findings: count })}
      </p>
      <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-hairline-strong bg-paper py-1.5">
        <span className="min-w-0 truncate font-mono text-[12.5px] font-semibold" title={file.filename}>
          {file.filename}
        </span>
        <span className="font-mono text-[11px] tabular-nums">
          <span className="text-pass">+{file.additions}</span>{' '}
          <span className="text-fail">−{file.deletions}</span>
        </span>
        {count > 0 && (
          <span className="font-mono text-[11px] text-ink-muted">
            {t('files.inFile', { n: count })}
          </span>
        )}
        <label className="ml-auto flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-muted">
          <input type="checkbox" checked={viewed}
                 aria-label={t('files.markViewed', { path: file.filename })}
                 onChange={() => onToggleViewed(file.filename)}
                 className="accent-(--brand)" />
          {t('files.viewed')}
        </label>
      </div>

      {truncated && (
        <p className="mt-1.5 border-l-2 border-warn bg-surface px-2.5 py-1.5 font-mono text-[11px] text-ink-muted">
          {t('files.patchTruncated', { n: truncated[1] })}
        </p>
      )}

      {anchors.header.length > 0 && (
        <div className="mt-2 grid gap-2">{anchors.header.map(renderCard)}</div>
      )}

      {viewed ? null : !file.patch ? (
        <p className="mt-2 font-mono text-[11px] text-ink-muted">{t('files.noPatch')}</p>
      ) : diffFile ? (
        <DiffBoundary fallback={rawFallback}>
          <div className="mt-2 overflow-x-auto rounded border border-hairline">
            <DiffView
              diffFile={diffFile}
              diffViewMode={mode === 'split' ? DiffModeEnum.Split : DiffModeEnum.Unified}
              diffViewTheme={theme}
              diffViewHighlight
              diffViewFontSize={12}
              registerHighlighter={highlighter}
              extendData={extendData}
              renderExtendLine={({ data }) => (
                <div className="grid gap-2 border-y border-hairline bg-paper px-3 py-2">
                  {(data as Finding[]).map(renderCard)}
                </div>
              )}
            />
          </div>
        </DiffBoundary>
      ) : (
        rawFallback
      )}
    </section>
  )
}
