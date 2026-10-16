import { StrictMode, Suspense, lazy, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Activity, ArrowDownRight, ArrowRight, Check, CircleAlert, Database, GitBranch, LockKeyhole, Play, RefreshCw, ScanSearch, ShieldCheck, Sparkles } from 'lucide-react'
import { api, idPath, type ActionProposal, type AgentMessage, type AgentSession, type Audit, type Investigation, type Overview, type RecoveryJob, type Run } from './api'
import { SoftPillButton } from './components/SoftPillButton'
import './style.css'

const EvidenceGraph = lazy(() => import('./components/EvidenceGraph').then(({ EvidenceGraph }) => ({ default: EvidenceGraph })))

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 3_000 } } })
const labels: Record<string, string> = {
  'demo-contaminated-a': 'Experiment A',
  'demo-contaminated-b': 'Experiment B',
  'demo-clean-control': 'Clean control',
  'demo-unknown-lineage': 'Unknown lineage',
}

function humanExperiment(id: string) { return labels[id] ?? id }
function shortId(id: string) { return id.length > 27 ? `${id.slice(0, 14)}…${id.slice(-8)}` : id }
function score(value: number | undefined) { return value === undefined ? '—' : `${(value * 100).toFixed(1)}%` }
function time(value: string | null | undefined) { return value ? new Date(value).toLocaleString() : '—' }
function statusLabel(value: string) { return value.replaceAll('_', ' ') }

