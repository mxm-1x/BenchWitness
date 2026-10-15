"""Focused bounds tests for impact discovery side effects."""

from typing import cast

import pytest
from benchwitness_api.graph_lineage import (
    AuditEvidence,
    AuditResult,
    ExperimentRunRecord,
    GraphLineageStore,
    ImpactScopeExceeded,
    MetricClaimRecord,
    RunCandidate,
)
from benchwitness_api.impact import ImpactService


class OversizedImpactGraph:
    def __init__(self) -> None:
        self.candidates = [
            RunCandidate(
                run_id=f"run:{index}",
                experiment_id=f"experiment:{index}",
                training_dataset_id=f"dataset:training:{index}",
                evaluation_dataset_id=f"dataset:evaluation:{index}",
            )
            for index in range(11)
        ]
        self.materialized_run_ids: list[str] = []

    def list_source_family_runs(self, source_record_id: str) -> list[RunCandidate]:
        return self.candidates

    def get_run(self, run_id: str) -> ExperimentRunRecord:
        candidate = next(item for item in self.candidates if item.run_id == run_id)
        return ExperimentRunRecord(
            run_id=run_id,
            experiment_id=candidate.experiment_id,
            training_dataset_id=candidate.training_dataset_id,
            evaluation_dataset_id=candidate.evaluation_dataset_id,
            model_id="demo-model",
            model_config_json="{}",
            created_at="2026-10-15T00:00:00+00:00",
            python_version="3.12.0",
            training_sample_count=200,
            evaluation_sample_count=100,
            accuracy=0.5,
            precision=0.5,
            recall=0.5,
            f1=0.5,
            true_positive=25,
            false_positive=25,
            true_negative=25,
            false_negative=25,
            prediction_sha256="a" * 64,
            manifest_sha256="b" * 64,
            artifact_path="artifacts/runs/test",
        )

    def audit(self, experiment_id: str) -> AuditResult:
        candidate = next(item for item in self.candidates if item.experiment_id == experiment_id)
        evidence = tuple(
            AuditEvidence(
                canonical_source_record_id="source:shared",
                training_dataset_id=candidate.training_dataset_id,
                training_sample_id=f"sample:training:{experiment_id}:{index}",
                training_derivation_hops=1,
                evaluation_dataset_id=candidate.evaluation_dataset_id,
                evaluation_sample_id=f"sample:evaluation:{experiment_id}:{index}",
                evaluation_derivation_hops=1,
            )
            for index in range(100)
        )
        return AuditResult(
            experiment_id=experiment_id,
            status="confirmed",
            coverage_complete=True,
            training_dataset_id=candidate.training_dataset_id,
            evaluation_dataset_id=candidate.evaluation_dataset_id,
            training_samples_without_source=0,
            evaluation_samples_without_source=0,
            training_manifest_verified=True,
            evaluation_manifest_verified=True,
            source_artifact_verified=True,
            evidence=evidence,
        )

    def materialize_run_claims(
        self, run: ExperimentRunRecord
    ) -> tuple[str, str, tuple[MetricClaimRecord, ...]]:
        self.materialized_run_ids.append(run.run_id)
        raise AssertionError("oversized scope must fail before materializing run claims")


def test_impact_path_limit_fails_before_materializing_claims() -> None:
    graph = OversizedImpactGraph()

    with pytest.raises(ImpactScopeExceeded, match="1,000-path"):
        ImpactService(cast(GraphLineageStore, graph)).investigate_source("source:shared")

    assert graph.materialized_run_ids == []
