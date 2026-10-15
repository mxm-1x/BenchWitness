"""Minimal process and FalkorDB readiness endpoints."""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from benchwitness_api.graph import GraphProbe, GraphUnavailable
from benchwitness_api.settings import GraphSettings


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyStatus(BaseModel):
    status: Literal["ready", "not_ready"]
    graph: Literal["reachable", "unreachable"]


@lru_cache(maxsize=1)
def get_graph_probe() -> GraphProbe:
    return GraphProbe(GraphSettings.from_env())


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
