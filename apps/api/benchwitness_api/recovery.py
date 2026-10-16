"""Explicit repair approval and Redis dispatch; FalkorDB owns the job state."""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from uuid import uuid4

from redis import Redis
from rq import Queue

from benchwitness_api.graph_lineage import (
    ActionNotAllowed,
    GraphLineageStore,
    QuarantineActionRecord,
    RecoveryJobRecord,
)

REPAIR_JOB_TIMEOUT_SECONDS = 300
REPAIR_JOB_STALE_GRACE_SECONDS = 60


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
        job = self._mark_stale_if_needed(self._graph.create_recovery_job(action_id, original_ids))
        if job.status in ("queued", "running", "succeeded"):
            return job
        expected_status = job.status
        if expected_status not in ("pending_enqueue", "failed"):
            return job
        if not self._graph.transition_recovery_job(job.job_id, expected_status, "queued"):
            return self._graph.get_recovery_job(job.job_id)
        try:
            broker_job_id = (
                "bw-repair-"
                + hashlib.sha256(job.job_id.encode()).hexdigest()[:20]
                + "-"
                + uuid4().hex[:12]
            )
            self._queue.enqueue(
                "benchwitness_ml.recovery_worker.run_recovery_job",
                job.job_id,
                job_id=broker_job_id,
                job_timeout=REPAIR_JOB_TIMEOUT_SECONDS,
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
        return self._mark_stale_if_needed(self._graph.get_recovery_job(job_id))

    def _mark_stale_if_needed(self, job: RecoveryJobRecord) -> RecoveryJobRecord:
        if job.status != "running" or not job.started_at:
            return job
        try:
            started_at = datetime.fromisoformat(job.started_at)
        except ValueError:
            return job
        if started_at.tzinfo is None:
            return job
        age = (datetime.now(UTC) - started_at.astimezone(UTC)).total_seconds()
        if age <= REPAIR_JOB_TIMEOUT_SECONDS + REPAIR_JOB_STALE_GRACE_SECONDS:
            return job
        self._graph.fail_stale_recovery_job(job.job_id, job.started_at)
        return self._graph.get_recovery_job(job.job_id)


class RecoveryQueueUnavailable(RuntimeError):
    """The dedicated Redis broker could not accept an approved repair."""


def queue_from_env() -> Queue:
    host = os.environ.get("REDIS_BROKER_HOST", "127.0.0.1")
    port = int(os.environ.get("REDIS_BROKER_PORT", "6380"))
    return Queue("benchwitness-repair", connection=Redis(host=host, port=port))
