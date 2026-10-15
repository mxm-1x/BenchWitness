# BenchWitness — Initial Codex prompt (USE ON/AFTER OCTOBER 15, 2026, 00:01 IST ONLY)

Read `AGENTS.md` and `PROJECT_BLUEPRINT.md` in full. This is a four-day FalkorDB hackathon; the main work starts now. Build BenchWitness, a graph-native ML evaluation integrity tool.

Your first task is **Milestone 1 only**, not the entire system:

1. Propose a concise directory structure for a modular-monolith repo with `apps/web`, `apps/api`, `workers/ml`, and `infra` (adapt names if a cleaner structure is justified).
2. Establish local development conventions: Python package management with `uv`, lint/type/test commands, React/Vite/TypeScript frontend tooling, `.env.example`, and Docker Compose services for FalkorDB and a **separate** Redis job broker.
3. Implement a minimal API health/readiness endpoint and verified connection to FalkorDB, plus a small CLI/healthcheck that can show whether the graph is reachable.
4. Add one integration test against real FalkorDB and one API smoke test.
5. Document exact commands to install, start services and run tests on macOS. Spend nothing on services: no paid APIs, payment-card trials, or hosted runtime dependency. The complete demo must work locally.
6. Do **not** create an LLM chatbot, generic dashboards, fake experiment metrics, complicated worker queue or speculative features in this milestone.

After implementation, run all available tests/lint/type checks. Report precisely what passed or failed, what files changed, and the next milestone. Do not proceed automatically beyond Milestone 1 without human review. Use clear typed interfaces and avoid overengineering.

**Upcoming milestones (reference only):** sample-level data-lineage and seed graph -> real ML experiment metrics -> multi-hop impact and quarantine -> approved clean rerun via worker -> typed agent/memory -> polished graph-backed dashboard -> video and submission.
