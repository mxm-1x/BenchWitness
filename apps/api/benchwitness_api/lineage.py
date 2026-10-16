"""Deterministic synthetic records and immutable dataset lineage manifests."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from typing import Any

SCENARIO_VERSION = "synthetic-memorization-v2"
DEMO_EXPERIMENTS = (
    "demo-v2-contaminated-a",
    "demo-v2-contaminated-b",
    "demo-v2-clean-control",
    "demo-v2-unknown-lineage",
)
EVALUATION_DATASET_ID = f"dataset:{SCENARIO_VERSION}:eval"
CLEAN_TRAINING_DATASET_ID = f"dataset:{SCENARIO_VERSION}:train-clean-control"


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
    source_family_id: str
    generator_version: str
    source_records: tuple[SourceRecord, ...]
    sample_rows: tuple[dict[str, Any], ...]
    source_link_rows: tuple[dict[str, str], ...]
    derivation_rows: tuple[dict[str, str], ...]
    manifests: tuple[DatasetManifest, ...]
    membership_rows: tuple[dict[str, str], ...]
    experiments: tuple[ExperimentLineage, ...]
    source_digest: str
    split_digest: str
    train_source_record_ids: tuple[str, ...]
    eval_source_record_ids: tuple[str, ...]
    leaked_source_record_ids: tuple[str, ...]


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
    """Build the disclosed synthetic memorization probe and exact source lineage."""
    if row_count < 8 or row_count % 2:
        raise ValueError("row_count must be an even integer of at least 8")

    rng = random.Random(seed)
    label_rng = random.Random(seed + 1_000_003)
    records: list[SourceRecord] = []
    for index in range(row_count):
        x1 = round(rng.uniform(-1.0, 1.0), 6)
        x2 = round(rng.uniform(-1.0, 1.0), 6)
        records.append(
            SourceRecord(
                source_record_id=f"source:{SCENARIO_VERSION}:{index:04d}",
                features=(x1, x2),
                # Labels are independent of features. This deliberately tests exact
                # memorization through copied rows, not generalization quality.
                label=label_rng.getrandbits(1),
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
    leak_rng = random.Random(seed + 7_919)
    leaked_ids = tuple(sorted(leak_rng.sample(sorted(eval_ids), round(len(eval_ids) * 0.2))))
    split_data = {
        "train_source_record_ids": sorted(train_ids),
        "eval_source_record_ids": sorted(eval_ids),
        "leaked_source_record_ids": list(leaked_ids),
    }
    split_digest = _digest(split_data)

    sample_rows: list[dict[str, Any]] = []
    source_link_rows: list[dict[str, str]] = []
    derivation_rows: list[dict[str, str]] = []
    source_to_sample: dict[str, str] = {}
    for record in records:
        sample_id = f"sample:{SCENARIO_VERSION}:source:{record.source_record_id.rsplit(':', 1)[1]}"
        source_to_sample[record.source_record_id] = sample_id
        sample_rows.append({"id": sample_id, "kind": "source", "lineage_complete": True})
        source_link_rows.append(
            {"sample_id": sample_id, "source_record_id": record.source_record_id}
        )

    contaminated_sample_ids: dict[str, list[str]] = {}
    for experiment_id in DEMO_EXPERIMENTS[:2]:
        copied_ids: list[str] = []
        for leaked_source_id in leaked_ids:
            copied_sample_id = (
                f"sample:{SCENARIO_VERSION}:copy:{experiment_id}:"
                f"{leaked_source_id.rsplit(':', 1)[1]}"
            )
            copied_ids.append(copied_sample_id)
            sample_rows.append({"id": copied_sample_id, "kind": "copy", "lineage_complete": True})
            derivation_rows.append(
                {
                    "sample_id": copied_sample_id,
                    "parent_sample_id": source_to_sample[leaked_source_id],
                }
            )
        contaminated_sample_ids[experiment_id] = copied_ids

    unknown_sample_id = f"sample:{SCENARIO_VERSION}:unknown"
    sample_rows.append({"id": unknown_sample_id, "kind": "unknown", "lineage_complete": False})

    manifest_specs: list[tuple[str, str, list[str], bool]] = [
        (
            EVALUATION_DATASET_ID,
            "evaluation",
            [source_to_sample[item] for item in sorted(eval_ids)],
            True,
        ),
        (
            f"dataset:{SCENARIO_VERSION}:train-contaminated-a",
            "training",
            [source_to_sample[item] for item in sorted(train_ids)]
            + contaminated_sample_ids["demo-v2-contaminated-a"],
            True,
        ),
        (
            f"dataset:{SCENARIO_VERSION}:train-contaminated-b",
            "training",
            [source_to_sample[item] for item in sorted(train_ids)]
            + contaminated_sample_ids["demo-v2-contaminated-b"],
            True,
        ),
        (
            CLEAN_TRAINING_DATASET_ID,
            "training",
            [source_to_sample[item] for item in sorted(train_ids)],
            True,
        ),
        (
            f"dataset:{SCENARIO_VERSION}:train-unknown-lineage",
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
            DEMO_EXPERIMENTS[0],
            f"dataset:{SCENARIO_VERSION}:train-contaminated-a",
            EVALUATION_DATASET_ID,
        ),
        ExperimentLineage(
            DEMO_EXPERIMENTS[1],
            f"dataset:{SCENARIO_VERSION}:train-contaminated-b",
            EVALUATION_DATASET_ID,
        ),
        ExperimentLineage(DEMO_EXPERIMENTS[2], CLEAN_TRAINING_DATASET_ID, EVALUATION_DATASET_ID),
        ExperimentLineage(
            DEMO_EXPERIMENTS[3],
            f"dataset:{SCENARIO_VERSION}:train-unknown-lineage",
            EVALUATION_DATASET_ID,
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
        source_family_id=SCENARIO_VERSION,
        generator_version="independent-binary-labels-v2",
        source_records=tuple(records),
        sample_rows=tuple(sample_rows),
        source_link_rows=tuple(source_link_rows),
        derivation_rows=tuple(derivation_rows),
        manifests=manifests,
        membership_rows=tuple(membership_rows),
        experiments=experiments,
        source_digest=source_digest,
        split_digest=split_digest,
        train_source_record_ids=tuple(sorted(train_ids)),
        eval_source_record_ids=tuple(sorted(eval_ids)),
        leaked_source_record_ids=leaked_ids,
    )
