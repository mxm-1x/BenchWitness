"""Deterministic synthetic records and immutable dataset lineage manifests."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    source_record_id: str
    features: tuple[float, float]
    label: int


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    role: str
    sample_ids: tuple[str, ...]
    lineage_complete: bool
    digest: str


@dataclass(frozen=True)
class ExperimentLineage:
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str


@dataclass(frozen=True)
class DemoScenario:
    source_records: tuple[SourceRecord, ...]
    sample_rows: tuple[dict[str, Any], ...]
    source_link_rows: tuple[dict[str, str], ...]
    derivation_rows: tuple[dict[str, str], ...]
    manifests: tuple[DatasetManifest, ...]
    membership_rows: tuple[dict[str, str], ...]
    experiments: tuple[ExperimentLineage, ...]
    source_digest: str
    split_digest: str


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def dataset_manifest_digest(
    dataset_id: str, role: str, sample_ids: tuple[str, ...] | list[str], lineage_complete: bool
) -> str:
    """Hash the immutable manifest identity and sorted sample membership."""
    return _digest(
        {
            "dataset_id": dataset_id,
            "role": role,
            "sample_ids": sorted(sample_ids),
            "lineage_complete": lineage_complete,
        }
    )


def source_records_digest(source_rows: list[dict[str, Any]]) -> str:
    """Hash canonical source rows in their stable generated order."""
    return _digest(source_rows)


def build_demo_scenario(row_count: int = 400, seed: int = 20261015) -> DemoScenario:
    """Build a repeatable split and source-level lineage fixture without metric claims."""
    if row_count < 8 or row_count % 2:
        raise ValueError("row_count must be an even integer of at least 8")

    rng = random.Random(seed)
    records: list[SourceRecord] = []
    for index in range(row_count):
        x1 = round(rng.uniform(-1.0, 1.0), 6)
        x2 = round(rng.uniform(-1.0, 1.0), 6)
        records.append(
            SourceRecord(
                source_record_id=f"source:synthetic-v1:{index:04d}",
                features=(x1, x2),
                label=int(x1 + x2 >= 0.0),
            )
        )

    # Split each label independently so the fixed 75/25 partition preserves classes.
    eval_ids: list[str] = []
    train_ids: list[str] = []
    for label in (0, 1):
        label_ids = [record.source_record_id for record in records if record.label == label]
        label_rng = random.Random(seed + label + 1)
        label_rng.shuffle(label_ids)
        eval_size = max(1, round(len(label_ids) * 0.25))
        eval_ids.extend(label_ids[:eval_size])
        train_ids.extend(label_ids[eval_size:])

    if not eval_ids or not train_ids:
        raise ValueError("generated data must contain training and evaluation records")

    source_rows = [
        {
            "source_record_id": record.source_record_id,
            "features": list(record.features),
            "label": record.label,
        }
        for record in records
    ]
    source_digest = source_records_digest(source_rows)
    split_data = {
        "train_source_record_ids": sorted(train_ids),
        "eval_source_record_ids": sorted(eval_ids),
    }
    split_digest = _digest(split_data)

    sample_rows: list[dict[str, Any]] = []
    source_link_rows: list[dict[str, str]] = []
    derivation_rows: list[dict[str, str]] = []
    source_to_sample: dict[str, str] = {}
    for record in records:
        sample_id = f"sample:source-v1:{record.source_record_id.rsplit(':', 1)[1]}"
        source_to_sample[record.source_record_id] = sample_id
        sample_rows.append({"id": sample_id, "kind": "source", "lineage_complete": True})
        source_link_rows.append(
            {"sample_id": sample_id, "source_record_id": record.source_record_id}
        )

    leaked_source_id = min(eval_ids)
    contaminated_sample_ids: dict[str, str] = {}
    for experiment_id in ("demo-contaminated-a", "demo-contaminated-b"):
        copied_sample_id = f"sample:copy:{experiment_id}:{leaked_source_id.rsplit(':', 1)[1]}"
        contaminated_sample_ids[experiment_id] = copied_sample_id
        sample_rows.append({"id": copied_sample_id, "kind": "copy", "lineage_complete": True})
        derivation_rows.append(
            {
                "sample_id": copied_sample_id,
                "parent_sample_id": source_to_sample[leaked_source_id],
            }
        )

    unknown_sample_id = "sample:unknown:demo"
    sample_rows.append({"id": unknown_sample_id, "kind": "unknown", "lineage_complete": False})

    manifest_specs: list[tuple[str, str, list[str], bool]] = [
        (
            "dataset:eval-v1",
            "evaluation",
            [source_to_sample[item] for item in sorted(eval_ids)],
            True,
        ),
        (
            "dataset:train-contaminated-a-v1",
            "training",
            [source_to_sample[item] for item in sorted(train_ids)]
            + [contaminated_sample_ids["demo-contaminated-a"]],
            True,
        ),
        (
            "dataset:train-contaminated-b-v1",
            "training",
            [source_to_sample[item] for item in sorted(train_ids)]
            + [contaminated_sample_ids["demo-contaminated-b"]],
            True,
        ),
        (
            "dataset:train-clean-control-v1",
            "training",
            [source_to_sample[item] for item in sorted(train_ids)],
            True,
        ),
        (
            "dataset:train-unknown-lineage-v1",
            "training",
            [source_to_sample[item] for item in sorted(train_ids)] + [unknown_sample_id],
            False,
        ),
    ]
    manifests = tuple(
        DatasetManifest(
            dataset_id=dataset_id,
            role=role,
            sample_ids=tuple(sample_ids),
            lineage_complete=lineage_complete,
            digest=dataset_manifest_digest(dataset_id, role, sample_ids, lineage_complete),
        )
        for dataset_id, role, sample_ids, lineage_complete in manifest_specs
    )
    manifest_by_id = {manifest.dataset_id: manifest for manifest in manifests}
    membership_rows = [
        {"dataset_id": manifest.dataset_id, "sample_id": sample_id}
        for manifest in manifests
        for sample_id in manifest.sample_ids
    ]
    experiments = (
        ExperimentLineage(
            "demo-contaminated-a", "dataset:train-contaminated-a-v1", "dataset:eval-v1"
        ),
        ExperimentLineage(
            "demo-contaminated-b", "dataset:train-contaminated-b-v1", "dataset:eval-v1"
        ),
        ExperimentLineage(
            "demo-clean-control", "dataset:train-clean-control-v1", "dataset:eval-v1"
        ),
        ExperimentLineage(
            "demo-unknown-lineage", "dataset:train-unknown-lineage-v1", "dataset:eval-v1"
        ),
    )
    # Keep the variable referenced so a changed manifest definition cannot silently
    # omit a manifest from the scenario's experiment references.
    if any(
        experiment.training_dataset_id not in manifest_by_id
        or experiment.evaluation_dataset_id not in manifest_by_id
        for experiment in experiments
    ):
        raise ValueError("experiment references an unknown dataset manifest")

    return DemoScenario(
        source_records=tuple(records),
        sample_rows=tuple(sample_rows),
        source_link_rows=tuple(source_link_rows),
        derivation_rows=tuple(derivation_rows),
        manifests=manifests,
        membership_rows=tuple(membership_rows),
        experiments=experiments,
        source_digest=source_digest,
        split_digest=split_digest,
    )
