import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Empty, Eyebrow, Ledger, Row, Tile } from '../components'

interface ConfigState {
  org: string
  interval_minutes: number
  post_comment: boolean
  skip_human: boolean
  auto_describe: boolean
  docs_fix_pr: boolean
  inline_suggestions: boolean
  gate: { verification_score_min: number }
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
      <div className="notice notice-fail">
        {error} — create <code>prsentinel.yml</code> next to the repo, or point
        <code> PRSENTINEL_CONFIG</code> at it.
      </div>
    )
  }
  if (!cfg) return <div className="page-sub">Loading…</div>

  return (
    <>
      <h1 className="page-title">What the poller watches</h1>
      <p className="page-sub">{cfg.config_path}</p>

      {error && <div className="notice notice-fail">{error}</div>}

      <div className="tiles">
        <Tile label="Org" value={cfg.org || '—'} />
        <Tile label="Poll every" value={`${cfg.interval_minutes}m`} />
        <Tile label="Gate at" value={`${Math.round(cfg.gate.verification_score_min * 100)}%`}
              note="minimum verification score" />
        <Tile label="Posts comments" value={cfg.post_comment ? 'yes' : 'no'} />
        <Tile label="Writes doc PRs" value={cfg.docs_fix_pr ? 'yes' : 'no'} />
        <Tile label="Rewrites PR body" value={cfg.auto_describe ? 'yes' : 'no'} />
      </div>

      <Eyebrow>Repositories</Eyebrow>
      <div className="toolbar">
        <input
          type="text"
          value={newRepo}
          placeholder={cfg.org ? 'repo-name or owner/repo' : 'owner/repo'}
          onChange={(e) => setNewRepo(e.target.value)}
        />
        <button
          className="button"
          disabled={!newRepo.trim()}
          onClick={() => act(async () => {
            await api.addRepo(newRepo.trim(), 'auto')
            setNewRepo('')
          })}
        >
          Watch repo
        </button>
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
                  <select
                    value={r.mode === 'unlisted' ? 'manual' : r.mode}
                    onChange={(e) => act(() => api.setMode(r.name, e.target.value))}
                  >
                    <option value="auto">auto</option>
                    <option value="manual">manual</option>
                  </select>{' '}
                  {r.mode !== 'unlisted' && (
                    <button className="button button-quiet"
                            onClick={() => act(() => api.removeRepo(r.name))}>
                      Remove
                    </button>
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
