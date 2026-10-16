"""Allowlisted, bounded FalkorDB writes and exact lineage audit queries."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from falkordb import FalkorDB  # type: ignore[import-untyped]

from benchwitness_api.lineage import (
    DEMO_EXPERIMENTS,
    DemoScenario,
    dataset_manifest_digest,
    source_records_digest,
)
from benchwitness_api.settings import GraphSettings

_QUERY_TIMEOUT_MS = 5_000
_WRITE_BATCH_SIZE = 200
_MAX_EVIDENCE_PATHS = 100
_MAX_DATASET_SAMPLES = 1_000
_MAX_IMPACT_RUNS = 100
_MAX_IMPACT_ROWS = 1_000
_LOGGER = logging.getLogger(__name__)

_UPSERT_SOURCES = """
UNWIND $rows AS row
MERGE (source:SourceRecord {id: row.id})
SET source.family_id = row.family_id,
    source.source_version = row.source_version
RETURN count(source)
"""
_UPSERT_SAMPLES = """
UNWIND $rows AS row
MERGE (sample:SampleVersion {id: row.id})
SET sample.kind = row.kind,
    sample.lineage_complete = row.lineage_complete
RETURN count(sample)
"""
_UPSERT_DATASETS = """
UNWIND $rows AS row
MERGE (dataset:DatasetVersion {id: row.id})
SET dataset.role = row.role,
    dataset.manifest_hash = row.manifest_hash,
    dataset.sample_count = row.sample_count,
    dataset.lineage_complete = row.lineage_complete,
    dataset.source_family_id = row.source_family_id,
    dataset.source_manifest_hash = row.source_manifest_hash,
    dataset.source_record_count = row.source_record_count
RETURN count(dataset)
"""
_LINK_SOURCE_RECORDS = """
UNWIND $rows AS row
MATCH (sample:SampleVersion {id: row.sample_id})
MATCH (source:SourceRecord {id: row.source_record_id})
MERGE (sample)-[:DERIVED_FROM]->(source)
RETURN count(sample)
"""
_LINK_DERIVATIONS = """
UNWIND $rows AS row
MATCH (sample:SampleVersion {id: row.sample_id})
MATCH (parent:SampleVersion {id: row.parent_sample_id})
MERGE (sample)-[:DERIVED_FROM]->(parent)
RETURN count(sample)
"""
_LINK_MEMBERSHIPS = """
UNWIND $rows AS row
MATCH (dataset:DatasetVersion {id: row.dataset_id})
MATCH (sample:SampleVersion {id: row.sample_id})
MERGE (dataset)-[:CONTAINS]->(sample)
RETURN count(dataset)
"""
_LINK_EXPERIMENTS = """
UNWIND $rows AS row
MERGE (experiment:Experiment {id: row.id})
WITH experiment, row
MATCH (training:DatasetVersion {id: row.training_dataset_id})
MATCH (evaluation:DatasetVersion {id: row.evaluation_dataset_id})
MERGE (experiment)-[:TRAINS_ON]->(training)
MERGE (experiment)-[:TESTS_ON]->(evaluation)
RETURN count(experiment)
"""
_GET_EXPERIMENT = """
MATCH (experiment:Experiment {id: $experiment_id})-[:TRAINS_ON]->(training:DatasetVersion)
MATCH (experiment)-[:TESTS_ON]->(evaluation:DatasetVersion)
RETURN experiment.id, training.id, training.lineage_complete,
       evaluation.id, evaluation.lineage_complete
LIMIT 2
"""
_LIST_DEMO_EXPERIMENT_IDS = """
MATCH (experiment:Experiment)
WHERE experiment.id IN $experiment_ids
RETURN experiment.id
ORDER BY experiment.id
LIMIT 5
"""
_LIST_RUN_SUMMARIES = """
MATCH (experiment:Experiment)-[:HAS_RUN]->(run:ExperimentRun)
MATCH (run)-[:TRAINED_ON]->(training:DatasetVersion)
MATCH (run)-[:EVALUATED_ON]->(evaluation:DatasetVersion)
RETURN run.id, experiment.id, training.id, evaluation.id, run.created_at,
       run.training_sample_count, run.evaluation_sample_count, run.accuracy
ORDER BY run.created_at DESC, run.id DESC
LIMIT $limit
"""
_GET_DATASET_MANIFEST = """
MATCH (dataset:DatasetVersion {id: $dataset_id})
OPTIONAL MATCH (dataset)-[:CONTAINS]->(sample:SampleVersion)
RETURN dataset.id, dataset.role, dataset.lineage_complete, dataset.sample_count,
       dataset.manifest_hash, collect(DISTINCT sample.id), dataset.source_family_id,
       dataset.source_manifest_hash, dataset.source_record_count
LIMIT 1
"""
_GET_SOURCE_RECORDS = """
MATCH (source:SourceRecord {family_id: $family_id})
RETURN count(source), collect(source.id)
"""
_RESOLVE_DATASET_SAMPLES = """
MATCH (dataset:DatasetVersion {id: $dataset_id})-[:CONTAINS]->(sample:SampleVersion)
OPTIONAL MATCH (sample)-[:DERIVED_FROM*1..3]->(source:SourceRecord)
RETURN sample.id, collect(DISTINCT source.id)
LIMIT $limit
"""
_COUNT_INVALID_SOURCE_RESOLUTION = """
MATCH (dataset:DatasetVersion {id: $dataset_id})
OPTIONAL MATCH (dataset)-[:CONTAINS]->(sample:SampleVersion)
OPTIONAL MATCH (sample)-[:DERIVED_FROM*1..3]->(source:SourceRecord)
WITH sample, count(DISTINCT source) AS source_count
RETURN sum(CASE WHEN sample IS NOT NULL AND source_count = 0 THEN 1 ELSE 0 END),
       sum(CASE WHEN sample IS NOT NULL AND source_count > 1 THEN 1 ELSE 0 END)
"""
_COUNT_INCOMPLETE_LINEAGE_SAMPLES = """
MATCH (dataset:DatasetVersion {id: $dataset_id})
OPTIONAL MATCH (dataset)-[:CONTAINS]->(sample:SampleVersion)
OPTIONAL MATCH (sample)-[:DERIVED_FROM]->(parent)
OPTIONAL MATCH (parent)-[:DERIVED_FROM*0..3]->(source:SourceRecord)
WITH sample, parent, count(DISTINCT source) AS parent_source_count
WITH sample, count(DISTINCT parent) AS parent_count,
     sum(CASE WHEN parent IS NOT NULL AND parent_source_count <> 1 THEN 1 ELSE 0 END)
       AS unresolved_parent_count
WHERE sample IS NOT NULL
  AND (sample.lineage_complete IS NULL OR sample.lineage_complete <> true
       OR parent_count = 0 OR unresolved_parent_count > 0)
RETURN count(sample)
"""
_FIND_OVERLAPS = """
MATCH (experiment:Experiment {id: $experiment_id})-[:TRAINS_ON]->(training:DatasetVersion)
MATCH (experiment)-[:TESTS_ON]->(evaluation:DatasetVersion)
MATCH (training)-[:CONTAINS]->(training_sample:SampleVersion)
MATCH training_path = (training_sample)-[:DERIVED_FROM*1..3]->(source:SourceRecord)
MATCH (evaluation)-[:CONTAINS]->(evaluation_sample:SampleVersion)
MATCH evaluation_path = (evaluation_sample)-[:DERIVED_FROM*1..3]->(evaluation_source:SourceRecord)
WHERE source.id = evaluation_source.id
RETURN source.id, training.id, training_sample.id, length(training_path),
       evaluation.id, evaluation_sample.id, length(evaluation_path)
LIMIT $limit
"""
_RECORD_RUN = """
MERGE (run:ExperimentRun {id: $run_id})
ON CREATE SET run.experiment_id = $experiment_id,
    run.training_dataset_id = $training_dataset_id,
    run.evaluation_dataset_id = $evaluation_dataset_id,
    run.model_id = $model_id,
    run.model_config = $model_config,
    run.created_at = $created_at,
    run.python_version = $python_version,
    run.training_sample_count = $training_sample_count,
    run.evaluation_sample_count = $evaluation_sample_count,
    run.accuracy = $accuracy,
    run.precision = $precision,
    run.recall = $recall,
    run.f1 = $f1,
    run.true_positive = $true_positive,
    run.false_positive = $false_positive,
    run.true_negative = $true_negative,
    run.false_negative = $false_negative,
    run.prediction_sha256 = $prediction_sha256,
    run.manifest_sha256 = $manifest_sha256,
    run.artifact_path = $artifact_path
