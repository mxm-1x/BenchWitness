"""Command-line graph connectivity probe."""

import json

from benchwitness_api.graph import GraphProbe, GraphUnavailable
from benchwitness_api.settings import GraphSettings


def main() -> int:
    """Print a machine-readable result and exit nonzero when graph is unavailable."""
    try:
        GraphProbe(GraphSettings.from_env()).check()
    except GraphUnavailable:
        print(json.dumps({"graph": "unreachable"}))
        return 1
    print(json.dumps({"graph": "reachable"}))
    return 0
