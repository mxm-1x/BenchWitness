"""Deterministic fixture and artifact contract checks."""

import json
from pathlib import Path

import pytest
from benchwitness_api.demo_seed import DemoSeedService
from benchwitness_api.lineage import DemoScenario, build_demo_scenario


class RecordingGraphStore:
    def __init__(self) -> None:
        self.seeded = False

    def seed(self, scenario: DemoScenario) -> None:
        self.seeded = True


def test_demo_scenario_is_deterministic_and_disjoint_before_injected_copies() -> None:
    first = build_demo_scenario()
    second = build_demo_scenario()

    assert first.source_digest == second.source_digest
    assert first.split_digest == second.split_digest
    assert first.source_records == second.source_records
    train_ids = {
        row["source_record_id"]
        for row in first.source_link_rows
        if row["sample_id"]
        in {
            sample_id
            for manifest in first.manifests
            if manifest.dataset_id == "dataset:synthetic-memorization-v2:train-clean-control"
            for sample_id in manifest.sample_ids
        }
    }
    eval_ids = {
        row["source_record_id"]
        for row in first.source_link_rows
        if row["sample_id"]
        in {
            sample_id
            for manifest in first.manifests
            if manifest.dataset_id == "dataset:synthetic-memorization-v2:eval"
            for sample_id in manifest.sample_ids
        }
    }
    assert len(first.source_records) == 400
    assert len(train_ids) == 300
    assert len(eval_ids) == 100
    assert train_ids.isdisjoint(eval_ids)


def test_demo_seed_writes_source_split_and_immutable_manifests(tmp_path: Path) -> None:
    graph = RecordingGraphStore()
    legacy_artifact_dir = tmp_path / "demo"
    legacy_artifact_dir.mkdir()
    legacy_source = legacy_artifact_dir / "source_records.jsonl"
    legacy_source.write_text("preserved v1 artifact\n", encoding="utf-8")
    service = DemoSeedService(graph, legacy_artifact_dir)
    receipt = service.seed()
    service.seed()

    assert graph.seeded
    assert legacy_source.read_text(encoding="utf-8") == "preserved v1 artifact\n"
    assert receipt["source_records_processed"] == 400
    artifact_dir = tmp_path / "demo" / "scenarios" / "synthetic-memorization-v2"
    source_rows = [
        json.loads(line)
        for line in (artifact_dir / "source_records.jsonl").read_text().splitlines()
    ]
    split = json.loads((artifact_dir / "split_manifest.json").read_text())
    assert len(source_rows) == 400
    assert len(split["train_source_record_ids"]) == 300
    assert len(split["eval_source_record_ids"]) == 100
    assert set(split["train_source_record_ids"]).isdisjoint(split["eval_source_record_ids"])
    assert len(split["leaked_source_record_ids"]) == 20
    assert (
        split["label_generation"]
        == "seeded independent binary labels; features carry no label signal"
    )
    assert len(list((artifact_dir / "manifests").glob("*.json"))) == 5


def test_immutable_artifact_writer_refuses_same_version_drift(tmp_path: Path) -> None:
    artifact = tmp_path / "manifest.json"
    DemoSeedService._write_atomic(artifact, '{"version": 2}\n')
    with pytest.raises(ValueError, match="create a new scenario version"):
        DemoSeedService._write_atomic(artifact, '{"version": 3}\n')


def test_two_runs_share_an_exact_leaked_source_while_unknown_stays_untraced() -> None:
    scenario = build_demo_scenario()
    source_by_sample = {
        row["sample_id"]: row["source_record_id"] for row in scenario.source_link_rows
    }
    parent_by_copy = {row["sample_id"]: row["parent_sample_id"] for row in scenario.derivation_rows}
    copies = [
        row["sample_id"]
        for row in scenario.derivation_rows
        if row["sample_id"].startswith("sample:synthetic-memorization-v2:copy:")
    ]
    assert len(copies) == 40
    leaked_sources = {source_by_sample[parent_by_copy[sample_id]] for sample_id in copies}
    assert len(leaked_sources) == 20

    evaluation = next(
        m for m in scenario.manifests if m.dataset_id == "dataset:synthetic-memorization-v2:eval"
    )
    evaluation_sources = {source_by_sample[sample_id] for sample_id in evaluation.sample_ids}
    clean = next(
        m
        for m in scenario.manifests
        if m.dataset_id == "dataset:synthetic-memorization-v2:train-clean-control"
    )
    clean_sources = {source_by_sample[sample_id] for sample_id in clean.sample_ids}
    assert leaked_sources <= evaluation_sources
    assert clean_sources.isdisjoint(evaluation_sources)

    unknown = next(
        m
        for m in scenario.manifests
        if m.dataset_id == "dataset:synthetic-memorization-v2:train-unknown-lineage"
    )
    unknown_sample = next(
        sample_id
        for sample_id in unknown.sample_ids
        if sample_id.startswith("sample:synthetic-memorization-v2:unknown")
    )
    assert not unknown.lineage_complete
    assert unknown_sample not in source_by_sample
    assert unknown_sample not in parent_by_copy
