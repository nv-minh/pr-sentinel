import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { GraphNode } from '../api'
import { GLYPH, TONE_COLOR, formatCost } from '../status'
import { STATUS_TONE, STATUS_WORD } from './layout'

export type PhaseNodeData = GraphNode & { selected: boolean }

export default function PhaseNode({ data }: NodeProps) {
  const node = data as unknown as PhaseNodeData
  const tone = STATUS_TONE[node.status]
  const dim = node.status === 'pending' || node.status === 'skipped'

  return (
    <div
      className={`w-[160px] rounded border bg-surface px-3 py-2.5 text-left shadow-sm ${
        node.selected ? 'border-brand ring-2 ring-brand' : 'border-hairline-strong'
      } ${dim ? 'opacity-60' : ''}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-hairline-strong" />
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-sm font-semibold">{node.label}</span>
        <span className="font-mono text-[11px] font-bold" style={{ color: TONE_COLOR[tone] }}>
          {GLYPH[tone]}
        </span>
      </div>
      <div className="font-mono text-[10px] uppercase tracking-[0.12em]"
           style={{ color: TONE_COLOR[tone] }}>
        {STATUS_WORD[node.status]}
      </div>
      {node.metrics.length > 0 && (
        <dl className="mt-1.5 space-y-0.5 font-mono text-[10.5px] text-ink-muted">
          {node.metrics.map((m) => (
            <div key={m.label} className="flex justify-between gap-2">
              <dt>{m.label}</dt>
              <dd className="tabular-nums text-ink">{m.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {node.cost_usd !== null && (
        <div className="mt-1.5 border-t border-hairline pt-1 font-mono text-[10px] text-ink-muted">
          {formatCost(node.cost_usd)}
          {node.duration_ms ? ` · ${Math.round(node.duration_ms / 1000)}s` : ''}
        </div>
      )}
      <Handle type="source" position={Position.Right} className="!bg-hairline-strong" />
    </div>
  )
}
