"""Bounded, graph-backed impact investigations and approval-gated quarantine."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from benchwitness_api.graph_lineage import (
    ActionNotAllowed,
    AuditEvidence,
    AuditResult,
    ExperimentRunRecord,
    GraphLineageStore,
    ImpactedRunRecord,
    ImpactEvidenceRecord,
    ImpactInvestigationRecord,
    ImpactScopeExceeded,
    QuarantineActionRecord,
)


class ImpactService:
    """Trace exact source overlap into measured run claims and approval records."""

    def __init__(self, graph: GraphLineageStore) -> None:
        self._graph = graph

    def investigate_source(self, source_record_id: str) -> ImpactInvestigationRecord:
        """Persist evidence for every completely verified run in the source family."""
        candidates = self._graph.list_source_family_runs(source_record_id)
        audit_cache: dict[str, AuditResult] = {}
        unresolved: set[str] = set()
        verified_runs: list[tuple[ExperimentRunRecord, tuple[AuditEvidence, ...]]] = []
        evidence_path_count = 0

        for candidate in candidates:
            try:
                run = self._graph.get_run(candidate.run_id)
            except KeyError:
                unresolved.add(candidate.run_id)
                continue
            if (
                run.experiment_id != candidate.experiment_id
                or run.training_dataset_id != candidate.training_dataset_id
                or run.evaluation_dataset_id != candidate.evaluation_dataset_id
            ):
                unresolved.add(candidate.run_id)
                continue

            if candidate.experiment_id not in audit_cache:
                try:
                    audit_cache[candidate.experiment_id] = self._graph.audit(
                        candidate.experiment_id
                    )
                except KeyError:
                    unresolved.add(candidate.run_id)
                    continue
            audit = audit_cache[candidate.experiment_id]
            if (
                audit.training_dataset_id != candidate.training_dataset_id
                or audit.evaluation_dataset_id != candidate.evaluation_dataset_id
                or not audit.coverage_complete
            ):
                unresolved.add(candidate.run_id)
                continue

            source_evidence = tuple(
                evidence
                for evidence in audit.evidence
                if evidence.canonical_source_record_id == source_record_id
            )
            if not source_evidence:
                continue
            if audit.status != "confirmed":
                unresolved.add(candidate.run_id)
                continue
            if evidence_path_count + len(source_evidence) > 1_000:
                raise ImpactScopeExceeded(
                    "source overlap evidence exceeds the 1,000-path investigation limit"
                )
            evidence_path_count += len(source_evidence)
            verified_runs.append((run, source_evidence))

        # Check the full response bound before creating any projected claim nodes.
        impacted_runs: list[ImpactedRunRecord] = []
        for run, source_evidence in verified_runs:
            model_configuration_id, evaluation_claim_id, metrics = (
                self._graph.materialize_run_claims(run)
            )
            impacted_runs.append(
                ImpactedRunRecord(
                    run_id=run.run_id,
                    experiment_id=run.experiment_id,
                    training_dataset_id=run.training_dataset_id,
                    evaluation_dataset_id=run.evaluation_dataset_id,
                    model_id=run.model_id,
                    model_configuration_id=model_configuration_id,
                    evaluation_claim_id=evaluation_claim_id,
                    metrics=metrics,
                    evidence=tuple(
                        self._impact_evidence(run.run_id, item) for item in source_evidence
                    ),
                    integrity_status="suspect",
                )
            )

        coverage_complete = not unresolved
        if impacted_runs:
            status: Literal["confirmed", "clean_within_recorded_lineage", "unknown"] = "confirmed"
        elif coverage_complete:
            status = "clean_within_recorded_lineage"
        else:
            status = "unknown"
        investigation = ImpactInvestigationRecord(
            investigation_id=f"investigation:{uuid4().hex}",
            source_record_id=source_record_id,
            created_at=datetime.now(UTC).isoformat(timespec="milliseconds"),
            finding_status=status,
            coverage_complete=coverage_complete,
            unresolved_run_ids=tuple(sorted(unresolved)),
            impacted_runs=tuple(impacted_runs),
        )
        self._graph.record_impact_investigation(investigation)
        return self._graph.get_investigation(investigation.investigation_id)

    @staticmethod
    def _impact_evidence(run_id: str, evidence: AuditEvidence) -> ImpactEvidenceRecord:
        return ImpactEvidenceRecord(
            run_id=run_id,
            canonical_source_record_id=evidence.canonical_source_record_id,
            training_dataset_id=evidence.training_dataset_id,
            training_sample_id=evidence.training_sample_id,
            training_derivation_hops=evidence.training_derivation_hops,
            evaluation_dataset_id=evidence.evaluation_dataset_id,
            evaluation_sample_id=evidence.evaluation_sample_id,
            evaluation_derivation_hops=evidence.evaluation_derivation_hops,
        )

    def propose_quarantine(self, investigation_id: str, reason: str) -> QuarantineActionRecord:
        """Create a proposal only when the impact scope is confirmed and complete."""
        return self._graph.propose_quarantine(investigation_id, reason)

    def approve_quarantine(
        self, action_id: str, approver: str, reason: str
    ) -> QuarantineActionRecord:
        """Record an explicit approval decision; the underlying claims remain unchanged."""
        return self._graph.approve_quarantine(action_id, approver, reason)

    def get_investigation(self, investigation_id: str) -> ImpactInvestigationRecord:
        return self._graph.get_investigation(investigation_id)


__all__ = ["ActionNotAllowed", "ImpactService"]
