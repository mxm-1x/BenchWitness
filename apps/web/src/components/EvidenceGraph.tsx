import { useEffect, useRef, useState } from 'react'
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { ZoomIn, ZoomOut, Maximize2, Layers } from 'lucide-react'
import type { Investigation } from '../api'

const shortId = (id: string) => id.length > 24 ? `${id.slice(0, 10)}…${id.slice(-7)}` : id

function getNodeRole(kind: string): { label: string; badgeClass: string } {
  switch (kind) {
    case 'source': return { label: 'Canonical Source Record', badgeClass: 'bg-[#5B2BE8]/10 text-[#5B2BE8] border-[#DDD0FA]' }
    case 'sample': return { label: 'Derived Sample Version', badgeClass: 'bg-[#EA580C]/10 text-[#EA580C] border-[#FED7AA]' }
    case 'dataset': return { label: 'Dataset Collection', badgeClass: 'bg-[#8B5CF6]/10 text-[#8B5CF6] border-[#DDD0FA]' }
    case 'run': return { label: 'Measured Experiment Run', badgeClass: 'bg-[#0D9488]/10 text-[#0D9488] border-[#A7F3D0]' }
    case 'claim': return { label: 'Evaluation Claim', badgeClass: 'bg-[#ED3C65]/10 text-[#ED3C65] border-[#FECDD8]' }
    default: return { label: 'Graph Entity', badgeClass: 'bg-violet-100/60 text-violet-800 border-violet-200' }
  }
}

