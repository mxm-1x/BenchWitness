# BenchWitness

BenchWitness audits ML evaluation integrity using a FalkorDB evidence graph. Milestones 1–7 provide sample-level lineage audits, deterministic CPU experiment runs, graph-backed impact investigation, approval-gated quarantine, approved clean recovery, typed agent tools with cross-session memory, and a browser workflow. Metrics are calculated from saved predictions; source ancestry and decisions are retained in FalkorDB.

## Layout

| Path | Purpose |
|---|---|
| `apps/api/benchwitness_api` | FastAPI app, synthetic lineage generator, graph seed and audit |
| `apps/api/benchwitness_api/impact.py` | Bounded impact investigation and quarantine approval service |
| `apps/api/benchwitness_api/recovery.py` | Repair approval and Redis dispatch |
| `apps/api/benchwitness_api/agent.py` | Typed local tool routing and verified graph memory |
| `apps/api/tests` | API smoke, deterministic fixture and real-graph integration tests |
| `apps/site` | Selected Next.js landing page and graph-backed workspace on port 3000 |
| `apps/web` | Earlier React/Vite workspace, retained for review |
| `workers/ml/benchwitness_ml` | Deterministic CPU runner and approved repair worker |
| `infra` | Infrastructure notes; root `compose.yaml` is the runnable setup |

## Requirements

- macOS on Apple Silicon, Python 3.12 through `uv`, Node.js 20.19 or newer, npm, and a working Docker Compose daemon.
- No paid API, cloud account, or external runtime service. FalkorDB and the job broker are separate local containers.

## Quick start: run the local demo

