# BenchWitness — Hackathon Engineering Blueprint

**Status:** planning blueprint; Milestone 1 foundation began after the event opened.
**Event:** WeMakeDevs × FalkorDB Graph Hacks, 15–18 October 2026 (IST)
**Primary track:** Agents That Act on Connected Data
**Secondary track, only if demonstrated:** Agent Memory and Coordination
**Budget:** zero service spend; full demo runs locally without paid APIs, promotional credits, or payment-card trials.

See [PRE_EVENT_STRATEGY.md](PRE_EVENT_STRATEGY.md) for the updated product, architecture, UI, agent, business, and demo planning notes. These remain pre-event discussion notes.
See [DEVELOPMENT_AND_GIT_PLAN.md](DEVELOPMENT_AND_GIT_PLAN.md) for the phase and GitHub commit plan.
See [DATASET_INVENTORY.md](DATASET_INVENTORY.md) for the required synthetic source, derived manifests, controls, and optional licensed public data.

> Compliance: The organizers permit ideas, notes, graph sketches and diagrams before the start. Main coding and design work must begin **after 15 October 2026 at 12:01 AM IST**. Do not scaffold, generate implementation files, or start building before then. AI-assisted work must be disclosed, verified, and understood by the participant.

## 1. One-paragraph pitch

BenchWitness is a graph-native AI agent that audits ML evaluation integrity. Given a collection of versioned training datasets, evaluation datasets and experiment runs, it traces record-level provenance to detect confirmed training/evaluation overlap, propagates the impact through multiple evaluation claims, quarantines invalid results after approval, and performs a reproducible clean retraining/re-evaluation. It stores evidence and decisions as a persistent FalkorDB graph, making every conclusion and action inspectable.

**Tagline:** Trace the data. Challenge the score. Prove the recovery.

## 2. Who benefits and what counts as success

Users: ML scientists, model-evaluation engineers, applied AI teams, and benchmark maintainers.

Core user story: “A source record was copied into training after the test split. Which model scores are now untrustworthy, what evidence proves it, and can you recover a valid comparison?”

A compelling demo must prove all of the following:
1. More than one evaluation can be affected by a single source-record contamination event.
2. FalkorDB stores actual dataset membership, source-record ancestry, model and evaluation dependencies, and prior investigation memory.
3. An agent tool uses bounded graph traversals to produce a concrete evidence path.
4. Impacted evaluations are marked `suspect`/`quarantined`, with old claims retained.
5. After explicit approval, a small model is **refitted** without contaminating training records and re-evaluated against a held-out set.
6. Scores are calculated from real predictions; never hardcode expected values or a forced score drop.
7. A new agent session can retrieve the earlier investigation and act differently because of it.
8. The core auditing and impact propagation stop working when FalkorDB is unavailable.

## 3. Scope and non-goals

### Hackathon MVP (must ship)
- One seeded, deterministic, entirely synthetic/publicly licensed tabular classification scenario.
- Three lightweight experiment runs sharing some data ancestry; at least two actually affected.
- Record-level provenance, explicit transformations, dataset versions and membership.
- Training/evaluation overlap audit with a `confirmed` result only for defensible record-level identity.
- Multi-hop impact propagation from contaminated source records to evaluation runs and metrics.
- Human approval for quarantine/repair.
- CPU-only training/retraining and evaluation with auditable artifacts.
- Persistent agent investigation notes, evidence and decisions in FalkorDB.
- Polished dashboard: experiments, interactive evidence path, investigation details, before/after results, agent activity.
- One-command local startup, seed, end-to-end demo, test suite, README, video.

### Explicit non-goals
- Arbitrary ML framework support; arbitrary user-supplied executable training code.
- Real-world private datasets or claims about opaque proprietary LLM training corpora.
- Unbounded graph paths, unrestricted model-written Cypher or untrusted shell execution.
- Multiple roles/auth, billing, complex multi-tenancy, billing telemetry or a generic MLOps platform.
- Model registry, feature store, Kubernetes, Kafka, Spark, paid embeddings, or large local LLMs.
- Fully autonomous destructive repair. Never erase original claims.

### Optional only after MVP works
- Similarity detection as a separate `suspected` evidence class (never label as confirmed solely from semantic similarity).
- Exportable provenance report, shareable investigation link, human-readable chain of custody.
- Cross-session memory that suppresses repeated known false positives.
- Optional polish that depends on paid services or a hosted runtime.

## 4. Suggested technology stack

