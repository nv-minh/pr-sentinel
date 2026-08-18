import { useEffect, useMemo, useRef } from 'react'
import {
  Background, ReactFlow, type Edge, type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { Pipeline } from '../api'
import { useLookup, useT } from '../i18n'
import { GLYPH, TONE_COLOR } from '../status'
import { useTheme } from '../theme'
import PhaseNode from './PhaseNode'
import { POSITION, STATUS_KEY, STATUS_TONE } from './layout'

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
  const t = useT()
  const lookup = useLookup()
  const still = prefersReducedMotion()
  const wrapperRef = useRef<HTMLDivElement>(null)

  // React Flow's attribution link ("React Flow", bottom-right of the canvas)
  // is required by its licence to stay visible — paying to hide it via
  // proOptions.hideAttribution is not an option here — but it is still a real
  // <a href> and the only focusable element left inside this aria-hidden
  // canvas. There is no prop to take it out of the tab order, so reach into
  // the DOM directly. Do not remove this effect to "clean up" a stray
  // tabindex: PipelineGraph.test.tsx asserts the canvas has zero focusable
  // descendants, and this is what keeps that true.
  useEffect(() => {
    const link = wrapperRef.current?.querySelector('.react-flow__attribution a')
    link?.setAttribute('tabindex', '-1')
  })

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
      <div ref={wrapperRef} className="h-[380px] rounded border border-hairline bg-paper" aria-hidden="true">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          colorMode={theme}
          fitView
          fitViewOptions={{ padding: 0.15 }}
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          onNodeClick={(_, node) => onSelect(node.id)}
          minZoom={0.4}
          maxZoom={1.4}
        >
          <Background gap={18} size={1} color="var(--hairline)" />
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
              {lookup(`graph.phase.${node.id}`, node.label)}{' '}
              <span style={{ color: TONE_COLOR[STATUS_TONE[node.status]] }}>
                {GLYPH[STATUS_TONE[node.status]]} {t(STATUS_KEY[node.status])}
              </span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  )
}