function App() {
  const [token, setToken] = useState(() => sessionStorage.getItem('bw-token') ?? '')
  const [sourceId, setSourceId] = useState('')
  const [investigationId, setInvestigationId] = useState(() => sessionStorage.getItem('bw-investigation') ?? '')
  const [jobId, setJobId] = useState(() => sessionStorage.getItem('bw-job') ?? '')
  const [quarantine, setQuarantine] = useState<ActionProposal | null>(null)
  const [repair, setRepair] = useState<ActionProposal | null>(null)
  const [proposalReason, setProposalReason] = useState('')
  const [approvalReason, setApprovalReason] = useState('')
  const [agentSession, setAgentSession] = useState<AgentSession | null>(null)
  const [agentMessage, setAgentMessage] = useState<AgentMessage | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const ready = useQuery({ queryKey: ['ready'], queryFn: () => api<{ status: string; graph: string }>('/readyz'), refetchInterval: 10_000 })
  const overview = useQuery({ queryKey: ['overview'], queryFn: () => api<Overview>('/api/v1/overview'), refetchInterval: 10_000 })
  const investigation = useQuery({
    queryKey: ['investigation', investigationId], enabled: Boolean(investigationId),
    queryFn: () => api<Investigation>(`/api/v1/investigations/${idPath(investigationId)}`),
  })
  const job = useQuery({
    queryKey: ['job', jobId], enabled: Boolean(jobId),
    queryFn: () => api<RecoveryJob>(`/api/v1/jobs/${idPath(jobId)}`),
    refetchInterval: (query) => ['pending_enqueue', 'queued', 'running'].includes(query.state.data?.status ?? '') ? 1_500 : false,
  })

  useEffect(() => {
    if (!sourceId && overview.data) {
      const confirmed = overview.data.audits.find((item) => item.status === 'confirmed' && item.evidence.length)
      if (confirmed) setSourceId(confirmed.evidence[0].canonical_source_record_id)
    }
  }, [overview.data, sourceId])
  useEffect(() => { if (job.data?.status === 'succeeded') void overview.refetch() }, [job.data?.status])

  function rememberToken(value: string) { setToken(value); sessionStorage.setItem('bw-token', value) }
  function rememberInvestigation(value: string) { setInvestigationId(value); sessionStorage.setItem('bw-investigation', value) }
  function rememberJob(value: string) { setJobId(value); sessionStorage.setItem('bw-job', value) }
  async function act(name: string, task: () => Promise<void>) {
    setBusy(name); setError(''); setNotice('')
    try { await task() } catch (caught) { setError(caught instanceof Error ? caught.message : 'Request failed') }
    finally { setBusy('') }
  }

  const audits = overview.data?.audits ?? []
  const runs = overview.data?.runs ?? []
  const report = investigation.data
  const currentJob = job.data
  const latest = (experimentId: string) => runs.find((item) => item.experiment_id === experimentId)
  const runById = (id: string) => runs.find((item) => item.run_id === id)
  const tokenMissing = !token.trim()
  const activeSource = sourceId.trim()

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <a className="brand" href="#top" aria-label="BenchWitness home"><span className="brand-mark"><GitBranch size={22} /></span><span>BENCH<span>WITNESS</span></span></a>
        <div className="workspace-pill"><span className="pulse-dot" /> LOCAL WORKSPACE <span className="workspace-suffix">/ DEMO</span></div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Primary navigation">
          <a href="#overview"><Activity size={17} /> Overview</a>
          <a href="#experiments"><Database size={17} /> Experiments</a>
          <a href="#evidence"><ScanSearch size={17} /> Evidence graph</a>
          <a href="#recovery"><ShieldCheck size={17} /> Recovery</a>
          <a href="#agent"><Sparkles size={17} /> Agent memory</a>
        </nav>
        <div className="sidebar-footer"><span className="footer-line" /><p>Trace the data.<br />Challenge the score.<br /><strong>Prove the recovery.</strong></p><small>FalkorDB GRAPH HACKS · 2026</small></div>
      </aside>

      <main id="top" className="main-content">
        <header className="topbar"><div className="breadcrumb">WORKSPACE <span>/</span> INTEGRITY OVERVIEW</div><div className="top-right"><span className={`connection ${ready.isSuccess ? 'up' : 'down'}`}><span className="pulse-dot" /> GRAPH {ready.isSuccess ? 'CONNECTED' : 'UNAVAILABLE'}</span><span className="avatar">BW</span></div></header>
        <div className="content-wrap">
          <section id="overview" className="hero">
            <div className="hero-copy"><span className="eyebrow"><span className="eyebrow-line" /> EVALUATION INTEGRITY, VERIFIED</span><h1>Every score has<br /><em>a story.</em></h1><p>Trace exact source records through training, evidence, and recovery. Every result below comes from your local graph and measured runs.</p><div className="hero-actions"><SoftPillButton variant="light" className="hero-primary" disabled={Boolean(busy) || tokenMissing} onClick={() => void act('seed', async () => { await api('/api/v1/demo/seed', token, 'POST'); await overview.refetch(); setNotice('Synthetic lineage seeded in FalkorDB.') })}><GitBranch size={16} /> {busy === 'seed' ? 'Seeding…' : 'Seed graph'} <ArrowRight size={15} /></SoftPillButton><button className="text-button" disabled={Boolean(busy) || tokenMissing || !audits.length} onClick={() => void act('evaluate', async () => { await api('/api/v1/demo/evaluate', token, 'POST'); await overview.refetch(); setNotice('Measured baseline runs appended to the graph.') })}><Play size={15} /> {busy === 'evaluate' ? 'Evaluating…' : 'Run baseline evaluations'}</button></div></div>
            <div className="hero-visual" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" /><div className="orbit-node node-a" /><div className="orbit-node node-b" /><div className="orbit-node node-c" /><div className="orbit-node node-d" /><div className="orbit-center"><GitBranch size={35} strokeWidth={1.4} /></div><div className="hero-visual-label">SOURCE → EVIDENCE → TRUST</div></div>
          </section>

          <div className="credential-strip"><div><LockKeyhole size={17} /><span>Local approval token</span><small>Kept in this browser tab</small></div><input aria-label="Local API bearer token" type="password" autoComplete="off" placeholder="Paste BENCHWITNESS_API_TOKEN from .env" value={token} onChange={(event) => rememberToken(event.target.value)} /><span className={tokenMissing ? 'credential-state missing' : 'credential-state'}>{tokenMissing ? 'REQUIRED FOR ACTIONS' : 'READY'}</span></div>
          {error && <div className="alert error" role="alert"><CircleAlert size={18} /><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
          {notice && <div className="alert success" role="status"><Check size={18} /><span>{notice}</span><button onClick={() => setNotice('')} aria-label="Dismiss notice">×</button></div>}
          {overview.isError && <div className="alert error" role="alert"><CircleAlert size={18} />Unable to read FalkorDB overview. Check that Compose and the API are running.</div>}

          <section className="stats-grid" aria-label="Graph-backed summary">
            <Stat label="EXPERIMENTS" value={audits.length ? String(audits.length) : '—'} detail="Graph-defined configurations" icon={<Database size={19} />} />
            <Stat label="MEASURED RUNS" value={runs.length ? String(runs.length) : '—'} detail="Persisted evaluation versions" icon={<Activity size={19} />} />
            <Stat label="CONFIRMED OVERLAPS" value={audits.length ? String(audits.filter((item) => item.status === 'confirmed').length) : '—'} detail="Exact source ancestry" icon={<ScanSearch size={19} />} tone="amber" />
            <Stat label="AFFECTED RUNS" value={report ? String(report.impacted_runs.length) : '—'} detail={report ? 'In current investigation' : 'Run an investigation'} icon={<ArrowDownRight size={19} />} tone="lime" />
          </section>

          <section id="experiments" className="section-block"><SectionHeading index="01" title="Experiment ledger" subtitle="Current lineage audits and actual measured evaluations, read from FalkorDB." action={<button className="small-action" onClick={() => void overview.refetch()}><RefreshCw size={14} /> Refresh</button>} />
            {!audits.length ? <div className="empty-card">{overview.isLoading ? 'Loading graph records…' : 'No seeded experiments yet. Add the synthetic lineage, then run baseline evaluations.'}</div> : <div className="experiment-grid">{audits.map((audit) => <ExperimentCard key={audit.experiment_id} audit={audit} run={latest(audit.experiment_id)} onTrace={() => { if (audit.evidence[0]) { setSourceId(audit.evidence[0].canonical_source_record_id); document.getElementById('evidence')?.scrollIntoView({ behavior: 'smooth' }) } }} />)}</div>}
          </section>

          <section id="evidence" className="section-block"><SectionHeading index="02" title="Follow the evidence" subtitle="One canonical source, two graph paths, every dependent claim." />
            <div className="investigate-bar"><div><label htmlFor="source-id">CANONICAL SOURCE RECORD ID</label><input id="source-id" value={sourceId} onChange={(event) => setSourceId(event.target.value)} placeholder="source:synthetic-v1:…" /></div><SoftPillButton variant="dark" disabled={Boolean(busy) || tokenMissing || !activeSource || !runs.length} onClick={() => void act('investigate', async () => { const result = await api<Investigation>('/api/v1/impact', token, 'POST', { source_record_id: activeSource }); rememberInvestigation(result.investigation_id); setQuarantine(null); setRepair(null); setNotice(`Investigation ${shortId(result.investigation_id)} recorded.`) })}><ScanSearch size={15} /> {busy === 'investigate' ? 'Tracing…' : 'Investigate source'}</SoftPillButton></div>
            {investigation.isError && <div className="alert error" role="alert"><CircleAlert size={18} />Saved investigation is unavailable. Run a new investigation.</div>}
            {report ? <div className="evidence-grid"><div className="panel graph-panel"><div className="panel-heading"><div><span className="panel-kicker">GRAPH TRACE</span><h3>Exact lineage paths</h3></div><Status value={report.finding_status} /></div><Suspense fallback={<p className="muted">Loading evidence graph…</p>}><EvidenceGraph key={report.investigation_id} investigation={report} /></Suspense></div><div className="panel impact-panel"><div className="panel-heading"><div><span className="panel-kicker">BLAST RADIUS</span><h3>Dependent claims</h3></div><strong className="impact-count">{report.impacted_runs.length}</strong></div><p className="muted">{report.coverage_complete ? 'Complete within recorded lineage' : `Incomplete: ${report.unresolved_run_ids.length} unresolved runs`}</p>{report.impacted_runs.length ? report.impacted_runs.map((item) => <div className="impact-item" key={item.run_id}><div><strong>{humanExperiment(item.experiment_id)}</strong><Status value={item.integrity_status} /></div><code title={item.run_id}>{shortId(item.run_id)}</code><div className="metric-line">{item.metrics.map((metric) => <span key={metric.claim_id}>{metric.name.toUpperCase()} <b>{score(metric.value)}</b></span>)}</div></div>) : <p className="empty-state">No dependent claims found for this source.</p>}<div className="detail-foot">Investigation <code title={report.investigation_id}>{shortId(report.investigation_id)}</code><br />Recorded {time(report.created_at)}</div></div></div> : <div className="empty-card">Investigate a source to reveal its exact training and evaluation paths. The graph appears only after FalkorDB returns evidence.</div>}
          </section>

          <section id="recovery" className="section-block"><SectionHeading index="03" title="Decide & recover" subtitle="Proposals name affected claims. Each execution needs a separate, explicit approval." />
            <div className="decision-grid"><div className="panel decision-panel"><div className="panel-heading"><div><span className="panel-kicker">HUMAN REVIEW</span><h3>Approval gate</h3></div><LockKeyhole size={20} /></div><label htmlFor="proposal-reason">Proposal reason</label><input id="proposal-reason" value={proposalReason} onChange={(event) => setProposalReason(event.target.value)} placeholder="Why these claims need review" /><div className="decision-actions"><button className="small-action" disabled={!report || !report.coverage_complete || !report.impacted_runs.length || tokenMissing || !proposalReason.trim() || Boolean(busy)} onClick={() => void act('quarantine-proposal', async () => { setRepair(null); setQuarantine(await api<ActionProposal>(`/api/v1/investigations/${idPath(report!.investigation_id)}/quarantine-proposals`, token, 'POST', { reason: proposalReason.trim() })) })}>Propose quarantine</button><button className="small-action" disabled={!report || !report.coverage_complete || !report.impacted_runs.length || tokenMissing || !proposalReason.trim() || Boolean(busy)} onClick={() => void act('repair-proposal', async () => { setQuarantine(null); setRepair(await api<ActionProposal>(`/api/v1/investigations/${idPath(report!.investigation_id)}/repair-proposals`, token, 'POST', { reason: proposalReason.trim() })) })}>Propose clean repair</button></div>{(quarantine || repair) && <div className="scope-box"><span>TARGET SCOPE</span>{quarantine && <p>Quarantine: {quarantine.target_claim_ids.length} evaluation claims · {quarantine.status}</p>}{repair && <p>Repair: {repair.target_claim_ids.length} evaluation claims · {repair.status}</p>}<ul>{(repair ?? quarantine)?.target_claim_ids.map((id) => <li key={id}><code>{shortId(id)}</code></li>)}</ul></div>}<label htmlFor="approval-reason">Approval reason</label><input id="approval-reason" value={approvalReason} onChange={(event) => setApprovalReason(event.target.value)} placeholder="I reviewed the evidence and approve…" /><div className="decision-actions"><button className="small-action" disabled={!quarantine || quarantine.status === 'approved' || !approvalReason.trim() || tokenMissing || Boolean(busy)} onClick={() => void act('quarantine-approval', async () => { const result = await api<ActionProposal>(`/api/v1/actions/${idPath(quarantine!.action_id)}/approve`, token, 'POST', { reason: approvalReason.trim() }); setQuarantine(result); await investigation.refetch(); setNotice('Quarantine approval recorded in FalkorDB.') })}>Approve quarantine</button><SoftPillButton variant="light" size="sm" className="repair-button" disabled={!repair || repair.status === 'approved' || !approvalReason.trim() || tokenMissing || Boolean(busy)} onClick={() => void act('repair-approval', async () => { const result = await api<RecoveryJob>(`/api/v1/repairs/${idPath(repair!.action_id)}/approve`, token, 'POST', { reason: approvalReason.trim() }); rememberJob(result.job_id); setRepair({ ...repair!, status: 'approved' }); setNotice('Approved repair queued on the separate Redis broker.') })}>Approve & run repair <ArrowRight size={14} /></SoftPillButton></div></div>
            {job.isError && <div className="alert error" role="alert"><CircleAlert size={18} />Saved job could not be read from FalkorDB.</div>}
            <div className="panel job-panel"><div className="panel-heading"><div><span className="panel-kicker">VERSIONED OUTCOME</span><h3>Measured recovery</h3></div><Status value={currentJob?.status ?? 'awaiting approval'} /></div>{currentJob ? <><div className="job-timeline"><div><span>JOB ID</span><code title={currentJob.job_id}>{shortId(currentJob.job_id)}</code></div><div><span>STARTED</span><strong>{time(currentJob.started_at)}</strong></div><div><span>FINISHED</span><strong>{time(currentJob.finished_at)}</strong></div></div>{currentJob.error && <p className="job-error">{currentJob.error}</p>}{currentJob.status === 'succeeded' && <div className="compare-list">{currentJob.original_run_ids.map((originalId, index) => { const before = runById(originalId); const after = runById(currentJob.repaired_run_ids[index] ?? ''); return <div key={originalId} className="compare-row"><div><span>BEFORE · {humanExperiment(before?.experiment_id ?? originalId)}</span><strong>{score(before?.accuracy)}</strong><small>Original preserved</small></div><ArrowRight size={18} /><div><span>AFTER · CLEAN SPLIT</span><strong>{score(after?.accuracy)}</strong><small>{after ? `${after.training_sample_count} train / ${after.evaluation_sample_count} eval` : 'Loading measured run…'}</small></div></div> })}</div>}</> : <p className="empty-state">No recovery job yet. Approve a clean repair to run the worker and compare measured versions.</p>}</div></div>
          </section>

          <section id="agent" className="section-block agent-section"><SectionHeading index="04" title="Memory across sessions" subtitle="A fresh agent session verifies previous graph evidence before reusing it." /><div className="agent-grid"><div className="agent-intro"><div className="agent-icon"><Sparkles size={25} /></div><h3>Evidence that remembers.</h3><p>The local typed agent records a confirmed investigation in FalkorDB. Start a new session and investigate the same source to see whether the memory is verified or stale.</p><button className="small-action" disabled={tokenMissing || Boolean(busy)} onClick={() => void act('session', async () => { setAgentSession(await api<AgentSession>('/api/v1/agent/sessions', token, 'POST')); setAgentMessage(null) })}>{agentSession ? 'Start a fresh session' : 'Start agent session'} <ArrowRight size={14} /></button></div><div className="panel agent-result"><div className="panel-heading"><div><span className="panel-kicker">AGENT ACTIVITY</span><h3>{agentSession ? shortId(agentSession.session_id) : 'Awaiting a session'}</h3></div><span className="agent-live"><span className="pulse-dot" /> GRAPH MEMORY</span></div>{agentSession ? <><p className="muted">Created {time(agentSession.created_at)}</p><button className="small-action" disabled={!activeSource || Boolean(busy)} onClick={() => void act('agent-investigation', async () => { setAgentMessage(await api<AgentMessage>(`/api/v1/agent/sessions/${idPath(agentSession.session_id)}/messages`, token, 'POST', { intent: 'investigate_source', subject_id: activeSource })) })}><ScanSearch size={14} /> Investigate current source</button>{agentMessage && <div className="agent-answer"><Status value={`memory ${agentMessage.memory_status}`} /><p>{agentMessage.summary}</p><div>TOOLS USED <strong>{agentMessage.tools_used.join(' → ')}</strong></div>{agentMessage.investigation && <div>INVESTIGATION <code>{shortId(agentMessage.investigation.investigation_id)}</code></div>}</div>}</> : <p className="empty-state">Start a session after investigating a source. No answer is generated until graph tools return evidence.</p>}</div></div></section>
          <footer className="page-footer"><span>BENCHWITNESS / LOCAL EVIDENCE WORKSPACE</span><span>GRAPH: FALKORDB · JOBS: REDIS · METRICS: MEASURED</span></footer>
        </div>
      </main>
    </div>
  )
}

