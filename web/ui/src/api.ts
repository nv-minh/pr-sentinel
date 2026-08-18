export type Gate = 'pass' | 'warn' | 'fail' | 'unknown'

export interface PrRecord {
  pr: number
  title: string
  author: string
  base: string
  head: string
  verdict: string
  gate: Gate | ''
  verification_score: number | null
  business_risk: string
  gate_reasons: string[]
  cost_usd: number
  breaking: number
  test_gaps: number
  callers_at_risk: number
  claims_total: number
  bugs: number
  doc_errors: number
  open_questions: number
  rounds: number
  updated_at: string
  failed: boolean
  cross_pr?: number
}

export interface RepoRecord {
  owner: string
  repo: string
  prs_total: number
  bugs_total: number
  doc_errors_total: number
  breaking_total: number
  test_gaps_total: number
  cost_total: number
  avg_verification_score: number | null
  verdict_count: Record<string, number>
  gate_count: Record<string, number>
  prs: PrRecord[]
  open_prs: OpenPr[]
  open_questions: number
  has_data?: boolean
  mode?: string
}

export interface OpenPr {
  pr: number
  title: string
  draft: boolean
  status: 'reviewed' | 'reviewing' | 'not_reviewed'
  rounds: number | null
  bugs: number | null
  doc_errors: number | null
  unavailable: boolean
  started_at?: string | null
}

export interface Claim {
  id: string
  text: string
  category: string
  status: string
  evidence: string[]
  note: string
}

export interface PrDetail {
  reviewed: boolean
  owner: string
  repo: string
  pr: PrRecord
  title?: string
  body?: string
  claims?: Claim[]
  docs?: { path: string; status: string; what: string }[]
  impact?: {
    requirement: string
    impact: string
    area?: string
    detail: string
    requirement_source?: string
  }[]
  callers?: { symbol: string; defined_at: string; callers: string[]; risk: string; note: string }[]
  contracts?: { kind: string; path: string; status: string; detail: string }[]
  cross_pr?: {
    pr: number
    status: string
    symbol: string
    paths: string[]
    evidence: string[]
    detail: string
    confidence: number
  }[]
  siblings?: {
    scanned?: number
    truncated?: boolean
    skipped?: string
    siblings?: { pr: number; title: string; author: string; url: string
                 overlap: string; overlap_paths: string[]; updated_at: string }[]
  }
  tests?: {
    target: string
    assertion_quality: string
    uncovered_edge_cases: { case: string; where: string }[]
    note: string
  }[]
  threads?: { text: string; status: string; note: string }[]
  questions?: string[]
  answers?: { question: string; kind: string; answer: string }[]
  pruned?: { filename: string; reason: string; dropped: boolean }[]
  score?: {
    gate?: Gate
    verification_score?: number
    business_risk?: string
    doc_drift?: string[]
    reasons?: string[]
    labels?: string[]
  }
  usage?: { phase: string; cost_usd: number | null; num_turns: number; model: string }[]
  replies?: { author: string; body: string; created_at: string; source: string }[]
}

export interface GithubAccount {
  login: string
  active: boolean
  token_present: boolean
}

/** An open PR as GitHub reports it, merged with what `sessions/` already holds —
 *  the server returns `OpenPr`'s fields plus the GitHub-only ones. */
export interface GithubPr extends OpenPr {
  updated_at: string
  author: string
}

export interface GithubRepo {
  owner: string
  repo: string
  private: boolean
  pushed_at: string
  open_pr_count: number
  reviewed_count: number
  /** true when the repo has more open PRs than one page of the query returns */
  truncated: boolean
  prs: GithubPr[]
}

export interface ProviderInfo {
  name: string
  base_url: string
  model: string
  claims_model: string
  structured_output: 'native' | 'prompt'
  reports_cost: boolean
  token_env: string
  token_present: boolean
}

export interface ReviewStatus {
  running: boolean
  stale: boolean
  pid?: number
  started_at?: string
  elapsed_seconds?: number | null
  last?: { exit?: number; finished_at?: string }
}

export type PhaseStatus = 'done' | 'running' | 'pending' | 'skipped' | 'failed'

export interface GraphNode {
  id: string
  label: string
  status: PhaseStatus
  artifact: string
  cost_usd: number | null
  duration_ms: number | null
  model: string
  metrics: { label: string; value: string | number }[]
}

export interface GraphEdge {
  source: string
  target: string
}

export interface Pipeline {
  nodes: GraphNode[]
  edges: GraphEdge[]
  running: boolean
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) detail = String(body.detail)
    } catch {
      /* the body was not JSON — keep the status line */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  repos: () => request<{ repos: RepoRecord[] }>('/api/repos'),
  repo: (owner: string, repo: string) =>
    request<RepoRecord>(`/api/repos/${owner}/${repo}`),
  pr: (owner: string, repo: string, pr: number) =>
    request<PrDetail>(`/api/repos/${owner}/${repo}/pr/${pr}`),
  report: (owner: string, repo: string, pr: number) =>
    request<{ markdown: string }>(`/api/repos/${owner}/${repo}/pr/${pr}/report`),
  graph: (owner: string, repo: string, pr: number) =>
    request<Pipeline>(`/api/repos/${owner}/${repo}/pr/${pr}/graph`),
  config: () => request<any>('/api/config'),
  setProvider: (name: string) =>
    request<any>('/api/config/provider', {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  setLanguage: (language: string) =>
    request<any>('/api/config/language', {
      method: 'POST',
      body: JSON.stringify({ language }),
    }),
  setMode: (repo: string, mode: string) =>
    request<any>(`/api/config/repos/${encodeURIComponent(repo)}/mode`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
  addRepo: (repo: string, mode: string) =>
    request<any>('/api/config/repos', {
      method: 'POST',
      body: JSON.stringify({ repo, mode }),
    }),
  removeRepo: (repo: string) =>
    request<any>(`/api/config/repos/${encodeURIComponent(repo)}`, { method: 'DELETE' }),
  githubAccounts: () =>
    request<{ accounts: GithubAccount[]; active: string; gh_available: boolean }>(
      '/api/github/accounts',
    ),
  addGithubAccount: (token: string) =>
    request<{ login: string }>('/api/github/accounts', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  setActiveGithubAccount: (login: string) =>
    request<any>(`/api/github/accounts/${encodeURIComponent(login)}/active`, {
      method: 'POST',
    }),
  removeGithubAccount: (login: string) =>
    request<any>(`/api/github/accounts/${encodeURIComponent(login)}`, {
      method: 'DELETE',
    }),
  githubRepos: () =>
    request<{ login: string; repos: GithubRepo[]; truncated: boolean }>(
      '/api/github/repos',
    ),
  startReview: (owner: string, repo: string, pr: number, reply = false) =>
    request<any>(`/api/repos/${owner}/${repo}/pr/${pr}/review?reply=${reply}`, {
      method: 'POST',
    }),
  reviewStatus: (owner: string, repo: string, pr: number) =>
    request<ReviewStatus>(`/api/repos/${owner}/${repo}/pr/${pr}/review/status`),
  reviewLog: (owner: string, repo: string, pr: number) =>
    request<{ log: string; running: boolean }>(
      `/api/repos/${owner}/${repo}/pr/${pr}/review/log`,
    ),
}
