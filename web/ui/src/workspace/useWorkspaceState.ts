// The workspace's selection lives in the URL (?tab=&file=&finding=) so a
// finding is linkable and the back button undoes a selection. Tab switches
// replace history; selections push.
import { setQuery, useQuery } from '../router'

export type WorkspaceTab = 'overview' | 'pipeline' | 'report' | 'run'

export interface WorkspaceState {
  tab: WorkspaceTab
  file: string
  finding: string
  select: (patch: { tab?: WorkspaceTab; file?: string | null; finding?: string | null }) => void
}

const TABS: WorkspaceTab[] = ['overview', 'pipeline', 'report', 'run']

export function useWorkspaceState(): WorkspaceState {
  const query = useQuery()
  const tab = TABS.includes(query.tab as WorkspaceTab) ? (query.tab as WorkspaceTab) : 'overview'
  return {
    tab,
    file: query.file ?? '',
    finding: query.finding ?? '',
    select: (patch) => {
      const selection = patch.finding !== undefined || patch.file !== undefined
      setQuery({
        ...(patch.tab !== undefined ? { tab: patch.tab === 'overview' ? null : patch.tab } : {}),
        ...(patch.file !== undefined ? { file: patch.file } : {}),
        ...(patch.finding !== undefined ? { finding: patch.finding } : {}),
      }, { replace: !selection })
    },
  }
}
