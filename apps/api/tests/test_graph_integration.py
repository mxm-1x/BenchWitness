"""Real FalkorDB lineage integration tests; never silently skipped."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from benchwitness_api.demo_seed import DemoSeedService
from benchwitness_api.graph import GraphProbe
from benchwitness_api.graph_lineage import GraphLineageStore
from benchwitness_api.main import (
    app,
    get_demo_evaluation_runner,
    get_demo_seed_service,
    get_graph_lineage_store,
)
from benchwitness_api.settings import GraphSettings
from benchwitness_ml.runner import DemoEvaluationRunner
from falkordb import FalkorDB  # type: ignore[import-untyped]
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_graph_query_reaches_real_falkordb() -> None:
    GraphProbe(GraphSettings.from_env()).check()


@pytest.mark.integration
def test_real_graph_proves_overlap_clean_control_and_unknown_lineage(tmp_path: Path) -> None:
    settings = GraphSettings.from_env()
    test_graph_name = f"bw_m2_{uuid4().hex[:12]}"
    test_settings = GraphSettings(settings.host, settings.port, test_graph_name)
    graph = FalkorDB(host=settings.host, port=settings.port).select_graph(test_graph_name)
    artifact_dir = tmp_path / "demo"
    store = GraphLineageStore(test_settings, artifact_dir)

    try:
        app.dependency_overrides[get_demo_seed_service] = lambda: DemoSeedService(
            store, artifact_dir
        )
        app.dependency_overrides[get_graph_lineage_store] = lambda: store
        app.dependency_overrides[get_demo_evaluation_runner] = lambda: DemoEvaluationRunner(
            store, artifact_dir
        )
        client = TestClient(app)
        seeded = client.post("/api/v1/demo/seed")
        assert seeded.status_code == 200
        assert seeded.json()["source_records_processed"] == 400
        api_audit = client.get("/api/v1/experiments/demo-contaminated-a/lineage-audit")
        assert api_audit.status_code == 200
        assert api_audit.json()["status"] == "confirmed"
        assert api_audit.json()["coverage_complete"]
        assert api_audit.json()["source_artifact_verified"]

        evaluation_response = client.post("/api/v1/demo/evaluate")
        assert evaluation_response.status_code == 200
        runs = evaluation_response.json()["runs"]
        assert {run["experiment_id"] for run in runs} == {
            "demo-contaminated-a",
            "demo-contaminated-b",
            "demo-clean-control",
        }
        metrics_by_experiment = {}
        for run in runs:
            assert run["evaluation_sample_count"] == 100
            assert run["training_sample_count"] in (300, 301)
            assert (
                sum(
                    run[key]
                    for key in (
                        "true_positive",
                        "false_positive",
                        "true_negative",
                        "false_negative",
                    )
                )
                == run["evaluation_sample_count"]
            )
            prediction_path = Path(run["artifact_path"]) / "predictions.jsonl"
            prediction_bytes = prediction_path.read_bytes()
            assert hashlib.sha256(prediction_bytes).hexdigest() == run["prediction_sha256"]
            predictions = [json.loads(line) for line in prediction_bytes.splitlines()]
            true_positive = sum(
                item["actual"] == 1 and item["predicted"] == 1 for item in predictions
            )
            true_negative = sum(
                item["actual"] == 0 and item["predicted"] == 0 for item in predictions
            )
            false_positive = sum(
                item["actual"] == 0 and item["predicted"] == 1 for item in predictions
            )
            false_negative = sum(
                item["actual"] == 1 and item["predicted"] == 0 for item in predictions
            )
            expected_precision = (
                true_positive / (true_positive + false_positive)
                if true_positive + false_positive
                else 0.0
            )
            expected_recall = (
                true_positive / (true_positive + false_negative)
                if true_positive + false_negative
                else 0.0
            )
            expected_f1 = (
                2 * expected_precision * expected_recall / (expected_precision + expected_recall)
                if expected_precision + expected_recall
                else 0.0
            )
            assert run["accuracy"] == (true_positive + true_negative) / len(predictions)
            assert run["precision"] == pytest.approx(expected_precision)
            assert run["recall"] == pytest.approx(expected_recall)
            assert run["f1"] == pytest.approx(expected_f1)
            graph_run = store.get_run(run["run_id"])
            assert graph_run.experiment_id == run["experiment_id"]
            assert graph_run.training_dataset_id == run["training_dataset_id"]
            assert graph_run.evaluation_dataset_id == run["evaluation_dataset_id"]
            assert graph_run.accuracy == run["accuracy"]
            assert graph_run.prediction_sha256 == run["prediction_sha256"]
            metrics_by_experiment[run["experiment_id"]] = (
                run["accuracy"],
                run["precision"],
                run["recall"],
                run["f1"],
            )

        repeated_evaluation = client.post("/api/v1/demo/evaluate")
        assert repeated_evaluation.status_code == 200
        repeated_metrics = {
            run["experiment_id"]: (
                run["accuracy"],
                run["precision"],
                run["recall"],
                run["f1"],
            )
            for run in repeated_evaluation.json()["runs"]
        }
        assert repeated_metrics == metrics_by_experiment
        assert {run["run_id"] for run in repeated_evaluation.json()["runs"]}.isdisjoint(
            {run["run_id"] for run in runs}
        )
        app.dependency_overrides.clear()

        audits = {
            experiment_id: store.audit(experiment_id)
            for experiment_id in (
                "demo-contaminated-a",
                "demo-contaminated-b",
                "demo-clean-control",
                "demo-unknown-lineage",
            )
        }
        audit_a = audits["demo-contaminated-a"]
        audit_b = audits["demo-contaminated-b"]
        assert audit_a.status == "confirmed"
        assert audit_b.status == "confirmed"
        assert audit_a.coverage_complete
        assert audit_b.coverage_complete
        assert {item.canonical_source_record_id for item in audit_a.evidence} == {
            item.canonical_source_record_id for item in audit_b.evidence
        }
        assert audit_a.evidence[0].training_derivation_hops == 2
        assert audit_a.evidence[0].evaluation_derivation_hops == 1

        clean = audits["demo-clean-control"]
        assert clean.status == "clean_within_recorded_lineage"
        assert clean.coverage_complete
        assert clean.training_manifest_verified
        assert clean.evaluation_manifest_verified
        assert clean.source_artifact_verified
        assert clean.evidence == ()

        unknown = audits["demo-unknown-lineage"]
        assert unknown.status == "unknown"
        assert not unknown.coverage_complete
        assert unknown.training_samples_without_source == 1
        assert unknown.evidence == ()

        clean_manifest_path = artifact_dir / "manifests" / "train-clean-control-v1.json"
        original_manifest = clean_manifest_path.read_text(encoding="utf-8")
        clean_manifest_path.write_text(
            original_manifest.replace("sample_ids", "sample_ids_changed"), encoding="utf-8"
        )
        manifest_drift = store.audit("demo-clean-control")
        assert manifest_drift.status == "unknown"
        assert not manifest_drift.coverage_complete
        assert not manifest_drift.training_manifest_verified

        clean_manifest_path.write_text(original_manifest, encoding="utf-8")
        source_path = artifact_dir / "source_records.jsonl"
        source_rows = [
            json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()
        ]
        source_rows[0]["label"] = 1 - source_rows[0]["label"]
        source_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in source_rows) + "\n",
            encoding="utf-8",
        )
        source_drift = store.audit("demo-clean-control")
        assert source_drift.status == "unknown"
        assert not source_drift.coverage_complete
        assert not source_drift.source_artifact_verified
    finally:
        app.dependency_overrides.clear()
        graph.delete()
