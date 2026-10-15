# AGENTS.md — BenchWitness Codex Instructions

> Implementation began only after **2026-10-15 00:01 Asia/Kolkata** and an explicit human kickoff. Continue in reviewed milestones; keep pre-event notes identifiable.

## Mission
Build BenchWitness: a graph-native ML evaluation integrity agent that discovers exact training/evaluation source-record overlap, traces blast radius across evaluation claims, and performs approved, measured, versioned recovery.

## Read first
- `PROJECT_BLUEPRINT.md` — product, architecture sketch, domains, priority, tests, and schedule.
- `CODEX_KICKOFF_PROMPT.md` — initial implementation request to use *after the hackathon starts*.

## Engineering rules
1. Work in small vertical slices, not a huge unverified code dump.
2. Keep a modular monolith: React/TypeScript/Vite UI, FastAPI/Pydantic API, dedicated ML worker, FalkorDB authoritative graph, Redis queue only.
3. Preserve a strict source-of-truth boundary: graph for lineage, investigations, decisions and persistent memory; artifact storage for dataset/model bytes; queue for transient jobs.
4. Never return fabricated metrics, evidence paths, timestamps, repaired scores, benchmark claims, or successful job statuses.
5. `confirmed` leakage requires canonical source-record identities and real sample-level provenance. Generic shared parent datasets are not sufficient.
6. Missing provenance is `unknown`; do not equate no path with proof of clean data.
7. Bind Cypher parameters. Only allowlisted query templates and bounded path lengths, graph result limits and timeouts. No arbitrary LLM Cypher/shell/Python execution.
8. No automatic destructive action; quarantine and retraining need explicit user approval. Append new model/eval versions; retain originals.
9. LLMs may interpret natural language and explain query results, but deterministic services control evidence, impact propagation and model evaluation.
10. Build and test with synthetic/licensed data only. Do not collect private/restricted datasets.
11. Pin dependency versions once verified, use typed interfaces, documented exceptions and predictable return schemas.
12. Prefer simple, measured code over overengineering: no Kubernetes, Kafka, multi-cloud auth, generic workflow engine, speculative microservices, or mandatory paid API.
13. Produce a reproducible `docker compose` setup, seed command, test commands, and `.env.example` with placeholders.
14. Keep frontend visualizations backed by real graph data and job status; never fake a working flow.
15. Use tests with a running FalkorDB for core graph functionality. Include a *clean control* to prevent false-positive leakage claims.
16. Keep the CPU footprint suitable for a MacBook M3 with 8GB RAM.
17. Keep the hackathon build at zero service spend: no paid APIs, credits, trials requiring a payment card, or hosted runtime dependency. The complete demo must work locally with free/open-source tools; any optional local model must fit the machine and cannot be required for the core flow.

## Working protocol
For each implementation step: state the goal and acceptance test, implement only necessary files, run relevant tests/lint, summarize changed files and commands, note any failures explicitly, and stop at the next milestone. Do not silently ignore failing checks. Ask for human review on any meaningful product-design or destructive action decision.

## Winning demo protocol
One source record leaks into several model experiments; FalkorDB graph traversal proves each affected evaluation; user approves repair; an actual training/evaluation worker refits affected models and calculates new scores; a new agent session recalls the earlier investigation from FalkorDB. The project is incomplete unless that demo works without manually editing database state or hardcoding outcomes.

## Hackathon integrity
The organizers allow pre-event discussion, notes, graph sketches and diagrams, **not main design/implementation work**. Work produced by Codex during the event must be disclosed; the human must review, understand, and verify it. The mandatory deliverables are public repo, graph model, key Cypher, setup, working demo video, deployment or complete local setup, and track selection.
