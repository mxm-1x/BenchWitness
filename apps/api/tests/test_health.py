"""HTTP smoke and failure-state tests."""

from benchwitness_api.graph import GraphUnavailable
from benchwitness_api.main import app, get_graph_probe
from fastapi.testclient import TestClient


class UnavailableProbe:
    def check(self) -> None:
        raise GraphUnavailable("test failure")


def test_healthz_smoke() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_graph_failure() -> None:
    app.dependency_overrides[get_graph_probe] = lambda: UnavailableProbe()
    try:
        response = TestClient(app).get("/readyz")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "graph": "unreachable"}