function Stat({ label, value, detail, icon, tone = '' }: { label: string; value: string; detail: string; icon: React.ReactNode; tone?: string }) { return <div className={`stat-card ${tone}`}><div className="stat-top"><span>{label}</span>{icon}</div><strong>{value}</strong><small>{detail}</small></div> }
function SectionHeading({ index, title, subtitle, action }: { index: string; title: string; subtitle: string; action?: React.ReactNode }) { return <div className="section-heading"><div className="section-number">{index}</div><div><h2>{title}</h2><p>{subtitle}</p></div>{action && <div className="section-action">{action}</div>}</div> }
function Status({ value }: { value: string }) { const className = value.includes('confirmed') || value.includes('suspect') || value.includes('failed') ? 'warn' : value.includes('clean') || value.includes('succeeded') || value.includes('verified') || value.includes('approved') ? 'good' : 'neutral'; return <span className={`status-badge ${className}`}><span />{statusLabel(value)}</span> }
function ExperimentCard({ audit, run, onTrace }: { audit: Audit; run?: Run; onTrace: () => void }) { return <article className="experiment-card"><div className="experiment-card-head"><div className="experiment-icon"><GitBranch size={19} /></div><Status value={audit.status} /></div><div className="experiment-name"><span>MODEL CONFIGURATION</span><h3>{humanExperiment(audit.experiment_id)}</h3></div><div className="experiment-score"><strong>{score(run?.accuracy)}</strong><span>{run ? 'MEASURED ACCURACY' : 'NO MEASURED RUN'}</span></div><div className="experiment-meta"><span>TRAINING SET <code>{shortId(audit.training_dataset_id)}</code></span><span>EVALUATION SET <code>{shortId(audit.evaluation_dataset_id)}</code></span></div><div className="experiment-footer"><span>{run ? `${run.training_sample_count} train · ${run.evaluation_sample_count} eval` : 'Run the baseline to measure'}</span>{audit.evidence.length > 0 && <button onClick={onTrace}>Trace evidence <ArrowRight size={14} /></button>}</div></article> }

createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queryClient}><App /></QueryClientProvider></StrictMode>)
