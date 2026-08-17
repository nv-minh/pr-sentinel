import { useCallback, useEffect, useState } from 'react'
import type { ProviderInfo } from '../api'
import { api } from '../api'
import {
  Empty, ErrorNotice, Eyebrow, Ledger, Loading, Notice, PageSub, PageTitle, Row, Tile, Tiles,
} from '../components'
import { useLang, useT } from '../i18n'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

interface ConfigState {
  org: string
  interval_minutes: number
  post_comment: boolean
  skip_human: boolean
  auto_describe: boolean
  docs_fix_pr: boolean
  inline_suggestions: boolean
  language: string
  gate: { verification_score_min: number }
  provider: ProviderInfo
  providers: string[]
  repos: { name: string; mode: string }[]
  config_path: string
}

export function Config() {
  const [cfg, setCfg] = useState<ConfigState | null>(null)
  const [error, setError] = useState('')
  const [newRepo, setNewRepo] = useState('')
  const [uiLang, setUiLang] = useLang()
  const t = useT()

  const load = useCallback(() => {
    api.config().then(setCfg).catch((e) => setError(String(e.message)))
  }, [])

  useEffect(load, [load])

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn()
      setError('')
      load()
    } catch (e) {
      setError(String((e as Error).message))
    }
  }

  if (error && !cfg) {
    return (
      <ErrorNotice
        message={<>{error}{t('config.errorAfter')}<code>prsentinel.yml</code>
          {t('config.errorMid')}<code>PRSENTINEL_CONFIG</code>{t('config.errorEnd')}</>}
      />
    )
  }
  if (!cfg) return <Loading label={t('config.loading')} />

  return (
    <>
      <PageTitle>{t('config.title')}</PageTitle>
      <PageSub>{cfg.config_path}</PageSub>

      {error && <Notice tone="fail">{error}</Notice>}

      <Tiles>
        <Tile label={t('config.tileOrg')} value={cfg.org || '—'} />
        <Tile label={t('config.tilePollEvery')} value={`${cfg.interval_minutes}m`} />
        <Tile label={t('config.tileGateAt')} value={`${Math.round(cfg.gate.verification_score_min * 100)}%`}
              note={t('config.tileGateNote')} />
        <Tile label={t('config.tilePostsComments')} value={cfg.post_comment ? t('common.yes') : t('common.no')} />
        <Tile label={t('config.tileDocPrs')} value={cfg.docs_fix_pr ? t('common.yes') : t('common.no')} />
        <Tile label={t('config.tileRewritesBody')} value={cfg.auto_describe ? t('common.yes') : t('common.no')} />
      </Tiles>

      <Eyebrow>{t('config.providerHeading')}</Eyebrow>
      {!cfg.provider.token_present && (
        <Notice tone="fail">
          {t('config.noKeyBefore')}<code>{cfg.provider.name}</code>
          {t('config.noKeyMid')}<code>{cfg.provider.token_env}</code>
          {t('config.noKeyAfter')}<code>.env</code>{t('config.noKeyEnd')}
        </Notice>
      )}
      <Tiles>
        <Tile label={t('config.tileProvider')} value={cfg.provider.name} note={cfg.provider.base_url} />
        <Tile label={t('config.tileDeepDive')} value={<span className="text-base">{cfg.provider.model}</span>} />
        <Tile label={t('config.tileClaims')} value={cfg.provider.claims_model} />
        <Tile
          label={t('config.tileSchema')}
          value={cfg.provider.structured_output === 'native' ? t('config.schemaEnforced') : t('config.schemaPrompted')}
          note={cfg.provider.structured_output === 'native'
            ? t('config.schemaEnforcedNote')
            : t('config.schemaPromptedNote')}
        />
        <Tile label={t('config.tileKey')} value={cfg.provider.token_present ? t('config.keySet') : t('config.keyMissing')}
              note={cfg.provider.token_env} />
        <Tile label={t('config.tileCosts')} value={cfg.provider.reports_cost ? t('config.costsTracked') : t('config.costsUnknown')}
              note={cfg.provider.reports_cost ? '' : t('config.costsUnknownNote')} />
      </Tiles>
      <div className="my-2.5 flex flex-wrap items-center gap-2.5">
        <Select value={cfg.provider.name}
                onValueChange={(name) => act(() => api.setProvider(name))}>
          <SelectTrigger className="w-[180px] font-mono text-xs" aria-label={t('config.providerHeading')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {cfg.providers.map((name) => (
              <SelectItem key={name} value={name} className="font-mono text-xs">
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="font-mono text-[12px] uppercase tracking-[0.08em] text-ink-muted">
          {t('config.tokensNote')}
        </span>
      </div>

      <Eyebrow>{t('config.languageHeading')}</Eyebrow>
      <div className="my-2.5 flex flex-wrap items-start gap-6">
        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-muted">
            {t('config.uiLanguage')}
          </span>
          <Select value={uiLang} onValueChange={(next) => setUiLang(next as 'en' | 'vi')}>
            <SelectTrigger className="w-[150px] font-mono text-xs"
                           aria-label={t('config.uiLanguageAria')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en" className="font-mono text-xs">{t('lang.en')}</SelectItem>
              <SelectItem value="vi" className="font-mono text-xs">
                <span lang="vi">{t('lang.vi')}</span>
              </SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-ink-muted">{t('config.uiLanguageNote')}</span>
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-ink-muted">
            {t('config.reviewLanguage')}
          </span>
          <Select value={cfg.language}
                  onValueChange={(next) => act(() => api.setLanguage(next))}>
            <SelectTrigger className="w-[150px] font-mono text-xs"
                           aria-label={t('config.reviewLanguageAria')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="en" className="font-mono text-xs">{t('lang.en')}</SelectItem>
              <SelectItem value="vi" className="font-mono text-xs">
                <span lang="vi">{t('lang.vi')}</span>
              </SelectItem>
            </SelectContent>
          </Select>
          <span className="text-xs text-ink-muted">{t('config.reviewLanguageNote')}</span>
        </div>
      </div>
      <Notice>{t('config.languageFootnote')}</Notice>

      <Eyebrow>{t('config.reposHeading')}</Eyebrow>
      <div className="my-2.5 flex flex-wrap items-center gap-2.5">
        <input
          type="text"
          className="rounded border border-input bg-surface px-2 py-1.5 font-mono text-xs text-ink"
          value={newRepo}
          placeholder={cfg.org ? t('config.repoPlaceholderOrg') : t('config.repoPlaceholder')}
          onChange={(e) => setNewRepo(e.target.value)}
        />
        <Button
          disabled={!newRepo.trim()}
          onClick={() => act(async () => {
            await api.addRepo(newRepo.trim(), 'auto')
            setNewRepo('')
          })}
        >
          {t('config.watchRepo')}
        </Button>
      </div>

      <Ledger>
        {cfg.repos.length === 0 ? (
          <Empty>{t('config.noRepos')}</Empty>
        ) : (
          cfg.repos.map((r) => (
            <Row
              key={r.name}
              status={r.mode === 'auto' ? 'PASS' : r.mode === 'manual' ? 'PARTIAL' : 'UNVERIFIED'}
              title={r.name}
              meta={
                r.mode === 'auto' ? t('config.modeAuto')
                  : r.mode === 'manual' ? t('config.modeManual')
                  : t('config.modeUnlisted')
              }
              right={
                <>
                  <Select
                    value={r.mode === 'unlisted' ? 'manual' : r.mode}
                    onValueChange={(mode) => act(() => api.setMode(r.name, mode))}
                  >
                    <SelectTrigger className="h-7 w-[110px] font-mono text-xs" aria-label={t('config.modeAria', { repo: r.name })}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto" className="font-mono text-xs">auto</SelectItem>
                      <SelectItem value="manual" className="font-mono text-xs">manual</SelectItem>
                    </SelectContent>
                  </Select>{' '}
                  {r.mode !== 'unlisted' && (
                    <Button variant="outline" size="sm"
                            onClick={() => act(() => api.removeRepo(r.name))}>
                      {t('config.remove')}
                    </Button>
                  )}
                </>
              }
            />
          ))
        )}
      </Ledger>
    </>
  )
}
