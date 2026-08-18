import { Suspense, lazy } from 'react'
import type { Pipeline, PrDetail, PrExtras, ReviewStatus } from '../api'
import { Loading, Notice } from '../components'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { useT } from '../i18n'
import { Markdown } from './Markdown'
import { OverviewTab } from './OverviewTab'
import { RunTab } from './RunTab'
import type { WorkspaceState } from './useWorkspaceState'

const PipelineGraph = lazy(() => import('../graph/PipelineGraph'))

function ReportTab({ owner, repo, pr }: { owner: string; repo: string; pr: number }) {
  const t = useT()
  const report = useApi((signal) => api.report(owner, repo, pr, signal), [owner, repo, pr])
  if (report.loading) return <Loading label={t('report.loading')} />
  if (report.error || !report.data) return <p className="text-[13px] text-ink-muted">{t('report.empty')}</p>
  return <Markdown source={report.data.markdown} />
}

export function RightPane({ owner, repo, pr, data, extras, pipeline, status, running,
                            state, selectedPhase, onPhase }: {
  owner: string
  repo: string
  pr: number
  data: PrDetail
  extras: PrExtras | null
  pipeline: Pipeline | null
  status: ReviewStatus | null
  running: boolean
  state: WorkspaceState
  selectedPhase: string | null
  onPhase: (id: string) => void
}) {
  const t = useT()
  return (
    <Tabs value={state.tab} onValueChange={(v) => state.select({ tab: v as WorkspaceState['tab'] })}>
      <TabsList className="w-full justify-start rounded-sm bg-surface font-mono">
        <TabsTrigger value="overview" className="rounded-sm text-xs">{t('ws.tabOverview')}</TabsTrigger>
        <TabsTrigger value="pipeline" className="rounded-sm text-xs">{t('ws.tabPipeline')}</TabsTrigger>
        <TabsTrigger value="report" className="rounded-sm text-xs">{t('report.tab')}</TabsTrigger>
        <TabsTrigger value="run" className="rounded-sm text-xs">{t('run.tab')}</TabsTrigger>
      </TabsList>
      <TabsContent value="overview">
        <OverviewTab data={data} extras={extras} />
      </TabsContent>
      <TabsContent value="pipeline">
        {pipeline?.nodes?.length ? (
          <Suspense fallback={<Loading label={t('pr.pipelineLoading')} />}>
            <PipelineGraph pipeline={pipeline} selected={selectedPhase} onSelect={onPhase}
                           minZoom={0.15} />
          </Suspense>
        ) : (
          <Notice>{t('pr.noPipeline')}</Notice>
        )}
      </TabsContent>
      <TabsContent value="report">
        <ReportTab owner={owner} repo={repo} pr={pr} />
      </TabsContent>
      <TabsContent value="run">
        <RunTab owner={owner} repo={repo} pr={pr} data={data} status={status} running={running} />
      </TabsContent>
    </Tabs>
  )
}
