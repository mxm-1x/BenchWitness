"""Minimal process and FalkorDB readiness endpoints."""

import hmac
import os
from collections.abc import Awaitable, Callable
from functools import lru_cache
from typing import Annotated, Literal

from benchwitness_ml.runner import DemoEvaluationRunner, EvaluationBlocked
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response

from benchwitness_api.demo_seed import DemoSeedService, artifact_directory_from_env
from benchwitness_api.graph import GraphProbe, GraphUnavailable
from benchwitness_api.graph_lineage import (
    GraphLineageStore,
    ImpactInvestigationRecord,
    ImpactScopeExceeded,
    LineageGraphError,
    QuarantineActionRecord,
)
from benchwitness_api.impact import ActionNotAllowed, ImpactService
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


class ImpactRequest(BaseModel):
    source_record_id: str = Field(min_length=1, max_length=200)


class MetricClaimResponse(BaseModel):
    claim_id: str
    name: str
    value: float


class ImpactEvidenceResponse(BaseModel):
    run_id: str
    canonical_source_record_id: str
    training_dataset_id: str
    training_sample_id: str
    training_derivation_hops: int
    evaluation_dataset_id: str
    evaluation_sample_id: str
    evaluation_derivation_hops: int


class ImpactedRunResponse(BaseModel):
    run_id: str
    experiment_id: str
    training_dataset_id: str
    evaluation_dataset_id: str
    model_id: str
    model_configuration_id: str
    evaluation_claim_id: str
    integrity_status: Literal["suspect", "quarantined"]
    metrics: list[MetricClaimResponse]
    evidence: list[ImpactEvidenceResponse]


class ImpactInvestigationResponse(BaseModel):
    investigation_id: str
    source_record_id: str
    created_at: str
    finding_status: Literal["confirmed", "clean_within_recorded_lineage", "unknown"]
    coverage_complete: bool
    unresolved_run_ids: list[str]
    impacted_runs: list[ImpactedRunResponse]


class QuarantineProposalRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class QuarantineApprovalRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class QuarantineActionResponse(BaseModel):
    action_id: str
    investigation_id: str
    status: Literal["proposed", "approved"]
    reason: str
    created_at: str
    target_claim_ids: list[str]
    approval_id: str | None
    approver: str | None
    approval_reason: str | None
    approved_at: str | None


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


@lru_cache(maxsize=1)
def get_impact_service() -> ImpactService:
    return ImpactService(get_graph_lineage_store())


app = FastAPI(title="BenchWitness API", version="0.1.0")