export function EvidenceGraph({ investigation }: { investigation: Investigation }) {
  const container = useRef<HTMLDivElement>(null)
  const cyRef = useRef<Core | null>(null)
  const [selected, setSelected] = useState<{ id: string; label: string; kind: string } | null>(null)
  const [runId, setRunId] = useState(investigation.impacted_runs[0]?.run_id ?? '')
  const run = investigation.impacted_runs.find((item) => item.run_id === runId)
  const evidence = run?.evidence.slice(0, 50) ?? []
  const hidden = (run?.evidence.length ?? 0) - evidence.length

  useEffect(() => {
    if (!container.current || !run || !evidence.length) return
    const nodes = new Map<string, ElementDefinition>()
    const edges = new Map<string, ElementDefinition>()
    const addNode = (id: string, label: string, kind: string) => {
      if (!nodes.has(id)) nodes.set(id, { data: { id, label, kind } })
    }
    const addEdge = (from: string, to: string) => {
      const id = `${from} → ${to}`
      if (!edges.has(id)) edges.set(id, { data: { id, source: from, target: to } })
    }
    for (const path of evidence) {
      const claim = run.evaluation_claim_id
      addNode(path.canonical_source_record_id, `Source ${shortId(path.canonical_source_record_id)}`, 'source')
      addNode(path.training_sample_id, `Train ${shortId(path.training_sample_id)}`, 'sample')
      addNode(path.training_dataset_id, `Train Set ${shortId(path.training_dataset_id)}`, 'dataset')
      addNode(path.evaluation_sample_id, `Eval ${shortId(path.evaluation_sample_id)}`, 'sample')
      addNode(path.evaluation_dataset_id, `Eval Set ${shortId(path.evaluation_dataset_id)}`, 'dataset')
      addNode(run.run_id, `Run ${shortId(run.run_id)}`, 'run')
      addNode(claim, `Claim ${shortId(claim)}`, 'claim')
      addEdge(path.canonical_source_record_id, path.training_sample_id)
      addEdge(path.canonical_source_record_id, path.evaluation_sample_id)
      addEdge(path.training_sample_id, path.training_dataset_id)
      addEdge(path.evaluation_sample_id, path.evaluation_dataset_id)
      addEdge(path.training_dataset_id, run.run_id)
      addEdge(path.evaluation_dataset_id, run.run_id)
      addEdge(run.run_id, claim)
    }

    const cy = cytoscape({
      container: container.current,
      elements: [...nodes.values(), ...edges.values()],
      layout: {
        name: 'breadthfirst',
        directed: true,
        padding: 36,
        spacingFactor: 1.35,
        animate: false,
      },
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            color: '#1F1438',
            'font-family': 'system-ui, -apple-system, sans-serif',
            'font-size': 10,
            'font-weight': 600,
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'background-color': '#C4B5FD',
            'border-width': 2,
            'border-color': '#FFFFFF',
            width: 26,
            height: 26,
            'text-background-color': '#FFFFFF',
            'text-background-opacity': 0.9,
            'text-background-padding': '3px',
            'text-background-shape': 'roundrectangle',
            'text-border-color': '#E8E0F5',
            'text-border-width': 1,
            'text-border-opacity': 0.8,
          },
        },
        {
          selector: 'node[kind = "source"]',
          style: {
            'background-color': '#5B2BE8',
            'border-color': '#DDD0FA',
            'border-width': 3,
            width: 32,
            height: 32,
          },
        },
        {
          selector: 'node[kind = "sample"]',
          style: {
            'background-color': '#EA580C',
            'border-color': '#FED7AA',
            'border-width': 2,
            width: 24,
            height: 24,
          },
        },
        {
          selector: 'node[kind = "dataset"]',
          style: {
            shape: 'round-rectangle',
            'background-color': '#8B5CF6',
            'border-color': '#DDD0FA',
            'border-width': 2,
            width: 30,
            height: 24,
          },
        },
        {
          selector: 'node[kind = "run"]',
          style: {
            'background-color': '#0D9488',
            'border-color': '#A7F3D0',
            'border-width': 3,
            width: 30,
            height: 30,
          },
        },
        {
          selector: 'node[kind = "claim"]',
          style: {
            shape: 'diamond',
            'background-color': '#ED3C65',
            'border-color': '#FECDD8',
            'border-width': 2,
            width: 28,
            height: 28,
          },
        },
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': '#C4B5FD',
            'curve-style': 'bezier',
            'target-arrow-shape': 'triangle',
            'target-arrow-color': '#5B2BE8',
            'arrow-scale': 1.1,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width': 4,
            'border-color': '#2B1270',
          },
        },
      ],
    })

    cy.on('tap', 'node', (event) => {
      const node = event.target
      setSelected({ id: node.id(), label: node.data('label') ?? '', kind: node.data('kind') ?? '' })
    })

    cy.on('tap', (event) => {
      if (event.target === cy) setSelected(null)
    })

    cyRef.current = cy
    return () => cy.destroy()
  }, [run, evidence.length])

  function handleZoomIn() { cyRef.current?.zoom(cyRef.current.zoom() * 1.25) }
  function handleZoomOut() { cyRef.current?.zoom(cyRef.current.zoom() * 0.8) }
  function handleFit() { cyRef.current?.fit(undefined, 30) }

  if (!investigation.impacted_runs.length) {
    const completeCleanResult =
      investigation.finding_status === 'clean_within_recorded_lineage' && investigation.coverage_complete

    return (
      <div className="rounded-2xl border border-dashed border-[#DDD0FA] bg-[#FAF8FE] p-8 text-center text-[#6B5B87]">
        <Layers className="mx-auto mb-2 text-[#9888B2]" size={28} />
        <p className="font-medium">No confirmed impact paths are available for this source.</p>
        <p className="mt-1 text-xs text-[#9888B2]">
          {completeCleanResult
            ? 'Complete recorded lineage contains no confirmed sample overlap for this source.'
            : 'No impact paths were returned. Missing or incomplete provenance remains unknown; this is not proof the data is clean.'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Top Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#E8E0F5] bg-white p-3 shadow-xs">
        <div className="flex items-center gap-2">
          <label htmlFor="graph-run" className="text-xs font-semibold text-[#5B2BE8] uppercase tracking-wider">Run</label>
          <select
            id="graph-run"
            value={runId}
            onChange={(event) => { setRunId(event.target.value); setSelected(null) }}
            className="rounded-full border border-[#DDD0FA] bg-[#FAF8FE] px-3 py-1.5 text-xs font-medium text-[#1F1438] outline-none transition focus:border-[#5B2BE8] focus:ring-1 focus:ring-[#5B2BE8]"
          >
            {investigation.impacted_runs.map((item) => (
              <option key={item.run_id} value={item.run_id}>
                {shortId(item.run_id)} ({item.integrity_status})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="rounded-full bg-[#F1ECFE] px-2.5 py-1 text-[11px] font-semibold text-[#5B2BE8]">
            {evidence.length} path{evidence.length === 1 ? '' : 's'} shown{hidden > 0 ? ` · ${hidden} more in report` : ''}
          </span>
          <div className="flex items-center gap-1 border-l border-[#E8E0F5] pl-2">
            <button
              type="button"
              onClick={handleZoomIn}
              aria-label="Zoom in"
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#5B2BE8] transition"
            >
              <ZoomIn size={14} />
            </button>
            <button
              type="button"
              onClick={handleZoomOut}
              aria-label="Zoom out"
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#5B2BE8] transition"
            >
              <ZoomOut size={14} />
            </button>
            <button
              type="button"
              onClick={handleFit}
              aria-label="Reset zoom and fit graph"
              className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#5B2BE8] transition"
            >
              <Maximize2 size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Cytoscape Container */}
      <div className="relative overflow-hidden rounded-2xl border border-[#DDD0FA] bg-[#FAF8FE] shadow-inner">
        <div
          ref={container}
          className="h-[340px] w-full cursor-grab active:cursor-grabbing"
          role="img"
          aria-label="Graph of canonical source, training and evaluation samples, datasets, measured run, and evaluation claim"
        />

        {/* Floating Zoom & Pan hint */}
        <div className="pointer-events-none absolute bottom-3 right-3 rounded-full bg-white/85 px-2.5 py-1 text-[10px] text-[#9888B2] backdrop-blur-xs border border-[#E8E0F5]">
          Scroll to zoom · Drag to pan · Click node to inspect
        </div>
      </div>

      {/* Color-coded Node Legend */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#E8E0F5] bg-white px-3.5 py-2 text-[11px] text-[#6B5B87]">
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#5B2BE8] ring-2 ring-[#DDD0FA]" />
          <span className="font-medium text-[#1F1438]">Source Record</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#EA580C] ring-2 ring-[#FED7AA]" />
          <span className="font-medium text-[#1F1438]">Sample Version</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-xs bg-[#8B5CF6] ring-2 ring-[#DDD0FA]" />
          <span className="font-medium text-[#1F1438]">Dataset Collection</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-[#0D9488] ring-2 ring-[#A7F3D0]" />
          <span className="font-medium text-[#1F1438]">Measured Run</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rotate-45 bg-[#ED3C65] ring-2 ring-[#FECDD8]" />
          <span className="font-medium text-[#1F1438]">Evaluation Claim</span>
        </div>
      </div>

      {/* Selected Node Inspector */}
      {selected && (
        <div className="animate-in fade-in flex items-center justify-between gap-3 rounded-xl border border-[#DDD0FA] bg-[#F8F5FF] p-3 text-xs shadow-xs">
          <div>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${getNodeRole(selected.kind).badgeClass}`}>
                {getNodeRole(selected.kind).label}
              </span>
              <strong className="text-[#1F1438]">{selected.label}</strong>
            </div>
            <p className="mt-1 font-mono text-[11px] text-[#5B2BE8] break-all">{selected.id}</p>
          </div>
          <button
            type="button"
            onClick={() => setSelected(null)}
            className="text-xs text-[#9888B2] hover:text-[#1F1438] transition"
          >
            Clear
          </button>
        </div>
      )}

      {/* Path List */}
      {run && (
        <div className="max-h-[160px] space-y-2 overflow-y-auto rounded-xl border border-[#E8E0F5] bg-white p-3 text-xs">
          <div className="text-[10px] font-bold uppercase tracking-wider text-[#9888B2]">
            Detailed Provenance Paths ({evidence.length})
          </div>
          {evidence.map((path, index) => (
            <div
              key={`${path.run_id}-${path.training_sample_id}-${index}`}
              className="flex flex-col gap-1 rounded-lg border border-[#F1ECFE] bg-[#FAF8FE] p-2 font-mono text-[11px] text-[#6B5B87]"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-bold text-[#5B2BE8]">PATH {String(index + 1).padStart(2, '0')}</span>
                <span className="text-[10px] text-[#9888B2]">Canonical Source: <code className="text-[#1F1438]">{shortId(path.canonical_source_record_id)}</code></span>
              </div>
              <div className="flex flex-wrap items-center gap-1.5 text-[10px]">
                <span className="text-[#EA580C]">Train sample {shortId(path.training_sample_id)} ({path.training_derivation_hops}h)</span>
                <span className="text-[#9888B2]">→</span>
                <span className="text-[#8B5CF6]">Train set {shortId(path.training_dataset_id)}</span>
                <span className="text-[#9888B2]">│</span>
                <span className="text-[#EA580C]">Eval sample {shortId(path.evaluation_sample_id)} ({path.evaluation_derivation_hops}h)</span>
                <span className="text-[#9888B2]">→</span>
                <span className="text-[#8B5CF6]">Eval set {shortId(path.evaluation_dataset_id)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
