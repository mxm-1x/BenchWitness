"""Environment-backed connection settings for local development."""

from dataclasses import dataclass
from os import environ


@dataclass(frozen=True)
class GraphSettings:
    host: str
    port: int
    graph_name: str

    @classmethod
    def from_env(cls) -> "GraphSettings":
        """Read the FalkorDB address; invalid ports fail during startup."""
        return cls(
            host=environ.get("FALKORDB_HOST", "127.0.0.1"),
            port=int(environ.get("FALKORDB_PORT", "6379")),
            graph_name=environ.get("FALKORDB_GRAPH", "benchwitness"),
        )
