#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

project="benchwitness-fresh-$(date +%Y%m%d%H%M%S)-$$"
export FALKORDB_BIND_PORT="${BENCHWITNESS_FRESH_FALKORDB_BIND_PORT:-16379}"
export REDIS_BROKER_BIND_PORT="${BENCHWITNESS_FRESH_REDIS_BIND_PORT:-16380}"
export FALKORDB_HOST=127.0.0.1
export FALKORDB_PORT="$FALKORDB_BIND_PORT"
export FALKORDB_GRAPH="benchwitness_fresh_start"
export REDIS_BROKER_HOST=127.0.0.1
export REDIS_BROKER_PORT="$REDIS_BROKER_BIND_PORT"
export BENCHWITNESS_ARTIFACT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/benchwitness-fresh-artifacts.XXXXXX")"

compose() {
  docker compose --project-name "$project" "$@"
}

cleanup() {
  compose down --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$BENCHWITNESS_ARTIFACT_DIR"
}
trap cleanup EXIT

echo "Starting isolated, empty FalkorDB and Redis volumes in Compose project $project"
compose up -d --wait

echo "Checking the new graph, then seeding and measuring the synthetic demo"
uv sync --locked
npm ci --prefix apps/web
npm ci --prefix apps/site
uv run benchwitness-graph-health
uv run benchwitness-seed-demo
uv run benchwitness-run-demo

echo "Restarting FalkorDB and checking persisted lineage"
compose restart falkordb
for attempt in $(seq 1 30); do
  if uv run benchwitness-graph-health >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    echo "FalkorDB did not become reachable after restart" >&2
    exit 1
  fi
  sleep 1
done
uv run python -c 'from benchwitness_api.graph_lineage import GraphLineageStore; from benchwitness_api.settings import GraphSettings; store = GraphLineageStore(GraphSettings.from_env()); assert len(store.list_demo_experiment_ids()) == 4; assert store.audit("demo-v2-contaminated-a").status == "confirmed"; assert store.audit("demo-v2-clean-control").status == "clean_within_recorded_lineage"; print("FalkorDB restart persistence verified")'

echo "Running backend, integration, lint, type, and frontend production checks"
uv run pytest -q
uv run ruff check apps/api workers/ml
uv run ruff format --check apps/api workers/ml
uv run mypy
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm run build --prefix apps/web
npm run check --prefix apps/site

echo "Fresh-start verification passed. The test containers are stopped; the named graph volume is retained."
echo "Remove only this isolated test volume later with: docker volume rm ${project}_falkordb_data"
