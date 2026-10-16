import { useEffect, useRef, useState } from 'react'
import cytoscape, { type ElementDefinition } from 'cytoscape'
import type { Investigation } from '../api'

const shortId = (id: string) => id.length > 24 ? `${id.slice(0, 10)}…${id.slice(-7)}` : id

export function EvidenceGraph({ investigation }: { investigation: Investigation }) {
  const container = useRef<HTMLDivElement>(null)
  const [selected, setSelected] = useState<string | null>(null)
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
      addNode(path.training_sample_id, `Train sample ${shortId(path.training_sample_id)}`, 'sample')
      addNode(path.training_dataset_id, `Train set ${shortId(path.training_dataset_id)}`, 'dataset')
      addNode(path.evaluation_sample_id, `Eval sample ${shortId(path.evaluation_sample_id)}`, 'sample')
      addNode(path.evaluation_dataset_id, `Eval set ${shortId(path.evaluation_dataset_id)}`, 'dataset')
      addNode(run.run_id, `Measured run ${shortId(run.run_id)}`, 'run')
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
      layout: { name: 'breadthfirst', directed: true, padding: 32, spacingFactor: 1.4 },
      style: [
        { selector: 'node', style: {
          label: 'data(label)', color: '#dce7e1', 'background-color': '#233c3a',
          'border-width': 1, 'border-color': '#47726b', 'font-size': 10,
          'text-valign': 'bottom', 'text-margin-y': 8, width: 22, height: 22,
        } },
        { selector: 'node[kind = "source"]', style: { 'background-color': '#b6ed73', 'border-color': '#d9ff9d' } },
        { selector: 'node[kind = "claim"]', style: { 'background-color': '#eebf6e', 'border-color': '#ffd69d' } },
        { selector: 'node[kind = "run"]', style: { 'background-color': '#81acff', 'border-color': '#bfd1ff' } },
        { selector: 'edge', style: {
          width: 1.5, 'line-color': '#64827d', 'target-arrow-shape': 'triangle',
          'target-arrow-color': '#64827d', 'curve-style': 'bezier',
        } },
      ],
    })
    cy.on('tap', 'node', (event) => setSelected(event.target.id()))
    return () => cy.destroy()
  }, [run, evidence.length])

  if (!investigation.impacted_runs.length) {
    return <p className="empty-state">No confirmed impact paths are available for this source.</p>
  }
  return (
    <div className="graph-layout">
      <div className="graph-toolbar">
        <label htmlFor="graph-run">Evidence for run</label>
        <select id="graph-run" value={runId} onChange={(event) => { setRunId(event.target.value); setSelected(null) }}>
          {investigation.impacted_runs.map((item) => <option key={item.run_id} value={item.run_id}>{shortId(item.run_id)}</option>)}
        </select>
        <span>{evidence.length} path{evidence.length === 1 ? '' : 's'} shown{hidden > 0 ? ` · ${hidden} more in report` : ''}</span>
      </div>
      <div ref={container} className="evidence-graph" role="img" aria-label="Graph of canonical source, training and evaluation samples, datasets, measured run, and evaluation claim" />
      <div className="graph-caption">
        <span><i className="legend-dot source" /> Canonical source</span>
        <span><i className="legend-dot run" /> Measured run</span>
        <span><i className="legend-dot claim" /> Evaluation claim</span>
      </div>
      {selected && <p className="selected-node"><strong>Selected graph ID</strong> <code>{selected}</code></p>}
      {run && <div className="path-list">
        {evidence.map((path, index) => <div key={`${path.run_id}-${path.training_sample_id}-${index}`}>
          <span>PATH {String(index + 1).padStart(2, '0')}</span>
          <code>{path.canonical_source_record_id}</code>
          <span>→ training {path.training_sample_id} ({path.training_derivation_hops} hops)</span>
          <span>→ evaluation {path.evaluation_sample_id} ({path.evaluation_derivation_hops} hops)</span>
        </div>)}
      </div>}
    </div>
  )
}
