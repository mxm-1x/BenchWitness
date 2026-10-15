"""Seed the deterministic local demo graph and manifests."""

import json

from benchwitness_api.demo_seed import DemoSeedService, artifact_directory_from_env
from benchwitness_api.graph_lineage import GraphLineageStore, LineageGraphError
from benchwitness_api.settings import GraphSettings


def main() -> int:
    try:
        receipt = DemoSeedService(
            GraphLineageStore(GraphSettings.from_env()), artifact_directory_from_env()
        ).seed()
    except LineageGraphError:
        print(json.dumps({"error": "graph_unavailable"}))
        return 1
    print(json.dumps(receipt, indent=2))
    return 0
