# BenchWitness

BenchWitness will audit ML evaluation integrity using a FalkorDB evidence graph. This repository currently contains **Milestone 1 only**: local infrastructure, a graph connection probe, API health/readiness endpoints, and a minimal React/Vite shell. It has no seeded experiments or reported metrics yet.

## Layout

| Path | Purpose |
|---|---|
| `apps/api/benchwitness_api` | FastAPI app and FalkorDB probe |
| `apps/api/tests` | API smoke and real-graph integration tests |
| `apps/web` | React, TypeScript and Vite application shell |
| `workers/ml` | Reserved for the later CPU training worker |
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

The graph uses `127.0.0.1:6379`; the **separate** Redis job broker uses `127.0.0.1:6380`. Only FalkorDB is checked by `/readyz` in this milestone. The broker has no worker jobs yet. The FalkorDB container uses a named volume; `docker compose down` keeps it.

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

To start the frontend shell:

```sh
npm run dev --prefix apps/web
```

Vite prints the local URL. Opensource UI components and graph-backed product views are planned for later milestones.

## Checks

With Compose running, run the complete backend suite, including the real FalkorDB test:

```sh
uv run pytest
uv run ruff check apps/api
uv run ruff format --check apps/api
uv run mypy
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
```

`uv run pytest -m "not integration"` runs only the API smoke/failure-state tests when the graph is unavailable; it does **not** satisfy the integration gate. Stop local services with `docker compose down` when finished.

## Milestone boundary

No seed command exists yet because source-record lineage is Milestone 2. The [blueprint](PROJECT_BLUEPRINT.md), [strategy](PRE_EVENT_STRATEGY.md), [dataset inventory](DATASET_INVENTORY.md), and [phase plan](DEVELOPMENT_AND_GIT_PLAN.md) describe later work; they are not evidence that those features exist. Human review is required before the next milestone. AI-assisted implementation must be disclosed in the final submission.
