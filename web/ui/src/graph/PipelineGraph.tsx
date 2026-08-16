import { useMemo } from 'react'
import {
  Background, Controls, MiniMap, ReactFlow, type Edge, type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { Pipeline } from '../api'
import { TONE_COLOR } from '../status'
import { useTheme } from '../theme'
import PhaseNode from './PhaseNode'
import { POSITION, STATUS_TONE, STATUS_WORD } from './layout'

const nodeTypes = { phase: PhaseNode }

function prefersReducedMotion(): boolean {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

/** The pipeline as a graph, plus a text equivalent underneath it.
 *
 *  The canvas is aria-hidden: a pan-and-zoom surface is not navigable with a
 *  screen reader, so the list below carries the same information and the same
 *  ability to select a phase. */
export default function PipelineGraph({
  pipeline, selected, onSelect,
}: {
  pipeline: Pipeline
  selected: string | null
  onSelect: (id: string) => void
}) {
  const [theme] = useTheme()
  const still = prefersReducedMotion()

  const nodes: Node[] = useMemo(
    () => pipeline.nodes.map((node) => ({
      id: node.id,
      type: 'phase',
      position: POSITION[node.id] ?? { x: 0, y: 0 },
      data: { ...node, selected: node.id === selected },
      draggable: false,
      connectable: false,
      selectable: true,
    })),
    [pipeline.nodes, selected],
  )

  const edges: Edge[] = useMemo(() => {
    const status = new Map(pipeline.nodes.map((n) => [n.id, n.status]))
    return pipeline.edges.map((edge) => {
      const target = status.get(edge.target)
      const live = target === 'running'
      const faded = target === 'pending' || target === 'skipped'
      return {
        id: `${edge.source}-${edge.target}`,
        source: edge.source,
        target: edge.target,
        animated: live && !still,
        style: {
          stroke: live ? TONE_COLOR.warn : 'var(--hairline-strong)',
          strokeWidth: live ? 2 : 1,
          opacity: faded ? 0.45 : 1,
        },
      }
    })
  }, [pipeline.edges, pipeline.nodes, still])

  return (
    <div>
      <div className="h-[380px] rounded border border-hairline bg-paper" aria-hidden="true">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          onNodeClick={(_, node) => onSelect(node.id)}
          minZoom={0.4}
          maxZoom={1.4}
        >
          <Background gap={18} size={1} color="var(--hairline)" />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable
                   nodeColor={(n) => TONE_COLOR[STATUS_TONE[(n.data as { status: Pipeline['nodes'][number]['status'] }).status]]} />
        </ReactFlow>
      </div>

      <ol className="mt-3 flex flex-wrap gap-1.5" data-testid="pipeline-text">
        {pipeline.nodes.map((node) => (
          <li key={node.id}>
            <button
              type="button"
              data-phase={node.id}
              onClick={() => onSelect(node.id)}
              aria-pressed={node.id === selected}
              className={`rounded border px-2 py-1 font-mono text-[11px] uppercase tracking-[0.06em] ${
                node.id === selected
                  ? 'border-brand text-ink'
                  : 'border-hairline-strong text-ink-muted hover:text-ink'
              }`}
            >
              {node.label}{' '}
              <span style={{ color: TONE_COLOR[STATUS_TONE[node.status]] }}>
                {STATUS_WORD[node.status]}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}
