import { StrictMode, Suspense, lazy, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider, useQueries, useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  CircleAlert,
  Play,
  RefreshCw,
  ScanSearch,
  Layers,
  GitBranch,
  Sparkles,
  KeyRound,
  CheckCircle2,
  AlertCircle,
  Activity,
  ArrowUpRight,
  Eye,
  EyeOff,
  RotateCcw,
  SlidersHorizontal,
  ChevronRight,
  Menu,
  X,
} from 'lucide-react'
import {
  api,
  idPath,
  type ActionProposal,
  type AgentMessage,
  type AgentSession,
  type Audit,
  type Investigation,
  type Overview,
  type RecoveryJob,
  type Run,
} from './api'
import { SoftPillButton } from './components/SoftPillButton'
import './style.css'

const EvidenceGraph = lazy(() =>
  import('./components/EvidenceGraph').then(({ EvidenceGraph }) => ({ default: EvidenceGraph })),
)

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 3_000 },
  },
})

const labels: Record<string, string> = {
  'demo-v2-contaminated-a': 'Contaminated A',
  'demo-v2-contaminated-b': 'Contaminated B',
  'demo-v2-clean-control': 'Clean control',
  'demo-v2-unknown-lineage': 'Unknown lineage',
}

function humanExperiment(id: string) {
  return labels[id] ?? id
}

function shortId(id: string) {
  return id.length > 27 ? `${id.slice(0, 14)}…${id.slice(-8)}` : id
}

function score(value: number | undefined) {
  return value === undefined ? '—' : `${(value * 100).toFixed(1)}%`
}

