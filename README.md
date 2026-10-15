# BenchWitness

BenchWitness audits ML evaluation integrity using a FalkorDB evidence graph. **Milestone 3** adds a deterministic CPU 1-nearest-neighbor experiment runner. The runner resolves samples through the graph, verifies source artifacts, writes immutable prediction and run manifests, calculates metrics from those predictions, and records each run and its exact dataset versions in FalkorDB.

## Layout

| Path | Purpose |
|---|---|
| `apps/api/benchwitness_api` | FastAPI app, synthetic lineage generator, graph seed and audit |
| `apps/api/tests` | API smoke, deterministic fixture and real-graph integration tests |
| `apps/web` | React, TypeScript and Vite application shell |
| `workers/ml/benchwitness_ml` | Deterministic CPU experiment runner and run CLI |
| `infra` | Infrastructure notes; root `compose.yaml` is the runnable setup |

## Requirements

- macOS on Apple Silicon, Python 3.12 through `uv`, Node.js 20.19 or newer, npm, and a working Docker Compose daemon.
- No paid API, cloud account, or external runtime service. FalkorDB and the job broker are separate local containers.

## Install and start on macOS

Run from the repository root:

```sh
cp .env.example .env
set -a
source .env
set +a
nvm use
uv sync --locked
npm ci --prefix apps/web
docker compose up -d
docker compose ps
```

`nvm use` selects the version in `.nvmrc`. If you do not use nvm, select Node.js 20.19+ by another method before `npm ci`; Vite requires that version. The current macOS machine also has an older `/usr/local/bin/node`, so check `node --version` if Vite reports an engine warning.

The graph uses `127.0.0.1:6379`; the **separate** Redis job broker uses `127.0.0.1:6380`. `/readyz` checks FalkorDB. Redis has no worker jobs yet. The FalkorDB container uses a named volume; `docker compose down` keeps it.

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

The command writes source rows and manifests under `artifacts/demo/` (ignored by Git) and idempotently merges the lineage graph. It uses no external dataset, paid API, or hosted service. You can also seed through the API after starting Uvicorn:

```sh
curl -sS -X POST http://127.0.0.1:8000/api/v1/demo/seed
curl -sS http://127.0.0.1:8000/api/v1/experiments/demo-contaminated-a/lineage-audit
```

The scenario records one held-out canonical source row copied into each of two training versions, a clean training control from the same source family, and a sample with missing lineage. Auditing `demo-contaminated-a` and `demo-contaminated-b` returns `confirmed` with exact source and sample IDs; `demo-clean-control` returns `clean_within_recorded_lineage`; `demo-unknown-lineage` returns `unknown`. A complete result requires graph memberships and counts to match local manifests, and graph source IDs and counts to match the source artifact digest. The audit uses fixed parameter-bound Cypher, a three-hop derivation bound, a 100-path response cap, and a query timeout.

## Run and inspect measured demo experiments

After seeding the demo, run the three graph-defined experiments locally:

```sh
uv run benchwitness-run-demo
```

The API equivalent is `POST /api/v1/demo/evaluate`. Each invocation appends three new run versions; repeated runs use new run IDs and artifacts while producing the same metrics for unchanged seeded inputs. The runner uses 1-nearest-neighbor with squared Euclidean distance and deterministic sample-ID tie breaking. Accuracy, positive-class precision/recall/F1, and confusion counts are computed from saved predictions. Each run manifest records dataset IDs, model configuration, metric definition, counts, and checksums. Generated artifacts under `artifacts/runs/` are ignored by Git.

These are measured results on the included synthetic scenario, not a promise that contamination changes scores in a particular direction. The API runs this small demo synchronously. Redis remains reserved for the later approved recovery job milestone. Evaluation blocks if lineage is unknown or artifact integrity checks fail.

To start the frontend shell:

```sh
npm run dev --prefix apps/web
```

Vite prints the local URL. Opensource UI components and graph-backed product views are planned for later milestones.

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
```

`uv run pytest -m "not integration"` runs API and deterministic fixture tests when the graph is unavailable; it does **not** satisfy the real-graph integration gate. Stop local services with `docker compose down` when finished.

## Milestone boundary

Milestone 4 adds impact traversal and explicit quarantine approval. It is not implemented here. Do not treat lineage overlap as a measured score impact. The [blueprint](PROJECT_BLUEPRINT.md), [strategy](PRE_EVENT_STRATEGY.md), [dataset inventory](DATASET_INVENTORY.md), and [phase plan](DEVELOPMENT_AND_GIT_PLAN.md) describe later work; they are not evidence that those features exist. Human review is required before the next milestone. AI-assisted implementation must be disclosed in the final submission.
