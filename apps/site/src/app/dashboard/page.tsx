"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, GitBranch, RefreshCw } from "lucide-react";
import { SearchInput, SegmentedToggleButton, SoftPillButton } from "@/components/opensourceui";
import { api, idPath, type ActionProposal, type AgentMessage, type AgentSession, type Audit, type Investigation, type RecoveryJob, type Run } from "@/lib/api";
import { useOverview } from "@/lib/use-overview";

const tabs = ["Overview", "Experiment Ledger", "Lineage Trace", "Recovery Gate", "Agent Memory"];
const filters = ["All", "Confirmed", "Clean", "Unknown"];
const statusText: Record<Audit["status"], string> = {
  confirmed: "Confirmed overlap",
  clean_within_recorded_lineage: "Clean within recorded lineage",
  unknown: "Unknown — provenance incomplete",
};
const score = (value?: number) => value === undefined ? "—" : `${(value * 100).toFixed(1)}%`;
const message = (cause: unknown) => cause instanceof Error ? cause.message : "Operation failed";
const field = "w-full rounded-lg bg-neutral-100 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-neutral-900";

export default function Dashboard() {
  const { overview, ready, loading, error, refresh } = useOverview();
  const [tab, setTab] = useState(0);
  const [filter, setFilter] = useState(0);
  const [search, setSearch] = useState("");
  const [selectedExperiment, setSelectedExperiment] = useState("");
  const [source, setSource] = useState("");
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState("");
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [proposalReason, setProposalReason] = useState("");
  const [approvalReason, setApprovalReason] = useState("");
  const [quarantine, setQuarantine] = useState<ActionProposal | null>(null);
  const [repair, setRepair] = useState<ActionProposal | null>(null);
  const [job, setJob] = useState<RecoveryJob | null>(null);
  const [jobIdInput, setJobIdInput] = useState("");
  const [runDetails, setRunDetails] = useState<Record<string, Run>>({});
  const [session, setSession] = useState<AgentSession | null>(null);
  const [agentMessage, setAgentMessage] = useState<AgentMessage | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSelectedExperiment(params.get("experiment") ?? "");
    setToken(sessionStorage.getItem("benchwitness-api-token") ?? "");
    setJobIdInput(sessionStorage.getItem("benchwitness-job-id") ?? "");
  }, []);

  const audits = useMemo(() => overview?.audits ?? [], [overview]);
  const runs = overview?.runs ?? [];
  const selectedAudit = audits.find(a => a.experiment_id === selectedExperiment) ?? audits[0];
  const availableSources = useMemo(() => [...new Set(audits.flatMap(a => a.evidence.map(e => e.canonical_source_record_id)))], [audits]);
  const activeSource = source || selectedAudit?.evidence[0]?.canonical_source_record_id || "";
  const filteredAudits = audits.filter(a =>
    (filter === 0 || (filter === 1 && a.status === "confirmed") || (filter === 2 && a.status === "clean_within_recorded_lineage") || (filter === 3 && a.status === "unknown")) &&
    (a.experiment_id.toLowerCase().includes(search.toLowerCase()) || a.evidence.some(e => e.canonical_source_record_id.toLowerCase().includes(search.toLowerCase())))
  );

  const perform = useCallback(async (name: string, operation: () => Promise<void>) => {
    setBusy(name); setActionError(""); setNotice("");
    try { await operation(); } catch (cause) { setActionError(message(cause)); }
    finally { setBusy(""); }
  }, []);

  const fetchJob = useCallback(async (id: string) => {
    const result = await api<RecoveryJob>(`/api/v1/jobs/${idPath(id)}`);
    setJob(result);
    setJobIdInput(result.job_id);
    sessionStorage.setItem("benchwitness-job-id", result.job_id);
    if (result.status === "succeeded") {
      const ids = [...new Set([...result.original_run_ids, ...result.repaired_run_ids])];
      const details = await Promise.all(ids.map(runId => api<Run>(`/api/v1/runs/${idPath(runId)}`)));
      setRunDetails(Object.fromEntries(details.map(run => [run.run_id, run])));
      await refresh();
    }
    return result;
  }, [refresh]);

  useEffect(() => {
    if (!job || !["pending_enqueue", "queued", "running"].includes(job.status)) return;
    const timer = window.setInterval(() => { void fetchJob(job.job_id).catch(cause => setActionError(message(cause))); }, 2500);
    return () => window.clearInterval(timer);
  }, [job, fetchJob]);

  return <div className="min-h-screen bg-white text-neutral-950">
    <header className="sticky top-0 z-30 bg-white/95 px-6 py-4 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3"><Link href="/" aria-label="Home" className="grid size-9 place-items-center rounded-xl bg-black text-white"><GitBranch size={17}/></Link><div><strong className="block text-sm">BenchWitness</strong><span className="text-xs text-neutral-500">Evaluation integrity workspace</span></div></div>
        <div className="flex items-center gap-3 text-sm"><span role="status" className="hidden sm:block">FalkorDB {ready ? "reachable" : loading ? "checking" : "unavailable"}</span><SoftPillButton size="sm" onClick={() => void refresh()} disabled={loading}><RefreshCw size={14}/> Refresh</SoftPillButton><Link href="/" className="flex items-center gap-1"><ArrowLeft size={14}/> Home</Link></div>
      </div>
    </header>
    <main className="mx-auto max-w-7xl px-6 py-10">
      <div className="flex flex-wrap items-end justify-between gap-6"><div><p className="text-xs font-mono uppercase tracking-widest text-neutral-500">FalkorDB · local workspace</p><h1 className="mt-3 font-serif text-4xl md:text-5xl">Follow the evidence.</h1><p className="mt-4 max-w-2xl text-neutral-600">Inspect recorded lineage, trace impact, approve a clean refit, and compare saved run versions.</p></div><div className="max-w-full overflow-x-auto"><SegmentedToggleButton options={tabs} value={tab} onChange={setTab}/></div></div>
      {(error || actionError || notice) && <div role={error || actionError ? "alert" : "status"} className="mt-7 bg-neutral-100 p-4 text-sm">{error || actionError || notice}</div>}
      <section className="mt-8 bg-neutral-50 p-5"><label className="block text-xs font-semibold uppercase tracking-widest text-neutral-500" htmlFor="api-token">Local API token for write actions</label><div className="mt-3 flex flex-wrap items-center gap-3"><input id="api-token" className={`${field} max-w-md font-mono`} type={showToken ? "text" : "password"} value={token} autoComplete="off" placeholder="Paste BENCHWITNESS_API_TOKEN" onChange={e => { setToken(e.target.value); sessionStorage.setItem("benchwitness-api-token", e.target.value); }}/><button type="button" onClick={() => setShowToken(!showToken)} className="text-sm underline">{showToken ? "Hide" : "Show"}</button></div><p className="mt-2 text-xs text-neutral-500">Read operations work without a token. The token stays in this browser tab session.</p></section>

      {tab === 0 && <section className="mt-12"><div className="grid gap-6 md:grid-cols-3"><Metric label="Recorded experiments" value={overview ? String(audits.length) : "—"}/><Metric label="Confirmed overlap" value={overview ? String(audits.filter(a => a.status === "confirmed").length) : "—"}/><Metric label="Measured run versions" value={overview ? String(runs.length) : "—"}/></div><div className="mt-12 grid gap-8 md:grid-cols-2"><div><h2 className="font-serif text-3xl">Start with recorded data.</h2><p className="mt-4 text-neutral-600">The ledger shows graph audits and saved model evaluations. A confirmed finding requires matching canonical source identities and sample-level provenance.</p><div className="mt-6 flex flex-wrap gap-3"><SoftPillButton variant="dark" onClick={() => setTab(1)}>Open ledger <ArrowRight size={15}/></SoftPillButton><SoftPillButton onClick={() => setTab(2)}>Trace source</SoftPillButton></div></div><div className="bg-neutral-50 p-6"><h3 className="font-semibold">Local data setup</h3><p className="mt-2 text-sm text-neutral-600">Only use these if the graph is empty or you intentionally want to rerun the deterministic demo evaluations.</p><div className="mt-5 flex flex-wrap gap-3"><SoftPillButton size="sm" disabled={!token || !!busy} onClick={() => void perform("seed", async () => { await api("/api/v1/demo/seed", token, "POST"); await refresh(); setNotice("Seed completed; graph overview refreshed."); })}>Seed graph</SoftPillButton><SoftPillButton size="sm" disabled={!token || !!busy} onClick={() => void perform("evaluate", async () => { await api("/api/v1/demo/evaluate", token, "POST"); await refresh(); setNotice("Evaluation finished; measured runs refreshed."); })}>Run baseline evaluations</SoftPillButton></div></div></div></section>}

      {tab === 1 && <section className="mt-12"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-serif text-3xl">Experiment ledger</h2><p className="mt-2 text-sm text-neutral-500">Scores are read from saved model runs; unknown lineage stays unknown.</p></div><SearchInput label="Search experiments" placeholder="Experiment or source record" value={search} onChange={setSearch} onClear={() => setSearch("")}/></div><div className="mt-6 max-w-full overflow-x-auto"><SegmentedToggleButton options={filters} value={filter} onChange={setFilter}/></div><div className="mt-6 divide-y divide-neutral-200">{filteredAudits.length === 0 && <p className="py-8 text-neutral-500">No matching audits. Seed and evaluate the graph if it is empty.</p>}{filteredAudits.map(a => { const run = runs.find(r => r.experiment_id === a.experiment_id); return <button type="button" key={a.experiment_id} className="grid w-full gap-3 py-6 text-left hover:bg-neutral-50 md:grid-cols-[2fr_1.3fr_1fr_auto] md:items-center" onClick={() => { setSelectedExperiment(a.experiment_id); setTab(2); }}><span><strong className="block">{a.experiment_id}</strong><small className="text-neutral-500">{a.training_dataset_id} → {a.evaluation_dataset_id}</small></span><span className="text-sm">{statusText[a.status]}</span><span className="font-mono text-sm">{run ? `${score(run.accuracy)} measured` : "No measured run"}</span><ArrowRight size={17}/></button>; })}</div></section>}

      {tab === 2 && <section className="mt-12"><h2 className="font-serif text-3xl">Lineage trace</h2><p className="mt-2 text-sm text-neutral-500">Sample identities and derivation hops come from the graph audit. Investigation traces affected run and claim IDs.</p><div className="mt-6 grid gap-4 md:grid-cols-2"><label className="text-sm font-semibold">Experiment<select className={`${field} mt-2`} value={selectedAudit?.experiment_id ?? ""} onChange={e => { setSelectedExperiment(e.target.value); setInvestigation(null); setSource(""); }}>{audits.map(a => <option key={a.experiment_id} value={a.experiment_id}>{a.experiment_id}</option>)}</select></label><label className="text-sm font-semibold">Canonical source record<select className={`${field} mt-2`} value={activeSource} onChange={e => { setSource(e.target.value); setInvestigation(null); }}><option value="">Select a recorded source</option>{availableSources.map(id => <option key={id} value={id}>{id}</option>)}</select></label></div>
        {selectedAudit && <div className="mt-8 bg-neutral-50 p-6"><p className="text-xs font-mono uppercase text-neutral-500">{statusText[selectedAudit.status]} · {selectedAudit.evidence.length} evidence path(s)</p><p className="mt-2 text-sm">Coverage {selectedAudit.coverage_complete ? "complete" : "incomplete"}. Training missing source: {selectedAudit.training_samples_without_source}; evaluation missing source: {selectedAudit.evaluation_samples_without_source}.</p>{selectedAudit.evidence.length ? <div className="mt-5 space-y-4">{selectedAudit.evidence.map((e, index) => <div key={`${e.training_sample_id}-${e.evaluation_sample_id}-${index}`} className="grid gap-3 bg-white p-4 text-xs font-mono md:grid-cols-3"><div><span className="block text-neutral-500">Canonical source</span><strong className="break-all">{e.canonical_source_record_id}</strong></div><div><span className="block text-neutral-500">Training path · {e.training_derivation_hops} hops</span><strong className="break-all">{e.training_dataset_id} / {e.training_sample_id}</strong></div><div><span className="block text-neutral-500">Evaluation path · {e.evaluation_derivation_hops} hops</span><strong className="break-all">{e.evaluation_dataset_id} / {e.evaluation_sample_id}</strong></div></div>)}</div> : <p className="mt-4 text-sm text-neutral-500">No confirmed overlap path is recorded for this experiment.</p>}</div>}
        <div className="mt-7 flex flex-wrap items-center gap-4"><SoftPillButton variant="dark" disabled={!activeSource || !token || !!busy} onClick={() => void perform("impact", async () => { const result = await api<Investigation>("/api/v1/impact", token, "POST", { source_record_id: activeSource }); setInvestigation(result); setRepair(null); setQuarantine(null); setJob(null); setRunDetails({}); setJobIdInput(""); setNotice(`Investigation ${result.investigation_id} saved in FalkorDB.`); })}>Investigate source <ArrowRight size={15}/></SoftPillButton><span className="text-xs text-neutral-500">Requires local API token</span></div>
        {investigation && <div className="mt-8 bg-neutral-50 p-6"><p className="font-mono text-xs text-neutral-500">{investigation.investigation_id}</p><h3 className="mt-2 font-serif text-2xl">{investigation.impacted_runs.length} affected run(s)</h3><p className="mt-2 text-sm">Finding: {statusText[investigation.finding_status]}. Coverage {investigation.coverage_complete ? "complete" : "incomplete"}.</p>{investigation.unresolved_run_ids.length > 0 && <p className="mt-2 text-sm">Unresolved runs: {investigation.unresolved_run_ids.join(", ")}</p>}<div className="mt-5 divide-y divide-neutral-200">{investigation.impacted_runs.map(run => <div key={run.run_id} className="py-4 text-sm"><strong className="block">{run.experiment_id}</strong><span className="mt-1 block font-mono text-xs text-neutral-600">Run {run.run_id} · Claim {run.evaluation_claim_id} · {run.integrity_status}</span><span className="mt-1 block text-xs text-neutral-500">{run.evidence.length} sample evidence path(s)</span></div>)}</div><SoftPillButton size="sm" onClick={() => setTab(3)}>Review recovery gate →</SoftPillButton></div>}
      </section>}

      {tab === 3 && <section className="mt-12"><h2 className="font-serif text-3xl">Recovery gate</h2><p className="mt-2 max-w-2xl text-sm text-neutral-500">A proposal records scope. A separate approval enqueues work. Original runs remain; the worker writes new measured versions.</p>{!investigation ? <p className="mt-8 bg-neutral-50 p-6 text-sm">Run an investigation in Lineage Trace first, or retrieve a saved job below.</p> : <div className="mt-8 grid gap-8 lg:grid-cols-2"><div className="bg-neutral-50 p-6"><h3 className="font-semibold">1. Propose action</h3><p className="mt-2 text-xs text-neutral-500">Investigation {investigation.investigation_id} · {investigation.impacted_runs.length} affected run(s)</p><label className="mt-5 block text-xs font-semibold uppercase" htmlFor="proposal-reason">Proposal reason</label><textarea id="proposal-reason" className={`${field} mt-2 min-h-24`} value={proposalReason} onChange={e => setProposalReason(e.target.value)} placeholder="Describe the evidence and intended action"/><div className="mt-4 flex flex-wrap gap-3"><SoftPillButton size="sm" disabled={!token || !proposalReason.trim() || !investigation.coverage_complete || !investigation.impacted_runs.length || !!busy} onClick={() => void perform("quarantine", async () => { const result = await api<ActionProposal>(`/api/v1/investigations/${idPath(investigation.investigation_id)}/quarantine-proposals`, token, "POST", { reason: proposalReason.trim() }); setQuarantine(result); setRepair(null); setJob(null); setNotice(`Quarantine proposal ${result.action_id} saved.`); })}>Propose quarantine</SoftPillButton><SoftPillButton variant="dark" size="sm" disabled={!token || !proposalReason.trim() || !investigation.coverage_complete || !investigation.impacted_runs.length || !!busy} onClick={() => void perform("repair", async () => { const result = await api<ActionProposal>(`/api/v1/investigations/${idPath(investigation.investigation_id)}/repair-proposals`, token, "POST", { reason: proposalReason.trim() }); setRepair(result); setQuarantine(null); setJob(null); setNotice(`Clean refit proposal ${result.action_id} saved.`); })}>Propose clean refit</SoftPillButton></div></div>{(repair || quarantine) && <div className="bg-neutral-50 p-6"><h3 className="font-semibold">2. Review and approve</h3><p className="mt-2 text-xs font-mono break-all">Action {(repair ?? quarantine)?.action_id}</p><p className="mt-3 text-sm">Target claim IDs:</p><ul className="mt-2 list-inside list-disc font-mono text-xs">{(repair ?? quarantine)?.target_claim_ids.map(id => <li className="break-all" key={id}>{id}</li>)}</ul><label className="mt-5 block text-xs font-semibold uppercase" htmlFor="approval-reason">Approval reason</label><textarea id="approval-reason" className={`${field} mt-2 min-h-24`} value={approvalReason} onChange={e => setApprovalReason(e.target.value)} placeholder="I reviewed the evidence and approve this action"/><SoftPillButton variant="dark" className="mt-4" disabled={!token || !approvalReason.trim() || !!busy || !!job || (quarantine?.status === "approved")} onClick={() => void perform("approve", async () => { if (repair) { const result = await api<RecoveryJob>(`/api/v1/repairs/${idPath(repair.action_id)}/approve`, token, "POST", { reason: approvalReason.trim() }); setJob(result); setJobIdInput(result.job_id); sessionStorage.setItem("benchwitness-job-id", result.job_id); setNotice(`Repair job ${result.job_id} ${result.status}.`); } else if (quarantine) { const result = await api<ActionProposal>(`/api/v1/actions/${idPath(quarantine.action_id)}/approve`, token, "POST", { reason: approvalReason.trim() }); setQuarantine(result); setInvestigation(await api<Investigation>(`/api/v1/investigations/${idPath(investigation.investigation_id)}`)); setNotice(`Quarantine ${result.status} in FalkorDB.`); } })}>Approve {repair ? "clean refit" : "quarantine"} <ArrowRight size={15}/></SoftPillButton></div>}</div>}
        <div className="mt-10"><h3 className="font-serif text-2xl">Measured recovery</h3><div className="mt-4 flex flex-wrap gap-3"><input aria-label="Job ID" className={`${field} max-w-md font-mono`} value={jobIdInput} onChange={e => { setJobIdInput(e.target.value); setJob(null); setRunDetails({}); }} placeholder="Saved job ID"/><SoftPillButton size="sm" disabled={!jobIdInput || !!busy} onClick={() => void perform("job", async () => { await fetchJob(jobIdInput); setNotice("Job state refreshed from FalkorDB."); })}>Load job</SoftPillButton></div>{job && <div className="mt-6 bg-neutral-50 p-6"><p className="text-xs font-mono break-all">{job.job_id}</p><p className="mt-2 text-lg font-semibold">Status: {job.status}</p>{job.error && <p role="alert" className="mt-2 text-sm">Worker error: {job.error}</p>}<p className="mt-2 text-xs text-neutral-500">Started {job.started_at ?? "pending"} · Finished {job.finished_at ?? "pending"}</p>{job.status === "succeeded" && <div className="mt-6 grid gap-4 md:grid-cols-2">{job.original_run_ids.map((originalId, index) => { const repairedId = job.repaired_run_ids[index]; const before = runDetails[originalId]; const after = repairedId ? runDetails[repairedId] : undefined; return <div className="bg-white p-5" key={originalId}><p className="text-xs font-mono break-all">{before?.experiment_id ?? originalId}</p><div className="mt-4 grid grid-cols-2 gap-4"><div><span className="text-xs text-neutral-500">Original run</span><p className="font-serif text-3xl">{score(before?.accuracy)}</p><p className="text-xs">F1 {score(before?.f1)}</p></div><div><span className="text-xs text-neutral-500">Clean refit</span><p className="font-serif text-3xl">{score(after?.accuracy)}</p><p className="text-xs">F1 {score(after?.f1)}</p></div></div><p className="mt-4 text-xs text-neutral-500">{before && after ? before.accuracy === after.accuracy ? "Measured accuracy is unchanged; lineage has been repaired." : `Measured accuracy change: ${((after.accuracy - before.accuracy) * 100).toFixed(1)} percentage points.` : "Loading saved run metrics…"}</p></div>; })}</div>}</div>}</div>
      </section>}

      {tab === 4 && <section className="mt-12"><h2 className="font-serif text-3xl">Agent memory</h2><p className="mt-2 max-w-2xl text-sm text-neutral-500">Start a fresh session and ask the typed investigation tool about a canonical source. A second session can retrieve verified graph memory.</p><div className="mt-8 flex flex-wrap gap-3"><SoftPillButton variant="dark" disabled={!token || !!busy} onClick={() => void perform("session", async () => { const result = await api<AgentSession>("/api/v1/agent/sessions", token, "POST"); setSession(result); setAgentMessage(null); setNotice(`Session ${result.session_id} created.`); })}>Start fresh session</SoftPillButton><SoftPillButton disabled={!token || !session || !activeSource || !!busy} onClick={() => void perform("agent", async () => { const result = await api<AgentMessage>(`/api/v1/agent/sessions/${idPath(session!.session_id)}/messages`, token, "POST", { intent: "investigate_source", subject_id: activeSource }); setAgentMessage(result); })}>Investigate selected source</SoftPillButton></div><p className="mt-4 text-xs text-neutral-500">Selected source: {activeSource || "none — select one in Lineage Trace"}</p>{session && <p className="mt-3 font-mono text-xs break-all">Session {session.session_id}</p>}{agentMessage && <div className="mt-6 bg-neutral-50 p-6"><p className="text-xs font-mono">Memory {agentMessage.memory_status}{agentMessage.memory_id ? ` · ${agentMessage.memory_id}` : ""}</p><p className="mt-3 whitespace-pre-line text-sm leading-6">{agentMessage.summary}</p><p className="mt-4 text-xs text-neutral-500">Tools: {agentMessage.tools_used.join(", ") || "none"}</p></div>}</section>}
    </main><footer className="mx-auto mt-16 flex max-w-7xl items-center justify-between px-6 py-8 text-xs text-neutral-500"><span>BenchWitness · graph-backed evidence</span><Link href="/" className="flex items-center gap-1">Home <ArrowRight size={12}/></Link></footer>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="bg-neutral-50 p-6"><span className="text-xs uppercase tracking-widest text-neutral-500">{label}</span><strong className="mt-3 block font-serif text-4xl">{value}</strong></div>;
}
