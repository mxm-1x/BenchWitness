"""Allowlisted, bounded FalkorDB writes and exact lineage audit queries."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from falkordb import FalkorDB  # type: ignore[import-untyped]

from benchwitness_api.lineage import (
    DemoScenario,
    dataset_manifest_digest,
    source_records_digest,
)
from benchwitness_api.settings import GraphSettings

_QUERY_TIMEOUT_MS = 5_000
_WRITE_BATCH_SIZE = 200
_MAX_EVIDENCE_PATHS = 100

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
LIMIT 1
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
_COUNT_UNTRACED_SAMPLES = """
MATCH (dataset:DatasetVersion {id: $dataset_id})
OPTIONAL MATCH (dataset)-[:CONTAINS]->(sample:SampleVersion)
OPTIONAL MATCH (sample)-[:DERIVED_FROM*1..3]->(source:SourceRecord)
WITH sample, count(DISTINCT source) AS source_count
WHERE sample IS NOT NULL AND source_count = 0
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


class LineageGraphError(RuntimeError):
    """A fixed graph operation failed or returned an invalid result."""


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
    training_manifest_verified: bool
    evaluation_manifest_verified: bool
    source_artifact_verified: bool
    evidence: tuple[AuditEvidence, ...]


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
                    "family_id": "synthetic-classification-v1",
                    "source_version": "v1",
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
                    "source_family_id": "synthetic-classification-v1",
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
            row = rows[0]
            training_dataset_id = str(row[1])
            training_complete = bool(row[2])
            evaluation_dataset_id = str(row[3])
            evaluation_complete = bool(row[4])
            training_verification = self._verify_dataset_manifest(training_dataset_id)
            evaluation_verification = self._verify_dataset_manifest(evaluation_dataset_id)
            training_manifest_verified = training_verification[0]
            evaluation_manifest_verified = evaluation_verification[0]
            source_artifact_verified = (
                self._verify_source_artifact(training_verification[1:])
                and training_verification[1:] == evaluation_verification[1:]
            )
            training_untraced = self._count_untraced(training_dataset_id)
            evaluation_untraced = self._count_untraced(evaluation_dataset_id)
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
            training_manifest_verified=training_manifest_verified,
            evaluation_manifest_verified=evaluation_manifest_verified,
            source_artifact_verified=source_artifact_verified,
            evidence=evidence,
        )

    def _verify_dataset_manifest(self, dataset_id: str) -> tuple[bool, str, str, int]:
        rows = self._query(_GET_DATASET_MANIFEST, {"dataset_id": dataset_id})
        if len(rows) != 1 or len(rows[0]) != 9:
            raise LineageGraphError("FalkorDB returned invalid dataset manifest data")
        row = rows[0]
        role = str(row[1])
        lineage_complete = bool(row[2])
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
            return False, source_family_id, source_manifest_hash, source_record_count

        safe_name = dataset_id.removeprefix("dataset:").replace(":", "_")
        manifest_path = self._artifact_dir / "manifests" / f"{safe_name}.json"
        try:
            artifact_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifact_sample_ids = artifact_manifest["sample_ids"]
            manifest_verified = (
                artifact_manifest["dataset_id"] == dataset_id
                and artifact_manifest["role"] == role
                and bool(artifact_manifest["lineage_complete"]) == lineage_complete
                and isinstance(artifact_sample_ids, list)
                and tuple(sorted(str(sample_id) for sample_id in artifact_sample_ids)) == sample_ids
                and artifact_manifest["manifest_hash"] == graph_digest
                and dataset_manifest_digest(dataset_id, role, artifact_sample_ids, lineage_complete)
                == graph_digest
            )
        except (OSError, ValueError, TypeError, KeyError):
            manifest_verified = False
        return manifest_verified, source_family_id, source_manifest_hash, source_record_count

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
            source_lines = (
                (self._artifact_dir / "source_records.jsonl")
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

    def _count_untraced(self, dataset_id: str) -> int:
        rows = self._query(_COUNT_UNTRACED_SAMPLES, {"dataset_id": dataset_id})
        if len(rows) != 1 or len(rows[0]) != 1:
            raise LineageGraphError("FalkorDB returned invalid lineage coverage data")
        return int(rows[0][0])
