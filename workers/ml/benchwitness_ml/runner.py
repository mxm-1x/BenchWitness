"""Measured, deterministic CPU experiment runs for the seeded lineage scenario."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from benchwitness_api.graph_lineage import (
    ExperimentRunRecord,
    GraphLineageStore,
    ResolvedDataset,
)
from benchwitness_api.lineage import source_records_digest

_DEMO_EXPERIMENTS = (
    "demo-contaminated-a",
    "demo-contaminated-b",
    "demo-clean-control",
)
_MODEL_ID = "1nn-euclidean-v1"
_MODEL_CONFIG = {
    "algorithm": "1-nearest-neighbor",
    "distance": "squared-euclidean",
    "feature_columns": ["x1", "x2"],
    "label_column": "label",
    "tie_break": "sample_id_ascending",
}


class EvaluationBlocked(RuntimeError):
    """A run cannot proceed because the graph audit or input lineage is incomplete."""


@dataclass(frozen=True)
class SourceRow:
    features: tuple[float, float]
    label: int


@dataclass(frozen=True)
class TrainingSample:
    sample_id: str
    source_record_id: str
    features: tuple[float, float]
    label: int


@dataclass(frozen=True)
class Prediction:
    sample_id: str
    source_record_id: str
    actual: int
    predicted: int


@dataclass(frozen=True)
class BinaryMetrics:
    sample_count: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int


class DemoEvaluationRunner:
    """Run the fixed A/B/control experiments from graph-resolved sample inputs."""

    def __init__(self, graph: GraphLineageStore, artifact_dir: Path) -> None:
        self._graph = graph
        self._artifact_dir = artifact_dir

    def run_all(self) -> list[ExperimentRunRecord]:
        runs: list[ExperimentRunRecord] = []
        source_rows: dict[str, SourceRow] | None = None
        verified_source_hash: str | None = None
        for experiment_id in _DEMO_EXPERIMENTS:
            audit = self._graph.audit(experiment_id)
            if not audit.coverage_complete or audit.status not in (
                "confirmed",
                "clean_within_recorded_lineage",
            ):
                raise EvaluationBlocked(
                    f"experiment {experiment_id} does not have complete verified lineage"
                )

            training = self._graph.resolve_dataset(audit.training_dataset_id, "training")
            evaluation = self._graph.resolve_dataset(audit.evaluation_dataset_id, "evaluation")
            if (
                training.source_manifest_hash != evaluation.source_manifest_hash
                or training.source_record_count != evaluation.source_record_count
            ):
                raise EvaluationBlocked(
                    "training and evaluation datasets use different source manifests"
                )
            if verified_source_hash != training.source_manifest_hash:
                source_rows = self._load_source_rows(
                    training.source_manifest_hash, training.source_record_count
                )
                verified_source_hash = training.source_manifest_hash
            if source_rows is None:
                raise EvaluationBlocked("verified source rows could not be loaded")

            training_samples = self._materialize(training, source_rows)
            evaluation_samples = self._materialize(evaluation, source_rows)
            if not training_samples or not evaluation_samples:
                raise EvaluationBlocked("training and evaluation datasets must be nonempty")
            predictions = self._predict(training_samples, evaluation_samples)
            metrics = self._metrics(predictions)
            run = self._write_run_artifacts(
                experiment_id,
                training,
                evaluation,
                len(training_samples),
                predictions,
                metrics,
            )
            self._graph.record_run(run)
            runs.append(self._graph.get_run(run.run_id))
        return runs

    def run_recovery(self, original_run_id: str, job_id: str) -> tuple[ExperimentRunRecord, str]:
        """Refit 1-NN on the verified intended split and measure the held-out set."""
        original = self._graph.get_run(original_run_id)
        if original.model_id != _MODEL_ID or original.model_config_json != json.dumps(
            _MODEL_CONFIG, sort_keys=True, separators=(",", ":")
        ):
            raise EvaluationBlocked("original model configuration is unsupported for recovery")
        contaminated_audit = self._graph.audit(original.experiment_id)
        if (
            contaminated_audit.status != "confirmed"
            or not contaminated_audit.coverage_complete
            or original.training_dataset_id != contaminated_audit.training_dataset_id
            or original.evaluation_dataset_id != contaminated_audit.evaluation_dataset_id
        ):
            raise EvaluationBlocked("original run does not have verified contaminated lineage")
        clean = self._graph.resolve_dataset("dataset:train-clean-control-v1", "training")
        evaluation = self._graph.resolve_dataset(original.evaluation_dataset_id, "evaluation")
        split_path = self._artifact_dir / "split_manifest.json"
        try:
            split = json.loads(split_path.read_text(encoding="utf-8"))
            train_ids = {sample.source_record_id for sample in clean.samples}
            eval_ids = {sample.source_record_id for sample in evaluation.samples}
            if (
                sorted(train_ids) != split["train_source_record_ids"]
                or sorted(eval_ids) != split["eval_source_record_ids"]
                or train_ids & eval_ids
                or clean.source_manifest_hash != evaluation.source_manifest_hash
                or split["source_manifest_hash"] != clean.source_manifest_hash
            ):
                raise EvaluationBlocked("clean split does not match verified graph memberships")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise EvaluationBlocked("clean split artifact is invalid") from exc
        source_rows = self._load_source_rows(clean.source_manifest_hash, clean.source_record_count)
        training_samples = self._materialize(clean, source_rows)
        evaluation_samples = self._materialize(evaluation, source_rows)
        predictions = self._predict(training_samples, evaluation_samples)
        metrics = self._metrics(predictions)
        stable_id = hashlib.sha256(f"{job_id}\0{original_run_id}".encode()).hexdigest()[:24]
        run_id = f"run:repair:{stable_id}"
        experiment_id = f"experiment:repair:{stable_id}"
        self._graph.create_recovery_experiment(
            job_id, original_run_id, experiment_id, clean.dataset_id, evaluation.dataset_id
        )
        model_bytes = b"".join(
            (json.dumps(asdict(sample), sort_keys=True, separators=(",", ":")) + "\n").encode()
            for sample in training_samples
        )
        model_sha256 = hashlib.sha256(model_bytes).hexdigest()
        run = self._write_run_artifacts(
            experiment_id,
            clean,
            evaluation,
            len(training_samples),
            predictions,
            metrics,
            run_id=run_id,
            model_bytes=model_bytes,
        )
        self._graph.record_run(run)
        self._graph.link_recovery_run(
            job_id,
            original_run_id,
            run_id,
            str(Path(run.artifact_path) / "model-training-rows.jsonl"),
            model_sha256,
        )
        return self._graph.get_run(run_id), model_sha256

    def _load_source_rows(self, expected_digest: str, expected_count: int) -> dict[str, SourceRow]:
        source_path = self._artifact_dir / "source_records.jsonl"
        try:
            raw_rows = [
                json.loads(line) for line in source_path.read_text(encoding="utf-8").splitlines()
            ]
            if (
                source_records_digest(raw_rows) != expected_digest
                or len(raw_rows) != expected_count
            ):
                raise EvaluationBlocked(
                    "source artifact digest or count does not match graph metadata"
                )
            source_rows: dict[str, SourceRow] = {}
            for raw_row in raw_rows:
                source_id = str(raw_row["source_record_id"])
                raw_features = raw_row["features"]
                label = raw_row["label"]
                if (
                    not isinstance(raw_features, list)
                    or len(raw_features) != 2
                    or label not in (0, 1)
                    or source_id in source_rows
                ):
                    raise EvaluationBlocked("source artifact contains an invalid or duplicate row")
                source_rows[source_id] = SourceRow(
                    features=(float(raw_features[0]), float(raw_features[1])),
                    label=int(label),
                )
            return source_rows
        except EvaluationBlocked:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise EvaluationBlocked("source artifact could not be read") from exc

    @staticmethod
    def _materialize(
        dataset: ResolvedDataset, source_rows: dict[str, SourceRow]
    ) -> list[TrainingSample]:
        samples: list[TrainingSample] = []
        for membership in dataset.samples:
            source = source_rows.get(membership.source_record_id)
            if source is None:
                raise EvaluationBlocked(
                    f"sample {membership.sample_id} resolves to a missing source row"
                )
            samples.append(
                TrainingSample(
                    sample_id=membership.sample_id,
                    source_record_id=membership.source_record_id,
                    features=source.features,
                    label=source.label,
                )
            )
        return samples

    @staticmethod
    def _predict(
        training_samples: list[TrainingSample], evaluation_samples: list[TrainingSample]
    ) -> list[Prediction]:
        predictions: list[Prediction] = []
        for evaluation in evaluation_samples:
            nearest = min(
                training_samples,
                key=lambda training: (
                    (training.features[0] - evaluation.features[0]) ** 2
                    + (training.features[1] - evaluation.features[1]) ** 2,
                    training.sample_id,
                ),
            )
            predictions.append(
                Prediction(
                    sample_id=evaluation.sample_id,
                    source_record_id=evaluation.source_record_id,
                    actual=evaluation.label,
                    predicted=nearest.label,
                )
            )
        return predictions

    @staticmethod
    def _metrics(predictions: list[Prediction]) -> BinaryMetrics:
        if not predictions:
            raise EvaluationBlocked("cannot calculate metrics for an empty prediction set")
        true_positive = sum(p.actual == 1 and p.predicted == 1 for p in predictions)
        false_positive = sum(p.actual == 0 and p.predicted == 1 for p in predictions)
        true_negative = sum(p.actual == 0 and p.predicted == 0 for p in predictions)
        false_negative = sum(p.actual == 1 and p.predicted == 0 for p in predictions)
        count = len(predictions)
        accuracy = (true_positive + true_negative) / count
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return BinaryMetrics(
            sample_count=count,
            accuracy=accuracy,
            precision=precision,
            recall=recall,
            f1=f1,
            true_positive=true_positive,
            false_positive=false_positive,
            true_negative=true_negative,
            false_negative=false_negative,
        )

    def _write_run_artifacts(
        self,
        experiment_id: str,
        training: ResolvedDataset,
        evaluation: ResolvedDataset,
        training_sample_count: int,
        predictions: list[Prediction],
        metrics: BinaryMetrics,
        *,
        run_id: str | None = None,
        model_bytes: bytes | None = None,
    ) -> ExperimentRunRecord:
        run_id = run_id or f"run-{experiment_id}-{uuid4().hex}"
        created_at = datetime.now(UTC).isoformat(timespec="milliseconds")
        python_version = platform.python_version()
        prediction_bytes = b"".join(
            (json.dumps(asdict(prediction), sort_keys=True, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            for prediction in predictions
        )
        prediction_sha256 = hashlib.sha256(prediction_bytes).hexdigest()
        model_config = json.dumps(_MODEL_CONFIG, sort_keys=True, separators=(",", ":"))
        artifact_dir = self._artifact_dir / "runs" / run_id
        artifact_dir.mkdir(parents=True, exist_ok=False)
        prediction_path = artifact_dir / "predictions.jsonl"
        self._write_atomic(prediction_path, prediction_bytes)
        if model_bytes is not None:
            self._write_atomic(artifact_dir / "model-training-rows.jsonl", model_bytes)

        manifest_payload: dict[str, Any] = {
            "run_id": run_id,
            "experiment_id": experiment_id,
            "model_id": _MODEL_ID,
            "model_config": _MODEL_CONFIG,
            "created_at": created_at,
            "python_version": python_version,
            "training_dataset_id": training.dataset_id,
            "training_source_manifest_hash": training.source_manifest_hash,
            "training_sample_count": training_sample_count,
            "evaluation_dataset_id": evaluation.dataset_id,
            "evaluation_source_manifest_hash": evaluation.source_manifest_hash,
            "evaluation_sample_count": metrics.sample_count,
            "metric_definition": "binary positive-class precision, recall, f1; unweighted accuracy",
            "metrics": asdict(metrics),
            "prediction_sha256": prediction_sha256,
        }
        if model_bytes is not None:
            manifest_payload["model_sha256"] = hashlib.sha256(model_bytes).hexdigest()
        manifest_bytes = json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        manifest_payload["manifest_sha256"] = manifest_sha256
        manifest_path = artifact_dir / "manifest.json"
        self._write_atomic(
            manifest_path,
            (json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

        return ExperimentRunRecord(
            run_id=run_id,
            experiment_id=experiment_id,
            training_dataset_id=training.dataset_id,
            evaluation_dataset_id=evaluation.dataset_id,
            model_id=_MODEL_ID,
            model_config_json=model_config,
            created_at=created_at,
            python_version=python_version,
            training_sample_count=training_sample_count,
            evaluation_sample_count=metrics.sample_count,
            accuracy=metrics.accuracy,
            precision=metrics.precision,
            recall=metrics.recall,
            f1=metrics.f1,
            true_positive=metrics.true_positive,
            false_positive=metrics.false_positive,
            true_negative=metrics.true_negative,
            false_negative=metrics.false_negative,
            prediction_sha256=prediction_sha256,
            manifest_sha256=manifest_sha256,
            artifact_path=str(artifact_dir),
        )

    @staticmethod
    def _write_atomic(path: Path, contents: bytes) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(contents)
        temporary.replace(path)
