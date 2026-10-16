"""Approved repair runs against real FalkorDB and the separate Redis broker."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from benchwitness_api.demo_seed import DemoSeedService
from benchwitness_api.graph_lineage import ExperimentRunRecord, GraphLineageStore
from benchwitness_api.impact import ImpactService
from benchwitness_api.main import app, get_recovery_service
from benchwitness_api.recovery import RecoveryService, queue_from_env
from benchwitness_api.settings import GraphSettings
from benchwitness_ml.runner import DemoEvaluationRunner
from falkordb import FalkorDB  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
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
    broker = queue_from_env().connection
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
        source = store.audit("demo-v2-contaminated-a").evidence[0].canonical_source_record_id
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
            assert (
                repaired.training_dataset_id
                == "dataset:synthetic-memorization-v2:train-clean-control"
            )
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

        retry_job = api.post(
            f"/api/v1/repairs/{retry_proposal.json()['action_id']}/approve",
            headers=headers,
            json={"reason": "retry approved repair after broker recovery"},
        )
        assert retry_job.status_code == 200
        assert retry_job.json()["status"] == "queued"
        retry_job_id = retry_job.json()["job_id"]
        real_run_recovery = DemoEvaluationRunner.run_recovery
        recovery_calls = 0

        def fail_after_one_run(
            runner: DemoEvaluationRunner, original_run_id: str, current_job_id: str
        ) -> tuple[ExperimentRunRecord, str]:
            nonlocal recovery_calls
            recovery_calls += 1
            if recovery_calls == 2:
                raise RuntimeError("simulated worker interruption")
            return real_run_recovery(runner, original_run_id, current_job_id)

        with patch.object(DemoEvaluationRunner, "run_recovery", fail_after_one_run):
            SimpleWorker([queue], connection=broker).work(burst=True)
        partially_completed = api.get(f"/api/v1/jobs/{retry_job_id}").json()
        assert partially_completed["status"] == "failed"
        assert len(partially_completed["repaired_run_ids"]) == 1
        first_repaired_id = partially_completed["repaired_run_ids"][0]
        first_repaired_before_retry = store.get_run(first_repaired_id)

        retry_after_worker_failure = api.post(
            f"/api/v1/repairs/{retry_proposal.json()['action_id']}/approve",
            headers=headers,
            json={"reason": "retry after worker interruption"},
        )
        assert retry_after_worker_failure.status_code == 200
        assert retry_after_worker_failure.json()["status"] == "queued"
        SimpleWorker([queue], connection=broker).work(burst=True)
        retried_job = api.get(f"/api/v1/jobs/{retry_job_id}").json()
        assert retried_job["status"] == "succeeded"
        assert len(retried_job["repaired_run_ids"]) == 2
        first_repaired_after_retry = store.get_run(first_repaired_id)
        assert (
            first_repaired_after_retry.manifest_sha256
            == first_repaired_before_retry.manifest_sha256
        )
        assert first_repaired_after_retry.artifact_path == first_repaired_before_retry.artifact_path

        stale_investigation = ImpactService(store).investigate_source(source)
        stale_proposal = api.post(
            f"/api/v1/investigations/{stale_investigation.investigation_id}/repair-proposals",
            headers=headers,
            json={"reason": "test stale worker recovery"},
        )
        stale_action_id = stale_proposal.json()["action_id"]
        stale_queued = api.post(
            f"/api/v1/repairs/{stale_action_id}/approve",
            headers=headers,
            json={"reason": "reviewed evidence"},
        )
        stale_job_id = stale_queued.json()["job_id"]
        assert stale_queued.json()["status"] == "queued"
        assert store.transition_recovery_job(stale_job_id, "queued", "running")
        stale_started_at = (datetime.now(UTC) - timedelta(minutes=7)).isoformat(
            timespec="milliseconds"
        )
        client_graph.query(
            "MATCH (job:RecoveryJob {id: $job_id}) SET job.started_at = $started_at RETURN job.id",
            params={"job_id": stale_job_id, "started_at": stale_started_at},
        )
        assert queue.count == 1
        queue.empty()  # type: ignore[no-untyped-call]  # Simulate a timed-out RQ attempt.

        stale_status = api.get(f"/api/v1/jobs/{stale_job_id}").json()
        assert stale_status["status"] == "failed"
        assert stale_status["error"] == "worker_timeout:stale_running_job"
        stale_retry = api.post(
            f"/api/v1/repairs/{stale_action_id}/approve",
            headers=headers,
            json={"reason": "retry timed-out approved repair"},
        )
        assert stale_retry.status_code == 200
        assert stale_retry.json()["status"] == "queued"
        SimpleWorker([queue], connection=broker).work(burst=True)
        assert api.get(f"/api/v1/jobs/{stale_job_id}").json()["status"] == "succeeded"
    finally:
        app.dependency_overrides.clear()
        queue.empty()  # type: ignore[no-untyped-call]
        client_graph.delete()
