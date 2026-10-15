"""Orchestrate the deterministic demo seed and write reproducible local artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from benchwitness_api.lineage import DemoScenario, build_demo_scenario


class LineageSeeder(Protocol):
    def seed(self, scenario: DemoScenario) -> None: ...


class DemoSeedService:
    def __init__(self, graph: LineageSeeder, artifact_dir: Path) -> None:
        self._graph = graph
        self._artifact_dir = artifact_dir

    def seed(self) -> dict[str, Any]:
        scenario = build_demo_scenario()
        self._write_artifacts(scenario)
        self._graph.seed(scenario)
        return {
            "source_records_processed": len(scenario.source_records),
            "sample_versions_processed": len(scenario.sample_rows),
            "dataset_versions": [manifest.dataset_id for manifest in scenario.manifests],
            "experiments": [experiment.experiment_id for experiment in scenario.experiments],
            "source_manifest_hash": scenario.source_digest,
            "split_manifest_hash": scenario.split_digest,
            "artifact_directory": str(self._artifact_dir),
        }

    def _write_artifacts(self, scenario: DemoScenario) -> None:
        self._artifact_dir.mkdir(parents=True, exist_ok=True)
        source_path = self._artifact_dir / "source_records.jsonl"
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
            f"sample:source-v1:{record.source_record_id.rsplit(':', 1)[1]}": record.source_record_id
            for record in scenario.source_records
        }
        evaluation_manifest = next(
            manifest for manifest in scenario.manifests if manifest.dataset_id == "dataset:eval-v1"
        )
        training_manifest = next(
            manifest
            for manifest in scenario.manifests
            if manifest.dataset_id == "dataset:train-clean-control-v1"
        )
        split = {
            "schema_version": "1",
            "generator": "benchwitness_api.lineage.build_demo_scenario",
            "seed": 20261015,
            "source_record_count": len(scenario.source_records),
            "source_manifest_hash": scenario.source_digest,
            "split_manifest_hash": scenario.split_digest,
            "train_source_record_ids": sorted(
                source_sample_to_id[sample_id] for sample_id in training_manifest.sample_ids
            ),
            "eval_source_record_ids": sorted(
                source_sample_to_id[sample_id] for sample_id in evaluation_manifest.sample_ids
            ),
        }
        self._write_atomic(
            self._artifact_dir / "split_manifest.json",
            json.dumps(split, indent=2, sort_keys=True) + "\n",
        )

        manifest_dir = self._artifact_dir / "manifests"
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

    @staticmethod
    def _write_atomic(path: Path, contents: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(contents, encoding="utf-8")
        temporary.replace(path)


def artifact_directory_from_env() -> Path:
    return Path(os.environ.get("BENCHWITNESS_ARTIFACT_DIR", "artifacts/demo"))
