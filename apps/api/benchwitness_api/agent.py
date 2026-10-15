"""Local typed tool router with graph-backed, revalidated investigation memory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal
from uuid import uuid4

from benchwitness_api.graph_lineage import (
    AgentSessionRecord,
    AuditResult,
    GraphLineageStore,
    ImpactInvestigationRecord,
    RecoveryJobRecord,
)
from benchwitness_api.impact import ImpactService

AgentIntent = Literal["investigate_source", "audit_experiment", "get_job_status"]
MemoryStatus = Literal["none", "verified", "stale"]


@dataclass(frozen=True)
class AgentToolResult:
    session_id: str
    intent: AgentIntent
    subject_id: str
    tools_used: tuple[str, ...]
    memory_status: MemoryStatus
    memory_id: str | None
    summary: str
    investigation: ImpactInvestigationRecord | None = None
    audit: AuditResult | None = None
    job: RecoveryJobRecord | None = None


class AgentService:
    """Choose only fixed graph tools; never interpret free text as an approval."""

    def __init__(self, graph: GraphLineageStore) -> None:
        self._graph = graph
        self._impact = ImpactService(graph)

    def start_session(self) -> AgentSessionRecord:
        return self._graph.create_agent_session(f"agent-session:{uuid4().hex}")

    def get_session(self, session_id: str) -> AgentSessionRecord:
        return self._graph.get_agent_session(session_id)

    def dispatch(self, session_id: str, intent: AgentIntent, subject_id: str) -> AgentToolResult:
        self._graph.get_agent_session(session_id)
        if intent == "audit_experiment":
            audit = self._graph.audit(subject_id)
            return AgentToolResult(
                session_id,
                intent,
                subject_id,
                ("audit_experiment",),
                "none",
                None,
                f"Lineage audit: {audit.status}; coverage complete: {audit.coverage_complete}.",
                audit=audit,
            )
        if intent == "get_job_status":
            job = self._graph.get_recovery_job(subject_id)
            return AgentToolResult(
                session_id,
                intent,
                subject_id,
                ("get_job_status",),
                "none",
                None,
                f"Recovery job status: {job.status}.",
                job=job,
            )
        if intent == "investigate_source":
            return self._investigate_source(session_id, subject_id)
        raise ValueError("agent intent is not in the tool allowlist")

    def _investigate_source(self, session_id: str, source_id: str) -> AgentToolResult:
        memory = self._graph.latest_agent_memory(source_id)
        snapshot = self._source_snapshot(source_id)
        if memory is not None and snapshot is not None:
            try:
                recalled = self._graph.get_investigation(memory.investigation_id)
            except KeyError:
                recalled = None
            if (
                recalled is not None
                and recalled.source_record_id == source_id
                and recalled.finding_status == "confirmed"
                and recalled.coverage_complete
                and snapshot[0] == memory.fingerprint
                and self._investigation_evidence_keys(recalled) == snapshot[1]
            ):
                self._graph.recall_agent_memory(session_id, memory.memory_id)
                return AgentToolResult(
                    session_id,
                    "investigate_source",
                    source_id,
                    ("recall_prior_investigations", "revalidate_lineage"),
                    "verified",
                    memory.memory_id,
                    f"Reused verified investigation {recalled.investigation_id}; "
                    f"{len(recalled.impacted_runs)} affected runs.",
                    investigation=recalled,
                )
        investigation = self._impact.investigate_source(source_id)
        new_memory_id: str | None = None
        verified_snapshot = self._source_snapshot(source_id)
        if (
            snapshot is not None
            and verified_snapshot == snapshot
            and investigation.finding_status == "confirmed"
            and investigation.coverage_complete
            and self._investigation_evidence_keys(investigation) == snapshot[1]
        ):
            new_memory_id = self._graph.record_agent_memory(
                session_id, investigation.investigation_id, source_id, snapshot[0]
            ).memory_id
        return AgentToolResult(
            session_id,
            "investigate_source",
            source_id,
            ("recall_prior_investigations", "investigate_source")
            if memory
            else ("investigate_source",),
            "stale" if memory else "none",
            new_memory_id,
            f"New investigation {investigation.investigation_id}: "
            f"{investigation.finding_status}; {len(investigation.impacted_runs)} affected runs.",
            investigation=investigation,
        )

    @staticmethod
    def _investigation_evidence_keys(
        investigation: ImpactInvestigationRecord,
    ) -> tuple[tuple[str, str, str, str], ...]:
        return tuple(
            sorted(
                (
                    run.run_id,
                    evidence.canonical_source_record_id,
                    evidence.training_sample_id,
                    evidence.evaluation_sample_id,
                )
                for run in investigation.impacted_runs
                for evidence in run.evidence
            )
        )

    def _source_snapshot(
        self, source_id: str
    ) -> tuple[str, tuple[tuple[str, str, str, str], ...]] | None:
        """Hash current run/lineage inputs and enumerate exact source evidence paths."""
        candidates = self._graph.list_source_family_runs(source_id)
        current: list[dict[str, object]] = []
        evidence_keys: list[tuple[str, str, str, str]] = []
        audits: dict[str, AuditResult] = {}
        for candidate in candidates:
            try:
                run = self._graph.get_run(candidate.run_id)
                if candidate.experiment_id not in audits:
                    audits[candidate.experiment_id] = self._graph.audit(candidate.experiment_id)
            except KeyError:
                return None
            audit = audits[candidate.experiment_id]
            if (
                run.experiment_id != candidate.experiment_id
                or run.training_dataset_id != candidate.training_dataset_id
                or run.evaluation_dataset_id != candidate.evaluation_dataset_id
                or audit.training_dataset_id != candidate.training_dataset_id
                or audit.evaluation_dataset_id != candidate.evaluation_dataset_id
                or not audit.coverage_complete
            ):
                return None
            source_evidence = tuple(
                item for item in audit.evidence if item.canonical_source_record_id == source_id
            )
            if source_evidence and audit.status != "confirmed":
                return None
            evidence_keys.extend(
                (run.run_id, source_id, item.training_sample_id, item.evaluation_sample_id)
                for item in source_evidence
            )
            current.append(
                {
                    "run_id": run.run_id,
                    "run_manifest_sha256": run.manifest_sha256,
                    "audit_status": audit.status,
                    "training_dataset_id": audit.training_dataset_id,
                    "evaluation_dataset_id": audit.evaluation_dataset_id,
                    "evidence": [asdict(item) for item in source_evidence],
                }
            )
        encoded = json.dumps(current, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest(), tuple(sorted(evidence_keys))