First complete the one-time installation in [Install and start on macOS](#install-and-start-on-macos), including `docker compose up -d`. Then start these processes in separate terminals from the repository root. In each terminal, load `.env` before starting a process:

**Terminal 1 — API**

```sh
set -a
source .env
set +a
uv run uvicorn benchwitness_api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — recovery worker**

```sh
set -a
source .env
set +a
uv run benchwitness-worker
```

**Terminal 3 — web app**

```sh
npm run dev --prefix apps/site -- --hostname 127.0.0.1 --port 3000
```

Open <http://127.0.0.1:3000>, launch the workspace, and paste the local `BENCHWITNESS_API_TOKEN` from `.env`. If the graph has no demo data, click **Seed graph** and then **Run baseline evaluations** on the Overview tab. Seeding is idempotent; each baseline evaluation run appends three measured run versions, so skip it when runs are already present. Open **Experiment Ledger** to inspect the confirmed, clean-control, and unknown-lineage cases. The [browser workflow](#run-the-browser-workflow) describes the investigation, approved recovery, and memory steps.

### Data used by the demo

The repository does not contain a downloaded or precomputed dataset file. The checked-in generator creates the complete 400-row synthetic dataset and its split and lineage manifests locally; run `uv run benchwitness-seed-demo` or click **Seed graph** in the workspace. Generated files go under `artifacts/demo/scenarios/synthetic-memorization-v2/`, which Git ignores. The generator and its fixed seed are in the repository, so a clean clone can reproduce the demo without a download, dataset API key, or external data service. Dataset composition and integrity checks are described in [Seed and audit the lineage demo](#seed-and-audit-the-lineage-demo) and [DATASET_INVENTORY.md](DATASET_INVENTORY.md).

## Install and start on macOS

Run from the repository root:

```sh
cp .env.example .env
openssl rand -hex 32
# Paste the generated value into BENCHWITNESS_API_TOKEN in .env.
# Set BENCHWITNESS_APPROVER to the local reviewer's audit label.
set -a
source .env
set +a
nvm use
uv sync --locked
npm ci --prefix apps/web
npm ci --prefix apps/site
docker compose up -d
docker compose ps
```

`nvm use` selects the version in `.nvmrc`. If you do not use nvm, select Node.js 20.19+ by another method before `npm ci`; Vite requires that version. The current macOS machine also has an older `/usr/local/bin/node`, so check `node --version` if Vite reports an engine warning.

The graph uses `127.0.0.1:6379`; the **separate** Redis job broker uses `127.0.0.1:6380`. `/readyz` checks FalkorDB. The FalkorDB container uses a named volume; `docker compose down` keeps it.

Verify the graph engine, then start the API:

```sh
uv run benchwitness-graph-health
uv run uvicorn benchwitness_api.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
curl -i http://127.0.0.1:8000/healthz
curl -i http://127.0.0.1:8000/readyz
```

`/healthz` returns 200 when the API process responds. `/readyz` returns 200 only when a real FalkorDB Cypher query succeeds, otherwise 503. `benchwitness-graph-health` prints JSON and exits nonzero if the graph is unreachable. This query creates no nodes or evaluation claims.

## Seed and audit the lineage demo

With FalkorDB running, seed the deterministic 400-row synthetic source, split manifests, and versioned sample memberships:

```sh
uv run benchwitness-seed-demo
```

The command writes versioned source rows and manifests under `artifacts/demo/scenarios/synthetic-memorization-v2/` (ignored by Git) and idempotently merges the lineage graph. It uses no external dataset, paid API, or hosted service. Every API `POST` requires the bearer token configured in `.env`; read-only health and audit requests do not. You can also seed through the API after starting Uvicorn:

```sh
curl -sS -X POST http://127.0.0.1:8000/api/v1/demo/seed -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN"
curl -sS http://127.0.0.1:8000/api/v1/experiments/demo-v2-contaminated-a/lineage-audit
```

The active scenario is `synthetic-memorization-v2`. It creates 400 synthetic rows with random binary labels independent of the two numeric features, then makes a stratified 300/100 train/evaluation split. It copies 20 held-out rows, with their real source ancestry, into each contaminated training version. The clean control contains the 300 intended training rows; a separate fixture has missing lineage. Auditing `demo-v2-contaminated-a` and `demo-v2-contaminated-b` returns `confirmed`; `demo-v2-clean-control` returns `clean_within_recorded_lineage`; `demo-v2-unknown-lineage` returns `unknown`. Artifacts are stored under `artifacts/demo/scenarios/synthetic-memorization-v2/`, leaving the earlier v1 files intact. The split manifest records the label rule and copy policy. A complete result requires memberships and counts to match manifests, each sample's recorded ancestry to resolve through every parent branch to one canonical source, and graph source IDs/counts to match the source artifact digest. The audit uses fixed parameter-bound Cypher, a three-hop derivation bound, a 100-path response cap, and a query timeout.

## Run and inspect measured demo experiments

After seeding the demo, run the three graph-defined experiments locally:

```sh
uv run benchwitness-run-demo
```

The API equivalent is `POST /api/v1/demo/evaluate`. Each invocation appends three new run versions; repeated runs use new run IDs and artifacts while producing the same metrics for unchanged seeded inputs. The runner uses 1-nearest-neighbor with squared Euclidean distance and deterministic sample-ID tie breaking. Accuracy, positive-class precision/recall/F1, and confusion counts are computed from saved predictions. Each run manifest records dataset IDs, model configuration, metric definition, counts, and checksums. Generated source, prediction, and model artifacts are ignored by Git and stored beneath `artifacts/demo/scenarios/synthetic-memorization-v2/`.

This is a disclosed memorization stress test, not a general benchmark claim. Exact copied records give 1-nearest-neighbor a direct route to recall held-out labels. With the bundled seed, measured contaminated accuracy is 58.0% and clean-control accuracy is 48.0%; positive-class F1 is 60.4% and 50.0%, respectively. Recovery removes the copies and remeasures against the same 100 held-out records. The UI shows measured accuracy and F1 before and after, the split sizes, and both deltas. These are measured outcomes for this fixed synthetic probe; they do not describe expected performance on a representative task. Evaluation blocks if lineage is unknown or artifact integrity checks fail.

## Trace impact and quarantine a result

Use the `canonical_source_record_id` from a confirmed lineage audit. The investigation checks both the source-family index and actual sample ancestry paths, so a missing or stale family label cannot hide a run with recorded lineage to that source. It verifies each candidate's recorded dataset pair and returns exact training/evaluation sample paths with the model configuration, evaluation claim, and measured metric claims. If a candidate run cannot be verified, the report marks its scope incomplete and quarantine is disabled.

```sh
curl -sS -X POST http://127.0.0.1:8000/api/v1/impact -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN" -H 'Content-Type: application/json' -d '{"source_record_id":"<canonical_source_record_id-from-audit>"}'
```

The response includes an `investigation_id`. A quarantine proposal names the exact affected evaluation claim IDs and remains `proposed`; those claims and metrics are unchanged:

```sh
curl -sS -X POST "http://127.0.0.1:8000/api/v1/investigations/<investigation_id>/quarantine-proposals" -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN" -H 'Content-Type: application/json' -d '{"reason":"Confirmed sample-level train/evaluation overlap"}'
```

Only a separate explicit approval request appends the approval decision. Supply the `action_id` returned by the proposal and a reason. The approver identity comes from `BENCHWITNESS_APPROVER`, configured alongside the bearer token:

```sh
curl -sS -X POST "http://127.0.0.1:8000/api/v1/actions/<action_id>/approve" -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN" -H 'Content-Type: application/json' -d '{"reason":"I reviewed the source and sample evidence"}'
curl -sS "http://127.0.0.1:8000/api/v1/investigations/<investigation_id>"
```

The investigation then reports those claims as `quarantined` by following the approved decision edge. Original run records, evaluation claims, and metric values remain stored unchanged. The local bearer token guards every API `POST`, and the configured approver label is recorded with approval. This is a single-reviewer local gate; do not expose the API publicly without deployment-grade authentication and authorization.

### Graph model and key Cypher

FalkorDB is authoritative for source/sample lineage, datasets, experiments and measured runs, evaluation claims, investigation evidence, action proposals and approvals, recovery job state, and agent memory. Dataset and model bytes, prediction files, and split manifests live as local artifacts under `artifacts/`; Redis stores only transient worker messages.

The principal lineage edges are `DatasetVersion -[:CONTAINS]-> SampleVersion`, `SampleVersion -[:DERIVED_FROM]-> SampleVersion|SourceRecord`, and `Experiment -[:TRAINS_ON|TESTS_ON]-> DatasetVersion`. Runs connect to their consumed training/evaluation datasets and model configuration. A measured run links through `HAS_EVALUATION` to an `EvaluationClaim`, which links through `REPORTS` to `MetricClaim`. An `Investigation` establishes a `Finding`; the finding links to `LineageEvidence` and impacted claims. `ActionProposal -[:TARGETS]-> EvaluationClaim` records scope, `ApprovalDecision -[:APPROVES]-> ActionProposal` records explicit approval, and `AgentSession -[:REMEMBERS]-> AgentMemory -[:REFERS_TO]-> Investigation` supports cross-session verification.

The production queries are allowlisted templates in `apps/api/benchwitness_api/graph_lineage.py`. The sample-level audit joins canonical source IDs along bounded derivation paths, rather than inferring contamination from shared dataset names:

```cypher
MATCH (experiment:Experiment {id: $experiment_id})-[:TRAINS_ON]->(training:DatasetVersion)
MATCH (experiment)-[:TESTS_ON]->(evaluation:DatasetVersion)
MATCH (training)-[:CONTAINS]->(training_sample:SampleVersion)
MATCH training_path = (training_sample)-[:DERIVED_FROM*1..3]->(source:SourceRecord)
MATCH (evaluation)-[:CONTAINS]->(evaluation_sample:SampleVersion)
MATCH evaluation_path = (evaluation_sample)-[:DERIVED_FROM*1..3]->(evaluation_source:SourceRecord)
WHERE source.id = evaluation_source.id
RETURN source.id, training.id, training_sample.id, length(training_path),
       evaluation.id, evaluation_sample.id, length(evaluation_path)
LIMIT $limit
```

Impact discovery starts from the canonical record, follows derived sample memberships to the exact consumed dataset, then returns affected run IDs. The implementation runs both a source-family candidate query and this lineage traversal so a stale family label cannot hide recorded ancestry:

```cypher
MATCH (source:SourceRecord {id: $source_record_id})
MATCH (sample:SampleVersion)-[:DERIVED_FROM*1..3]->(source)
MATCH (dataset:DatasetVersion)-[:CONTAINS]->(sample)
MATCH (run:ExperimentRun)-[:TRAINED_ON]->(training:DatasetVersion)
MATCH (run)-[:EVALUATED_ON]->(evaluation:DatasetVersion)
WHERE dataset.id = training.id OR dataset.id = evaluation.id
RETURN DISTINCT run.id, run.experiment_id, training.id, evaluation.id
LIMIT $limit
```

The investigation then traverses from its finding to dependent evaluation and metric claims. All request values are bound parameters; query templates cap derivation depth, row counts, and execution time. The API does not accept user-authored Cypher.

```cypher
MATCH (investigation:Investigation {id: $investigation_id})-[:ESTABLISHED]->
      (finding:Finding)-[:IMPACTS]->(claim:EvaluationClaim)
MATCH (run:ExperimentRun)-[:HAS_EVALUATION]->(claim)
MATCH (run)-[:USES_MODEL_CONFIGURATION]->(model:ModelConfiguration)
MATCH (claim)-[:REPORTS]->(metric:MetricClaim)
RETURN run.id, run.experiment_id, model.id, claim.id, metric.id,
       metric.metric_name, metric.value
LIMIT $limit
```

## Approve and run clean recovery

Start the worker in a third terminal, from the repository root with `.env` sourced as above:

```sh
set -a
source .env
set +a
uv run benchwitness-worker
```

With a confirmed, complete investigation from `/api/v1/impact`, propose a repair. The proposal alone does not enqueue work. Review its target claim IDs, then approve separately with the local bearer token:

```sh
curl -sS -X POST "http://127.0.0.1:8000/api/v1/investigations/<investigation_id>/repair-proposals" -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN" -H 'Content-Type: application/json' -d '{"reason":"Restore the intended held-out split"}'
curl -sS -X POST "http://127.0.0.1:8000/api/v1/repairs/<action_id>/approve" -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN" -H 'Content-Type: application/json' -d '{"reason":"I reviewed the affected claims and approve a clean refit"}'
curl -sS "http://127.0.0.1:8000/api/v1/jobs/<job_id>"
```

The worker verifies the clean training and held-out evaluation memberships against FalkorDB and the saved split manifest, refits the fixed 1-nearest-neighbor classifier on the clean records, calculates fresh predictions and metrics, then appends a recovery experiment/run and hashed model-training-row artifact for each affected original run. `RecoveryJob` state and approval are stored in FalkorDB; Redis holds transient dispatch only. The `repaired_run_ids` in the job response can be inspected against the original run IDs. Repeating approval while queued or after success is idempotent. A broker or worker failure appears as a `failed` graph job; repeating the approval request explicitly retries it. Recovery artifacts are content-checked and reused when a retry resumes a partially completed job. The RQ attempt has a five-minute timeout. When a poll or approval sees a `running` job older than six minutes, it marks that attempt failed with a compare-and-set graph update; approving again retries the same approved repair.

## Typed agent and graph memory

Create a session, then send a typed intent. Use a confirmed source ID from the lineage audit. Supply the returned `session_id` in the message URL:

```sh
curl -sS -X POST http://127.0.0.1:8000/api/v1/agent/sessions -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN"
curl -sS -X POST "http://127.0.0.1:8000/api/v1/agent/sessions/<session_id>/messages" -H "Authorization: Bearer $BENCHWITNESS_API_TOKEN" -H 'Content-Type: application/json' -d '{"intent":"investigate_source","subject_id":"<canonical_source_record_id>"}'
```

Supported intents are `investigate_source`, `audit_experiment`, and `get_job_status`; `subject_id` is the corresponding source, experiment, or job ID. The response names the tools used and returns typed, graph-backed results. A confirmed, complete source investigation creates `AgentMemory` linked to its `Investigation` and `AgentSession`. A new session checks the current bounded run set, manifest hashes, audit results, and exact impact sample paths before recalling that memory. If the graph has changed, it performs a new investigation and reports `memory_status: stale`. It never treats memory alone as proof of current cleanliness. This local agent is deterministic and does not call an LLM or accept executable tool instructions. Repair and quarantine still require their separate explicit approval endpoints.

To demonstrate memory, create a **second** session with the first command and send the same `investigate_source` request using its new `session_id`. Its response should report `memory_status: verified` and the prior `investigation_id` if no run or lineage changed. Run `uv run benchwitness-run-demo` again, then repeat from a third session: the additional measured runs make the earlier snapshot stale, so a new investigation is recorded. `GET /api/v1/agent/sessions/<session_id>` confirms a session exists in FalkorDB.

## Run the browser workflow

Start FalkorDB and the separate Redis broker with `docker compose up -d`, then run the API and worker in separate terminals after sourcing `.env` in each. Start the selected web app in a third terminal:

```sh
npm run dev --prefix apps/site -- --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000`. Paste `BENCHWITNESS_API_TOKEN` into the local workspace token field; it is kept in that browser tab. Click **Seed graph**, then **Run baseline evaluations** if the graph has no recorded runs. Select a confirmed experiment, inspect its exact sample ancestry, and click **Investigate source**. Review target claim IDs, propose clean repair, enter a separate approval reason, and approve. The workspace polls the real worker job and loads saved before/after run metrics after success. Start another agent session and investigate the same source to inspect verified graph memory. Quarantine has a separate proposal and approval action.

The experiment ledger reads `GET /api/v1/overview`, which contains current audits and a bounded list of measured run versions. The evidence view reads an investigation by ID, and the job panel polls `GET /api/v1/jobs/<job_id>` while work is pending. Empty, unavailable, and failed states are shown explicitly. Frontend library attribution is in [apps/site/ATTRIBUTION.md](apps/site/ATTRIBUTION.md); the earlier Vite adaptation is in [apps/web/OPENSOURCE_UI_ATTRIBUTION.md](apps/web/OPENSOURCE_UI_ATTRIBUTION.md). No hosted service or paid API is required.

## Checks

With Compose running, run the complete backend suite, including the real FalkorDB test:

```sh
uv run pytest
uv run ruff check apps/api workers/ml
uv run ruff format --check apps/api workers/ml
uv run mypy
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
npm run lint --prefix apps/site
npm run typecheck --prefix apps/site
npm run build --prefix apps/site
```

`uv run pytest -m "not integration"` runs API and deterministic fixture tests when the graph is unavailable; it does **not** satisfy the real-graph integration gate. Stop local services with `docker compose down` when finished.

To verify the setup from new, isolated Docker volumes (without touching the normal `benchwitness` containers or graph), run:

```sh
./scripts/verify_fresh_start.sh
```

The script binds an isolated Compose project to `127.0.0.1:16379` and `127.0.0.1:16380`, seeds and measures the demo, restarts FalkorDB to verify persisted lineage, then runs the integration suite and quality checks. It stops its containers but keeps its uniquely named FalkorDB volume for inspection. Set `BENCHWITNESS_FRESH_FALKORDB_BIND_PORT` and `BENCHWITNESS_FRESH_REDIS_BIND_PORT` if those ports are occupied; these names avoid accidentally inheriting the standard development ports from a sourced `.env`. The script prints the exact volume name and a command to remove that isolated test volume when you choose.

## Milestone boundary

Milestones 1–7 are implemented. Fresh-volume seed, evaluation, restart persistence, integration, lint, type, and frontend build checks passed on 2026-10-16. The remaining release steps are human review, recording/reviewing the demo video, and submitting it with the selected track. Review [AI assistance disclosure](docs/AI_ASSISTANCE_DISCLOSURE.md), [demo script](docs/DEMO_SCRIPT.md), and [submission checklist](docs/SUBMISSION_CHECKLIST.md) before submitting. The [blueprint](PROJECT_BLUEPRINT.md), [strategy](PRE_EVENT_STRATEGY.md), [dataset inventory](DATASET_INVENTORY.md), and [phase plan](DEVELOPMENT_AND_GIT_PLAN.md) provide background.