WITH run
MATCH (experiment:Experiment {id: $experiment_id})
MATCH (training:DatasetVersion {id: $training_dataset_id})
MATCH (evaluation:DatasetVersion {id: $evaluation_dataset_id})
WHERE run.experiment_id = $experiment_id
  AND run.training_dataset_id = $training_dataset_id
  AND run.evaluation_dataset_id = $evaluation_dataset_id
MERGE (experiment)-[:HAS_RUN]->(run)
MERGE (run)-[:TRAINED_ON]->(training)
MERGE (run)-[:EVALUATED_ON]->(evaluation)
RETURN run.id
"""
_GET_RUN = """
MATCH (experiment:Experiment)-[:HAS_RUN]->(run:ExperimentRun {id: $run_id})
MATCH (run)-[:TRAINED_ON]->(training:DatasetVersion)
MATCH (run)-[:EVALUATED_ON]->(evaluation:DatasetVersion)
RETURN run.id, experiment.id, training.id, evaluation.id, run.model_id,
       run.model_config, run.created_at, run.python_version,
       run.training_sample_count, run.evaluation_sample_count,
       run.accuracy, run.precision, run.recall, run.f1,
       run.true_positive, run.false_positive, run.true_negative, run.false_negative,
       run.prediction_sha256, run.manifest_sha256, run.artifact_path
LIMIT 1
"""
_GET_SOURCE_FAMILY_RUNS = """
MATCH (run:ExperimentRun)-[:TRAINED_ON]->(training:DatasetVersion)
MATCH (run)-[:EVALUATED_ON]->(evaluation:DatasetVersion)
WHERE training.source_family_id = $source_family_id
   OR evaluation.source_family_id = $source_family_id
RETURN DISTINCT run.id, run.experiment_id, training.id, evaluation.id
LIMIT $limit
"""
_GET_SOURCE_LINEAGE_RUNS = """
MATCH (source:SourceRecord {id: $source_record_id})
MATCH (sample:SampleVersion)-[:DERIVED_FROM*1..3]->(source)
MATCH (dataset:DatasetVersion)-[:CONTAINS]->(sample)
MATCH (run:ExperimentRun)-[:TRAINED_ON]->(training:DatasetVersion)
MATCH (run)-[:EVALUATED_ON]->(evaluation:DatasetVersion)
WHERE dataset.id = training.id OR dataset.id = evaluation.id
RETURN DISTINCT run.id, run.experiment_id, training.id, evaluation.id
LIMIT $limit
"""
_GET_SOURCE_FAMILY = """
MATCH (source:SourceRecord {id: $source_record_id})
RETURN source.family_id
LIMIT 1
"""
_MATERIALIZE_RUN_CLAIMS = """
MATCH (run:ExperimentRun {id: $run_id})
MERGE (model:ModelConfiguration {id: $model_configuration_id})
ON CREATE SET model.model_id = $model_id,
              model.config_json = $model_config_json
MERGE (run)-[:USES_MODEL_CONFIGURATION]->(model)
MERGE (claim:EvaluationClaim {id: $evaluation_claim_id})
ON CREATE SET claim.run_id = run.id,
              claim.experiment_id = run.experiment_id,
              claim.reported_at = run.created_at,
              claim.source = 'measured_run'
MERGE (run)-[:HAS_EVALUATION]->(claim)
WITH run, claim
UNWIND $metrics AS metric
MERGE (metric_claim:MetricClaim {id: metric.id})
ON CREATE SET metric_claim.metric_name = metric.name,
              metric_claim.value = metric.value,
              metric_claim.status = 'reported'
MERGE (claim)-[:REPORTS]->(metric_claim)
RETURN count(metric_claim)
"""
_RECORD_INVESTIGATION = """
CREATE (investigation:Investigation {
    id: $investigation_id,
    source_record_id: $source_record_id,
    created_at: $created_at,
    status: 'pending',
    coverage_complete: false,
    unresolved_run_ids: []
})
CREATE (finding:Finding {
    id: $finding_id,
    source_record_id: $source_record_id,
    status: 'pending',
    coverage_complete: false,
    created_at: $created_at
})
CREATE (investigation)-[:ESTABLISHED]->(finding)
RETURN finding.id
"""
_FINALIZE_INVESTIGATION = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding {id: $finding_id})
SET investigation.status = $status,
    investigation.coverage_complete = $coverage_complete,
    investigation.unresolved_run_ids = $unresolved_run_ids,
    finding.status = $status,
    finding.coverage_complete = $coverage_complete
RETURN finding.id
"""
_DELETE_PARTIAL_INVESTIGATION = """
MATCH (investigation:Investigation {id: $investigation_id})
OPTIONAL MATCH (investigation)-[:ESTABLISHED]->(finding:Finding)
OPTIONAL MATCH (finding)-[:SUPPORTED_BY]->(evidence:LineageEvidence)
WITH investigation, collect(DISTINCT finding) AS findings,
     collect(DISTINCT evidence) AS evidence_nodes
FOREACH (evidence IN evidence_nodes | DETACH DELETE evidence)
FOREACH (finding IN findings | DETACH DELETE finding)
DETACH DELETE investigation
RETURN 1
"""
_LINK_FINDING_IMPACTS = """
UNWIND $claim_ids AS claim_id
MATCH (finding:Finding {id: $finding_id})
MATCH (claim:EvaluationClaim {id: claim_id})
MERGE (finding)-[:IMPACTS]->(claim)
RETURN count(claim)
"""
_RECORD_EVIDENCE_PATHS = """
UNWIND $rows AS row
MATCH (finding:Finding {id: $finding_id})
MATCH (source:SourceRecord {id: row.source_record_id})
MATCH (training:DatasetVersion {id: row.training_dataset_id})
MATCH (training_sample:SampleVersion {id: row.training_sample_id})
MATCH (evaluation:DatasetVersion {id: row.evaluation_dataset_id})
MATCH (evaluation_sample:SampleVersion {id: row.evaluation_sample_id})
MATCH (claim:EvaluationClaim {id: row.evaluation_claim_id})
MERGE (evidence:LineageEvidence {id: row.id})
ON CREATE SET evidence.run_id = row.run_id,
              evidence.canonical_source_record_id = row.source_record_id,
              evidence.training_derivation_hops = row.training_derivation_hops,
              evidence.evaluation_derivation_hops = row.evaluation_derivation_hops
MERGE (finding)-[:SUPPORTED_BY]->(evidence)
MERGE (evidence)-[:USES_SOURCE]->(source)
MERGE (evidence)-[:TRAINING_DATASET]->(training)
MERGE (evidence)-[:TRAINING_SAMPLE]->(training_sample)
MERGE (evidence)-[:EVALUATION_DATASET]->(evaluation)
MERGE (evidence)-[:EVALUATION_SAMPLE]->(evaluation_sample)
MERGE (evidence)-[:RELATES_TO]->(claim)
RETURN count(evidence)
"""
_GET_INVESTIGATION = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding)
RETURN investigation.id, investigation.source_record_id, investigation.created_at,
       finding.id, finding.status, finding.coverage_complete,
       investigation.unresolved_run_ids
LIMIT 1
"""
_GET_IMPACT_METRICS = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding)-[:IMPACTS]->(claim:EvaluationClaim)
MATCH (run:ExperimentRun)-[:HAS_EVALUATION]->(claim)
MATCH (run)-[:USES_MODEL_CONFIGURATION]->(model:ModelConfiguration)
MATCH (claim)-[:REPORTS]->(metric:MetricClaim)
RETURN run.id, run.experiment_id, run.training_dataset_id, run.evaluation_dataset_id,
       run.model_id, model.id, claim.id, metric.id, metric.metric_name, metric.value
LIMIT $limit
"""
_GET_IMPACT_EVIDENCE = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding)-[:SUPPORTED_BY]->(evidence:LineageEvidence)
MATCH (evidence)-[:RELATES_TO]->(claim:EvaluationClaim)
MATCH (evidence)-[:USES_SOURCE]->(source:SourceRecord)
MATCH (evidence)-[:TRAINING_DATASET]->(training:DatasetVersion)
MATCH (evidence)-[:TRAINING_SAMPLE]->(training_sample:SampleVersion)
MATCH (evidence)-[:EVALUATION_DATASET]->(evaluation:DatasetVersion)
MATCH (evidence)-[:EVALUATION_SAMPLE]->(evaluation_sample:SampleVersion)
RETURN evidence.run_id, source.id, training.id, training_sample.id,
       evidence.training_derivation_hops, evaluation.id,
       evaluation_sample.id, evidence.evaluation_derivation_hops