| Layer | Choice | Rationale |
|---|---|---|
| UI | React + TypeScript + Vite | Fast, clear SPA, mature ecosystem |
| UI styling | Tailwind CSS + Opensource UI components | Copy suitable React components into the event-time app; review Vite compatibility and accessibility |
| Client data | TanStack Query | API caching, mutations and polling |
| Routes | React Router | Small number of dashboard pages |
| Graph visualization | Cytoscape.js | Visualize bounded evidence subgraphs, not full raw database |
| Backend HTTP | Python 3.12+ + FastAPI | Python ML integration, OpenAPI contracts |
| Schemas | Pydantic v2 | Validated request/response data |
| Packaging | uv + pinned lockfile | Reproducible installation |
| Graph database | FalkorDB + official `falkordb` Python client | Central graph, query and memory functionality |
| Agent workflow | LangGraph + typed, allowlisted tools | Inspectable decision flow; LLM remains optional |
| LLM | No required LLM; optional small local model only after core demo works | Zero service spend and stable offline demo |
| Experiment | scikit-learn + NumPy + pandas + joblib | Fast genuine model fits and predictions |
| Job execution | RQ worker + dedicated Redis | Separate CPU compute, retries, observable jobs |
| Artifacts | Local versioned files first, S3-compatible optional | No needless infra; content hashes + graph metadata |
| Quality | pytest, Ruff, mypy or Pyright, Vitest, Playwright, pre-commit | Unit, contract and end-to-end verification |
| Local deployment | Docker Compose; frontend dev server | Isolated graph and queue, easy setup |
| CI | GitHub Actions | Lint, tests, build, no secrets in repo |

`Redis` in the worker queue is a separate service from the Redis-protocol FalkorDB deployment. Never use FalkorDB as an assumed drop-in general-purpose RQ Redis broker.

## 5. Architecture (logical)

```text
React Dashboard + Cytoscape.js
        |   REST (poll jobs / investigation states)
        v
FastAPI API + Pydantic
        |
        +--> Agent Orchestrator (LangGraph for typed flow)
        |        +--> Allowlisted graph investigation tools
        |        +--> Optional small local model (intent/explanation only)
        |
        +--> Domain Services (ingestion / leakage / impact / repair)
        |        +--> FalkorDB Repository (typed, parameterized Cypher)
        |        +--> Artifact Store (CSV, model joblib, manifests)
        |
        +--> Redis RQ queue --> Python worker
                                     |
                                     +--> scikit-learn train/eval
                                     +--> immutable artifact manifest
                                     +--> write graph results via service
```

This is a **modular monolith with a separate compute worker**, not a microservices application. Keep frontend, API, and worker as cohesive modules in one monorepo.

**Truth boundaries:** FalkorDB is authoritative for experiments, relationships, affected status, evidence, decisions, graph-backed memory and evaluation metadata; artifact storage holds bytes; queue Redis holds ephemeral job traffic. A graphical display alone never establishes lineage.

## 6. Graph model — initial sketch; refine/verify during event

Nodes (all carry stable opaque `id` and relevant timestamps/version hashes):
- `SourceRecord`: immutable canonical source identity; optionally a content hash; NOT a generic parent dataset.
- `SampleVersion`: versioned row or transformed sample, with transformation metadata and content digest.
- `DatasetVersion`: role-specific versioned collection, manifest hash, immutable membership.
- `Experiment`: name, exact config, seed, code/environment version.
- `TrainingRun`: inputs, status, time, artifact checksum.
- `ModelVersion`: model artifact hash, algorithm and hyperparameters.
- `EvaluationRun`: evaluated model, evaluated set, metric definition, status.
- `Metric`: actual measured numeric value, evaluation run, metric name, validity status.
- `Investigation`: trigger, status, scope, time, outcome.
- `Finding`: `confirmed | suspected | unknown`, rule, evidence source, graph paths.
- `Action`: proposed/approved/executed/failed, reason, idempotency key.
- `AgentSession` and `AgentMemory`: prior evidence, verified outcomes, timestamps and provenance.

