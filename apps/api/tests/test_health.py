"""HTTP smoke and failure-state tests."""

import pytest
from benchwitness_api.graph import GraphUnavailable
from benchwitness_api.graph_lineage import AuditEvidence, AuditResult
from benchwitness_api.main import (
    app,
    get_demo_seed_service,
    get_graph_lineage_store,
    get_graph_probe,
)
from fastapi.testclient import TestClient


class UnavailableProbe:
    def check(self) -> None:
        raise GraphUnavailable("test failure")


class SmokeSeedService:
    def seed(self) -> dict[str, object]:
        return {
            "source_records_processed": 400,
            "sample_versions_processed": 441,
            "dataset_versions": ["dataset:synthetic-memorization-v2:eval"],
            "experiments": ["demo-v2-contaminated-a"],
            "source_manifest_hash": "a" * 64,
            "split_manifest_hash": "b" * 64,
            "artifact_directory": "artifacts/demo",
        }


class SmokeLineageStore:
    def audit(self, experiment_id: str) -> AuditResult:
        return AuditResult(
            experiment_id=experiment_id,
            status="confirmed",
            coverage_complete=True,
            training_dataset_id="dataset:synthetic-memorization-v2:train-contaminated-a",
            evaluation_dataset_id="dataset:synthetic-memorization-v2:eval",
            training_samples_without_source=0,
            evaluation_samples_without_source=0,
            training_samples_with_ambiguous_source=0,
            evaluation_samples_with_ambiguous_source=0,
            training_samples_with_incomplete_lineage=0,
            evaluation_samples_with_incomplete_lineage=0,
            training_manifest_verified=True,
            evaluation_manifest_verified=True,
            source_artifact_verified=True,
            evidence=(
                AuditEvidence(
                    canonical_source_record_id="source:synthetic-memorization-v2:0012",
                    training_dataset_id="dataset:synthetic-memorization-v2:train-contaminated-a",
                    training_sample_id=(
                        "sample:synthetic-memorization-v2:copy:demo-v2-contaminated-a:0012"
                    ),
                    training_derivation_hops=2,
                    evaluation_dataset_id="dataset:synthetic-memorization-v2:eval",
                    evaluation_sample_id="sample:synthetic-memorization-v2:source:0012",
                    evaluation_derivation_hops=1,
                ),
            ),
        )


def test_healthz_smoke() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_post_requires_configured_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BENCHWITNESS_API_TOKEN", "test-token-" + "x" * 40)
    response = TestClient(app).post("/api/v1/demo/seed")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_api_post_is_disabled_without_token_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BENCHWITNESS_API_TOKEN", raising=False)
    response = TestClient(app).post("/api/v1/demo/seed")
    assert response.status_code == 503
    assert response.json()["error"] == "api_auth_not_configured"


def test_readyz_reports_graph_failure() -> None:
    app.dependency_overrides[get_graph_probe] = lambda: UnavailableProbe()
    try:
        response = TestClient(app).get("/readyz")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "graph": "unreachable"}


def test_seed_and_lineage_audit_api_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    api_token = "smoke-test-token-" + "x" * 40
    monkeypatch.setenv("BENCHWITNESS_API_TOKEN", api_token)
    app.dependency_overrides[get_demo_seed_service] = lambda: SmokeSeedService()
    app.dependency_overrides[get_graph_lineage_store] = lambda: SmokeLineageStore()
    try:
        client = TestClient(app)
        seed = client.post(
            "/api/v1/demo/seed",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        audit = client.get("/api/v1/experiments/demo-v2-contaminated-a/lineage-audit")
    finally:
        app.dependency_overrides.clear()

    assert seed.status_code == 200
    assert seed.json()["source_records_processed"] == 400
    assert audit.status_code == 200
    assert audit.json()["status"] == "confirmed"
    evidence = audit.json()["evidence"][0]
    assert evidence["canonical_source_record_id"] == "source:synthetic-memorization-v2:0012"
    assert evidence["training_derivation_hops"] == 2
