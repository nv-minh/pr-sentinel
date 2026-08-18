// Per-file "viewed" marks, keyed by head_sha so a force-push resets them —
// a mark on an outdated diff is worse than no mark.
const key = (owner: string, repo: string, pr: number) =>
  `pr-sentinel-viewed:${owner}/${repo}/${pr}`

export function loadViewed(owner: string, repo: string, pr: number,
                           headSha: string): Set<string> {
  try {
    const raw = localStorage.getItem(key(owner, repo, pr))
    if (!raw) return new Set()
    const data = JSON.parse(raw) as { head_sha?: string; files?: string[] }
    if (data.head_sha !== headSha || !Array.isArray(data.files)) return new Set()
    return new Set(data.files)
  } catch {
    return new Set()
  }
}

export function saveViewed(owner: string, repo: string, pr: number,
                           headSha: string, files: Set<string>): void {
  try {
    localStorage.setItem(key(owner, repo, pr),
                         JSON.stringify({ head_sha: headSha, files: [...files] }))
  } catch {
    /* storage full or blocked — viewed marks are a convenience, not state */
  }
}