Suggested edges (names/orientation may be refined during the event):
- `(DatasetVersion)-[:CONTAINS]->(SampleVersion)`
- `(SampleVersion)-[:DERIVED_FROM]->(SourceRecord | SampleVersion)`
- `(Experiment)-[:TRAINS_ON]->(DatasetVersion)`
- `(Experiment)-[:TESTS_ON]->(DatasetVersion)`
- `(TrainingRun)-[:BELONGS_TO]->(Experiment)`
- `(TrainingRun)-[:PRODUCED]->(ModelVersion)`
- `(EvaluationRun)-[:EVALUATES]->(ModelVersion)`
- `(EvaluationRun)-[:USES_DATASET]->(DatasetVersion)`
- `(EvaluationRun)-[:REPORTS]->(Metric)`
- `(Finding)-[:IMPACTS]->(Metric | EvaluationRun)`
- `(Investigation)-[:ESTABLISHED]->(Finding)`
- `(Action)-[:BASED_ON]->(Finding)`
- `(AgentSession)-[:REMEMBERS]->(AgentMemory)`
- `(AgentMemory)-[:REFERS_TO]->(Investigation | Finding | Action)`

### Defensible contamination rules
- `confirmed`: SAME canonical source-record ancestry appears in **training and evaluation memberships for the same experiment**, with actual recorded derivation links. A direct payload-exact duplicate can be confirmed under a separate documented policy if proper sample identity is available.
- `suspected`: normalized near-duplicate or feature similarity, missing transformation evidence, ambiguous source identity. It needs human validation.
- `unknown`: missing lineage; DO NOT claim the dataset is clean.
- `clean_under_recorded_lineage`: no matched overlap in the available complete sample records; only assert the boundaries of what was tested.
- A common parent *dataset* does not mean samples overlap. Do not treat ordinary shared dataset origin as leakage.
- Query bounds (e.g. 1..5 hops) and result caps must be explicit. Track truncated analysis and refuse absolute cleanliness claims on incomplete results.
- Propagation follows concrete dependency edges: finding -> affected evaluation -> metric/claim/report; do not arbitrarily invalidate unrelated models.
- Idempotent ingestion, stable IDs and versioned manifests are important so reruns do not fabricate new provenance.

## 7. One experimental scenario

Use a fully synthetic tabular dataset or scikit-learn generation with a fixed seed and small row count (e.g., 400–800), after the hackathon starts. Prefer one meaningful task to multiple superficial demos.

Proposed experiment:
1. Generate unique source-row IDs and features/labels; store a manifest.
2. Create an intended train/eval partition before any contamination; reserve evaluation identities.
3. Create three experiment configurations (e.g. 1-nearest-neighbor, tree, random forest) or three versions of the same simple model.
4. Inject an accidental **copy/transform of specific evaluation rows into training** for two of the experiments; record actual `DERIVED_FROM` relationships.
5. Train all models and measure metrics against the intended eval set.
6. Audit their lineage using FalkorDB, return confirmed overlap paths and affected results.
7. Approve repair: reconstruct the intended training memberships **without copies from the held-out eval set**; refit the model; evaluate on the same held-out evaluation records (not used in repaired training or tuning).
8. Store both original and repaired model/evaluation versions. Compare measured scores; do not assume they must change by any fixed amount.
9. Start a fresh agent session, investigate a reused contaminated source, and prove the earlier finding is retrieved.

Keep the data-generation recipe, code revision, random seed, transformation version, model hyperparameters, sample IDs, dataset hashes, and numeric results attached to runs. A synthetic memorization-oriented scenario may create a visibly large score difference, but do not fabricate it or mistake controlled synthetic validation for a general-world result.

## 8. Core services and responsibilities

- `GraphRepository`: typed query templates, explicit timeouts, parameter binding, mapping of graph results; no ad-hoc LLM Cypher.
- `LineageService`: exact source-record ancestry, evidence path, integrity of dataset manifest and membership.
- `AuditService`: determines `confirmed/suspected/unknown`, links findings to experiment/evaluation.
- `ImpactService`: traverses exact dependent evaluations and metrics, computes impact scope.
- `ExperimentService`: records immutable dataset/train/eval/model versions and their hashes.
- `RepairService`: creates a proposed repair, seeks approval, queues work, records versioned result.
- `AgentService`: typed user intent, chooses allowed read tools, obtains evidence, prepares explainable actions; all mutations through the corresponding domain service.
- `MemoryService`: writes and retrieves verified FalkorDB observations/decisions across new sessions; distinguish claims from verified facts.

### Agent tools (allowlist)
- `audit_experiment(experiment_id)`
- `trace_source_record(source_record_id, max_hops)`
- `list_impacted_evaluations(finding_id)`
- `get_evidence_subgraph(investigation_id)`
- `recall_prior_investigations(source_record_id)`
- `propose_quarantine(evaluation_ids, evidence_ids)`
- `propose_repair(experiment_id, approved_split_policy)`
- `get_job_status(job_id)`

