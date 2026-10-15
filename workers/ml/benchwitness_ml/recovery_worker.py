"""Run approved repairs from the dedicated Redis queue."""

from __future__ import annotations

import logging

from benchwitness_api.demo_seed import artifact_directory_from_env
from benchwitness_api.graph_lineage import GraphLineageStore
from benchwitness_api.recovery import queue_from_env
from benchwitness_api.settings import GraphSettings
from rq import Worker

from benchwitness_ml.runner import DemoEvaluationRunner

_LOGGER = logging.getLogger(__name__)


def run_recovery_job(job_id: str) -> None:
    graph = GraphLineageStore(GraphSettings.from_env(), artifact_directory_from_env())
    job = graph.get_recovery_job(job_id)
    if job.status != "queued":
        return
    if not graph.transition_recovery_job(job_id, "queued", "running"):
        return
    completed: list[str] = []
    runner = DemoEvaluationRunner(graph, artifact_directory_from_env())
    try:
        for original_run_id in job.original_run_ids:
            repaired, _ = runner.run_recovery(original_run_id, job_id)
            completed.append(repaired.run_id)
    except Exception as exc:
        _LOGGER.exception("Recovery job %s failed", job_id)
        graph.transition_recovery_job(
            job_id,
            "running",
            "failed",
            error=f"recovery_failed:{type(exc).__name__}",
            repaired_run_ids=tuple(completed),
        )
        raise
    graph.transition_recovery_job(job_id, "running", "succeeded", repaired_run_ids=tuple(completed))


def main() -> int:
    queue = queue_from_env()
    Worker([queue], connection=queue.connection).work()
    return 0
