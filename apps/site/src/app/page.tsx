"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { ArrowRight, GitBranch, RefreshCw } from "lucide-react";
import { AnnotatedText, GraphPaperPattern, SearchInput, SegmentedToggleButton, SoftPillButton } from "@/components/opensourceui";
import { useOverview } from "@/lib/use-overview";
import type { Audit, IntegrityStatus } from "@/lib/api";

const labels: Record<IntegrityStatus, string> = {
  confirmed: "Confirmed overlap",
  clean_within_recorded_lineage: "Clean within recorded lineage",
  unknown: "Unknown lineage",
};
const filters: (IntegrityStatus | "all")[] = ["all", "confirmed", "clean_within_recorded_lineage", "unknown"];

export default function Home() {
  const { overview, ready, loading, error, refresh } = useOverview();
  const [filter, setFilter] = useState(0);
  const [search, setSearch] = useState("");
  const audits = (overview?.audits ?? []).filter((audit: Audit) =>
    (filter === 0 || audit.status === filters[filter]) &&
    (audit.experiment_id.toLowerCase().includes(search.toLowerCase()) || audit.evidence.some(e => e.canonical_source_record_id.toLowerCase().includes(search.toLowerCase())))
  );
  const runs = overview?.runs ?? [];
  return (
    <main className="min-h-screen bg-white text-neutral-950">
      <header className="sticky top-0 z-30 bg-white/95 backdrop-blur px-6 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-3 font-bold tracking-tight"><span className="grid size-9 place-items-center rounded-xl bg-black text-white"><GitBranch size={17}/></span> BenchWitness</Link>
          <nav className="flex items-center gap-5 text-sm"><a href="#platform" className="hidden sm:block hover:underline">Platform</a><a href="#audits" className="hidden sm:block hover:underline">Audits</a><Link href="/dashboard" className="rounded-full bg-black px-5 py-2.5 font-semibold text-white">Launch workspace →</Link></nav>
        </div>
      </header>
      <section className="relative isolate overflow-hidden px-6 py-20 md:py-28 text-center">
        <GraphPaperPattern className="absolute inset-0 -z-10 opacity-45" />
        <div className="mx-auto max-w-5xl">
          <p className="mb-8 inline-flex rounded-full bg-neutral-100 px-4 py-2 text-xs font-mono uppercase tracking-widest">Graph-native evaluation integrity</p>
          <h1 className="font-serif text-5xl leading-[1.13] tracking-tight md:text-6xl">You told everyone to trust your model.<br/>Now give them the <AnnotatedText variant="underline" color="text-neutral-800">graph evidence</AnnotatedText> to prove it.</h1>
          <p className="mx-auto mt-8 max-w-2xl text-lg leading-relaxed text-neutral-600">Trace exact source-record overlap from training samples to evaluation claims. Review the affected runs, approve a clean refit, and compare measured versions.</p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3"><Link href="/dashboard"><SoftPillButton variant="dark" size="lg">Open live workspace <ArrowRight size={16}/></SoftPillButton></Link><a href="#audits"><SoftPillButton variant="light" size="lg">Inspect recorded audits</SoftPillButton></a></div>
          <div className="mt-12 flex flex-wrap justify-center gap-5 font-mono text-xs text-neutral-500"><span>FalkorDB {ready ? "reachable" : loading ? "checking" : "unavailable"}</span><span>Local API :8000</span><span>Zero paid services</span></div>
        </div>
      </section>
      <section id="platform" className="mx-auto grid max-w-7xl gap-10 px-6 py-16 md:grid-cols-2 md:items-center">
        <div><p className="text-xs font-mono uppercase tracking-widest text-neutral-500">The evidence chain</p><h2 className="mt-4 font-serif text-4xl">Every claim has a source.</h2><p className="mt-5 max-w-lg leading-7 text-neutral-600">BenchWitness checks canonical source identities and sample-level derivation. Missing provenance stays unknown. Original evaluation versions stay in the graph when a clean rerun is approved.</p><Link className="mt-7 inline-block font-semibold underline underline-offset-4" href="/dashboard">Trace a source record →</Link></div>
        <div className="bg-neutral-50 p-6"><Image src="/provenance-hero.png" alt="Illustration of source-record lineage" width={900} height={540} className="h-auto w-full"/></div>
      </section>
      <section id="audits" className="mx-auto max-w-7xl px-6 py-16">
        <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-mono uppercase tracking-widest text-neutral-500">Live from FalkorDB</p><h2 className="mt-3 font-serif text-4xl">Evaluation ledger</h2></div><SoftPillButton onClick={() => void refresh()} disabled={loading} size="sm"><RefreshCw size={14}/> Refresh</SoftPillButton></div>
        {error && <p role="alert" className="mt-6 bg-neutral-100 p-4 text-sm">{error}. Start the local API and FalkorDB, then refresh.</p>}
        <div className="mt-8 flex flex-wrap items-center justify-between gap-4"><div className="max-w-full overflow-x-auto"><SegmentedToggleButton options={["All", "Confirmed", "Clean", "Unknown"]} value={filter} onChange={setFilter}/></div><SearchInput label="Search audits" placeholder="Experiment or source record" value={search} onChange={setSearch} onClear={() => setSearch("")}/></div>
        <div className="mt-5 divide-y divide-neutral-200">{loading && !overview ? <p className="py-10 text-neutral-500">Loading graph-backed audits…</p> : audits.length === 0 ? <p className="py-10 text-neutral-500">No recorded audits match this view.</p> : audits.map(audit => { const run = runs.find(r => r.experiment_id === audit.experiment_id); return <Link key={audit.experiment_id} href={`/dashboard?experiment=${encodeURIComponent(audit.experiment_id)}`} className="grid gap-3 py-6 transition-colors hover:bg-neutral-50 md:grid-cols-[2fr_1.2fr_1fr_auto] md:items-center"><div><p className="font-semibold">{audit.experiment_id}</p><p className="mt-1 text-xs text-neutral-500">{audit.training_dataset_id} → {audit.evaluation_dataset_id}</p></div><span className="text-sm">{labels[audit.status]}</span><span className="font-mono text-sm">{run ? `${(run.accuracy * 100).toFixed(1)}% measured` : "No measured run"}</span><ArrowRight size={17}/></Link>; })}</div>
      </section>
      <footer className="px-6 py-8 text-center text-xs text-neutral-500">BenchWitness · Local graph evidence and measured recovery</footer>
    </main>
  );
}