LIMIT $limit
"""
_GET_QUARANTINED_CLAIMS = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding)
MATCH (action:ActionProposal {action_type: 'quarantine'})-[:BASED_ON]->(finding)
MATCH (approval:ApprovalDecision)-[:APPROVES]->(action)
MATCH (action)-[:TARGETS]->(claim:EvaluationClaim)
RETURN DISTINCT claim.id
LIMIT $limit
"""
_CREATE_QUARANTINE_PROPOSAL = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding)
WHERE finding.status = 'confirmed' AND finding.coverage_complete = true
MATCH (finding)-[:IMPACTS]->(claim:EvaluationClaim)
WITH investigation, finding, collect(DISTINCT claim) AS claims
WHERE size(claims) > 0
MERGE (action:ActionProposal {id: $action_id})
ON CREATE SET action.action_type = 'quarantine',
              action.investigation_id = investigation.id,
              action.reason = $reason,
              action.created_at = $created_at
MERGE (action)-[:BASED_ON]->(finding)
WITH action, claims
UNWIND claims AS claim
MERGE (action)-[:TARGETS]->(claim)
RETURN action.id, count(claim)
"""
_APPROVE_QUARANTINE = """
MATCH (action:ActionProposal {id: $action_id, action_type: 'quarantine'})
MATCH (action)-[:BASED_ON]->(finding:Finding)
WHERE finding.status = 'confirmed' AND finding.coverage_complete = true
MATCH (action)-[:TARGETS]->(claim:EvaluationClaim)
WITH action, count(DISTINCT claim) AS target_count
WHERE target_count > 0
MERGE (approval:ApprovalDecision {id: $approval_id})
ON CREATE SET approval.approver = $approver,
              approval.reason = $reason,
              approval.created_at = $created_at
MERGE (approval)-[:APPROVES]->(action)
RETURN approval.id
"""
_GET_ACTION = """
MATCH (action:ActionProposal {id: $action_id})
OPTIONAL MATCH (action)-[:TARGETS]->(claim:EvaluationClaim)
OPTIONAL MATCH (approval:ApprovalDecision)-[:APPROVES]->(action)
RETURN action.id, action.investigation_id, action.action_type, action.reason,
       action.created_at, collect(DISTINCT claim.id), collect(DISTINCT approval.id),
       collect(DISTINCT approval.approver), collect(DISTINCT approval.reason),
       collect(DISTINCT approval.created_at)
LIMIT 1
"""

_PROPOSE_REPAIR = """
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->(finding:Finding)
WHERE finding.status = 'confirmed' AND finding.coverage_complete = true
MATCH (finding)-[:IMPACTS]->(claim:EvaluationClaim)
WITH investigation, finding, collect(DISTINCT claim) AS claims
WHERE size(claims) > 0
MERGE (action:ActionProposal {id: $action_id})
ON CREATE SET action.action_type = 'repair', action.investigation_id = investigation.id,
              action.reason = $reason, action.created_at = $created_at
MERGE (action)-[:BASED_ON]->(finding)
WITH action, claims
UNWIND claims AS claim
MERGE (action)-[:TARGETS]->(claim)
RETURN action.id, count(claim)
"""
_APPROVE_REPAIR = """
MATCH (action:ActionProposal {id: $action_id, action_type: 'repair'})-[:BASED_ON]->
      (finding:Finding {status: 'confirmed', coverage_complete: true})
MATCH (action)-[:TARGETS]->(claim:EvaluationClaim)
WITH action, count(DISTINCT claim) AS target_count
WHERE target_count > 0
MERGE (approval:ApprovalDecision {id: $approval_id})
ON CREATE SET approval.approver = $approver, approval.reason = $reason,
              approval.created_at = $created_at
MERGE (approval)-[:APPROVES]->(action)
RETURN approval.id
"""
_CREATE_RECOVERY_JOB = """
MATCH (approval:ApprovalDecision)-[:APPROVES]->(action:ActionProposal
      {id: $action_id, action_type: 'repair'})
MERGE (job:RecoveryJob {id: $job_id})
ON CREATE SET job.status = 'pending_enqueue', job.created_at = $created_at,
              job.original_run_ids = $original_run_ids
MERGE (action)-[:STARTS]->(job)
RETURN job.id
"""
_GET_RECOVERY_JOB = """
MATCH (action:ActionProposal)-[:STARTS]->(job:RecoveryJob {id: $job_id})
RETURN job.id, action.id, job.status, job.created_at, job.started_at,
       job.finished_at, job.error, job.original_run_ids, job.repaired_run_ids
LIMIT 1
"""
_SET_RECOVERY_JOB_STATUS = """
MATCH (job:RecoveryJob {id: $job_id})
WHERE job.status = $expected_status
SET job.status = $status, job.started_at = $started_at,
    job.finished_at = $finished_at, job.error = $error,
    job.repaired_run_ids = $repaired_run_ids
RETURN job.id
"""
_FAIL_STALE_RECOVERY_JOB = """
MATCH (job:RecoveryJob {id: $job_id})
WHERE job.status = 'running' AND job.started_at = $expected_started_at
SET job.status = 'failed', job.finished_at = $finished_at,
    job.error = 'worker_timeout:stale_running_job'
RETURN job.id
"""
_LINK_RECOVERY_RUN = """
MATCH (job:RecoveryJob {id: $job_id})
MATCH (original:ExperimentRun {id: $original_run_id})
MATCH (repaired:ExperimentRun {id: $repaired_run_id})
MERGE (job)-[:REPAIRS]->(original)
MERGE (job)-[:PRODUCED]->(repaired)
MERGE (repaired)-[:REPLACES]->(original)
MERGE (model:ModelVersion {id: $model_version_id})
ON CREATE SET model.artifact_path = $model_artifact_path,
              model.sha256 = $model_sha256, model.created_at = $created_at
MERGE (repaired)-[:PRODUCED_MODEL]->(model)
RETURN repaired.id
"""
_CREATE_RECOVERY_EXPERIMENT = """
MATCH (job:RecoveryJob {id: $job_id})
MATCH (original:ExperimentRun {id: $original_run_id})
MATCH (training:DatasetVersion {id: $training_dataset_id})
MATCH (evaluation:DatasetVersion {id: $evaluation_dataset_id})
MERGE (experiment:Experiment {id: $experiment_id})
ON CREATE SET experiment.recovery_job_id = job.id, experiment.original_run_id = original.id
MERGE (experiment)-[:TRAINS_ON]->(training)
MERGE (experiment)-[:TESTS_ON]->(evaluation)
MERGE (experiment)-[:REPAIRS_RUN]->(original)
RETURN experiment.id
"""
_CREATE_AGENT_SESSION = """
CREATE (session:AgentSession {id: $session_id, created_at: $created_at})
RETURN session.id, session.created_at
"""
_GET_AGENT_SESSION = """
MATCH (session:AgentSession {id: $session_id})
RETURN session.id, session.created_at
LIMIT 1
"""
_GET_LATEST_AGENT_MEMORY = """
MATCH (memory:AgentMemory {source_record_id: $source_record_id})-[:REFERS_TO]->
      (investigation:Investigation)
RETURN memory.id, memory.source_record_id, memory.investigation_id,
       memory.fingerprint, memory.created_at
ORDER BY memory.created_at DESC
LIMIT 1
"""
_RECORD_AGENT_MEMORY = """
MATCH (session:AgentSession {id: $session_id})
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding {status: 'confirmed', coverage_complete: true})
MATCH (source:SourceRecord {id: $source_record_id})
WHERE investigation.source_record_id = source.id
MERGE (memory:AgentMemory {id: $memory_id})
ON CREATE SET memory.source_record_id = source.id,
              memory.investigation_id = investigation.id,
              memory.fingerprint = $fingerprint,
              memory.created_at = $created_at
MERGE (session)-[:RECORDED]->(memory)
MERGE (memory)-[:REFERS_TO]->(investigation)
MERGE (memory)-[:USES_SOURCE]->(source)
RETURN memory.id
"""
_RECALL_AGENT_MEMORY = """
MATCH (session:AgentSession {id: $session_id})
MATCH (memory:AgentMemory {id: $memory_id})-[:REFERS_TO]->
      (investigation:Investigation)