function accuracyDelta(before: Run | undefined, after: Run | undefined) {
  if (!before || !after) return 'Awaiting comparison'
  const delta = (after.accuracy - before.accuracy) * 100
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)} pp acc`
}

function f1Delta(before: Run | undefined, after: Run | undefined) {
  if (before?.f1 === undefined || after?.f1 === undefined) return 'F1 pending'
  const delta = (after.f1 - before.f1) * 100
  return `${delta > 0 ? '+' : ''}${delta.toFixed(1)} pp F1`
}

function runSize(run: Run | undefined) {
  return run
    ? `${run.training_sample_count} train / ${run.evaluation_sample_count} eval`
    : 'Loading run…'
}

function time(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString() : '—'
}

function statusLabel(value: string) {
  return value.replaceAll('_', ' ')
}

type TabId = 'overview' | 'experiments' | 'evidence' | 'recovery' | 'agent' | 'all'
type LedgerFilter = 'all' | 'confirmed' | 'clean' | 'unknown'
const tabIds: readonly TabId[] = ['overview', 'experiments', 'evidence', 'recovery', 'agent', 'all']

function getInitialTab(): TabId {
  const storedTab = sessionStorage.getItem('bw-active-tab')
  return tabIds.includes(storedTab as TabId) ? storedTab as TabId : 'overview'
}

function App() {
  const [activeTab, setActiveTab] = useState<TabId>(getInitialTab)
  const [ledgerFilter, setLedgerFilter] = useState<LedgerFilter>('all')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [tokenDrawerOpen, setTokenDrawerOpen] = useState(false)

  const [token, setToken] = useState(() => sessionStorage.getItem('bw-token') ?? '')
  const [showToken, setShowToken] = useState(false)
  const [sourceId, setSourceId] = useState('')
  const [investigationId, setInvestigationId] = useState(
    () => sessionStorage.getItem('bw-v2-investigation') ?? '',
  )
  const [jobId, setJobId] = useState(() => sessionStorage.getItem('bw-v2-job') ?? '')
  const [quarantine, setQuarantine] = useState<ActionProposal | null>(null)
  const [repair, setRepair] = useState<ActionProposal | null>(null)
  const [proposalReason, setProposalReason] = useState('')
  const [approvalReason, setApprovalReason] = useState('')
  const [agentSession, setAgentSession] = useState<AgentSession | null>(null)
  const [agentMessage, setAgentMessage] = useState<AgentMessage | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const ready = useQuery({
    queryKey: ['ready'],
    queryFn: () => api<{ status: string; graph: string }>('/readyz'),
    refetchInterval: 10_000,
  })

  const overview = useQuery({
    queryKey: ['overview'],
    queryFn: () => api<Overview>('/api/v1/overview'),
    refetchInterval: 10_000,
  })

  const investigation = useQuery({
    queryKey: ['investigation', investigationId],
    enabled: Boolean(investigationId),
    queryFn: () => api<Investigation>(`/api/v1/investigations/${idPath(investigationId)}`),
  })

  const job = useQuery({
    queryKey: ['job', jobId],
    enabled: Boolean(jobId),
    queryFn: () => api<RecoveryJob>(`/api/v1/jobs/${idPath(jobId)}`),
    refetchInterval: (query) =>
      ['pending_enqueue', 'queued', 'running'].includes(query.state.data?.status ?? '') ? 1_500 : false,
  })

  const recoveryRunIds = job.data
    ? [...new Set([...job.data.original_run_ids, ...job.data.repaired_run_ids])]
    : []

  const recoveryRunQueries = useQueries({
    queries: recoveryRunIds.map((runId) => ({
      queryKey: ['run', runId],
      queryFn: () => api<Run>(`/api/v1/runs/${idPath(runId)}`),
    })),
  })

  useEffect(() => {
    if (!sourceId && overview.data) {
      const confirmed = overview.data.audits.find(
        (item) => item.status === 'confirmed' && item.evidence.length,
      )
      if (confirmed) setSourceId(confirmed.evidence[0].canonical_source_record_id)
    }
  }, [overview.data, sourceId])

  useEffect(() => {
    if (job.data?.status === 'succeeded') void overview.refetch()
  }, [job.data?.status])

  function switchTab(tab: TabId) {
    setActiveTab(tab)
    sessionStorage.setItem('bw-active-tab', tab)
    setMobileMenuOpen(false)
  }

  function rememberToken(value: string) {
    setToken(value)
    sessionStorage.setItem('bw-token', value)
  }

  function rememberInvestigation(value: string) {
    setInvestigationId(value)
    sessionStorage.setItem('bw-v2-investigation', value)
  }

  function rememberJob(value: string) {
    setJobId(value)
    sessionStorage.setItem('bw-v2-job', value)
  }

  async function act(name: string, task: () => Promise<void>) {
    setBusy(name)
    setError('')
    setNotice('')
    try {
      await task()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Request failed')
    } finally {
      setBusy('')
    }
  }

  const audits = overview.data?.audits ?? []
  const runs = overview.data?.runs ?? []
  const report = investigation.data
  const currentJob = job.data
  const latest = (experimentId: string) => runs.find((item) => item.experiment_id === experimentId)

  const recoveryRunById = new Map(
    recoveryRunIds.map((id, index) => [id, recoveryRunQueries[index]?.data]),
  )
  const runById = (id: string) => recoveryRunById.get(id) ?? runs.find((item) => item.run_id === id)

  const recoveryComparisons =
    currentJob?.status === 'succeeded'
      ? currentJob.original_run_ids.map((originalId, index) => ({
          before: runById(originalId),
          after: runById(currentJob.repaired_run_ids[index] ?? ''),
        }))
      : []

  const recoveryMetricsReady =
    recoveryComparisons.length > 0 &&
    recoveryComparisons.every(({ before, after }) => Boolean(before && after))

  const recoveryAccuracyUnchanged =
    recoveryComparisons.length > 0 &&
    recoveryComparisons.every(
      ({ before, after }) => before && after && before.accuracy === after.accuracy,
    )

  const recoveryAccuracyFell =
    recoveryComparisons.length > 0 &&
    recoveryComparisons.every(
      ({ before, after }) => before && after && after.accuracy < before.accuracy,
    )

  const repairActionId =
    currentJob?.status === 'failed'
      ? currentJob.action_id
      : repair?.status === 'proposed'
        ? repair.action_id
        : ''

  const tokenMissing = !token.trim()
  const activeSource = sourceId.trim()
  const confirmedAuditCount = audits.filter((item) => item.status === 'confirmed').length
  const cleanAuditCount = audits.filter((item) => item.status === 'clean_within_recorded_lineage').length
  const unknownAuditCount = audits.filter((item) => item.status === 'unknown').length

  const candidateSources = [
    ...new Set(
      audits
        .filter((a) => a.status === 'confirmed')
        .flatMap((a) => a.evidence.map((e) => e.canonical_source_record_id)),
    ),
  ].slice(0, 4)

  const filteredAudits = audits.filter((audit) => {
    if (ledgerFilter === 'confirmed') return audit.status === 'confirmed'
    if (ledgerFilter === 'clean') return audit.status === 'clean_within_recorded_lineage'
    if (ledgerFilter === 'unknown') return audit.status === 'unknown'
    return true
  })

  function selectSource(id: string) {
    setSourceId(id)
    if (id.trim() !== (investigation.data?.source_record_id ?? '')) {
      rememberInvestigation('')
      setQuarantine(null)
      setRepair(null)
      setAgentMessage(null)
    }
  }

  function handleTraceSource(id: string) {
    selectSource(id)
    switchTab('evidence')
  }

  return (
    <div className="min-h-screen bg-[#FAF7F2] text-[#1B1133] antialiased flex flex-col md:flex-row">
      {/* SIDEBAR NAVIGATION (Desktop persistent, mobile collapsible drawer) */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 border-r border-[#E8E0F5] bg-[#FAF7F2] p-4 flex flex-col justify-between transition-transform duration-200 md:translate-x-0 md:static ${
          mobileMenuOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full'
        }`}
      >
        <div>
          {/* Brand Mark */}
          <div className="flex items-center justify-between pb-4 border-b border-[#E8E0F5]">
            <a href="#overview" onClick={() => switchTab('overview')} className="flex items-center gap-2.5 group">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#5B2BE8] text-white shadow-[0_2px_10px_rgba(91,43,232,0.3)] transition-transform duration-200 group-hover:scale-105">
                <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="6" cy="6" r="3" />
                  <circle cx="18" cy="7" r="3" />
                  <circle cx="12" cy="18" r="3" />
                  <path d="m8.6 7.4 6.8 2.2" />
                  <path d="m7.8 8.4 2.8 7.2" />
                  <path d="m16.2 9.4-2.8 6.2" />
                </svg>
              </div>
              <div>
                <span className="font-editorial text-lg font-bold tracking-tight text-[#1B1133]">
                  BenchWitness<span className="text-[#ED3C65]">.</span>
                </span>
                <span className="block text-[10px] font-bold uppercase tracking-wider text-[#9888B2]">
                  ML Audit Console
                </span>
              </div>
            </a>
            <button
              type="button"
              onClick={() => setMobileMenuOpen(false)}
              className="p-1 rounded-lg text-[#9888B2] hover:bg-[#F1ECFE] md:hidden"
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
          </div>

          {/* Main Navigation Views */}
          <nav className="mt-5 space-y-1" aria-label="Dashboard views">
            <NavItem
              label="Overview"
              icon={<Activity size={16} />}
              active={activeTab === 'overview'}
              onClick={() => switchTab('overview')}
            />
            <NavItem
              label="Experiment Ledger"
              icon={<Layers size={16} />}
              badge={audits.length ? String(audits.length) : undefined}
              active={activeTab === 'experiments'}
              onClick={() => switchTab('experiments')}
            />
            <NavItem
              label="Lineage Trace"
              icon={<ScanSearch size={16} />}
              badge={report ? `${report.impacted_runs.length} runs` : undefined}
              active={activeTab === 'evidence'}
              onClick={() => switchTab('evidence')}
            />
            <NavItem
              label="Recovery Gate"
              icon={<RotateCcw size={16} />}
              badge={currentJob?.status}
              active={activeTab === 'recovery'}
              onClick={() => switchTab('recovery')}
            />
            <NavItem
              label="Agent Memory"
              icon={<Sparkles size={16} />}
              active={activeTab === 'agent'}
              onClick={() => switchTab('agent')}
            />
            <div className="pt-2">
              <NavItem
                label="All Modules"
                icon={<SlidersHorizontal size={16} />}
                active={activeTab === 'all'}
                onClick={() => switchTab('all')}
              />
            </div>
          </nav>

          {/* Leakage Filter Spaces (Inspired by Tines Spaces) */}
          <div className="mt-6 pt-4 border-t border-[#E8E0F5]">
            <span className="px-3 text-[10px] font-bold uppercase tracking-wider text-[#9888B2]">
              Audit Spaces
            </span>
            <div className="mt-2 space-y-0.5 text-xs">
              <button
                type="button"
                onClick={() => {
                  setLedgerFilter('confirmed')
                  switchTab('experiments')
                }}
                className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-left transition ${
                  activeTab === 'experiments' && ledgerFilter === 'confirmed'
                    ? 'bg-[#FFF0F4] text-[#ED3C65] font-semibold'
                    : 'text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#1B1133]'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#ED3C65]" />
                  # Confirmed Overlap
                </span>
                <span className="text-[10px] font-mono text-[#9888B2]">{confirmedAuditCount}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setLedgerFilter('clean')
                  switchTab('experiments')
                }}
                className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-left transition ${
                  activeTab === 'experiments' && ledgerFilter === 'clean'
                    ? 'bg-[#ECFDF5] text-[#059669] font-semibold'
                    : 'text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#1B1133]'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#0D9488]" />
                  # Clean Control
                </span>
                <span className="text-[10px] font-mono text-[#9888B2]">{cleanAuditCount}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setLedgerFilter('unknown')
                  switchTab('experiments')
                }}
                className={`w-full flex items-center justify-between px-3 py-1.5 rounded-lg text-left transition ${
                  activeTab === 'experiments' && ledgerFilter === 'unknown'
                    ? 'bg-[#FFF7ED] text-[#EA580C] font-semibold'
                    : 'text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#1B1133]'
                }`}
              >
                <span className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full bg-[#EA580C]" />
                  # Unknown Lineage
                </span>
                <span className="text-[10px] font-mono text-[#9888B2]">{unknownAuditCount}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Sidebar Footer: Graph & Token Status */}
        <div className="pt-4 border-t border-[#E8E0F5] space-y-2">
          {/* Graph Connectivity Indicator */}
          <div
            className={`flex items-center justify-between px-3 py-2 rounded-xl border text-[11px] font-medium ${
              ready.isSuccess
                ? 'border-[#A7F3D0] bg-[#ECFDF5] text-[#065F46]'
                : 'border-[#FECDD8] bg-[#FFF0F4] text-[#9F1239]'
            }`}
          >
            <div className="flex items-center gap-2">
              <span className={`h-2 w-2 rounded-full ${ready.isSuccess ? 'bg-[#10B981] pulse-glow' : 'bg-[#ED3C65]'}`} />
              <span>{ready.isSuccess ? 'FalkorDB Connected' : 'Graph Offline'}</span>
            </div>
            <span className="font-mono text-[9px] uppercase">port 6379</span>
          </div>

          {/* Token Status Button */}
          <button
            type="button"
            onClick={() => setTokenDrawerOpen(!tokenDrawerOpen)}
            className={`w-full flex items-center justify-between px-3 py-2 rounded-xl border text-[11px] font-medium transition ${
              tokenMissing
                ? 'border-[#FED7AA] bg-[#FFF7ED] text-[#EA580C] hover:bg-[#FFEDD5]'
                : 'border-[#DDD0FA] bg-white text-[#5B2BE8] hover:bg-[#F6F2FE]'
            }`}
          >
            <div className="flex items-center gap-2">
              <KeyRound size={13} />
              <span>{tokenMissing ? 'Token Required' : 'Token Active'}</span>
            </div>
            <span className="text-[10px] font-bold uppercase">{tokenMissing ? 'Setup' : 'Edit'}</span>
          </button>
        </div>
      </aside>

      {/* BACKDROP FOR MOBILE MENU */}
      {mobileMenuOpen && (
        <div
          onClick={() => setMobileMenuOpen(false)}
          className="fixed inset-0 z-30 bg-black/20 backdrop-blur-xs md:hidden"
        />
      )}

      {/* MAIN DASHBOARD CONTENT AREA */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* TOP COMMAND DECK & ACTION BAR */}
        <header className="sticky top-0 z-20 border-b border-[#E8E0F5] bg-[#FAF7F2]/95 backdrop-blur-md px-4 py-2.5 sm:px-6 flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileMenuOpen(true)}
              className="p-1.5 rounded-lg text-[#6B5B87] hover:bg-[#F1ECFE] md:hidden"
              aria-label="Open sidebar"
            >
              <Menu size={20} />
            </button>

            {/* Breadcrumb / Title */}
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[#9888B2]">Console</span>
              <ChevronRight size={12} className="text-[#9888B2]" />
              <strong className="font-semibold text-[#1B1133] capitalize">
                {activeTab === 'all' ? 'Full Workspace' : activeTab === 'evidence' ? 'Lineage Trace' : activeTab}
              </strong>
            </div>
          </div>

          {/* Quick Actions & Seed/Eval Controls */}
          <div className="flex items-center gap-2">
            <SoftPillButton
              variant="primary"
              size="sm"
              disabled={Boolean(busy) || tokenMissing}
              onClick={() =>
                void act('seed', async () => {
                  await api('/api/v1/demo/seed', token, 'POST')
                  await overview.refetch()
                  setNotice('Synthetic lineage seeded in FalkorDB.')
                })
              }
            >
              <span>{busy === 'seed' ? 'Seeding…' : 'Seed Graph'}</span>
              <ArrowRight size={13} />
            </SoftPillButton>

            <SoftPillButton
              variant="light"
              size="sm"
              disabled={Boolean(busy) || tokenMissing || !audits.length}
              onClick={() =>
                void act('evaluate', async () => {
                  await api('/api/v1/demo/evaluate', token, 'POST')
                  await overview.refetch()
                  setNotice('Baseline evaluations measured.')
                })
              }
            >
              <Play size={13} />
              <span className="hidden sm:inline">{busy === 'evaluate' ? 'Evaluating…' : 'Run Baseline'}</span>
            </SoftPillButton>

            <button
              type="button"
              onClick={() => setTokenDrawerOpen(!tokenDrawerOpen)}
              className={`p-2 rounded-full border transition ${
                tokenMissing
                  ? 'border-[#FECDD8] bg-[#FFF0F4] text-[#ED3C65]'
                  : 'border-[#DDD0FA] bg-white text-[#5B2BE8] hover:bg-[#F1ECFE]'
              }`}
              title={tokenMissing ? 'Token missing - click to configure' : 'Token configured'}
            >
              <KeyRound size={15} />
            </button>
          </div>
        </header>

        {/* TOKEN CONFIGURATION DRAWER / TRAY */}
        {tokenDrawerOpen && (
          <div className="border-b border-[#DDD0FA] bg-[#FAF8FE] p-4 px-6 animate-in slide-in-from-top-2">
            <div className="max-w-3xl mx-auto flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-[#5B2BE8] flex items-center gap-1.5">
                  <KeyRound size={14} /> Local Bearer Authorization Token
                </h4>
                <p className="text-xs text-[#6B5B87] mt-0.5">
                  Stored strictly in this browser tab's sessionStorage. Copy <code className="text-[#1B1133] font-mono">BENCHWITNESS_API_TOKEN</code> from your local <code className="text-[#1B1133] font-mono">.env</code>.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <div className="relative">
                  <input
                    aria-label="Local API bearer token"
                    type={showToken ? 'text' : 'password'}
                    placeholder="Paste token from .env"
                    value={token}
                    onChange={(event) => rememberToken(event.target.value)}
                    className="w-64 rounded-full border border-[#DDD0FA] bg-white px-3.5 py-1.5 pr-8 text-xs font-mono text-[#1B1133] outline-none transition focus:border-[#5B2BE8] focus:ring-1 focus:ring-[#5B2BE8]"
                  />
                  <button
                    type="button"
                    onClick={() => setShowToken(!showToken)}
                    aria-label={showToken ? 'Hide local API token' : 'Show local API token'}
                    aria-pressed={showToken}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#9888B2] hover:text-[#5B2BE8]"
                  >
                    {showToken ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
                <SoftPillButton
                  variant="primary"
                  size="sm"
                  onClick={() => setTokenDrawerOpen(false)}
                >
                  Done
                </SoftPillButton>
              </div>
            </div>
          </div>
        )}

        {/* FEEDBACK TOASTS */}
        <div className="px-4 pt-4 sm:px-6">
          {error && (
            <div
              className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-[#FECDD8] bg-[#FFF0F4] p-3 text-xs font-medium text-[#9F1239] shadow-xs"
              role="alert"
            >
              <div className="flex items-center gap-2">
                <CircleAlert className="shrink-0 text-[#ED3C65]" size={16} />
                <span>{error}</span>
              </div>
              <button
                onClick={() => setError('')}
                className="rounded-full p-1 text-[#ED3C65] hover:bg-[#FFE2EA]"
              >
                ✕
              </button>
            </div>
          )}

          {notice && (
            <div
              className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-[#A7F3D0] bg-[#ECFDF5] p-3 text-xs font-medium text-[#065F46] shadow-xs"
              role="status"
            >
              <div className="flex items-center gap-2">
                <CheckCircle2 className="shrink-0 text-[#10B981]" size={16} />
                <span>{notice}</span>
              </div>
              <button
                onClick={() => setNotice('')}
                className="rounded-full p-1 text-[#059669] hover:bg-[#D1FAE5]"
              >
                ✕
              </button>
            </div>
          )}

          {overview.isError && (
            <div
              className="mb-4 flex items-center gap-2 rounded-xl border border-[#FECDD8] bg-[#FFF0F4] p-3 text-xs font-medium text-[#9F1239]"
              role="alert"
            >
              <CircleAlert className="shrink-0 text-[#ED3C65]" size={16} />
              <span>FalkorDB overview unreachable. Check Docker Compose and FastAPI backend on port 8000.</span>
            </div>
          )}
        </div>

        {/* WORKSPACE MAIN BODY */}
        <main className="flex-1 px-4 py-4 sm:px-6 space-y-6">
          {/* TAB 1: OVERVIEW & TELEMETRY */}
          {(activeTab === 'overview' || activeTab === 'all') && (
            <section id="overview" className="space-y-6">
              {/* Executive Telemetry Metric Strip */}
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <MetricCard
                  label="Confirmed Overlaps"
                  value={overview.data ? String(confirmedAuditCount) : '—'}
                  detail="Exact source record leakage"
                  status={confirmedAuditCount > 0 ? 'coral' : 'neutral'}
                  icon={<AlertCircle size={16} className="text-[#ED3C65]" />}
                />
                <MetricCard
                  label="Audited Experiments"
                  value={audits.length ? String(audits.length) : '—'}
                  detail="Configurations in FalkorDB"
                  status="violet"
                  icon={<GitBranch size={16} className="text-[#5B2BE8]" />}
                />
                <MetricCard
                  label="Measured Runs"
                  value={runs.length ? String(runs.length) : '—'}
                  detail="Persisted evaluation versions"
                  status="mint"
                  icon={<Layers size={16} className="text-[#0D9488]" />}
                />
                <MetricCard
                  label="Blast Radius Claims"
                  value={report ? String(report.impacted_runs.length) : '—'}
                  detail={report ? 'In active source trace' : 'Requires investigation'}
                  status="orange"
                  icon={<Activity size={16} className="text-[#EA580C]" />}
                />
              </div>

              {/* Two Column Layout: Model Audit Ledger & Provenance Topology Canvas */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left (7 cols): Quick Model Audit Summary Table */}
                <div className="lg:col-span-7 rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-3 border-b border-[#E8E0F5]">
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                          Operational Matrix
                        </span>
                        <h3 className="text-base font-bold text-[#1B1133]">Lineage Audit Status</h3>
                      </div>
                      <SoftPillButton
                        variant="secondary"
                        size="xs"
                        onClick={() => switchTab('experiments')}
                      >
                        View Full Ledger <ArrowRight size={11} />
                      </SoftPillButton>
                    </div>

                    <div className="mt-4 divide-y divide-[#F1ECFE]">
                      {audits.map((audit) => {
                        const run = latest(audit.experiment_id)
                        return (
                          <div key={audit.experiment_id} className="py-3 flex items-center justify-between gap-3 text-xs">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <strong className="font-bold text-[#1B1133]">{humanExperiment(audit.experiment_id)}</strong>
                                <StatusBadge value={audit.status} />
                              </div>
                              <div className="mt-1 font-mono text-[10px] text-[#9888B2]">
                                {run ? `${run.training_sample_count} train / ${run.evaluation_sample_count} eval` : 'Unmeasured'}
                              </div>
                            </div>

                            <div className="flex items-center gap-4 shrink-0">
                              <div className="text-right">
                                <span className="block font-editorial text-lg font-bold text-[#1B1133] tabular-nums">
                                  {score(run?.accuracy)}
                                </span>
                                <span className="text-[9px] font-semibold text-[#9888B2] uppercase">Accuracy</span>
                              </div>

                              {audit.evidence.length > 0 && (
                                <button
                                  type="button"
                                  onClick={() => handleTraceSource(audit.evidence[0].canonical_source_record_id)}
                                  className="p-1.5 rounded-lg text-[#5B2BE8] hover:bg-[#F1ECFE] transition"
                                  title="Open this source in Lineage Trace"
                                  aria-label="Open this source in Lineage Trace"
                                >
                                  <ScanSearch size={16} />
                                </button>
                              )}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-[#E8E0F5] flex items-center justify-between text-xs text-[#9888B2]">
                    <span>FalkorDB Authoritative Lineage</span>
                    <span>Deterministic 1-NN Model</span>
                  </div>
                </div>

                {/* Right (5 cols): Provenance Topology Card & Benchmark Spec */}
                <div className="lg:col-span-5 rounded-2xl border border-[#DDD0FA] bg-gradient-to-b from-[#F7F3FF] to-[#FAF7F2] p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                        Architecture Topology
                      </span>
                      <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-[#5B2BE8] border border-[#DDD0FA]">
                        400 Records
                      </span>
                    </div>

                    {/* Integrated Artwork */}
                    <div className="my-3 overflow-hidden rounded-xl border border-[#DDD0FA] bg-white p-2">
                      <img
                        src="/provenance-hero.png"
                        alt="Provenance graph topology"
                        className="h-32 w-full object-contain mx-auto"
                      />
                    </div>

                    <h4 className="text-xs font-bold text-[#1B1133] uppercase tracking-wide">
                      Synthetic 1-NN Evaluation Probe
                    </h4>
                    <p className="mt-1 text-xs text-[#6B5B87] leading-relaxed">
                      300 training and 100 held-out evaluation samples. 20 exact source records are copied into contaminated training splits. The 1-NN classifier isolates memorization leakage without model capacity confounding.
                    </p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-[#DDD0FA] flex items-center justify-between text-[11px] text-[#9888B2]">
                    <span>Held-Out Test Set</span>
                    <span className="text-[#059669] font-medium">Zero Synthetic Spend</span>
                  </div>
                </div>
              </div>

              {/* Detected Leaky Source Records Hotlist */}
              {candidateSources.length > 0 && (
                <div className="rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#ED3C65]">
                        Confirmed Contamination Candidates
                      </span>
                      <h4 className="text-sm font-bold text-[#1B1133]">Leaky Source Records</h4>
                    </div>
                    <span className="text-xs text-[#9888B2]">Select a source to open the lineage trace</span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {candidateSources.map((id) => {
                      const experimentNames = audits
                        .filter(
                          (audit) =>
                            audit.status === 'confirmed' &&
                            audit.evidence.some((item) => item.canonical_source_record_id === id),
                        )
                        .map((audit) => humanExperiment(audit.experiment_id))

                      return (
                        <button
                          key={id}
                          type="button"
                          onClick={() => handleTraceSource(id)}
                          className="group flex flex-col justify-between p-3 rounded-xl border border-[#E8E0F5] bg-[#FAF8FE] hover:border-[#5B2BE8] hover:bg-[#F5F0FF] text-left transition"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-bold uppercase text-[#5B2BE8]">Source Record</span>
                            <ArrowUpRight size={13} className="text-[#9888B2] group-hover:text-[#5B2BE8] transition" />
                          </div>
                          <div className="mt-2 font-mono text-xs font-semibold text-[#1B1133] truncate">
                            {shortId(id)}
                          </div>
                          <span className="mt-2 text-[10px] text-[#059669] font-medium">
                            Found in {experimentNames.join(' · ')}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </section>
          )}

          {/* TAB 2: EXPERIMENT LEDGER */}
          {(activeTab === 'experiments' || activeTab === 'all') && (
            <section id="experiments" className="space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-[#E8E0F5]">
                <div>
                  <h3 className="font-editorial text-2xl font-bold text-[#1B1133]">
                    Experiment Ledger
                  </h3>
                  <p className="text-xs text-[#6B5B87]">
                    Lineage audits and measured evaluation metrics stored in FalkorDB.
                  </p>
                </div>

                {/* Filter Pills */}
                <div className="flex items-center gap-1.5">
                  <button
                    type="button"
                    onClick={() => setLedgerFilter('all')}
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                      ledgerFilter === 'all'
                        ? 'bg-[#5B2BE8] text-white shadow-xs'
                        : 'bg-white text-[#6B5B87] hover:bg-[#F1ECFE] border border-[#E8E0F5]'
                    }`}
                  >
                    All ({audits.length})
                  </button>
                  <button
                    type="button"
                    onClick={() => setLedgerFilter('confirmed')}
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                      ledgerFilter === 'confirmed'
                        ? 'bg-[#ED3C65] text-white shadow-xs'
                        : 'bg-white text-[#6B5B87] hover:bg-[#FFF0F4] border border-[#E8E0F5]'
                    }`}
                  >
                    Confirmed ({confirmedAuditCount})
                  </button>
                  <button
                    type="button"
                    onClick={() => setLedgerFilter('clean')}
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                      ledgerFilter === 'clean'
                        ? 'bg-[#0D9488] text-white shadow-xs'
                        : 'bg-white text-[#6B5B87] hover:bg-[#ECFDF5] border border-[#E8E0F5]'
                    }`}
                  >
                    Clean ({cleanAuditCount})
                  </button>
                  <button
                    type="button"
                    onClick={() => setLedgerFilter('unknown')}
                    className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
                      ledgerFilter === 'unknown'
                        ? 'bg-[#EA580C] text-white shadow-xs'
                        : 'bg-white text-[#6B5B87] hover:bg-[#FFF7ED] border border-[#E8E0F5]'
                    }`}
                  >
                    Unknown ({unknownAuditCount})
                  </button>

                  <button
                    type="button"
                    onClick={() => void overview.refetch()}
                    className="p-1.5 rounded-full text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#5B2BE8] border border-[#E8E0F5] bg-white transition ml-1"
                    title="Refresh from graph"
                  >
                    <RefreshCw size={13} className={overview.isFetching ? 'animate-spin' : ''} />
                  </button>
                </div>
              </div>

              {/* Grid of Experiment Cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-5">
                {filteredAudits.map((audit) => (
                  <ExperimentCard
                    key={audit.experiment_id}
                    audit={audit}
                    run={latest(audit.experiment_id)}
                    onTrace={() => {
                      if (audit.evidence[0]) {
                        handleTraceSource(audit.evidence[0].canonical_source_record_id)
                      }
                    }}
                  />
                ))}
              </div>
            </section>
          )}

          {/* TAB 3: LINEAGE INVESTIGATION & CYTOSCAPE WORKBENCH */}
          {(activeTab === 'evidence' || activeTab === 'all') && (
            <section id="evidence" className="space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-[#E8E0F5]">
                <div>
                  <h3 className="font-editorial text-2xl font-bold text-[#1B1133]">
                    Lineage Investigation & Evidence Trace
                  </h3>
                  <p className="text-xs text-[#6B5B87]">
                    Bounded traversal of FalkorDB graph identifying exact training and evaluation overlaps.
                  </p>
                </div>
              </div>

              {/* Search & Candidate Bar */}
              <div className="rounded-2xl border border-[#DDD0FA] bg-white p-4 shadow-xs space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                  <div className="relative flex-1">
                    <div className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-[#5B2BE8]">
                      <ScanSearch size={18} />
                    </div>
                    <input
                      id="source-id"
                      aria-label="Canonical source record ID"
                      value={sourceId}
                      onChange={(event) => selectSource(event.target.value)}
                      placeholder="source:synthetic-memorization-v2:0052"
                      className="w-full rounded-full border border-[#DDD0FA] bg-[#FAF8FE] py-2 pl-11 pr-4 text-xs font-mono text-[#1B1133] outline-none transition focus:border-[#5B2BE8] focus:ring-1 focus:ring-[#5B2BE8]"
                    />
                  </div>

                  <SoftPillButton
                    variant="primary"
                    size="md"
                    disabled={Boolean(busy) || tokenMissing || !activeSource || !runs.length}
                    onClick={() =>
                      void act('investigate', async () => {
                        const result = await api<Investigation>('/api/v1/impact', token, 'POST', {
                          source_record_id: activeSource,
                        })
                        rememberInvestigation(result.investigation_id)
                        setQuarantine(null)
                        setRepair(null)
                        setNotice(`Investigation recorded for ${shortId(result.investigation_id)}.`)
                      })
                    }
                  >
                    <ScanSearch size={14} />
                    <span>{busy === 'investigate' ? 'Tracing…' : 'Investigate Source'}</span>
                  </SoftPillButton>
                </div>

                {/* Candidate Sources Chips */}
                {candidateSources.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-[#F1ECFE] text-xs">
                    <span className="text-[10px] font-bold uppercase text-[#9888B2]">Quick Source Presets:</span>
                    {candidateSources.map((id) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => selectSource(id)}
                        className={`rounded-full px-2.5 py-0.5 font-mono text-[11px] font-medium transition ${
                          sourceId === id
                            ? 'bg-[#5B2BE8] text-white'
                            : 'bg-[#F1ECFE] text-[#5B2BE8] hover:bg-[#E5DAFB] border border-[#DDD0FA]'
                        }`}
                      >
                        {shortId(id)}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Main Evidence Workbench */}
              {report ? (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left (7 cols): Cytoscape Graph Trace Canvas */}
                  <div className="lg:col-span-7 rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs space-y-4">
                    <div className="flex items-center justify-between pb-3 border-b border-[#E8E0F5]">
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                          Graph Trace Canvas
                        </span>
                        <h4 className="text-base font-bold text-[#1B1133]">Provenance Topology</h4>
                      </div>
                      <StatusBadge value={report.finding_status} />
                    </div>

                    <Suspense fallback={<div className="h-[340px] rounded-2xl bg-[#FAF8FE] flex items-center justify-center text-xs text-[#9888B2]">Loading Cytoscape layout…</div>}>
                      <EvidenceGraph key={report.investigation_id} investigation={report} />
                    </Suspense>
                  </div>

                  {/* Right (5 cols): Blast Radius & Impacted Claims Table */}
                  <div className="lg:col-span-5 rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs flex flex-col justify-between">
                    <div>
                      <div className="flex items-center justify-between pb-3 border-b border-[#E8E0F5]">
                        <div>
                          <span className="text-[10px] font-bold uppercase tracking-wider text-[#ED3C65]">
                            Blast Radius Propagation
                          </span>
                          <h4 className="text-base font-bold text-[#1B1133]">Dependent Claims</h4>
                        </div>
                        <span className="font-editorial text-3xl font-normal text-[#5B2BE8] tabular-nums">
                          {report.impacted_runs.length}
                        </span>
                      </div>

                      <div className="mt-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                            report.coverage_complete
                              ? 'bg-[#ECFDF5] text-[#059669] border border-[#A7F3D0]'
                              : 'bg-[#FFF7ED] text-[#EA580C] border border-[#FED7AA]'
                          }`}
                        >
                          {report.coverage_complete
                            ? 'Complete within recorded lineage'
                            : `Incomplete: ${report.unresolved_run_ids.length} unresolved runs`}
                        </span>
                      </div>

                      <div className="mt-4 space-y-3 max-h-[380px] overflow-y-auto pr-1">
                        {report.impacted_runs.map((item) => (
                          <div
                            key={item.run_id}
                            className="rounded-xl border border-[#F1ECFE] bg-[#FAF8FE] p-3 text-xs"
                          >
                            <div className="flex items-center justify-between">
                              <strong className="text-[#1B1133]">{humanExperiment(item.experiment_id)}</strong>
                              <StatusBadge value={item.integrity_status} />
                            </div>
                            <div className="mt-1 font-mono text-[10px] text-[#9888B2] truncate" title={item.run_id}>
                              {item.run_id}
                            </div>
                            <div className="mt-2 grid grid-cols-2 gap-2 border-t border-[#E8E0F5] pt-2">
                              {item.metrics.map((metric) => (
                                <div key={metric.claim_id} className="flex justify-between text-[11px]">
                                  <span className="text-[#6B5B87] uppercase">{metric.name}</span>
                                  <strong className="text-[#1B1133] tabular-nums">{score(metric.value)}</strong>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-[#E8E0F5] text-[11px] text-[#9888B2] flex justify-between">
                      <span>Investigation: <code className="text-[#5B2BE8]">{shortId(report.investigation_id)}</code></span>
                      <span>Recorded {time(report.created_at)}</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-[#DDD0FA] bg-white p-12 text-center text-[#6B5B87]">
                  <ScanSearch className="mx-auto mb-2 text-[#9888B2]" size={32} />
                  <p className="font-semibold text-[#1B1133]">No investigation loaded</p>
                  <p className="text-xs text-[#9888B2] mt-1">Select a source above and click "Investigate Source" to trace lineage.</p>
                </div>
              )}
            </section>
          )}

          {/* TAB 4: RECOVERY & GOVERNANCE GATE */}
          {(activeTab === 'recovery' || activeTab === 'all') && (
            <section id="recovery" className="space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-[#E8E0F5]">
                <div>
                  <h3 className="font-editorial text-2xl font-bold text-[#1B1133]">
                    Recovery & Governance Gate
                  </h3>
                  <p className="text-xs text-[#6B5B87]">
                    Deterministic quarantine and retraining with explicit human approval.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Left: Approval Gate */}
                <div className="rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs space-y-4">
                  <div className="pb-3 border-b border-[#E8E0F5]">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                      Human Authorization Gate
                    </span>
                    <h4 className="text-base font-bold text-[#1B1133]">Review & Execute</h4>
                  </div>

                  {/* Step 1 */}
                  <div className="space-y-2">
                    <label htmlFor="proposal-reason" className="block text-xs font-semibold text-[#5B2BE8] uppercase tracking-wider">
                      Step 1: Proposal Reason
                    </label>
                    <input
                      id="proposal-reason"
                      value={proposalReason}
                      onChange={(event) => setProposalReason(event.target.value)}
                      placeholder="Why these claims need review (e.g. Confirmed 20-row test leakage)"
                      className="w-full rounded-xl border border-[#DDD0FA] bg-[#FAF8FE] px-3.5 py-2 text-xs text-[#1B1133] outline-none transition focus:border-[#5B2BE8] focus:ring-1 focus:ring-[#5B2BE8]"
                    />
                    <div className="flex flex-wrap gap-2 pt-1">
                      <SoftPillButton
                        variant="coral"
                        size="sm"
                        disabled={
                          !report ||
                          !report.coverage_complete ||
                          !report.impacted_runs.length ||
                          tokenMissing ||
                          !proposalReason.trim() ||
                          Boolean(busy)
                        }
                        onClick={() =>
                          void act('quarantine-proposal', async () => {
                            setRepair(null)
                            setQuarantine(
                              await api<ActionProposal>(
                                `/api/v1/investigations/${idPath(report!.investigation_id)}/quarantine-proposals`,
                                token,
                                'POST',
                                { reason: proposalReason.trim() },
                              ),
                            )
                            setNotice('Quarantine proposal created.')
                          })
                        }
                      >
                        Propose Quarantine
                      </SoftPillButton>

                      <SoftPillButton
                        variant="secondary"
                        size="sm"
                        disabled={
                          !report ||
                          !report.coverage_complete ||
                          !report.impacted_runs.length ||
                          tokenMissing ||
                          !proposalReason.trim() ||
                          Boolean(busy)
                        }
                        onClick={() =>
                          void act('repair-proposal', async () => {
                            setQuarantine(null)
                            setRepair(
                              await api<ActionProposal>(
                                `/api/v1/investigations/${idPath(report!.investigation_id)}/repair-proposals`,
                                token,
                                'POST',
                                { reason: proposalReason.trim() },
                              ),
                            )
                            setNotice('Clean repair proposal created.')
                          })
                        }
                      >
                        Propose Clean Repair
                      </SoftPillButton>
                    </div>
                  </div>

                  {/* Scope Box */}
                  {(quarantine || repair) && (
                    <div className="rounded-xl border border-[#DDD0FA] bg-[#FAF8FE] p-3 text-xs">
                      <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                        Scope: {quarantine ? 'Quarantine' : 'Clean Repair'} ({quarantine?.status ?? repair?.status})
                      </span>
                      <p className="mt-1 font-semibold text-[#1B1133]">
                        Target Claims: {(quarantine ?? repair)?.target_claim_ids.length}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {(repair ?? quarantine)?.target_claim_ids.map((id) => (
                          <span key={id} className="rounded-md bg-white px-2 py-0.5 font-mono text-[10px] text-[#5B2BE8] border border-[#E8E0F5]">
                            {shortId(id)}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Step 2 */}
                  <div className="pt-3 border-t border-[#E8E0F5] space-y-2">
                    <label htmlFor="approval-reason" className="block text-xs font-semibold text-[#5B2BE8] uppercase tracking-wider">
                      Step 2: Approval Reason
                    </label>
                    <input
                      id="approval-reason"
                      value={approvalReason}
                      onChange={(event) => setApprovalReason(event.target.value)}
                      placeholder="I reviewed the evidence and approve retraining…"
                      className="w-full rounded-xl border border-[#DDD0FA] bg-[#FAF8FE] px-3.5 py-2 text-xs text-[#1B1133] outline-none transition focus:border-[#5B2BE8] focus:ring-1 focus:ring-[#5B2BE8]"
                    />
                    <div className="flex flex-wrap gap-2 pt-1">
                      <SoftPillButton
                        variant="mint"
                        size="sm"
                        disabled={
                          !quarantine ||
                          quarantine.status === 'approved' ||
                          !approvalReason.trim() ||
                          tokenMissing ||
                          Boolean(busy)
                        }
                        onClick={() =>
                          void act('quarantine-approval', async () => {
                            const result = await api<ActionProposal>(
                              `/api/v1/actions/${idPath(quarantine!.action_id)}/approve`,
                              token,
                              'POST',
                              { reason: approvalReason.trim() },
                            )
                            setQuarantine(result)
                            await investigation.refetch()
                            setNotice('Quarantine approval recorded in FalkorDB.')
                          })
                        }
                      >
                        Approve Quarantine
                      </SoftPillButton>

                      <SoftPillButton
                        variant="primary"
                        size="md"
                        disabled={!repairActionId || !approvalReason.trim() || tokenMissing || Boolean(busy)}
                        onClick={() =>
                          void act('repair-approval', async () => {
                            try {
                              const result = await api<RecoveryJob>(
                                `/api/v1/repairs/${idPath(repairActionId)}/approve`,
                                token,
                                'POST',
                                { reason: approvalReason.trim() },
                              )
                              rememberJob(result.job_id)
                              queryClient.setQueryData(['job', result.job_id], result)
                              if (repair) setRepair({ ...repair, status: 'approved' })
                              setNotice(
                                currentJob?.status === 'failed'
                                  ? 'Approved repair retry queued on Redis.'
                                  : 'Approved repair queued on Redis.',
                              )
                            } catch (caught) {
                              try {
                                const failed = await api<RecoveryJob>(
                                  `/api/v1/jobs/${idPath(`job:repair:${repairActionId}`)}`,
                                )
                                rememberJob(failed.job_id)
                                queryClient.setQueryData(['job', failed.job_id], failed)
                              } catch {
                                /* fallback */
                              }
                              throw caught
                            }
                          })
                        }
                      >
                        <span>
                          {currentJob?.status === 'failed' ? 'Retry Approved Repair' : 'Approve & Run Repair'}
                        </span>
                        <ArrowRight size={14} />
                      </SoftPillButton>
                    </div>
                  </div>
                </div>

                {/* Right: Measured Outcome */}
                <div className="rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-3 border-b border-[#E8E0F5]">
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                          Versioned Outcome
                        </span>
                        <h4 className="text-base font-bold text-[#1B1133]">Measured Recovery</h4>
                      </div>
                      <StatusBadge value={currentJob?.status ?? 'awaiting approval'} />
                    </div>

                    {currentJob ? (
                      <div className="mt-4 space-y-4">
                        {/* Timeline */}
                        <div className="grid grid-cols-3 gap-2 rounded-xl border border-[#F1ECFE] bg-[#FAF8FE] p-3 text-xs">
                          <div>
                            <span className="text-[10px] font-bold uppercase text-[#9888B2]">Job ID</span>
                            <div className="font-mono text-[11px] text-[#1B1133] truncate" title={currentJob.job_id}>
                              {shortId(currentJob.job_id)}
                            </div>
                          </div>
                          <div>
                            <span className="text-[10px] font-bold uppercase text-[#9888B2]">Started</span>
                            <div className="text-[11px] text-[#1B1133]">{time(currentJob.started_at)}</div>
                          </div>
                          <div>
                            <span className="text-[10px] font-bold uppercase text-[#9888B2]">Finished</span>
                            <div className="text-[11px] text-[#1B1133]">{time(currentJob.finished_at)}</div>
                          </div>
                        </div>

                        {currentJob.status === 'succeeded' && (
                          <div className="space-y-3">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                              Measured Comparison Ledger
                            </span>
                            {currentJob.original_run_ids.map((originalId, index) => {
                              const before = runById(originalId)
                              const after = runById(currentJob.repaired_run_ids[index] ?? '')

                              return (
                                <div key={originalId} className="rounded-xl border border-[#DDD0FA] bg-[#FAF8FE] p-3 text-xs">
                                  <div className="grid grid-cols-1 sm:grid-cols-3 items-center gap-3">
                                    <div className="rounded-lg border border-[#FECDD8] bg-[#FFF0F4] p-2.5 text-center sm:text-left">
                                      <span className="text-[9px] font-bold uppercase text-[#9F1239]">Before (Contaminated)</span>
                                      <div className="font-editorial text-xl font-bold text-[#9F1239] tabular-nums mt-0.5">
                                        {score(before?.accuracy)}
                                      </div>
                                      <div className="text-[10px] text-[#6B5B87]">F1 {score(before?.f1)}</div>
                                      <div className="text-[9px] text-[#9888B2]">{runSize(before)}</div>
                                    </div>

                                    <div className="flex flex-col items-center justify-center gap-1 text-center">
                                      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-[#5B2BE8] text-white">
                                        <ArrowRight size={12} />
                                      </div>
                                      <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-bold text-[#5B2BE8] border border-[#DDD0FA]">
                                        {accuracyDelta(before, after)}
                                      </span>
                                      <span className="text-[9px] text-[#9888B2]">
                                        {f1Delta(before, after)}
                                      </span>
                                    </div>

                                    <div className="rounded-lg border border-[#A7F3D0] bg-[#ECFDF5] p-2.5 text-center sm:text-left">
                                      <span className="text-[9px] font-bold uppercase text-[#065F46]">After (Clean Refit)</span>
                                      <div className="font-editorial text-xl font-bold text-[#065F46] tabular-nums mt-0.5">
                                        {score(after?.accuracy)}
                                      </div>
                                      <div className="text-[10px] text-[#6B5B87]">F1 {score(after?.f1)}</div>
                                      <div className="text-[9px] text-[#9888B2]">{runSize(after)}</div>
                                    </div>
                                  </div>
                                </div>
                              )
                            })}

                            <p className="mt-3 rounded-lg bg-[#FAF8FE] p-2.5 text-[11px] leading-relaxed text-[#6B5B87] border border-[#E8E0F5]">
                              {recoveryMetricsReady ? (
                                <>
                                  Both runs evaluate on the exact same held-out evaluation set. Original runs are preserved in FalkorDB.{' '}
                                  {recoveryAccuracyUnchanged
                                    ? 'Lineage confirms the overlap, while this model’s measured accuracy stayed unchanged after cleanup.'
                                    : recoveryAccuracyFell
                                      ? 'The contaminated runs scored higher because exact held-out rows were copied into training. The clean rerun purges those rows to restore evaluation integrity.'
                                      : 'The displayed metric delta is calculated directly from saved before and after model predictions.'}
                                </>
                              ) : (
                                'Loading saved before and after metrics from FalkorDB…'
                              )}
                            </p>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mt-8 rounded-xl border border-dashed border-[#DDD0FA] p-8 text-center text-xs text-[#9888B2]">
                        <RotateCcw className="mx-auto mb-2 text-[#9888B2]" size={28} />
                        <p className="font-semibold text-[#1B1133]">No recovery job active</p>
                        <p className="mt-1">Propose and approve a clean repair to trigger the ML worker.</p>
                      </div>
                    )}
                  </div>

                  <div className="mt-4 pt-3 border-t border-[#E8E0F5] text-xs text-[#6B5B87]">
                    Original evaluation versions are strictly preserved in FalkorDB; clean retraining appends new versions.
                  </div>
                </div>
              </div>
            </section>
          )}

          {/* TAB 5: AGENT MEMORY */}
          {(activeTab === 'agent' || activeTab === 'all') && (
            <section id="agent" className="space-y-5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-[#E8E0F5]">
                <div>
                  <h3 className="font-editorial text-2xl font-bold text-[#1B1133]">
                    Agent Memory Console
                  </h3>
                  <p className="text-xs text-[#6B5B87]">
                    FalkorDB-backed persistent agent memory across independent sessions.
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left (5 cols): Description & Session Starter */}
                <div className="lg:col-span-5 rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                      Graph-Backed Agent Memory
                    </span>
                    <h4 className="mt-1 text-base font-bold text-[#1B1133]">Cross-Session Verification</h4>
                    <p className="mt-3 text-xs leading-relaxed text-[#6B5B87]">
                      The agent persists confirmed investigations into FalkorDB. Fresh sessions retrieve and verify existing evidence before reuse, guaranteeing consistency without model hallucination.
                    </p>
                  </div>

                  <div className="mt-6 pt-4 border-t border-[#E8E0F5]">
                    <SoftPillButton
                      variant="primary"
                      size="md"
                      disabled={tokenMissing || Boolean(busy)}
                      onClick={() =>
                        void act('session', async () => {
                          setAgentSession(await api<AgentSession>('/api/v1/agent/sessions', token, 'POST'))
                          setAgentMessage(null)
                          setNotice('Fresh agent session initialized in FalkorDB.')
                        })
                      }
                    >
                      <Sparkles size={14} />
                      <span>{agentSession ? 'Start Fresh Session' : 'Start Agent Session'}</span>
                      <ArrowRight size={14} />
                    </SoftPillButton>
                  </div>
                </div>

                {/* Right (7 cols): Terminal Inspector */}
                <div className="lg:col-span-7 rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between pb-3 border-b border-[#E8E0F5]">
                      <div>
                        <span className="text-[10px] font-bold uppercase tracking-wider text-[#5B2BE8]">
                          Agent Session Terminal
                        </span>
                        <h4 className="text-sm font-bold text-[#1B1133]">
                          {agentSession ? `Session ${shortId(agentSession.session_id)}` : 'Awaiting Session'}
                        </h4>
                      </div>
                      <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                        agentSession
                          ? 'bg-[#ECFDF5] text-[#059669] border-[#A7F3D0]'
                          : 'bg-[#F7F4FC] text-[#9888B2] border-[#E8E0F5]'
                      }`}>
                        {agentSession ? 'SESSION ACTIVE' : 'NO ACTIVE SESSION'}
                      </span>
                    </div>

                    {agentSession ? (
                      <div className="mt-4 space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-[#9888B2]">
                          <span>Created {time(agentSession.created_at)}</span>
                          <SoftPillButton
                            variant="secondary"
                            size="sm"
                            disabled={!activeSource || tokenMissing || Boolean(busy)}
                            onClick={() =>
                              void act('agent-investigation', async () => {
                                setAgentMessage(
                                  await api<AgentMessage>(
                                    `/api/v1/agent/sessions/${idPath(agentSession.session_id)}/messages`,
                                    token,
                                    'POST',
                                    { intent: 'investigate_source', subject_id: activeSource },
                                  ),
                                )
                              })
                            }
                          >
                            <ScanSearch size={13} />
                            <span>Investigate Active Source</span>
                          </SoftPillButton>
                        </div>

                        {agentMessage ? (
                          <div className="rounded-xl border border-[#DDD0FA] bg-[#FAF8FE] p-4 text-xs space-y-3">
                            <div className="flex items-center justify-between">
                              <StatusBadge value={`memory ${agentMessage.memory_status}`} />
                              <span className="font-mono text-[10px] text-[#9888B2]">
                                Memory ID: {agentMessage.memory_id ? shortId(agentMessage.memory_id) : 'None'}
                              </span>
                            </div>
                            <p className="text-xs leading-relaxed text-[#1B1133] font-medium">
                              {agentMessage.summary}
                            </p>
                            <div className="flex flex-wrap items-center gap-1.5 border-t border-[#E8E0F5] pt-2 text-[11px] text-[#6B5B87]">
                              <span className="font-bold text-[#5B2BE8]">Executed Tool Flow:</span>
                              {agentMessage.tools_used.map((tool, idx) => (
                                <span
                                  key={idx}
                                  className="rounded-md bg-white px-2 py-0.5 font-mono text-[10px] text-[#1B1133] border border-[#DDD0FA]"
                                >
                                  {tool}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : (
                          <div className="rounded-xl border border-dashed border-[#DDD0FA] p-8 text-center text-xs text-[#9888B2]">
                            Click "Investigate Active Source" to query the session.
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="mt-8 rounded-xl border border-dashed border-[#DDD0FA] p-8 text-center text-xs text-[#9888B2]">
                        <Sparkles className="mx-auto mb-2 text-[#9888B2]" size={28} />
                        <p className="font-semibold text-[#1B1133]">No active session</p>
                        <p className="mt-1">Initialize a session to verify agent memory traversal.</p>
                      </div>
                    )}
                  </div>

                  <div className="mt-4 pt-3 border-t border-[#E8E0F5] text-xs text-[#9888B2]">
                    Allowlisted graph investigation tools only · No arbitrary model execution
                  </div>
                </div>
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}

function NavItem({
  label,
  icon,
  badge,
  active,
  onClick,
}: {
  label: string
  icon: React.ReactNode
  badge?: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition ${
        active
          ? 'bg-[#5B2BE8] text-white shadow-xs'
          : 'text-[#6B5B87] hover:bg-[#F1ECFE] hover:text-[#5B2BE8]'
      }`}
    >
      <div className="flex items-center gap-2.5">
        <span className={active ? 'text-white' : 'text-[#6B5B87]'}>{icon}</span>
        <span>{label}</span>
      </div>
      {badge && (
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
            active ? 'bg-white/20 text-white' : 'bg-[#F1ECFE] text-[#5B2BE8]'
          }`}
        >
          {badge}
        </span>
      )}
    </button>
  )
}

function MetricCard({
  label,
  value,
  detail,
  status,
  icon,
}: {
  label: string
  value: string
  detail: string
  status: 'coral' | 'violet' | 'mint' | 'orange' | 'neutral'
  icon: React.ReactNode
}) {
  const borderClass =
    status === 'coral'
      ? 'border-[#FECDD8] bg-[#FFF8FA]'
      : 'border-[#E8E0F5] bg-white'

  const valueColor =
    status === 'coral'
      ? 'text-[#ED3C65]'
      : 'text-[#1B1133]'

  return (
    <div className={`rounded-2xl border p-4 shadow-xs transition hover:shadow-md ${borderClass}`}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-[#9888B2]">{label}</span>
        {icon}
      </div>
      <strong className={`font-editorial mt-2 block text-3xl font-bold tabular-nums ${valueColor}`}>
        {value}
      </strong>
      <span className="mt-1 block text-xs text-[#9888B2]">{detail}</span>
    </div>
  )
}

function StatusBadge({ value }: { value: string }) {
  const isWarn =
    value.includes('confirmed') ||
    value.includes('suspect') ||
    value.includes('failed') ||
    value.includes('stale')
  const isGood =
    value.includes('clean') ||
    value.includes('succeeded') ||
    value.includes('verified') ||
    value.includes('approved')
  const isUnknown = value.includes('unknown') || value.includes('none')

  let badgeClasses = 'border-[#DDD0FA] bg-[#F1ECFE] text-[#5B2BE8]'
  let dotColor = 'bg-[#5B2BE8]'

  if (isWarn) {
    badgeClasses = 'border-[#FECDD8] bg-[#FFF0F4] text-[#ED3C65]'
    dotColor = 'bg-[#ED3C65]'
  } else if (isGood) {
    badgeClasses = 'border-[#A7F3D0] bg-[#ECFDF5] text-[#059669]'
    dotColor = 'bg-[#10B981]'
  } else if (isUnknown) {
    badgeClasses = 'border-[#FED7AA] bg-[#FFF7ED] text-[#EA580C]'
    dotColor = 'bg-[#EA580C]'
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${badgeClasses}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${dotColor}`} />
      <span>{statusLabel(value)}</span>
    </span>
  )
}

function ExperimentCard({
  audit,
  run,
  onTrace,
}: {
  audit: Audit
  run?: Run
  onTrace: () => void
}) {
  return (
    <article className="flex flex-col justify-between rounded-2xl border border-[#E8E0F5] bg-white p-5 shadow-xs transition hover:border-[#DDD0FA] hover:shadow-md">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-bold tracking-wider uppercase text-[#9888B2]">
            Experiment
          </span>
          <StatusBadge value={audit.status} />
        </div>

        <div className="mt-3">
          <h3 className="text-base font-bold text-[#1B1133]">{humanExperiment(audit.experiment_id)}</h3>
          <p className="font-mono text-[10px] text-[#9888B2] truncate" title={audit.experiment_id}>
            {audit.experiment_id}
          </p>
        </div>

        <div className="mt-2 inline-block rounded-md bg-[#FAF8FE] px-2 py-0.5 text-[10px] font-semibold text-[#5B2BE8] border border-[#F1ECFE]">
          1-Nearest Neighbor (k=1)
        </div>

        <div className="mt-4 flex items-baseline gap-2">
          <strong className="font-editorial text-3xl font-bold tracking-tight text-[#1B1133] tabular-nums">
            {score(run?.accuracy)}
          </strong>
          <span className="text-[11px] font-semibold text-[#9888B2]">
            {run ? 'Measured Accuracy' : 'No Measured Run'}
          </span>
        </div>

        <div className="mt-4 space-y-1.5 border-t border-[#E8E0F5] pt-3 text-[11px]">
          <div className="flex justify-between text-[#6B5B87]">
            <span>Training Set:</span>
            <code className="text-[#1B1133]">{shortId(audit.training_dataset_id)}</code>
          </div>
          <div className="flex justify-between text-[#6B5B87]">
            <span>Evaluation Set:</span>
            <code className="text-[#1B1133]">{shortId(audit.evaluation_dataset_id)}</code>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1 text-[10px]">
          {audit.training_manifest_verified && (
            <span className="rounded-sm bg-[#ECFDF5] px-1.5 py-0.5 text-[#059669]">
              ✓ Train Manifest
            </span>
          )}
          {audit.evaluation_manifest_verified && (
            <span className="rounded-sm bg-[#ECFDF5] px-1.5 py-0.5 text-[#059669]">
              ✓ Eval Manifest
            </span>
          )}
          {audit.training_samples_without_source > 0 && (
            <span className="rounded-sm bg-[#FFF7ED] px-1.5 py-0.5 text-[#EA580C]">
              {audit.training_samples_without_source} unmapped source
            </span>
          )}
        </div>
      </div>

      <div className="mt-5 flex items-center justify-between gap-2 border-t border-[#E8E0F5] pt-3 text-[11px] text-[#9888B2]">
        <span>
          {run
            ? `${run.training_sample_count} tr · ${run.evaluation_sample_count} ev`
            : 'Unmeasured'}
        </span>
        {audit.evidence.length > 0 && (
          <button
            type="button"
            onClick={onTrace}
            className="inline-flex items-center gap-1 font-semibold text-[#5B2BE8] hover:text-[#4C1ED1] transition"
          >
            <span>Trace in Graph</span>
            <ArrowRight size={13} />
          </button>
        )}
      </div>
    </article>
  )
}

// Keep the root on its container so Vite HMR rerenders instead of mounting twice.
type RootContainer = HTMLElement & { benchWitnessRoot?: ReturnType<typeof createRoot> }

const rootContainer = document.getElementById('root') as RootContainer | null
if (!rootContainer) throw new Error('Missing #root application container')

const root = rootContainer.benchWitnessRoot ?? createRoot(rootContainer)
rootContainer.benchWitnessRoot = root
root.render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
