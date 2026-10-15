"""Explicit repair approval and Redis dispatch; FalkorDB owns the job state."""

from __future__ import annotations

import hashlib
import os

from redis import Redis
from rq import Queue

from benchwitness_api.graph_lineage import (
    ActionNotAllowed,
    GraphLineageStore,
    QuarantineActionRecord,
    RecoveryJobRecord,
)


class RecoveryService:
    def __init__(self, graph: GraphLineageStore, queue: Queue) -> None:
        self._graph = graph
        self._queue = queue

    def propose(self, investigation_id: str, reason: str) -> QuarantineActionRecord:
        return self._graph.propose_repair(investigation_id, reason)

    def approve_and_enqueue(self, action_id: str, approver: str, reason: str) -> RecoveryJobRecord:
        action = self._graph.approve_repair(action_id, approver, reason)
        investigation = self._graph.get_investigation(action.investigation_id)
        original_ids = tuple(sorted(run.run_id for run in investigation.impacted_runs))
        if not original_ids:
            raise ActionNotAllowed("repair has no measured impacted runs")
        job = self._graph.create_recovery_job(action_id, original_ids)
        if job.status != "pending_enqueue":
            return job
        if not self._graph.transition_recovery_job(job.job_id, "pending_enqueue", "queued"):
            return self._graph.get_recovery_job(job.job_id)
        try:
            broker_job_id = "bw-repair-" + hashlib.sha256(job.job_id.encode()).hexdigest()
            self._queue.enqueue(
                "benchwitness_ml.recovery_worker.run_recovery_job",
                job.job_id,
                job_id=broker_job_id,
                job_timeout=300,
                result_ttl=60,
                failure_ttl=3600,
            )
        except Exception as exc:
            self._graph.transition_recovery_job(
                job.job_id, "queued", "failed", error=f"queue_unavailable:{type(exc).__name__}"
            )
            raise RecoveryQueueUnavailable("Redis broker could not accept the repair job") from exc
        return self._graph.get_recovery_job(job.job_id)

    def get_job(self, job_id: str) -> RecoveryJobRecord:
        return self._graph.get_recovery_job(job_id)


class RecoveryQueueUnavailable(RuntimeError):
    """The dedicated Redis broker could not accept an approved repair."""


def queue_from_env() -> Queue:
    host = os.environ.get("REDIS_BROKER_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_BROKER_PORT", "6380"))
    return Queue("benchwitness-repair", connection=Redis(host=host, port=port))