MERGE (session)-[:REMEMBERS]->(memory)
RETURN memory.id
"""


class LineageGraphError(RuntimeError):
    """A fixed graph operation failed or returned an invalid result."""


class ActionNotAllowed(RuntimeError):
    """A quarantine proposal or approval failed its evidence preconditions."""


class ImpactScopeExceeded(RuntimeError):
    """A source-family traversal exceeds its configured run bound."""


@dataclass(frozen=True)
class AuditEvidence:
    canonical_source_record_id: str
    training_dataset_id: str
    training_sample_id: str
    training_derivation_hops: int
    evaluation_dataset_id: str
    evaluation_sample_id: str
    evaluation_derivation_hops: int


@dataclass(frozen=True)
class AuditResult:
    experiment_id: str
    status: Literal["confirmed", "clean_within_recorded_lineage", "unknown"]
    coverage_complete: bool
    training_dataset_id: str
    evaluation_dataset_id: str
    training_samples_without_source: int
    evaluation_samples_without_source: int
    training_samples_with_ambiguous_source: int
    evaluation_samples_with_ambiguous_source: int
    training_samples_with_incomplete_lineage: int
    evaluation_samples_with_incomplete_lineage: int
    training_manifest_verified: bool
    evaluation_manifest_verified: bool
    source_artifact_verified: bool
    evidence: tuple[AuditEvidence, ...]


@dataclass(frozen=True)
class ResolvedSample:
    sample_id: str
    source_record_id: str


@dataclass(frozen=True)
class ResolvedDataset:
    dataset_id: str
    role: str
    source_family_id: str
    source_manifest_hash: str
    source_record_count: int
    samples: tuple[ResolvedSample, ...]


@dataclass(frozen=True)
class ExperimentRunRecord:
    run_id: str
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str
    model_id: str
    model_config_json: str
    created_at: str
    python_version: str
    training_sample_count: int
    evaluation_sample_count: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    prediction_sha256: str
    manifest_sha256: str
    artifact_path: str


@dataclass(frozen=True)
class ExperimentRunSummary:
    """Minimal graph-backed fields needed for the browser overview."""

    run_id: str
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str
    created_at: str
    training_sample_count: int
    evaluation_sample_count: int
    accuracy: float


@dataclass(frozen=True)
class RunCandidate:
    run_id: str
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str


@dataclass(frozen=True)
class MetricClaimRecord:
    claim_id: str
    name: str
    value: float


@dataclass(frozen=True)
class ImpactEvidenceRecord:
    run_id: str
    canonical_source_record_id: str
    training_dataset_id: str
    training_sample_id: str
    training_derivation_hops: int
    evaluation_dataset_id: str
    evaluation_sample_id: str
    evaluation_derivation_hops: int


@dataclass(frozen=True)
class ImpactedRunRecord:
    run_id: str
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str
    model_id: str
    model_configuration_id: str
    evaluation_claim_id: str
    metrics: tuple[MetricClaimRecord, ...]
    evidence: tuple[ImpactEvidenceRecord, ...]
    integrity_status: Literal["suspect", "quarantined"]


@dataclass(frozen=True)
class ImpactInvestigationRecord:
    investigation_id: str
    source_record_id: str
    created_at: str
    finding_status: Literal["confirmed", "clean_within_recorded_lineage", "unknown"]
    coverage_complete: bool
    unresolved_run_ids: tuple[str, ...]
    impacted_runs: tuple[ImpactedRunRecord, ...]


@dataclass(frozen=True)
class QuarantineActionRecord:
    action_id: str
    investigation_id: str
    status: Literal["proposed", "approved"]
    reason: str
    created_at: str
    target_claim_ids: tuple[str, ...]
    approval_id: str | None = None
    approver: str | None = None
    approval_reason: str | None = None
    approved_at: str | None = None


@dataclass(frozen=True)
class RecoveryJobRecord:
    job_id: str
    action_id: str
    status: Literal["pending_enqueue", "queued", "running", "succeeded", "failed"]
    created_at: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    original_run_ids: tuple[str, ...]
    repaired_run_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentSessionRecord:
    session_id: str
    created_at: str


@dataclass(frozen=True)
class AgentMemoryRecord:
    memory_id: str
    source_record_id: str
    investigation_id: str
    fingerprint: str
    created_at: str


class GraphLineageStore:
    """Persist the demo lineage graph and query its exact source-record paths."""

    def __init__(self, settings: GraphSettings, artifact_dir: Path | None = None) -> None:
        self._settings = settings
        self._artifact_dir = artifact_dir or Path(
            os.environ.get("BENCHWITNESS_ARTIFACT_DIR", "artifacts/demo")
        )

    def _query(self, query: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        try:
            client = FalkorDB(
                host=self._settings.host,
                port=self._settings.port,
                socket_connect_timeout=1,
                socket_timeout=6,
            )
            graph = client.select_graph(self._settings.graph_name)
            result = graph.query(query, params=params, timeout=_QUERY_TIMEOUT_MS).result_set
        except Exception as exc:
            raise LineageGraphError("FalkorDB lineage query failed") from exc
        if not isinstance(result, list):
            raise LineageGraphError("FalkorDB returned an invalid lineage result")
        return result

    def _write_batches(self, query: str, rows: tuple[dict[str, Any], ...]) -> None:
        for start in range(0, len(rows), _WRITE_BATCH_SIZE):
            batch = list(rows[start : start + _WRITE_BATCH_SIZE])
            self._query(query, {"rows": batch})

    def seed(self, scenario: DemoScenario) -> None:
        """Idempotently merge only the fixed synthetic demo scenario."""
        self._write_batches(
            _UPSERT_SOURCES,
            tuple(
                {
                    "id": record.source_record_id,
                    "family_id": scenario.source_family_id,
                    "source_version": scenario.source_family_id,
                }
                for record in scenario.source_records
            ),
        )
        self._write_batches(_UPSERT_SAMPLES, scenario.sample_rows)
        self._write_batches(
            _UPSERT_DATASETS,
            tuple(
                {
                    "id": manifest.dataset_id,
                    "role": manifest.role,
                    "manifest_hash": manifest.digest,
                    "sample_count": len(manifest.sample_ids),
                    "lineage_complete": manifest.lineage_complete,
                    "source_family_id": scenario.source_family_id,
                    "source_manifest_hash": scenario.source_digest,
                    "source_record_count": len(scenario.source_records),
                }
                for manifest in scenario.manifests
            ),
        )
        self._write_batches(_LINK_SOURCE_RECORDS, scenario.source_link_rows)
        self._write_batches(_LINK_DERIVATIONS, scenario.derivation_rows)
        self._write_batches(_LINK_MEMBERSHIPS, scenario.membership_rows)
        self._write_batches(
            _LINK_EXPERIMENTS,
            tuple(
                {
                    "id": experiment.experiment_id,
                    "training_dataset_id": experiment.training_dataset_id,
                    "evaluation_dataset_id": experiment.evaluation_dataset_id,
                }
                for experiment in scenario.experiments
            ),
        )

    def audit(self, experiment_id: str) -> AuditResult:
        """Return exact shared canonical records and conservative coverage status."""
        try:
            rows = self._query(_GET_EXPERIMENT, {"experiment_id": experiment_id})
            if not rows:
                raise KeyError(experiment_id)
            if len(rows) != 1 or len(rows[0]) != 5:
                raise LineageGraphError(
                    "experiment must resolve to exactly one training/evaluation pair"
                )
            row = rows[0]
            if type(row[2]) is not bool or type(row[4]) is not bool:
                raise LineageGraphError("FalkorDB returned invalid experiment lineage status")
            training_dataset_id = str(row[1])
            training_complete = row[2]
            evaluation_dataset_id = str(row[3])
            evaluation_complete = row[4]
            training_verification = self._verify_dataset_manifest(training_dataset_id)
            evaluation_verification = self._verify_dataset_manifest(evaluation_dataset_id)
            training_manifest_verified = training_verification[0]
            evaluation_manifest_verified = evaluation_verification[0]
            source_artifact_verified = (
                self._verify_source_artifact(training_verification[2:5])
                and training_verification[2:5] == evaluation_verification[2:5]
            )
            training_untraced, training_ambiguous = self._count_invalid_source_resolution(
                training_dataset_id
            )
            evaluation_untraced, evaluation_ambiguous = self._count_invalid_source_resolution(
                evaluation_dataset_id
            )
            training_incomplete = self._count_incomplete_lineage_samples(training_dataset_id)
            evaluation_incomplete = self._count_incomplete_lineage_samples(evaluation_dataset_id)
            raw_evidence = self._query(
                _FIND_OVERLAPS,
                {"experiment_id": experiment_id, "limit": _MAX_EVIDENCE_PATHS + 1},
            )
        except KeyError:
            raise
        except LineageGraphError:
            raise
        except Exception as exc:
            raise LineageGraphError("FalkorDB returned invalid audit data") from exc

        truncated = len(raw_evidence) > _MAX_EVIDENCE_PATHS
        evidence = tuple(
            AuditEvidence(
                canonical_source_record_id=str(item[0]),
                training_dataset_id=str(item[1]),
                training_sample_id=str(item[2]),
                training_derivation_hops=int(item[3]),
                evaluation_dataset_id=str(item[4]),
                evaluation_sample_id=str(item[5]),
                evaluation_derivation_hops=int(item[6]),
            )
            for item in raw_evidence[:_MAX_EVIDENCE_PATHS]
        )
        coverage_complete = (
            training_complete
            and evaluation_complete
            and training_manifest_verified
            and evaluation_manifest_verified
            and source_artifact_verified
            and training_untraced == 0
            and evaluation_untraced == 0
            and training_ambiguous == 0
            and evaluation_ambiguous == 0
            and training_incomplete == 0
            and evaluation_incomplete == 0
            and not truncated
        )
        if evidence:
            status: Literal["confirmed", "clean_within_recorded_lineage", "unknown"] = "confirmed"
        elif coverage_complete:
            status = "clean_within_recorded_lineage"
        else:
            status = "unknown"
        return AuditResult(
            experiment_id=experiment_id,
            status=status,
            coverage_complete=coverage_complete,
            training_dataset_id=training_dataset_id,
            evaluation_dataset_id=evaluation_dataset_id,
            training_samples_without_source=training_untraced,
            evaluation_samples_without_source=evaluation_untraced,
            training_samples_with_ambiguous_source=training_ambiguous,
            evaluation_samples_with_ambiguous_source=evaluation_ambiguous,
            training_samples_with_incomplete_lineage=training_incomplete,
            evaluation_samples_with_incomplete_lineage=evaluation_incomplete,
            training_manifest_verified=training_manifest_verified,
            evaluation_manifest_verified=evaluation_manifest_verified,
            source_artifact_verified=source_artifact_verified,
            evidence=evidence,
        )

    def list_demo_experiment_ids(self) -> tuple[str, ...]:
        """Discover only the fixed demo experiment family from FalkorDB."""
        rows = self._query(_LIST_DEMO_EXPERIMENT_IDS, {"experiment_ids": list(DEMO_EXPERIMENTS)})
        if len(rows) > 4 or any(len(row) != 1 for row in rows):
            raise LineageGraphError("FalkorDB returned an invalid demo experiment list")
        return tuple(str(row[0]) for row in rows)

    def list_run_summaries(self) -> tuple[ExperimentRunSummary, ...]:
        """Return at most 100 minimal run summaries without reading artifact paths."""
        rows = self._query(_LIST_RUN_SUMMARIES, {"limit": 100})
        if any(len(row) != 8 for row in rows):
            raise LineageGraphError("FalkorDB returned an invalid run summary")
        summaries: list[ExperimentRunSummary] = []
        for row in rows:
            summaries.append(
                ExperimentRunSummary(
                    run_id=str(row[0]),
                    experiment_id=str(row[1]),
                    training_dataset_id=str(row[2]),
                    evaluation_dataset_id=str(row[3]),
                    created_at=str(row[4]),
                    training_sample_count=int(row[5]),
                    evaluation_sample_count=int(row[6]),
                    accuracy=float(row[7]),
                )
            )
        return tuple(summaries)

    def _verify_dataset_manifest(self, dataset_id: str) -> tuple[bool, str, str, str, int, int]:
        rows = self._query(_GET_DATASET_MANIFEST, {"dataset_id": dataset_id})
        if len(rows) != 1 or len(rows[0]) != 9:
            raise LineageGraphError("FalkorDB returned invalid dataset manifest data")
        row = rows[0]
        role = str(row[1])
        if type(row[2]) is not bool:
            raise LineageGraphError("FalkorDB returned invalid dataset lineage status")
        lineage_complete = row[2]
        declared_count = int(row[3])
        graph_digest = str(row[4])
        raw_sample_ids = row[5] or []
        source_family_id = str(row[6])
        source_manifest_hash = str(row[7])
        source_record_count = int(row[8])
        if not isinstance(raw_sample_ids, list):
            raise LineageGraphError("FalkorDB returned invalid dataset memberships")
        sample_ids = tuple(sorted(str(sample_id) for sample_id in raw_sample_ids))
        calculated_digest = dataset_manifest_digest(dataset_id, role, sample_ids, lineage_complete)
        if declared_count != len(sample_ids) or calculated_digest != graph_digest:
            return (
                False,
                role,
                source_family_id,
                source_manifest_hash,
                source_record_count,
                declared_count,
            )

        scenario_artifact_dir = self._artifact_dir_for_family(source_family_id)
        if scenario_artifact_dir is None:
            return (
                False,
                role,
                source_family_id,
                source_manifest_hash,
                source_record_count,
                declared_count,
            )
        safe_name = dataset_id.removeprefix("dataset:").replace(":", "_")
        manifest_path = scenario_artifact_dir / "manifests" / f"{safe_name}.json"
        try:
            artifact_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact_sample_ids = artifact_manifest["sample_ids"]
            manifest_verified = (
                artifact_manifest["dataset_id"] == dataset_id
                and artifact_manifest["role"] == role
                and type(artifact_manifest["lineage_complete"]) is bool
                and artifact_manifest["lineage_complete"] == lineage_complete
                and isinstance(artifact_sample_ids, list)
                and tuple(sorted(str(sample_id) for sample_id in artifact_sample_ids)) == sample_ids
                and artifact_manifest["manifest_hash"] == graph_digest
                and dataset_manifest_digest(dataset_id, role, artifact_sample_ids, lineage_complete)
                == graph_digest
            )
        except (OSError, ValueError, TypeError, KeyError):
            manifest_verified = False
        return (
            manifest_verified,
            role,
            source_family_id,
            source_manifest_hash,
            source_record_count,
            declared_count,
        )

    def _verify_source_artifact(self, metadata: tuple[str, str, int]) -> bool:
        family_id, expected_digest, expected_count = metadata
        rows = self._query(_GET_SOURCE_RECORDS, {"family_id": family_id})
        if len(rows) != 1 or len(rows[0]) != 2:
            raise LineageGraphError("FalkorDB returned invalid source manifest data")
        graph_count = int(rows[0][0])
        raw_graph_ids = rows[0][1] or []
        if not isinstance(raw_graph_ids, list):
            raise LineageGraphError("FalkorDB returned invalid source record IDs")
        try:
            scenario_artifact_dir = self._artifact_dir_for_family(family_id)
            if scenario_artifact_dir is None:
                return False
            source_lines = (
                (scenario_artifact_dir / "source_records.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
            source_rows = [json.loads(line) for line in source_lines]
            source_ids = [str(source_row["source_record_id"]) for source_row in source_rows]
            artifact_digest = source_records_digest(source_rows)
        except (OSError, ValueError, TypeError, KeyError):
            return False
        graph_ids = sorted(str(source_id) for source_id in raw_graph_ids)
        return (
            graph_count == expected_count == len(source_rows)
            and len(set(source_ids)) == len(source_ids)
            and sorted(source_ids) == graph_ids
            and artifact_digest == expected_digest
        )

    def _artifact_dir_for_family(self, family_id: str) -> Path | None:
        if family_id == "synthetic-classification-v1":
            return self._artifact_dir
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", family_id):
            return None
        return self._artifact_dir / "scenarios" / family_id

    def resolve_dataset(
        self, dataset_id: str, expected_role: Literal["training", "evaluation"]
    ) -> ResolvedDataset:
        """Resolve graph memberships to canonical rows after verifying their artifacts."""
        verification = self._verify_dataset_manifest(dataset_id)
        if not verification[0] or verification[1] != expected_role:
            raise LineageGraphError("dataset manifest or role is not verified")
        if not self._verify_source_artifact(verification[2:5]):
            raise LineageGraphError("source artifact does not match graph lineage")

        rows = self._query(
            _RESOLVE_DATASET_SAMPLES,
            {"dataset_id": dataset_id, "limit": _MAX_DATASET_SAMPLES + 1},
        )
        if len(rows) > _MAX_DATASET_SAMPLES or len(rows) != verification[5]:
            raise LineageGraphError("dataset sample count exceeds the verified manifest")

        resolved: list[ResolvedSample] = []
        seen_sample_ids: set[str] = set()
        for row in rows:
            if len(row) != 2:
                raise LineageGraphError("FalkorDB returned invalid sample lineage data")
            sample_id = str(row[0])
            raw_source_ids = row[1] or []
            if not isinstance(raw_source_ids, list) or len(raw_source_ids) != 1:
                raise LineageGraphError("dataset contains a sample without one canonical source")
            if sample_id in seen_sample_ids:
                raise LineageGraphError("FalkorDB returned duplicate dataset membership")
            seen_sample_ids.add(sample_id)
            resolved.append(ResolvedSample(sample_id, str(raw_source_ids[0])))
        return ResolvedDataset(
            dataset_id=dataset_id,
            role=expected_role,
            source_family_id=verification[2],
            source_manifest_hash=verification[3],
            source_record_count=verification[4],
            samples=tuple(sorted(resolved, key=lambda sample: sample.sample_id)),
        )

    def record_run(self, record: ExperimentRunRecord) -> None:
        """Append a measured run and its exact dataset edges to the graph."""
        params = record.__dict__.copy()
        params["model_config"] = params.pop("model_config_json")
        rows = self._query(_RECORD_RUN, params)
        if rows != [[record.run_id]]:
            raise LineageGraphError("FalkorDB did not persist the experiment run and dataset edges")
        persisted = self.get_run(record.run_id)
        float_fields = {"accuracy", "precision", "recall", "f1"}
        mismatches = [
            name
            for name in record.__dict__
            if (
                not math.isclose(
                    record.__dict__[name], persisted.__dict__[name], rel_tol=1e-12, abs_tol=1e-12
                )
                if name in float_fields
                else record.__dict__[name] != persisted.__dict__[name]
            )
        ]
        if mismatches:
            raise LineageGraphError(
                f"persisted experiment run differs from its measured artifact: {mismatches}"
            )

    def get_run(self, run_id: str) -> ExperimentRunRecord:
        """Read a persisted experiment run through a fixed query template."""
        rows = self._query(_GET_RUN, {"run_id": run_id})
        if not rows:
            raise KeyError(run_id)
        row = rows[0]
        if len(row) != 21:
            raise LineageGraphError("FalkorDB returned invalid experiment run data")
        return ExperimentRunRecord(
            run_id=str(row[0]),
            experiment_id=str(row[1]),
            training_dataset_id=str(row[2]),
            evaluation_dataset_id=str(row[3]),
            model_id=str(row[4]),
            model_config_json=str(row[5]),
            created_at=str(row[6]),
            python_version=str(row[7]),
            training_sample_count=int(row[8]),
            evaluation_sample_count=int(row[9]),
            accuracy=float(row[10]),
            precision=float(row[11]),
            recall=float(row[12]),
            f1=float(row[13]),
            true_positive=int(row[14]),
            false_positive=int(row[15]),
            true_negative=int(row[16]),
            false_negative=int(row[17]),
            prediction_sha256=str(row[18]),
            manifest_sha256=str(row[19]),
            artifact_path=str(row[20]),
        )

    def list_source_family_runs(self, source_record_id: str) -> list[RunCandidate]:
        """List bounded candidates from both the family index and exact lineage."""
        source_rows = self._query(_GET_SOURCE_FAMILY, {"source_record_id": source_record_id})
        if not source_rows:
            raise KeyError(source_record_id)
        if len(source_rows) != 1 or len(source_rows[0]) != 1:
            raise LineageGraphError("FalkorDB returned invalid source family data")
        source_family_id = source_rows[0][0]
        if not isinstance(source_family_id, str) or not source_family_id:
            raise LineageGraphError("FalkorDB source record has no verified family identifier")
        family_params = {
            "source_family_id": source_family_id,
            "limit": _MAX_IMPACT_RUNS + 1,
        }
        lineage_params = {
            "source_record_id": source_record_id,
            "limit": _MAX_IMPACT_RUNS + 1,
        }
        family_rows = self._query(
            _GET_SOURCE_FAMILY_RUNS,
            family_params,
        )
        lineage_rows = self._query(_GET_SOURCE_LINEAGE_RUNS, lineage_params)
        if len(family_rows) > _MAX_IMPACT_RUNS or len(lineage_rows) > _MAX_IMPACT_RUNS:
            raise ImpactScopeExceeded(
                f"source family exceeds the {_MAX_IMPACT_RUNS}-run impact limit"
            )
        candidates_by_key: dict[tuple[str, str, str, str], RunCandidate] = {}
        for row in [*family_rows, *lineage_rows]:
            if len(row) != 4:
                raise LineageGraphError("FalkorDB returned invalid impact candidate data")
            candidate = RunCandidate(
                run_id=str(row[0]),
                experiment_id=str(row[1]),
                training_dataset_id=str(row[2]),
                evaluation_dataset_id=str(row[3]),
            )
            key = (
                candidate.run_id,
                candidate.experiment_id,
                candidate.training_dataset_id,
                candidate.evaluation_dataset_id,
            )
            candidates_by_key[key] = candidate
        if len(candidates_by_key) > _MAX_IMPACT_RUNS:
            raise ImpactScopeExceeded(
                f"source family exceeds the {_MAX_IMPACT_RUNS}-run impact limit"
            )
        return [candidates_by_key[key] for key in sorted(candidates_by_key)]

    def materialize_run_claims(
        self, run: ExperimentRunRecord
    ) -> tuple[str, str, tuple[MetricClaimRecord, ...]]:
        """Project persisted measured run values into typed graph claim nodes."""
        config_digest = hashlib.sha256(
            f"{run.model_id}\0{run.model_config_json}".encode()
        ).hexdigest()
        model_configuration_id = f"model-configuration:{config_digest}"
        evaluation_claim_id = f"evaluation-claim:{run.run_id}"
        values = (
            ("accuracy", run.accuracy),
            ("precision", run.precision),
            ("recall", run.recall),
            ("f1", run.f1),
        )
        metrics = tuple(
            MetricClaimRecord(claim_id=f"metric-claim:{run.run_id}:{name}", name=name, value=value)
            for name, value in values
        )
        rows = self._query(
            _MATERIALIZE_RUN_CLAIMS,
            {
                "run_id": run.run_id,
                "model_configuration_id": model_configuration_id,
                "model_id": run.model_id,
                "model_config_json": run.model_config_json,
                "evaluation_claim_id": evaluation_claim_id,
                "metrics": [
                    {"id": metric.claim_id, "name": metric.name, "value": metric.value}
                    for metric in metrics
                ],
            },
        )
        if rows != [[len(metrics)]]:
            raise LineageGraphError("FalkorDB did not persist the run's measured claims")
        return model_configuration_id, evaluation_claim_id, metrics

    def record_impact_investigation(self, investigation: ImpactInvestigationRecord) -> None:
        """Append a finding, exact evidence paths and run-claim impact edges."""
        finding_id = f"finding:{investigation.investigation_id}"
        try:
            rows = self._query(
                _RECORD_INVESTIGATION,
                {
                    "investigation_id": investigation.investigation_id,
                    "finding_id": finding_id,
                    "source_record_id": investigation.source_record_id,
                    "created_at": investigation.created_at,
                },
            )
            if rows != [[finding_id]]:
                raise LineageGraphError("FalkorDB did not create the investigation record")

            claim_ids = sorted({run.evaluation_claim_id for run in investigation.impacted_runs})
            if claim_ids:
                link_rows = self._query(
                    _LINK_FINDING_IMPACTS, {"finding_id": finding_id, "claim_ids": claim_ids}
                )
                if link_rows != [[len(claim_ids)]]:
                    raise LineageGraphError("FalkorDB did not link all impacted evaluation claims")

            evidence_rows: list[dict[str, Any]] = []
            for impacted_run in investigation.impacted_runs:
                for evidence in impacted_run.evidence:
                    evidence_key = (
                        f"{investigation.investigation_id}\0{evidence.run_id}"
                        f"\0{evidence.canonical_source_record_id}\0{evidence.training_sample_id}"
                        f"\0{evidence.evaluation_sample_id}"
                    )
                    evidence_rows.append(
                        {
                            "id": f"evidence:{hashlib.sha256(evidence_key.encode()).hexdigest()}",
                            "run_id": evidence.run_id,
                            "source_record_id": evidence.canonical_source_record_id,
                            "training_dataset_id": evidence.training_dataset_id,
                            "training_sample_id": evidence.training_sample_id,
                            "training_derivation_hops": evidence.training_derivation_hops,
                            "evaluation_dataset_id": evidence.evaluation_dataset_id,
                            "evaluation_sample_id": evidence.evaluation_sample_id,
                            "evaluation_derivation_hops": evidence.evaluation_derivation_hops,
                            "evaluation_claim_id": impacted_run.evaluation_claim_id,
                        }
                    )
            for offset in range(0, len(evidence_rows), _WRITE_BATCH_SIZE):
                batch = evidence_rows[offset : offset + _WRITE_BATCH_SIZE]
                evidence_result = self._query(
                    _RECORD_EVIDENCE_PATHS, {"finding_id": finding_id, "rows": batch}
                )
                if evidence_result != [[len(batch)]]:
                    raise LineageGraphError("FalkorDB did not persist all impact evidence paths")

            finalized = self._query(
                _FINALIZE_INVESTIGATION,
                {
                    "investigation_id": investigation.investigation_id,
                    "finding_id": finding_id,
                    "status": investigation.finding_status,
                    "coverage_complete": investigation.coverage_complete,
                    "unresolved_run_ids": list(investigation.unresolved_run_ids),
                },
            )
            if finalized != [[finding_id]]:
                raise LineageGraphError("FalkorDB did not finalize the investigation")
        except Exception:
            try:
                self._query(
                    _DELETE_PARTIAL_INVESTIGATION,
                    {"investigation_id": investigation.investigation_id},
                )
            except LineageGraphError:
                _LOGGER.exception(
                    "Failed to clean up partial impact investigation %s",
                    investigation.investigation_id,
                )
            raise

    def get_investigation(self, investigation_id: str) -> ImpactInvestigationRecord:
        """Read a persisted bounded impact report and its derived quarantine state."""
        header_rows = self._query(_GET_INVESTIGATION, {"investigation_id": investigation_id})
        if not header_rows:
            raise KeyError(investigation_id)
        if len(header_rows) != 1 or len(header_rows[0]) != 7:
            raise LineageGraphError("FalkorDB returned invalid investigation data")
        header = header_rows[0]
        metric_rows = self._query(
            _GET_IMPACT_METRICS,
            {"investigation_id": investigation_id, "limit": _MAX_IMPACT_ROWS + 1},
        )
        if len(metric_rows) > _MAX_IMPACT_ROWS:
            raise LineageGraphError("impact report exceeds the configured result limit")
        evidence_rows = self._query(
            _GET_IMPACT_EVIDENCE,
            {"investigation_id": investigation_id, "limit": _MAX_IMPACT_ROWS + 1},
        )
        if len(evidence_rows) > _MAX_IMPACT_ROWS:
            raise LineageGraphError("impact evidence exceeds the configured result limit")
        quarantined_rows = self._query(
            _GET_QUARANTINED_CLAIMS,
            {"investigation_id": investigation_id, "limit": _MAX_IMPACT_ROWS + 1},
        )
        if len(quarantined_rows) > _MAX_IMPACT_ROWS:
            raise LineageGraphError("quarantine target set exceeds the configured result limit")
        quarantined_claim_ids: set[str] = set()
        for row in quarantined_rows:
            if len(row) != 1:
                raise LineageGraphError("FalkorDB returned invalid quarantine target data")
            if row[0] is not None:
                quarantined_claim_ids.add(str(row[0]))

        runs: dict[str, dict[str, Any]] = {}
        for row in metric_rows:
            if len(row) != 10:
                raise LineageGraphError("FalkorDB returned invalid metric claim data")
            run_id = str(row[0])
            run_data = runs.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "experiment_id": str(row[1]),
                    "training_dataset_id": str(row[2]),
                    "evaluation_dataset_id": str(row[3]),
                    "model_id": str(row[4]),
                    "model_configuration_id": str(row[5]),
                    "evaluation_claim_id": str(row[6]),
                    "metrics": {},
                    "evidence": [],
                },
            )
            run_data["metrics"][str(row[8])] = MetricClaimRecord(
                claim_id=str(row[7]), name=str(row[8]), value=float(row[9])
            )

        for row in evidence_rows:
            if len(row) != 8:
                raise LineageGraphError("FalkorDB returned invalid impact evidence data")
            run_id = str(row[0])
            evidence_run = runs.get(run_id)
            if evidence_run is None:
                continue
            evidence_run["evidence"].append(
                ImpactEvidenceRecord(
                    run_id=run_id,
                    canonical_source_record_id=str(row[1]),
                    training_dataset_id=str(row[2]),
                    training_sample_id=str(row[3]),
                    training_derivation_hops=int(row[4]),
                    evaluation_dataset_id=str(row[5]),
                    evaluation_sample_id=str(row[6]),
                    evaluation_derivation_hops=int(row[7]),
                )
            )

        impacted_runs = tuple(
            ImpactedRunRecord(
                run_id=run_data["run_id"],
                experiment_id=run_data["experiment_id"],
                training_dataset_id=run_data["training_dataset_id"],
                evaluation_dataset_id=run_data["evaluation_dataset_id"],
                model_id=run_data["model_id"],
                model_configuration_id=run_data["model_configuration_id"],
                evaluation_claim_id=run_data["evaluation_claim_id"],
                metrics=tuple(sorted(run_data["metrics"].values(), key=lambda metric: metric.name)),
                evidence=tuple(run_data["evidence"]),
                integrity_status=(
                    "quarantined"
                    if run_data["evaluation_claim_id"] in quarantined_claim_ids
                    else "suspect"
                ),
            )
            for run_data in sorted(runs.values(), key=lambda item: item["run_id"])
        )
        raw_unresolved = header[6] or []
        if not isinstance(raw_unresolved, list):
            raise LineageGraphError("FalkorDB returned invalid unresolved run references")
        return ImpactInvestigationRecord(
            investigation_id=str(header[0]),
            source_record_id=str(header[1]),
            created_at=str(header[2]),
            finding_status=str(header[4]),  # type: ignore[arg-type]
            coverage_complete=bool(header[5]),
            unresolved_run_ids=tuple(sorted(str(item) for item in raw_unresolved)),
            impacted_runs=impacted_runs,
        )

    def propose_quarantine(self, investigation_id: str, reason: str) -> QuarantineActionRecord:
        """Record an unapproved proposal targeting only confirmed impacted claims."""
        investigation = self.get_investigation(investigation_id)
        if investigation.finding_status != "confirmed" or not investigation.coverage_complete:
            raise ActionNotAllowed("quarantine requires a confirmed finding with complete scope")
        action_id = f"action:quarantine:{investigation_id}"
        rows = self._query(
            _CREATE_QUARANTINE_PROPOSAL,
            {
                "investigation_id": investigation_id,
                "action_id": action_id,
                "reason": reason,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        if not rows:
            raise ActionNotAllowed("investigation has no eligible evaluation claims to quarantine")
        if len(rows) != 1 or len(rows[0]) != 2:
            raise LineageGraphError("FalkorDB returned invalid quarantine proposal data")
        return self.get_quarantine_action(action_id)

    def approve_quarantine(
        self, action_id: str, approver: str, reason: str
    ) -> QuarantineActionRecord:
        """Append an explicit approval decision without editing original claims."""
        action = self.get_quarantine_action(action_id)
        if action.status == "approved":
            return action
        investigation = self.get_investigation(action.investigation_id)
        if investigation.finding_status != "confirmed" or not investigation.coverage_complete:
            raise ActionNotAllowed("approval requires a confirmed finding with complete scope")
        approval_id = f"approval:{action_id}"
        rows = self._query(
            _APPROVE_QUARANTINE,
            {
                "action_id": action_id,
                "approval_id": approval_id,
                "approver": approver,
                "reason": reason,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        if rows != [[approval_id]]:
            raise ActionNotAllowed("quarantine proposal is missing or no longer eligible")
        return self.get_quarantine_action(action_id)

    def get_quarantine_action(self, action_id: str) -> QuarantineActionRecord:
        rows = self._query(_GET_ACTION, {"action_id": action_id})
        if not rows:
            raise KeyError(action_id)
        if len(rows) != 1 or len(rows[0]) != 10:
            raise LineageGraphError("FalkorDB returned invalid quarantine action data")
        row = rows[0]

        def first_string(values: Any) -> str | None:
            if isinstance(values, list):
                for value in values:
                    if value is not None:
                        return str(value)
            return None

        raw_targets = row[5] or []
        if not isinstance(raw_targets, list):
            raise LineageGraphError("FalkorDB returned invalid quarantine targets")
        approval_id = first_string(row[6])
        return QuarantineActionRecord(
            action_id=str(row[0]),
            investigation_id=str(row[1]),
            status="approved" if approval_id else "proposed",
            reason=str(row[3]),
            created_at=str(row[4]),
            target_claim_ids=tuple(sorted(str(item) for item in raw_targets if item is not None)),
            approval_id=approval_id,
            approver=first_string(row[7]),
            approval_reason=first_string(row[8]),
            approved_at=first_string(row[9]),
        )

    def propose_repair(self, investigation_id: str, reason: str) -> QuarantineActionRecord:
        investigation = self.get_investigation(investigation_id)
        if investigation.finding_status != "confirmed" or not investigation.coverage_complete:
            raise ActionNotAllowed("repair requires confirmed evidence and complete scope")
        action_id = f"action:repair:{investigation_id}"
        rows = self._query(
            _PROPOSE_REPAIR,
            {
                "investigation_id": investigation_id,
                "action_id": action_id,
                "reason": reason,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1]:
            raise ActionNotAllowed("investigation has no eligible claims to repair")
        return self.get_repair_action(action_id)

    def get_repair_action(self, action_id: str) -> QuarantineActionRecord:
        rows = self._query(_GET_ACTION, {"action_id": action_id})
        if len(rows) != 1 or len(rows[0]) != 10 or rows[0][2] != "repair":
            raise KeyError(action_id)
        row = rows[0]

        def first(values: Any) -> str | None:
            return next((str(value) for value in values if value is not None), None)

        approval_id = first(row[6] or [])
        return QuarantineActionRecord(
            action_id=str(row[0]),
            investigation_id=str(row[1]),
            status="approved" if approval_id else "proposed",
            reason=str(row[3]),
            created_at=str(row[4]),
            target_claim_ids=tuple(sorted(str(value) for value in row[5] if value is not None)),
            approval_id=approval_id,
            approver=first(row[7] or []),
            approval_reason=first(row[8] or []),
            approved_at=first(row[9] or []),
        )

    def approve_repair(self, action_id: str, approver: str, reason: str) -> QuarantineActionRecord:
        action = self.get_repair_action(action_id)
        if action.status == "approved":
            return action
        investigation = self.get_investigation(action.investigation_id)
        if investigation.finding_status != "confirmed" or not investigation.coverage_complete:
            raise ActionNotAllowed("repair approval requires complete confirmed evidence")
        approval_id = f"approval:{action_id}"
        rows = self._query(
            _APPROVE_REPAIR,
            {
                "action_id": action_id,
                "approval_id": approval_id,
                "approver": approver,
                "reason": reason,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        if rows != [[approval_id]]:
            raise ActionNotAllowed("repair proposal is missing or no longer eligible")
        return self.get_repair_action(action_id)

    def create_recovery_job(
        self, action_id: str, original_run_ids: tuple[str, ...]
    ) -> RecoveryJobRecord:
        action = self.get_repair_action(action_id)
        if action.status != "approved" or not original_run_ids:
            raise ActionNotAllowed("repair job requires approval and measured impacted runs")
        job_id = f"job:repair:{action_id}"
        rows = self._query(
            _CREATE_RECOVERY_JOB,
            {
                "action_id": action_id,
                "job_id": job_id,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "original_run_ids": list(original_run_ids),
            },
        )
        if rows != [[job_id]]:
            raise LineageGraphError("FalkorDB did not persist the recovery job")
        return self.get_recovery_job(job_id)

    def get_recovery_job(self, job_id: str) -> RecoveryJobRecord:
        rows = self._query(_GET_RECOVERY_JOB, {"job_id": job_id})
        if not rows:
            raise KeyError(job_id)
        if len(rows) != 1 or len(rows[0]) != 9:
            raise LineageGraphError("FalkorDB returned invalid recovery job data")
        row = rows[0]
        return RecoveryJobRecord(
            job_id=str(row[0]),
            action_id=str(row[1]),
            status=str(row[2]),  # type: ignore[arg-type]
            created_at=str(row[3]),
            started_at=str(row[4]) if row[4] else None,
            finished_at=str(row[5]) if row[5] else None,
            error=str(row[6]) if row[6] else None,
            original_run_ids=tuple(str(value) for value in (row[7] or [])),
            repaired_run_ids=tuple(str(value) for value in (row[8] or [])),
        )

    def transition_recovery_job(
        self,
        job_id: str,
        expected: str,
        status: str,
        *,
        error: str | None = None,
        repaired_run_ids: tuple[str, ...] | None = None,
    ) -> bool:
        allowed_transitions = {
            ("pending_enqueue", "queued"),
            ("queued", "running"),
            ("queued", "failed"),
            ("running", "failed"),
            ("running", "succeeded"),
            ("failed", "queued"),
        }
        if (expected, status) not in allowed_transitions:
            return False
        current = self.get_recovery_job(job_id)
        now = datetime.now(UTC).isoformat(timespec="milliseconds")
        retained_run_ids = list(current.repaired_run_ids)
        retained_run_ids.extend(repaired_run_ids or ())
        rows = self._query(
            _SET_RECOVERY_JOB_STATUS,
            {
                "job_id": job_id,
                "expected_status": expected,
                "status": status,
                "started_at": now
                if status == "running"
                else None
                if status == "queued"
                else current.started_at,
                "finished_at": now if status in ("succeeded", "failed") else None,
                "error": error if status == "failed" else None,
                "repaired_run_ids": list(dict.fromkeys(retained_run_ids)),
            },
        )
        return rows == [[job_id]]

    def fail_stale_recovery_job(self, job_id: str, started_at: str) -> bool:
        """Fail a timed-out running attempt only if its start timestamp is unchanged."""
        rows = self._query(
            _FAIL_STALE_RECOVERY_JOB,
            {
                "job_id": job_id,
                "expected_started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        return rows == [[job_id]]

    def link_recovery_run(
        self,
        job_id: str,
        original_run_id: str,
        repaired_run_id: str,
        model_artifact_path: str,
        model_sha256: str,
    ) -> None:
        rows = self._query(
            _LINK_RECOVERY_RUN,
            {
                "job_id": job_id,
                "original_run_id": original_run_id,
                "repaired_run_id": repaired_run_id,
                "model_version_id": f"model-version:{repaired_run_id}",
                "model_artifact_path": model_artifact_path,
                "model_sha256": model_sha256,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        if rows != [[repaired_run_id]]:
            raise LineageGraphError("FalkorDB did not link the recovery run and model version")

    def create_recovery_experiment(
        self,
        job_id: str,
        original_run_id: str,
        experiment_id: str,
        training_dataset_id: str,
        evaluation_dataset_id: str,
    ) -> None:
        rows = self._query(
            _CREATE_RECOVERY_EXPERIMENT,
            {
                "job_id": job_id,
                "original_run_id": original_run_id,
                "experiment_id": experiment_id,
                "training_dataset_id": training_dataset_id,
                "evaluation_dataset_id": evaluation_dataset_id,
            },
        )
        if rows != [[experiment_id]]:
            raise LineageGraphError("FalkorDB did not persist the recovery experiment")

    def create_agent_session(self, session_id: str) -> AgentSessionRecord:
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds")
        rows = self._query(
            _CREATE_AGENT_SESSION, {"session_id": session_id, "created_at": created_at}
        )
        if rows != [[session_id, created_at]]:
            raise LineageGraphError("FalkorDB did not create the agent session")
        return AgentSessionRecord(session_id, created_at)

    def get_agent_session(self, session_id: str) -> AgentSessionRecord:
        rows = self._query(_GET_AGENT_SESSION, {"session_id": session_id})
        if not rows:
            raise KeyError(session_id)
        if len(rows) != 1 or len(rows[0]) != 2:
            raise LineageGraphError("FalkorDB returned invalid agent session data")
        return AgentSessionRecord(str(rows[0][0]), str(rows[0][1]))

    def latest_agent_memory(self, source_record_id: str) -> AgentMemoryRecord | None:
        rows = self._query(_GET_LATEST_AGENT_MEMORY, {"source_record_id": source_record_id})
        if not rows:
            return None
        if len(rows) != 1 or len(rows[0]) != 5:
            raise LineageGraphError("FalkorDB returned invalid agent memory data")
        row = rows[0]
        return AgentMemoryRecord(*(str(value) for value in row))

    def record_agent_memory(
        self,
        session_id: str,
        investigation_id: str,
        source_record_id: str,
        fingerprint: str,
    ) -> AgentMemoryRecord:
        memory_id = f"agent-memory:{investigation_id}"
        rows = self._query(
            _RECORD_AGENT_MEMORY,
            {
                "session_id": session_id,
                "investigation_id": investigation_id,
                "source_record_id": source_record_id,
                "memory_id": memory_id,
                "fingerprint": fingerprint,
                "created_at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            },
        )
        if rows != [[memory_id]]:
            raise LineageGraphError("FalkorDB did not record verified agent memory")
        memory = self.latest_agent_memory(source_record_id)
        if memory is None or memory.memory_id != memory_id:
            raise LineageGraphError("FalkorDB did not return the recorded agent memory")
        return memory

    def recall_agent_memory(self, session_id: str, memory_id: str) -> None:
        rows = self._query(
            _RECALL_AGENT_MEMORY,
            {
                "session_id": session_id,
                "memory_id": memory_id,
            },
        )
        if rows != [[memory_id]]:
            raise LineageGraphError("FalkorDB did not link recalled memory to the session")

    def _count_invalid_source_resolution(self, dataset_id: str) -> tuple[int, int]:
        rows = self._query(_COUNT_INVALID_SOURCE_RESOLUTION, {"dataset_id": dataset_id})
        if len(rows) != 1 or len(rows[0]) != 2:
            raise LineageGraphError("FalkorDB returned invalid lineage coverage data")
        return int(rows[0][0] or 0), int(rows[0][1] or 0)

    def _count_incomplete_lineage_samples(self, dataset_id: str) -> int:
        rows = self._query(_COUNT_INCOMPLETE_LINEAGE_SAMPLES, {"dataset_id": dataset_id})
        if len(rows) != 1 or len(rows[0]) != 1:
            raise LineageGraphError("FalkorDB returned invalid lineage completeness data")
        return int(rows[0][0] or 0)
