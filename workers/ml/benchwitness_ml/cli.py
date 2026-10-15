"""Run real CPU-only metrics for the seeded experiment family."""

import json
from dataclasses import asdict

from benchwitness_api.demo_seed import artifact_directory_from_env
from benchwitness_api.graph_lineage import GraphLineageStore, LineageGraphError
from benchwitness_api.settings import GraphSettings

from benchwitness_ml.runner import DemoEvaluationRunner, EvaluationBlocked


def main() -> int:
    graph = GraphLineageStore(GraphSettings.from_env())
    try:
        runs = DemoEvaluationRunner(graph, artifact_directory_from_env()).run_all()
    except (EvaluationBlocked, LineageGraphError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps({"runs": [asdict(run) for run in runs]}, indent=2))
    return 0
