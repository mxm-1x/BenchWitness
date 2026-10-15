"""Minimal process and FalkorDB readiness endpoints."""

from functools import lru_cache
from typing import Annotated, Literal

from benchwitness_ml.runner import DemoEvaluationRunner, EvaluationBlocked
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from benchwitness_api.demo_seed import DemoSeedService, artifact_directory_from_env
from benchwitness_api.graph import GraphProbe, GraphUnavailable
from benchwitness_api.graph_lineage import (
    GraphLineageStore,
    LineageGraphError,
)
from benchwitness_api.settings import GraphSettings


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    graph: Literal["reachable", "unreachable"]


class DemoSeedResponse(BaseModel):
    source_records_processed: int
    sample_versions_processed: int
    dataset_versions: list[str]
    experiments: list[str]
    source_manifest_hash: str
    split_manifest_hash: str
    artifact_directory: str


class LineageEvidenceResponse(BaseModel):
    canonical_source_record_id: str
    training_dataset_id: str
    training_sample_id: str
    training_derivation_hops: int
    evaluation_dataset_id: str
    evaluation_sample_id: str
    evaluation_derivation_hops: int


class LineageAuditResponse(BaseModel):
    experiment_id: str
    status: Literal["confirmed", "clean_within_recorded_lineage", "unknown"]
    coverage_complete: bool
    training_dataset_id: str
    evaluation_dataset_id: str
    training_samples_without_source: int
    evaluation_samples_without_source: int
    training_manifest_verified: bool
    evaluation_manifest_verified: bool
    source_artifact_verified: bool
    evidence: list[LineageEvidenceResponse]


class ExperimentRunResponse(BaseModel):
    run_id: str
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str
    model_id: str
    model_config_json: str
    created_at: str
    python_version: str
    training_sample_count: int
    evaluation_sample_count: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    prediction_sha256: str
    manifest_sha256: str
    artifact_path: str


class DemoEvaluationResponse(BaseModel):
    runs: list[ExperimentRunResponse]


@lru_cache(maxsize=1)
def get_graph_probe() -> GraphProbe:
    return GraphProbe(GraphSettings.from_env())


@lru_cache(maxsize=1)
def get_graph_lineage_store() -> GraphLineageStore:
    return GraphLineageStore(GraphSettings.from_env())


@lru_cache(maxsize=1)
def get_demo_seed_service() -> DemoSeedService:
    return DemoSeedService(get_graph_lineage_store(), artifact_directory_from_env())


@lru_cache(maxsize=1)
def get_demo_evaluation_runner() -> DemoEvaluationRunner:
    return DemoEvaluationRunner(get_graph_lineage_store(), artifact_directory_from_env())


app = FastAPI(title="BenchWitness API", version="0.1.0")


@app.get("/healthz", response_model=HealthStatus)
def healthz() -> HealthStatus:
    return HealthStatus()


@app.get("/readyz", response_model=ReadyStatus)
def readyz(probe: Annotated[GraphProbe, Depends(get_graph_probe)]) -> ReadyStatus | JSONResponse:
    try:
        probe.check()
    except GraphUnavailable:
        body = ReadyStatus(status="not_ready", graph="unreachable")
        return JSONResponse(status_code=503, content=body.model_dump())
    return ReadyStatus(status="ready", graph="reachable")


@app.post("/api/v1/demo/seed", response_model=DemoSeedResponse)
def seed_demo(
    service: Annotated[DemoSeedService, Depends(get_demo_seed_service)],
) -> DemoSeedResponse | JSONResponse:
    try:
        return DemoSeedResponse(**service.seed())
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={"error": "graph_unavailable", "message": "FalkorDB seed failed"},
        )


@app.get(
    "/api/v1/experiments/{experiment_id}/lineage-audit",
    response_model=LineageAuditResponse,
)
def audit_experiment_lineage(
    experiment_id: str,
    store: Annotated[GraphLineageStore, Depends(get_graph_lineage_store)],
) -> LineageAuditResponse | JSONResponse:
    try:
        result = store.audit(experiment_id)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": "experiment_not_found", "experiment_id": experiment_id},
        )
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={"error": "graph_unavailable", "message": "FalkorDB audit failed"},
        )
    return LineageAuditResponse(
        experiment_id=result.experiment_id,
        status=result.status,
        coverage_complete=result.coverage_complete,
        training_dataset_id=result.training_dataset_id,
        evaluation_dataset_id=result.evaluation_dataset_id,
        training_samples_without_source=result.training_samples_without_source,
        evaluation_samples_without_source=result.evaluation_samples_without_source,
        training_manifest_verified=result.training_manifest_verified,
        evaluation_manifest_verified=result.evaluation_manifest_verified,
        source_artifact_verified=result.source_artifact_verified,
        evidence=[LineageEvidenceResponse(**evidence.__dict__) for evidence in result.evidence],
    )


@app.post("/api/v1/demo/evaluate", response_model=DemoEvaluationResponse)
def evaluate_demo(
    runner: Annotated[DemoEvaluationRunner, Depends(get_demo_evaluation_runner)],
) -> DemoEvaluationResponse | JSONResponse:
    try:
        runs = runner.run_all()
    except EvaluationBlocked as exc:
        return JSONResponse(
            status_code=409,
            content={"error": "evaluation_blocked", "message": str(exc)},
        )
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={"error": "graph_unavailable", "message": "FalkorDB evaluation failed"},
        )
    return DemoEvaluationResponse(runs=[ExperimentRunResponse(**run.__dict__) for run in runs])