Only an authenticated/explicit HTTP approval from the user may commit quarantines or enqueue retraining. A natural-language request is not approval.

## 9. Planned HTTP API sketch

Version all endpoints under `/api/v1` and return consistent machine-readable errors.

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/healthz`, `/readyz` | Basic process and graph/queue readiness |
| POST | `/api/v1/demo/seed` | Idempotent deterministic scenario seed (disabled on public production by default) |
| GET | `/api/v1/experiments` | Experiment list with integrity status |
| GET | `/api/v1/experiments/{id}` | Detail, dataset versions, run results |
| POST | `/api/v1/investigations` | Start a graph-backed audit |
| GET | `/api/v1/investigations/{id}` | Status, finding list, evidence summary |
| GET | `/api/v1/investigations/{id}/graph` | Bounded evidence-only Cytoscape nodes/edges |
| POST | `/api/v1/investigations/{id}/actions` | Approve typed quarantine/repair actions |
| GET | `/api/v1/jobs/{id}` | Poll async worker status |
| POST | `/api/v1/agent/messages` | Ask question, request plan and explanation; session ID |

Statuses are explicit: `pending`, `running`, `awaiting_approval`, `completed`, `failed`; evaluation validity `valid_under_tested_lineage`, `suspect`, `quarantined`, `revalidated`, or `unknown` as appropriate. An investigation's completeness and query bounds should be returned to the frontend.

Use OpenAPI generation to derive frontend TS contracts. Set upload/schema limits. Do not allow arbitrary file paths or model code supplied via API.

## 10. UI pages

1. **Overview:** KPI tiles for experiments, confirmed findings, affected results and repaired outcomes; clearly display *measured* values only.
2. **Experiments:** List, actual metrics and validity state; action to investigate.
3. **Investigation detail:** Side-by-side evidence explanation and bounded lineage graph with clickable nodes, source-to-training/eval paths, exact impact list.
4. **Recovery:** Before/after model artifacts, split manifests, run output, approval controls, job statuses.
5. **Agent activity:** User query, graph tools called, citations to graph evidence, memory recalled in new session.

Design: sophisticated but uncluttered dark dashboard, accessible contrast, responsive at laptop size; avoid fabricated realtime metrics, unnecessary animations or generic chatbot-first layout. The graph should represent true query results.

## 11. Security, resilience, quality

- Use demo-only synthetic/public data; never include private or restricted records.
- Environment variables for secrets; `.env.example` uses placeholders; no keys committed.
- Do not expose unauthenticated mutation endpoints on a public deployment. Demo token/basic gate is acceptable for MVP.
- Strong Pydantic validation, payload limits, file size and type limits, content hashing, path allowlists.
- Never run arbitrary LLM-generated Cypher, shell scripts or Python; parameterized bounded Cypher only.
- Explicit approval for any mutation, append-only findings and results; idempotency keys for repair jobs.
- Guard against prompt injection in external dataset metadata. Treat it as untrusted text.
- Worker retry strategy and failure state, healthchecks, deterministic seeds and bounded memory/CPU use.
- No claim of complete verification when source-record lineage is missing, sampling is incomplete, or query bounds are reached.
- Record audit events in FalkorDB so a fresh agent session has true shared context.
- Unit tests, graph integration tests against actual FalkorDB, a full seeded end-to-end test and API contract tests.
- CI: backend lint/type/tests; frontend lint/type/build; seeded smoke test if resources permit.

## 12. Test matrix and acceptance criteria

| Test | Expected |
|---|---|
| Direct train/eval duplicated source record | Confirmed, with two membership paths |
| Multi-hop copied/transformed evaluation row | Confirmed, concrete source ancestry path |
| Same dataset family but disjoint source records | No false confirmed leakage |
| Missing input provenance | Unknown/suspected, not clean |
| Graph path query reaches configured bound | Flag incomplete analysis |
| One source record shared by multiple evaluations | All and only relevant evaluation/metric nodes impacted |
| Approval omitted | No quarantine/retrain action executes |
| Approved repair | New model version and fresh measured evaluation; original preserved |
| Worker job repeated | Idempotent (no duplicate repair results) |
| Graph unavailable | Audit/impact and memory features fail safely and visibly |
| New agent session | Retrieves prior graph-backed finding with source evidence |
| Same seed/environment | Repeatable run and consistent hashes within appropriate tolerance |

Optional quantitative reporting: precision/recall against intentionally seeded ground-truth contamination, test pass/fail count, p50/p95 query latency on the seeded graph, elapsed CPU train/eval time, number of affected runs. Only show actual measurements.

## 13. Four-day execution plan (MAIN BUILD BEGINS ONLY AFTER OCT 15 START)

### Day 1 — Oct 15: vertical backend slice
- Confirm dependencies and API; create monorepo with lint/test wiring.
- Run FalkorDB in Docker with persistent volume; develop graph model, indexes where tested.
- Build deterministic seed manifest and dataset/lineage ingestion.
- Write/read graph queries for source overlap and multi-hop provenance, with clean control tests.
- Implement first seeded API returning genuine, query-derived findings.

**Gate:** graph-based audit proves overlap in a test and correctly refuses a disjoint-sample false positive.

### Day 2 — Oct 16: executable impact and repair
- Add experiment runs, model artifacts and real scikit-learn metrics.
- Implement dependency traversal to affected evaluations/metrics.
- Add RQ worker and explicit user-approved quarantine/repair jobs.
- Refitting and evaluation with a clean intended training partition; preserve old scores.
- Integration test complete contamination-to-repair path.

**Gate:** one real contaminated experiment and one clean repair are completely reproducible; all scores computed.

### Day 3 — Oct 17: agent and polished frontend
- Graph-driven local agent tool calls and FalkorDB-backed session memory; no paid provider dependency.
- React screens, TanStack Query polling, Cytoscape bounded evidence visualization.
- Graph-path detail, action approval, repaired model comparison and memory demo.
- Improve loading, empty and failure states, accessibility, responsiveness.

**Gate:** judge can finish the full story without manually calling APIs.

### Day 4 — Oct 18: verification, submission
- Integration/E2E tests against fresh seeded graph and from blank Docker volumes.
- Fail-open/fail-safe checks, remove fake metrics, test restart persistence and idempotency.
- Write public README, architecture sketch, graph data model and core Cypher queries.
- Record a concise 3-min demo with actual changes, source evidence and cross-session recall.
- Verify reproducible local start with seed and complete demonstration; no hosted service is required.
- Submit before 11:59 PM IST with track selection, public repo, video and AI-assistance disclosure.

Priority cuts if behind: remove arbitrary dataset import, extra model types, advanced similarity, richer agent planning, optional local-model inference. Never cut FalkorDB graph reliance, measured rerun, evidence path, user approval or working demo.

## 14. Codex implementation sequence after event begins

Work in **small, testable slices**. Do not ask Codex to generate everything in one attempt.
1. Environment + repo + health endpoint + tests.
2. FalkorDB integration + schema/seed + query unit/integration tests.
3. Real experiment run + artifact manifests + contamination injection.
4. Audit + impact propagation + path evidence + false-positive controls.
5. Approved repair queue + worker + new measured version.
6. API contracts + frontend views + Cytoscape query-only visualization.
7. Agent tools + FalkorDB memories + session-reload demonstration.
8. Quality gates + docs + local Docker setup + demo recording.

Each step should ship with tests, changed-file summary, exact commands run and explicit unverified assumptions. User reviews all decisions and verifies no fabricated demo data.

## 15. Hackathon submission checklist

- [ ] Implementation timestamps are after Oct 15, 12:01 AM IST.
- [ ] FalkorDB provides essential graph capabilities; unavailable graph prevents core functions.
- [ ] Public repository and setup/seed instructions.
- [ ] FalkorDB graph data model and key Cypher queries in README.
- [ ] Synthetic/public, permitted sample data; licenses noted.
- [ ] Live or complete local run; visible persisted results and graph-backed memory.
- [ ] Real ML metrics and verified before/after reruns; no hardcoded score changes.
- [ ] Approval and historical evidence safeguards.
- [ ] 3-minute demo video, track name, submission before deadline.
- [ ] Acknowledge Codex/AI assistance and explain what the human built/tested.

## References

- [Official hackathon rules](https://www.wemakedevs.org/hackathons/falkordb/rules)
- [Official FalkorDB Python client](https://github.com/FalkorDB/falkordb-py)
- [FalkorDB parameterized query documentation](https://falkordb.github.io/docs-staging/commands/graph.query/)
- [FalkorDB variable-length Cypher matches](https://falkordb.github.io/docs-staging/cypher/match/)
- [FalkorDB Docker Compose guidance](https://falkordb.github.io/docs-staging/operations/docker/)
- [LangGraph persistence concepts](https://langchain-ai.github.io/langgraph/concepts/durable_execution/)
- [FastAPI background task tradeoffs](https://fastapi.tiangolo.com/tutorial/background-tasks/)
