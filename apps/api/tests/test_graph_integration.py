"""Real FalkorDB lineage integration tests; never silently skipped."""

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from benchwitness_api.demo_seed import DemoSeedService
from benchwitness_api.graph import GraphProbe
from benchwitness_api.graph_lineage import GraphLineageStore, LineageGraphError
from benchwitness_api.impact import ImpactService
from benchwitness_api.main import (
    app,
    get_demo_evaluation_runner,
    get_demo_seed_service,
    get_graph_lineage_store,
    get_impact_service,
)
from benchwitness_api.settings import GraphSettings
from benchwitness_ml.runner import DemoEvaluationRunner
from falkordb import FalkorDB  # type: ignore[import-untyped]
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_graph_query_reaches_real_falkordb() -> None:
    GraphProbe(GraphSettings.from_env()).check()


@pytest.mark.integration
def test_real_graph_proves_overlap_clean_control_and_unknown_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_token = "integration-test-token-" + "x" * 40
    monkeypatch.setenv("BENCHWITNESS_API_TOKEN", api_token)
    monkeypatch.setenv("BENCHWITNESS_APPROVER", "integration-test-reviewer")
    auth_headers = {"Authorization": f"Bearer {api_token}"}
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
        app.dependency_overrides[get_impact_service] = lambda: ImpactService(store)
        client = TestClient(app)
        evaluate_before_seed = client.post("/api/v1/demo/evaluate", headers=auth_headers)
        assert evaluate_before_seed.status_code == 409
        assert evaluate_before_seed.json()["error"] == "demo_not_seeded"
        seeded = client.post("/api/v1/demo/seed", headers=auth_headers)
        assert seeded.status_code == 200
        assert seeded.json()["source_records_processed"] == 400
        api_audit = client.get("/api/v1/experiments/demo-v2-contaminated-a/lineage-audit")
        assert api_audit.status_code == 200
        assert api_audit.json()["status"] == "confirmed"
        assert api_audit.json()["coverage_complete"]
        assert api_audit.json()["source_artifact_verified"]

        evaluation_response = client.post("/api/v1/demo/evaluate", headers=auth_headers)
        assert evaluation_response.status_code == 200
        runs = evaluation_response.json()["runs"]
        overview = client.get("/api/v1/overview")
        assert overview.status_code == 200
        assert {audit["experiment_id"] for audit in overview.json()["audits"]} == {
            "demo-v2-contaminated-a",
            "demo-v2-contaminated-b",
            "demo-v2-clean-control",
            "demo-v2-unknown-lineage",
        }
        assert {run["run_id"] for run in overview.json()["runs"]} == {run["run_id"] for run in runs}
        assert all("artifact_path" not in run for run in overview.json()["runs"])
        assert all(
            set(run)
            == {
                "run_id",
                "experiment_id",
                "training_dataset_id",
                "evaluation_dataset_id",
                "created_at",
                "training_sample_count",
                "evaluation_sample_count",
                "accuracy",
            }
            for run in overview.json()["runs"]
        )
        assert (
            client.get(f"/api/v1/runs/{runs[0]['run_id']}").json()["accuracy"]
            == runs[0]["accuracy"]
        )
        assert {run["experiment_id"] for run in runs} == {
            "demo-v2-contaminated-a",
            "demo-v2-contaminated-b",
            "demo-v2-clean-control",
        }
        metrics_by_experiment = {}
        for run in runs:
            assert run["evaluation_sample_count"] == 100
            assert run["training_sample_count"] in (300, 320)
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

        repeated_evaluation = client.post("/api/v1/demo/evaluate", headers=auth_headers)
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
        accuracy_by_experiment = {run["experiment_id"]: run["accuracy"] for run in runs}
        assert (
            accuracy_by_experiment["demo-v2-contaminated-a"]
            == accuracy_by_experiment["demo-v2-contaminated-b"]
        )
        assert (
            accuracy_by_experiment["demo-v2-contaminated-a"]
            - accuracy_by_experiment["demo-v2-clean-control"]
            >= 0.05
        )
        audits = {
            experiment_id: store.audit(experiment_id)
            for experiment_id in (
                "demo-v2-contaminated-a",
                "demo-v2-contaminated-b",
                "demo-v2-clean-control",
                "demo-v2-unknown-lineage",
            )
        }
        audit_a = audits["demo-v2-contaminated-a"]
        audit_b = audits["demo-v2-contaminated-b"]
        assert audit_a.status == "confirmed"
        assert audit_b.status == "confirmed"
        assert audit_a.coverage_complete
        assert audit_b.coverage_complete
        assert len(audit_a.evidence) == 20
        assert len(audit_b.evidence) == 20
        assert {item.canonical_source_record_id for item in audit_a.evidence} == {
            item.canonical_source_record_id for item in audit_b.evidence
        }
        assert audit_a.evidence[0].training_derivation_hops == 2
        assert audit_a.evidence[0].evaluation_derivation_hops == 1

        # A sample with multiple canonical ancestors cannot be called clean.
        ambiguous_sample_id = audit_a.evidence[0].training_sample_id
        scenario_artifact_dir = artifact_dir / "scenarios" / "synthetic-memorization-v2"
        split = json.loads((scenario_artifact_dir / "split_manifest.json").read_text())
        non_eval_source_id = split["train_source_record_ids"][0]
        graph.query(
            "MATCH (sample:SampleVersion {id: $sample_id}) "
            "MATCH (source:SourceRecord {id: $source_id}) "
            "MERGE (sample)-[:DERIVED_FROM]->(source)",
            params={"sample_id": ambiguous_sample_id, "source_id": non_eval_source_id},
        )
        try:
            ambiguous_audit = store.audit("demo-v2-contaminated-a")
            assert ambiguous_audit.status == "confirmed"
            assert not ambiguous_audit.coverage_complete
            assert ambiguous_audit.training_samples_with_ambiguous_source == 1
        finally:
            graph.query(
                "MATCH (sample:SampleVersion {id: $sample_id})-"
                "[edge:DERIVED_FROM]->(source:SourceRecord {id: $source_id}) "
                "DELETE edge",
                params={"sample_id": ambiguous_sample_id, "source_id": non_eval_source_id},
            )

        unresolved_parent_id = "sample:synthetic-memorization-v2:unknown"
        graph.query(
            "MATCH (sample:SampleVersion {id: $sample_id}) "
            "MATCH (parent:SampleVersion {id: $parent_id}) "
            "MERGE (sample)-[:DERIVED_FROM]->(parent)",
            params={"sample_id": ambiguous_sample_id, "parent_id": unresolved_parent_id},
        )
        try:
            incomplete_audit = store.audit("demo-v2-contaminated-a")
            assert incomplete_audit.status == "confirmed"
            assert not incomplete_audit.coverage_complete
            assert incomplete_audit.training_samples_without_source == 0
            assert incomplete_audit.training_samples_with_ambiguous_source == 0
            assert incomplete_audit.training_samples_with_incomplete_lineage == 1
        finally:
            graph.query(
                "MATCH (sample:SampleVersion {id: $sample_id})-"
                "[edge:DERIVED_FROM]->(parent:SampleVersion {id: $parent_id}) "
                "DELETE edge",
                params={"sample_id": ambiguous_sample_id, "parent_id": unresolved_parent_id},
            )

        clean = audits["demo-v2-clean-control"]
        assert clean.status == "clean_within_recorded_lineage"
        assert clean.coverage_complete
        assert clean.training_manifest_verified
        assert clean.evaluation_manifest_verified
        assert clean.source_artifact_verified
        assert clean.evidence == ()

        unknown = audits["demo-v2-unknown-lineage"]
        assert unknown.status == "unknown"
        assert not unknown.coverage_complete
        assert unknown.training_samples_without_source == 1
        assert unknown.evidence == ()

        source_record_id = audit_a.evidence[0].canonical_source_record_id

        # The exact lineage traversal must still find affected runs when both
        # denormalized dataset family labels are missing or stale.
        stale_dataset_ids = {
            "dataset:synthetic-memorization-v2:train-contaminated-a",
            "dataset:synthetic-memorization-v2:eval",
        }
        for dataset_id in stale_dataset_ids:
            graph.query(
                "MATCH (dataset:DatasetVersion {id: $dataset_id}) "
                "SET dataset.source_family_id = $stale_family",
                params={"dataset_id": dataset_id, "stale_family": "stale-family-index"},
            )
        try:
            candidates_with_stale_index = store.list_source_family_runs(source_record_id)
            stale_a_run_ids = {
                run["run_id"] for run in runs if run["experiment_id"] == "demo-v2-contaminated-a"
            }
            assert stale_a_run_ids <= {
                candidate.run_id for candidate in candidates_with_stale_index
            }
            stale_impact_response = client.post(
                "/api/v1/impact",
                json={"source_record_id": source_record_id},
                headers=auth_headers,
            )
            assert stale_impact_response.status_code == 200
            assert stale_impact_response.json()["finding_status"] == "unknown"
            assert not stale_impact_response.json()["coverage_complete"]
        finally:
            for dataset_id in stale_dataset_ids:
                graph.query(
                    "MATCH (dataset:DatasetVersion {id: $dataset_id}) "
                    "SET dataset.source_family_id = $source_family",
                    params={
                        "dataset_id": dataset_id,
                        "source_family": "synthetic-memorization-v2",
                    },
                )

        # A failed evidence write removes its partial finding and investigation.
        original_query = store._query
        fail_evidence_once = True
        graph_counts_before_failure = {
            label: graph.query(f"MATCH (item:{label}) RETURN count(item)").result_set[0][0]
            for label in ("Investigation", "Finding", "LineageEvidence")
        }

        def fail_one_evidence_query(
            query: str, params: dict[str, Any] | None = None
        ) -> list[list[Any]]:
            nonlocal fail_evidence_once
            if "MERGE (finding)-[:SUPPORTED_BY]->(evidence)" in query and fail_evidence_once:
                fail_evidence_once = False
                original_query(query, params)
                raise LineageGraphError("injected evidence write failure")
            return original_query(query, params)

        store._query = fail_one_evidence_query  # type: ignore[method-assign]
        try:
            with pytest.raises(LineageGraphError, match="injected evidence write failure"):
                ImpactService(store).investigate_source(source_record_id)
        finally:
            store._query = original_query  # type: ignore[method-assign]
        for label, count in graph_counts_before_failure.items():
            assert graph.query(f"MATCH (item:{label}) RETURN count(item)").result_set == [[count]]

        impact_response = client.post(
            "/api/v1/impact",
            json={"source_record_id": source_record_id},
            headers=auth_headers,
        )
        assert impact_response.status_code == 200
        impact = impact_response.json()
        assert impact["finding_status"] == "confirmed"
        assert impact["coverage_complete"]
        impacted_runs = impact["impacted_runs"]
        assert {run["experiment_id"] for run in impacted_runs} == {
            "demo-v2-contaminated-a",
            "demo-v2-contaminated-b",
        }
        assert len(impacted_runs) == 4
        assert all(run["integrity_status"] == "suspect" for run in impacted_runs)
        assert all(
            evidence["canonical_source_record_id"] == source_record_id
            for run in impacted_runs
            for evidence in run["evidence"]
        )
        assert all(
            {metric["name"] for metric in run["metrics"]}
            == {"accuracy", "precision", "recall", "f1"}
            for run in impacted_runs
        )
        claim_ids = {run["evaluation_claim_id"] for run in impacted_runs}
        prior_run_metrics = {
            run["run_id"]: (
                store.get_run(run["run_id"]).accuracy,
                store.get_run(run["run_id"]).precision,
                store.get_run(run["run_id"]).recall,
                store.get_run(run["run_id"]).f1,
            )
            for run in impacted_runs
        }

        proposal_response = client.post(
            f"/api/v1/investigations/{impact['investigation_id']}/quarantine-proposals",
            json={"reason": "Confirmed sample-level train/evaluation overlap"},
            headers=auth_headers,
        )
        assert proposal_response.status_code == 200
        proposal = proposal_response.json()
        assert proposal["status"] == "proposed"
        assert set(proposal["target_claim_ids"]) == claim_ids

        pending_impact = client.get(f"/api/v1/investigations/{impact['investigation_id']}")
        assert pending_impact.status_code == 200
        assert {run["integrity_status"] for run in pending_impact.json()["impacted_runs"]} == {
            "suspect"
        }
        assert {
            run["evaluation_claim_id"] for run in pending_impact.json()["impacted_runs"]
        } == claim_ids

        approval_response = client.post(
            f"/api/v1/actions/{proposal['action_id']}/approve",
            json={"reason": "Human approval for demo test"},
            headers=auth_headers,
        )
        assert approval_response.status_code == 200
        assert approval_response.json()["status"] == "approved"
        assert approval_response.json()["approver"] == "integration-test-reviewer"
        assert set(approval_response.json()["target_claim_ids"]) == claim_ids

        quarantined_impact = client.get(f"/api/v1/investigations/{impact['investigation_id']}")
        assert quarantined_impact.status_code == 200
        assert {run["integrity_status"] for run in quarantined_impact.json()["impacted_runs"]} == {
            "quarantined"
        }
        assert {
            run["evaluation_claim_id"] for run in quarantined_impact.json()["impacted_runs"]
        } == claim_ids
        for run_id, old_metrics in prior_run_metrics.items():
            persisted_run = store.get_run(run_id)
            assert (
                persisted_run.accuracy,
                persisted_run.precision,
                persisted_run.recall,
                persisted_run.f1,
            ) == old_metrics

        source_rows_for_control = [
            json.loads(line)
            for line in (scenario_artifact_dir / "source_records.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        clean_source_id = next(
            row["source_record_id"]
            for row in source_rows_for_control
            if row["source_record_id"] != source_record_id
        )
        clean_impact_response = client.post(
            "/api/v1/impact",
            json={"source_record_id": clean_source_id},
            headers=auth_headers,
        )
        assert clean_impact_response.status_code == 200
        clean_impact = clean_impact_response.json()
        assert clean_impact["finding_status"] == "clean_within_recorded_lineage"
        assert clean_impact["coverage_complete"]
        assert clean_impact["impacted_runs"] == []
        blocked_proposal = client.post(
            f"/api/v1/investigations/{clean_impact['investigation_id']}/quarantine-proposals",
            json={"reason": "A clean source must not be quarantined"},
            headers=auth_headers,
        )
        assert blocked_proposal.status_code == 409

        clean_manifest_path = (
            scenario_artifact_dir
            / "manifests"
            / "synthetic-memorization-v2_train-clean-control.json"
        )
        original_manifest = clean_manifest_path.read_text(encoding="utf-8")
        clean_manifest_path.write_text(
            original_manifest.replace("sample_ids", "sample_ids_changed"), encoding="utf-8"
        )
        manifest_drift = store.audit("demo-v2-clean-control")
        assert manifest_drift.status == "unknown"
        assert not manifest_drift.coverage_complete
        assert not manifest_drift.training_manifest_verified

        clean_manifest_path.write_text(original_manifest, encoding="utf-8")
        source_path = scenario_artifact_dir / "source_records.jsonl"
        source_rows = [
            json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()
        ]
        source_rows[0]["label"] = 1 - source_rows[0]["label"]
        source_path.write_text(
            "\n".join(json.dumps(row, sort_keys=True) for row in source_rows) + "\n",
            encoding="utf-8",
        )
        source_drift = store.audit("demo-v2-clean-control")
        assert source_drift.status == "unknown"
        assert not source_drift.coverage_complete
        assert not source_drift.source_artifact_verified
    finally:
        app.dependency_overrides.clear()
        graph.delete()
