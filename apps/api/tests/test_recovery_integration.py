"""Approved repair runs against real FalkorDB and the separate Redis broker."""

from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from benchwitness_api.demo_seed import DemoSeedService
from benchwitness_api.graph_lineage import GraphLineageStore
from benchwitness_api.impact import ImpactService
from benchwitness_api.main import app, get_recovery_service
from benchwitness_api.recovery import RecoveryService
from benchwitness_api.settings import GraphSettings
from benchwitness_ml.runner import DemoEvaluationRunner
from falkordb import FalkorDB  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from redis import Redis
from rq import Queue, SimpleWorker


@pytest.mark.integration
def test_approved_recovery_is_measured_and_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = GraphSettings.from_env()
    name = f"bw_repair_{uuid4().hex[:12]}"
    artifact_dir = tmp_path / "demo"
    store = GraphLineageStore(GraphSettings(settings.host, settings.port, name), artifact_dir)
    client_graph = FalkorDB(host=settings.host, port=settings.port).select_graph(name)
    broker = Redis(host="127.0.0.1", port=6380)
    queue = Queue(f"bw-repair-test-{uuid4().hex[:8]}", connection=broker)
    service = RecoveryService(store, queue)
    token = "test-token-" + "x" * 40
    monkeypatch.setenv("BENCHWITNESS_API_TOKEN", token)
    monkeypatch.setenv("BENCHWITNESS_APPROVER", "test-reviewer")
    monkeypatch.setenv("FALKORDB_GRAPH", name)
    monkeypatch.setenv("BENCHWITNESS_ARTIFACT_DIR", str(artifact_dir))
    app.dependency_overrides[get_recovery_service] = lambda: service
    headers = {"Authorization": f"Bearer {token}"}
    try:
        DemoSeedService(store, artifact_dir).seed()
        original = DemoEvaluationRunner(store, artifact_dir).run_all()
        source = store.audit("demo-contaminated-a").evidence[0].canonical_source_record_id
        investigation = ImpactService(store).investigate_source(source)
        assert len(investigation.impacted_runs) == 2
        api = TestClient(app)
        proposal = api.post(
            f"/api/v1/investigations/{investigation.investigation_id}/repair-proposals",
            headers=headers,
            json={"reason": "restore held-out split"},
        )
        assert proposal.status_code == 200
        assert proposal.json()["status"] == "proposed"
        action_id = proposal.json()["action_id"]
        job_id = f"job:repair:{action_id}"
        assert api.get(f"/api/v1/jobs/{job_id}").status_code == 404
        response = api.post(
            f"/api/v1/repairs/{action_id}/approve",
            headers=headers,
            json={"reason": "reviewed exact source overlap"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "queued"
        assert (
            api.post(
                f"/api/v1/repairs/{action_id}/approve",
                headers=headers,
                json={"reason": "duplicate request"},
            ).json()["job_id"]
            == job_id
        )
        assert queue.count == 1
        SimpleWorker([queue], connection=broker).work(burst=True)
        finished = api.get(f"/api/v1/jobs/{job_id}")
        assert finished.status_code == 200
        assert finished.json()["status"] == "succeeded", finished.text
        assert len(finished.json()["repaired_run_ids"]) == 2
        for run_id in finished.json()["repaired_run_ids"]:
            repaired = store.get_run(run_id)
            assert repaired.training_dataset_id == "dataset:train-clean-control-v1"
            assert store.audit(repaired.experiment_id).status == "clean_within_recorded_lineage"
            assert (Path(repaired.artifact_path) / "model-training-rows.jsonl").is_file()
            assert repaired.run_id not in {run.run_id for run in original}
        assert all(store.get_run(run.run_id).run_id == run.run_id for run in original)
        again = api.post(
            f"/api/v1/repairs/{action_id}/approve",
            headers=headers,
            json={"reason": "duplicate request"},
        )
        assert again.json()["repaired_run_ids"] == finished.json()["repaired_run_ids"]
        assert queue.count == 0

        retry_investigation = ImpactService(store).investigate_source(source)
        retry_proposal = api.post(
            f"/api/v1/investigations/{retry_investigation.investigation_id}/repair-proposals",
            headers=headers,
            json={"reason": "broker failure case"},
        )
        assert retry_proposal.status_code == 200
        with patch.object(queue, "enqueue", side_effect=ConnectionError("broker down")):
            failed = api.post(
                f"/api/v1/repairs/{retry_proposal.json()['action_id']}/approve",
                headers=headers,
                json={"reason": "reviewed evidence"},
            )
        assert failed.status_code == 503
        failed_job = api.get(f"/api/v1/jobs/job:repair:{retry_proposal.json()['action_id']}")
        assert failed_job.json()["status"] == "failed"
        assert failed_job.json()["error"] == "queue_unavailable:ConnectionError"
    finally:
        app.dependency_overrides.clear()
        queue.empty()  # type: ignore[no-untyped-call]
        client_graph.delete()
