"""Fresh agent sessions retrieve and revalidate graph-backed investigation memory."""

from pathlib import Path
from uuid import uuid4

import pytest
from benchwitness_api.agent import AgentService
from benchwitness_api.demo_seed import DemoSeedService
from benchwitness_api.graph_lineage import GraphLineageStore
from benchwitness_api.main import app, get_agent_service
from benchwitness_api.settings import GraphSettings
from benchwitness_ml.runner import DemoEvaluationRunner
from falkordb import FalkorDB  # type: ignore[import-untyped]
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_new_agent_session_recalls_verified_memory_then_reinvestigates_stale_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = GraphSettings.from_env()
    name = f"bw_agent_{uuid4().hex[:12]}"
    graph = FalkorDB(host=settings.host, port=settings.port).select_graph(name)
    artifact_dir = tmp_path / "demo"
    store = GraphLineageStore(GraphSettings(settings.host, settings.port, name), artifact_dir)
    token = "agent-test-token-" + "x" * 40
    monkeypatch.setenv("BENCHWITNESS_API_TOKEN", token)
    headers = {"Authorization": f"Bearer {token}"}
    app.dependency_overrides[get_agent_service] = lambda: AgentService(store)
    try:
        DemoSeedService(store, artifact_dir).seed()
        runner = DemoEvaluationRunner(store, artifact_dir)
        runner.run_all()
        source = store.audit("demo-v2-contaminated-a").evidence[0].canonical_source_record_id
        client = TestClient(app)
        assert client.post("/api/v1/agent/sessions").status_code == 401

        first_session = client.post("/api/v1/agent/sessions", headers=headers).json()["session_id"]
        request = {"intent": "investigate_source", "subject_id": source}
        assert (
            client.post(
                f"/api/v1/agent/sessions/{first_session}/messages",
                headers=headers,
                json={"intent": "approve_repair", "subject_id": source},
            ).status_code
            == 422
        )
        first = client.post(
            f"/api/v1/agent/sessions/{first_session}/messages",
            headers=headers,
            json=request,
        )
        assert first.status_code == 200, first.text
        first_data = first.json()
        assert first_data["memory_status"] == "none"
        assert first_data["tools_used"] == ["investigate_source"]
        assert first_data["investigation"]["finding_status"] == "confirmed"
        assert len(first_data["investigation"]["impacted_runs"]) == 2
        for run in first_data["investigation"]["impacted_runs"]:
            for evidence in run["evidence"]:
                assert evidence["training_sample_id"].startswith(
                    "sample:synthetic-memorization-v2:copy:"
                )
                assert evidence["evaluation_sample_id"].startswith(
                    "sample:synthetic-memorization-v2:source:"
                )
        assert first_data["memory_id"] is not None

        # A new service instance and session have no Python conversation state.
        app.dependency_overrides[get_agent_service] = lambda: AgentService(store)
        second_session = client.post("/api/v1/agent/sessions", headers=headers).json()["session_id"]
        second = client.post(
            f"/api/v1/agent/sessions/{second_session}/messages",
            headers=headers,
            json=request,
        )
        assert second.status_code == 200, second.text
        second_data = second.json()
        assert second_data["memory_status"] == "verified"
        assert second_data["tools_used"] == ["recall_prior_investigations", "revalidate_lineage"]
        assert (
            second_data["investigation"]["investigation_id"]
            == first_data["investigation"]["investigation_id"]
        )
        edge = graph.query(
            "MATCH (s:AgentSession {id: $session_id})-[:REMEMBERS]->(m:AgentMemory) "
            "RETURN m.id LIMIT 1",
            params={"session_id": second_session},
        ).result_set
        assert edge == [[first_data["memory_id"]]]

        clean = client.post(
            f"/api/v1/agent/sessions/{second_session}/messages",
            headers=headers,
            json={"intent": "audit_experiment", "subject_id": "demo-v2-clean-control"},
        )
        assert clean.status_code == 200
        assert clean.json()["audit"]["status"] == "clean_within_recorded_lineage"
        assert clean.json()["memory_status"] == "none"

        # A new measured run changes the current candidate set and invalidates the snapshot.
        runner.run_all()
        third_session = client.post("/api/v1/agent/sessions", headers=headers).json()["session_id"]
        third = client.post(
            f"/api/v1/agent/sessions/{third_session}/messages",
            headers=headers,
            json=request,
        )
        assert third.status_code == 200, third.text
        third_data = third.json()
        assert third_data["memory_status"] == "stale"
        assert third_data["tools_used"] == ["recall_prior_investigations", "investigate_source"]
        assert (
            third_data["investigation"]["investigation_id"]
            != first_data["investigation"]["investigation_id"]
        )
        assert len(third_data["investigation"]["impacted_runs"]) == 4
    finally:
        app.dependency_overrides.clear()
        graph.delete()
