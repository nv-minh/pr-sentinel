import { useCallback, useEffect, useState } from 'react'
import type { ProviderInfo } from '../api'
import { api } from '../api'
import {
  Empty, ErrorNotice, Eyebrow, Ledger, Loading, Notice, PageSub, PageTitle, Row, Tile, Tiles,
} from '../components'
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
        message={<>{error} — create <code>prsentinel.yml</code> next to the repo, or point <code>PRSENTINEL_CONFIG</code> at it.</>}
      />
    )
  }
  if (!cfg) return <Loading label="Loading configuration" />

  return (
    <>
      <PageTitle>What the poller watches</PageTitle>
      <PageSub>{cfg.config_path}</PageSub>

      {error && <Notice tone="fail">{error}</Notice>}

      <Tiles>
        <Tile label="Org" value={cfg.org || '—'} />
        <Tile label="Poll every" value={`${cfg.interval_minutes}m`} />
        <Tile label="Gate at" value={`${Math.round(cfg.gate.verification_score_min * 100)}%`}
              note="minimum verification score" />
        <Tile label="Posts comments" value={cfg.post_comment ? 'yes' : 'no'} />
        <Tile label="Writes doc PRs" value={cfg.docs_fix_pr ? 'yes' : 'no'} />
        <Tile label="Rewrites PR body" value={cfg.auto_describe ? 'yes' : 'no'} />
      </Tiles>

      <Eyebrow>Model provider</Eyebrow>
      {!cfg.provider.token_present && (
        <Notice tone="fail">
          No key for <code>{cfg.provider.name}</code> — set{' '}
          <code>{cfg.provider.token_env}</code> in <code>.env</code>. Reviews will
          refuse to start until it is there.
        </Notice>
      )}
      <Tiles>
        <Tile label="Provider" value={cfg.provider.name} note={cfg.provider.base_url} />
        <Tile label="Deep dive" value={<span className="text-base">{cfg.provider.model}</span>} />
        <Tile label="Claims" value={cfg.provider.claims_model} />
        <Tile
          label="Schema"
          value={cfg.provider.structured_output === 'native' ? 'enforced' : 'prompted'}
          note={cfg.provider.structured_output === 'native'
            ? 'the API validates the JSON'
            : 'the reply is parsed and repaired'}
        />
        <Tile label="Key" value={cfg.provider.token_present ? 'set' : 'missing'}
              note={cfg.provider.token_env} />
        <Tile label="Costs" value={cfg.provider.reports_cost ? 'tracked' : 'unknown'}
              note={cfg.provider.reports_cost ? '' : 'budget caps do not apply'} />
      </Tiles>
      <div className="my-2.5 flex flex-wrap items-center gap-2.5">
        <Select value={cfg.provider.name}
                onValueChange={(name) => act(() => api.setProvider(name))}>
          <SelectTrigger className="w-[180px] font-mono text-xs" aria-label="Model provider">
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
          tokens are read from the environment only
        </span>
      </div>

      <Eyebrow>Repositories</Eyebrow>
      <div className="my-2.5 flex flex-wrap items-center gap-2.5">
        <input
          type="text"
          className="rounded border border-input bg-surface px-2 py-1.5 font-mono text-xs text-ink"
          value={newRepo}
          placeholder={cfg.org ? 'repo-name or owner/repo' : 'owner/repo'}
          onChange={(e) => setNewRepo(e.target.value)}
        />
        <Button
          disabled={!newRepo.trim()}
          onClick={() => act(async () => {
            await api.addRepo(newRepo.trim(), 'auto')
            setNewRepo('')
          })}
        >
          Watch repo
        </Button>
      </div>

      <Ledger>
        {cfg.repos.length === 0 ? (
          <Empty>No repositories configured yet.</Empty>
        ) : (
          cfg.repos.map((r) => (
            <Row
              key={r.name}
              status={r.mode === 'auto' ? 'PASS' : r.mode === 'manual' ? 'PARTIAL' : 'UNVERIFIED'}
              title={r.name}
              meta={
                r.mode === 'auto' ? 'Reviewed automatically'
                  : r.mode === 'manual' ? 'Reviewed only when you ask'
                  : 'Not configured'
              }
              right={
                <>
                  <Select
                    value={r.mode === 'unlisted' ? 'manual' : r.mode}
                    onValueChange={(mode) => act(() => api.setMode(r.name, mode))}
                  >
                    <SelectTrigger className="h-7 w-[110px] font-mono text-xs" aria-label={`Mode for ${r.name}`}>
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
                      Remove
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
