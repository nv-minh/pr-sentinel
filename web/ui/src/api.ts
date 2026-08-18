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
  confidence?: number | null
}

export interface SnapshotFile {
  filename: string
  status: string
  additions: number
  deletions: number
  patch: string
}

export interface SnapshotThread {
  path: string | null
  line: number | null
  author: string
  body: string
  resolved: boolean
  outdated: boolean
}

export interface PrFiles {
  files: SnapshotFile[]
  pruned: { filename: string; reason: string; dropped: boolean }[]
  commits: { sha: string; message: string }[]
  threads: SnapshotThread[]
  base_sha: string
  head_sha: string
}

export interface FileSlice {
  path: string
  start: number
  end: number
  total_lines: number
  lines: string[]
}

export interface PocTest {
  target: string
  framework: string
  test_code: string
  why_it_fails: string
}

export interface DocPatch {
  path: string
  old_snippet: string
  new_snippet: string
  line_hint: number
  why: string
}

export interface PrExtras {
  ticket: { primary?: string; tickets?: Record<string, unknown>[]; skipped?: string } | null
  poc: PocTest[] | null
  patches: DocPatch[] | null
  neutralized: { phase: string; items: string[] }[] | null
  description: { description?: string; summary?: string } | null
}

export interface TraceEvent {
  type: 'tool' | 'text'
  tool?: string
  summary: string
}

export interface TracePhase {
  phase: string
  session_id: string
  events: TraceEvent[]
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
  usage?: { phase: string; session_id?: string; cost_usd: number | null
            num_turns: number; duration_ms?: number | null; model: string }[]
  replies?: { author: string; body: string; created_at: string; source: string }[]
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
  repos: (signal?: AbortSignal) =>
    request<{ repos: RepoRecord[] }>('/api/repos', { signal }),
  repo: (owner: string, repo: string, signal?: AbortSignal) =>
    request<RepoRecord>(`/api/repos/${owner}/${repo}`, { signal }),
  pr: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<PrDetail>(`/api/repos/${owner}/${repo}/pr/${pr}`, { signal }),
  report: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<{ markdown: string }>(`/api/repos/${owner}/${repo}/pr/${pr}/report`, { signal }),
  graph: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<Pipeline>(`/api/repos/${owner}/${repo}/pr/${pr}/graph`, { signal }),
  prFiles: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<PrFiles>(`/api/repos/${owner}/${repo}/pr/${pr}/files`, { signal }),
  prFile: (owner: string, repo: string, pr: number, path: string,
           start: number, end: number, signal?: AbortSignal) =>
    request<FileSlice>(
      `/api/repos/${owner}/${repo}/pr/${pr}/file?path=${encodeURIComponent(path)}&start=${start}&end=${end}`,
      { signal },
    ),
  prExtras: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<PrExtras>(`/api/repos/${owner}/${repo}/pr/${pr}/extras`, { signal }),
  prTrace: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<TracePhase[]>(`/api/repos/${owner}/${repo}/pr/${pr}/trace`, { signal }),
  config: (signal?: AbortSignal) => request<any>('/api/config', { signal }),
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
  startReview: (owner: string, repo: string, pr: number, reply = false) =>
    request<any>(`/api/repos/${owner}/${repo}/pr/${pr}/review?reply=${reply}`, {
      method: 'POST',
    }),
  reviewStatus: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<ReviewStatus>(`/api/repos/${owner}/${repo}/pr/${pr}/review/status`, { signal }),
  reviewLog: (owner: string, repo: string, pr: number, signal?: AbortSignal) =>
    request<{ log: string; running: boolean }>(
      `/api/repos/${owner}/${repo}/pr/${pr}/review/log`,
      { signal },
    ),
}
