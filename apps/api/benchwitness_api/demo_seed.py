"""Orchestrate the deterministic demo seed and write reproducible local artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from benchwitness_api.lineage import (
    CLEAN_TRAINING_DATASET_ID,
    EVALUATION_DATASET_ID,
    DemoScenario,
    build_demo_scenario,
)


class LineageSeeder(Protocol):
    def seed(self, scenario: DemoScenario) -> None: ...


class DemoSeedService:
    def __init__(self, graph: LineageSeeder, artifact_dir: Path) -> None:
        self._graph = graph
        self._artifact_dir = artifact_dir

    def seed(self) -> dict[str, Any]:
        scenario = build_demo_scenario()
        scenario_artifact_dir = self._scenario_artifact_dir(scenario.source_family_id)
        self._write_artifacts(scenario, scenario_artifact_dir)
        self._graph.seed(scenario)
        return {
            "source_records_processed": len(scenario.source_records),
            "sample_versions_processed": len(scenario.sample_rows),
            "dataset_versions": [manifest.dataset_id for manifest in scenario.manifests],
            "experiments": [experiment.experiment_id for experiment in scenario.experiments],
            "source_manifest_hash": scenario.source_digest,
            "split_manifest_hash": scenario.split_digest,
            "artifact_directory": str(scenario_artifact_dir),
        }

    def _write_artifacts(self, scenario: DemoScenario, artifact_dir: Path) -> None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        source_path = artifact_dir / "source_records.jsonl"
        source_lines = [
            json.dumps(
                {
                    "source_record_id": record.source_record_id,
                    "features": list(record.features),
                    "label": record.label,
                },
                sort_keys=True,
            )
            for record in scenario.source_records
        ]
        self._write_atomic(source_path, "\n".join(source_lines) + "\n")

        # The canonical split is reconstructed from the two direct memberships below;
        # sample-version IDs deliberately remain distinct from source-record IDs.
        source_sample_to_id = {
            row["sample_id"]: row["source_record_id"] for row in scenario.source_link_rows
        }
        evaluation_manifest = next(
            manifest
            for manifest in scenario.manifests
            if manifest.dataset_id == EVALUATION_DATASET_ID
        )
        training_manifest = next(
            manifest
            for manifest in scenario.manifests
            if manifest.dataset_id == CLEAN_TRAINING_DATASET_ID
        )
        split = {
            "schema_version": "2",
            "generator": scenario.generator_version,
            "source_family_id": scenario.source_family_id,
            "seed": 20261015,
            "source_record_count": len(scenario.source_records),
            "source_manifest_hash": scenario.source_digest,
            "split_manifest_hash": scenario.split_digest,
            "label_generation": "seeded independent binary labels; features carry no label signal",
            "leakage_policy": "copy 20% of held-out source rows into each contaminated training set",
            "leaked_source_record_ids": list(scenario.leaked_source_record_ids),
            "train_source_record_ids": sorted(
                source_sample_to_id[sample_id] for sample_id in training_manifest.sample_ids
            ),
            "eval_source_record_ids": sorted(
                source_sample_to_id[sample_id] for sample_id in evaluation_manifest.sample_ids
            ),
        }
        self._write_atomic(
            artifact_dir / "split_manifest.json",
            json.dumps(split, indent=2, sort_keys=True) + "\n",
        )

        manifest_dir = artifact_dir / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        for manifest in scenario.manifests:
            safe_name = manifest.dataset_id.removeprefix("dataset:").replace(":", "_")
            payload = {
                "dataset_id": manifest.dataset_id,
                "role": manifest.role,
                "sample_ids": list(manifest.sample_ids),
                "lineage_complete": manifest.lineage_complete,
                "manifest_hash": manifest.digest,
            }
            self._write_atomic(
                manifest_dir / f"{safe_name}.json",
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
            )

    def _scenario_artifact_dir(self, source_family_id: str) -> Path:
        # Keep the prior v1 fixture available for old graph records and run artifacts.
        if source_family_id == "synthetic-classification-v1":
            return self._artifact_dir
        return self._artifact_dir / "scenarios" / source_family_id

    @staticmethod
    def _write_atomic(path: Path, contents: str) -> None:
        if path.exists():
            if path.read_text(encoding="utf-8") != contents:
                raise ValueError(
                    f"immutable scenario artifact changed at {path}; create a new scenario version"
                )
            return
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_text(contents, encoding="utf-8")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def artifact_directory_from_env() -> Path:
    return Path(os.environ.get("BENCHWITNESS_ARTIFACT_DIR", "artifacts/demo"))
