"""A real FalkorDB query used for readiness and local diagnostics."""

from falkordb import FalkorDB  # type: ignore[import-untyped]

from benchwitness_api.settings import GraphSettings


class GraphUnavailable(RuntimeError):
    """The FalkorDB graph command could not complete or returned an invalid result."""


class GraphProbe:
    """Check that the configured FalkorDB graph engine responds."""

    def __init__(self, settings: GraphSettings) -> None:
        self._settings = settings

    def check(self) -> None:
        """Run a constant Cypher query; a Redis PING alone is insufficient."""
        try:
            client = FalkorDB(
                host=self._settings.host,
                port=self._settings.port,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            graph = client.select_graph(self._settings.graph_name)
            result = graph.query("RETURN 1 AS ok", timeout=1000).result_set
        except Exception as exc:
            # A health boundary must classify all client/transport failures as unavailable.
            raise GraphUnavailable("FalkorDB graph query failed") from exc
        if result != [[1]]:
            raise GraphUnavailable("FalkorDB graph query returned an unexpected result")