@app.middleware("http")
async def authenticate_api_mutations(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Require a configured local bearer token for every API POST request."""
    if request.method == "POST" and request.url.path.startswith("/api/"):
        expected_token = os.environ.get("BENCHWITNESS_API_TOKEN", "")
        if len(expected_token) < 32:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "api_auth_not_configured",
                    "message": "Set BENCHWITNESS_API_TOKEN to a random value of at least 32 characters",
                },
            )
        authorization = request.headers.get("authorization", "")
        scheme, separator, supplied_token = authorization.partition(" ")
        if (
            scheme.lower() != "bearer"
            or not separator
            or not hmac.compare_digest(supplied_token, expected_token)
        ):
            return JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={"error": "unauthorized", "message": "A valid bearer token is required"},
            )
    return await call_next(request)


def get_approval_identity() -> str:
    """Return the locally configured identity bound to the API bearer token."""
    approver = os.environ.get("BENCHWITNESS_APPROVER", "").strip()
    if not approver:
        raise HTTPException(
            status_code=503,
            detail="Set BENCHWITNESS_APPROVER to the reviewer identity associated with the token",
        )
    return approver


def _impact_response(record: ImpactInvestigationRecord) -> ImpactInvestigationResponse:
    return ImpactInvestigationResponse(
        investigation_id=record.investigation_id,
        source_record_id=record.source_record_id,
        created_at=record.created_at,
        finding_status=record.finding_status,
        coverage_complete=record.coverage_complete,
        unresolved_run_ids=list(record.unresolved_run_ids),
        impacted_runs=[
            ImpactedRunResponse(
                run_id=run.run_id,
                experiment_id=run.experiment_id,
                training_dataset_id=run.training_dataset_id,
                evaluation_dataset_id=run.evaluation_dataset_id,
                model_id=run.model_id,
                model_configuration_id=run.model_configuration_id,
                evaluation_claim_id=run.evaluation_claim_id,
                integrity_status=run.integrity_status,
                metrics=[MetricClaimResponse(**metric.__dict__) for metric in run.metrics],
                evidence=[ImpactEvidenceResponse(**item.__dict__) for item in run.evidence],
            )
            for run in record.impacted_runs
        ],
    )


def _quarantine_action_response(action: QuarantineActionRecord) -> QuarantineActionResponse:
    return QuarantineActionResponse(
        action_id=action.action_id,
        investigation_id=action.investigation_id,
        status=action.status,
        reason=action.reason,
        created_at=action.created_at,
        target_claim_ids=list(action.target_claim_ids),
        approval_id=action.approval_id,
        approver=action.approver,
        approval_reason=action.approval_reason,
        approved_at=action.approved_at,
    )


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


@app.post("/api/v1/impact", response_model=ImpactInvestigationResponse)
def investigate_impact(
    request: ImpactRequest,
    service: Annotated[ImpactService, Depends(get_impact_service)],
) -> ImpactInvestigationResponse | JSONResponse:
    try:
        return _impact_response(service.investigate_source(request.source_record_id))
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={
                "error": "source_record_not_found",
                "source_record_id": request.source_record_id,
            },
        )
    except ImpactScopeExceeded as exc:
        return JSONResponse(
            status_code=413,
            content={"error": "impact_scope_exceeded", "message": str(exc)},
        )
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={"error": "impact_unavailable", "message": "FalkorDB impact query failed"},
        )


@app.get(
    "/api/v1/investigations/{investigation_id}",
    response_model=ImpactInvestigationResponse,
)
def get_investigation(
    investigation_id: str,
    service: Annotated[ImpactService, Depends(get_impact_service)],
) -> ImpactInvestigationResponse | JSONResponse:
    try:
        return _impact_response(service.get_investigation(investigation_id))
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": "investigation_not_found", "investigation_id": investigation_id},
        )
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={"error": "impact_unavailable", "message": "FalkorDB impact query failed"},
        )


@app.post(
    "/api/v1/investigations/{investigation_id}/quarantine-proposals",
    response_model=QuarantineActionResponse,
)
def propose_quarantine(
    investigation_id: str,
    request: QuarantineProposalRequest,
    service: Annotated[ImpactService, Depends(get_impact_service)],
) -> QuarantineActionResponse | JSONResponse:
    try:
        action = service.propose_quarantine(investigation_id, request.reason)
        return _quarantine_action_response(action)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": "investigation_not_found", "investigation_id": investigation_id},
        )
    except ActionNotAllowed as exc:
        return JSONResponse(
            status_code=409,
            content={"error": "quarantine_not_allowed", "message": str(exc)},
        )
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={
                "error": "graph_unavailable",
                "message": "FalkorDB quarantine proposal failed",
            },
        )


@app.post("/api/v1/actions/{action_id}/approve", response_model=QuarantineActionResponse)
def approve_quarantine(
    action_id: str,
    request: QuarantineApprovalRequest,
    approver: Annotated[str, Depends(get_approval_identity)],
    service: Annotated[ImpactService, Depends(get_impact_service)],
) -> QuarantineActionResponse | JSONResponse:
    try:
        action = service.approve_quarantine(action_id, approver, request.reason)
        return _quarantine_action_response(action)
    except KeyError:
        return JSONResponse(
            status_code=404,
            content={"error": "action_not_found", "action_id": action_id},
        )
    except ActionNotAllowed as exc:
        return JSONResponse(
            status_code=409,
            content={"error": "quarantine_approval_not_allowed", "message": str(exc)},
        )
    except LineageGraphError:
        return JSONResponse(
            status_code=503,
            content={"error": "graph_unavailable", "message": "FalkorDB approval failed"},
        )
