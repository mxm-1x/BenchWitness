export type IntegrityStatus = 'confirmed' | 'clean_within_recorded_lineage' | 'unknown'

export interface LineageEvidence {
  canonical_source_record_id: string
  training_dataset_id: string
  training_sample_id: string
  training_derivation_hops: number
  evaluation_dataset_id: string
  evaluation_sample_id: string
  evaluation_derivation_hops: number
}

export interface Audit {
  experiment_id: string
  status: IntegrityStatus
  coverage_complete: boolean
  training_dataset_id: string
  evaluation_dataset_id: string
  training_samples_without_source: number
  evaluation_samples_without_source: number
  training_samples_with_ambiguous_source: number
  evaluation_samples_with_ambiguous_source: number
  training_samples_with_incomplete_lineage: number
  evaluation_samples_with_incomplete_lineage: number
  training_manifest_verified: boolean
  evaluation_manifest_verified: boolean
  source_artifact_verified: boolean
  evidence: LineageEvidence[]
}

export interface Run {
  run_id: string
  experiment_id: string
  training_dataset_id: string
  evaluation_dataset_id: string
  created_at: string
  training_sample_count: number
  evaluation_sample_count: number
  accuracy: number
  precision?: number
  recall?: number
  f1?: number
}

export interface Overview {
  audits: Audit[]
  runs: Run[]
}

export interface ImpactEvidence extends LineageEvidence {
  run_id: string
}

export interface ImpactedRun {
  run_id: string
  experiment_id: string
  training_dataset_id: string
  evaluation_dataset_id: string
  model_id: string
  model_configuration_id: string
  evaluation_claim_id: string
  integrity_status: 'suspect' | 'quarantined'
  metrics: { claim_id: string; name: string; value: number }[]
  evidence: ImpactEvidence[]
}

export interface Investigation {
  investigation_id: string
  source_record_id: string
  created_at: string
  finding_status: IntegrityStatus
  coverage_complete: boolean
  unresolved_run_ids: string[]
  impacted_runs: ImpactedRun[]
}

export interface ActionProposal {
  action_id: string
  investigation_id: string
  status: 'proposed' | 'approved'
  reason: string
  created_at: string
  target_claim_ids: string[]
  approval_id: string | null
  approver: string | null
  approved_at: string | null
}

export interface RecoveryJob {
  job_id: string
  action_id: string
  status: 'pending_enqueue' | 'queued' | 'running' | 'succeeded' | 'failed'
  created_at: string
  started_at: string | null
  finished_at: string | null
  error: string | null
  original_run_ids: string[]
  repaired_run_ids: string[]
}

export interface AgentSession {
  session_id: string
  created_at: string
}

export interface AgentMessage {
  session_id: string
  intent: 'investigate_source' | 'audit_experiment' | 'get_job_status'
  subject_id: string
  tools_used: string[]
  memory_status: 'none' | 'verified' | 'stale'
  memory_id: string | null
  summary: string
  investigation: Investigation | null
  audit: Audit | null
  job: RecoveryJob | null
}

type ErrorPayload = { error?: string; message?: string; detail?: string }

export async function api<T>(
  path: string,
  token = '',
  method: 'GET' | 'POST' = 'GET',
  body?: object,
): Promise<T> {
  const response = await fetch(path, {
    method,
    cache: 'no-store',
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    let error: ErrorPayload = {}
    try { error = (await response.json()) as ErrorPayload } catch { /* keep HTTP status */ }
    throw new Error(error.message ?? error.detail ?? error.error ?? `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const idPath = (id: string) => encodeURIComponent(id)
