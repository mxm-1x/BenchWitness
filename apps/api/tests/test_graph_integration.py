"""Real FalkorDB integration test; never silently skipped."""

import pytest
from benchwitness_api.graph import GraphProbe
from benchwitness_api.settings import GraphSettings


@pytest.mark.integration
def test_graph_query_reaches_real_falkordb() -> None:
    GraphProbe(GraphSettings.from_env()).check()
