# BenchWitness — pre-event strategy and architecture notes

**Status:** discussion notes, not implementation. Main design and coding begin only after **15 October 2026, 00:01 IST**, on an explicit human kickoff. Recheck the event rules at kickoff. This note sharpens [PROJECT_BLUEPRINT.md](PROJECT_BLUEPRINT.md); it does not authorize building.

**Budget constraint:** zero service spend. Use local, free/open-source runtime components; do not rely on paid APIs, promotional credits, payment-card trials, or a hosted service for the working demo. A public code repository and video may use free publishing options, but the product must run from the documented local setup.

See [DEVELOPMENT_AND_GIT_PLAN.md](DEVELOPMENT_AND_GIT_PLAN.md) for phase gates, planned commits, push checks, and submission proof.

## Product thesis

**Pitch:** BenchWitness is an evidence and recovery desk for ML evaluation claims. It answers: “Did a held-out source record enter this model's training data, which published scores depend on that event, and what happened when we reran the work with a clean split?”

**Wedge:** Start with exact record-level provenance for small tabular experiments. Prove one issue end to end before attempting generic data ingestion or opaque model audits. A score can be *untrustworthy* without being numerically inflated; the product must show measured before/after scores and avoid promising a drop.

**Likely first user:** a benchmark maintainer or applied ML evaluation engineer who can supply sample IDs, dataset manifests, and run metadata. **Value hypothesis, not a verified market claim:** the tool could shorten the time between finding a contaminated record and identifying every evaluation claim that needs review. Validate this later with interviews and a timed manual-versus-assisted task. Do not invent ROI figures or customer logos for the demo.

**Scope of an honest claim:** BenchWitness can prove overlap *within recorded, complete lineage*. It cannot establish that an arbitrary outside model was trained cleanly. If provenance is missing, a query is truncated, or a manifest is incomplete, show `unknown`/`incomplete`, not “clean.”

## Why the graph is central

The primary demonstration is a traversal from one canonical `SourceRecord` through versioned samples and dataset memberships to **multiple actual training runs**, their model versions, evaluation runs, metrics, investigations, approvals, and prior agent memory. FalkorDB owns those relationships and decisions. Remove FalkorDB and auditing, impact analysis, and cross-session recall must visibly stop. Artifact files hold bytes and checksums; the separate Redis instance only brokers transient jobs.

The [official rules](https://www.wemakedevs.org/hackathons/falkordb/rules) require FalkorDB to do central work, allow only permitted data, permit pre-event notes and sketches, and require AI assistance disclosure. The [track description](https://www.wemakedevs.org/hackathons/falkordb) emphasizes graph-driven action, multi-hop reasoning, tools, and explainable paths. Enter **Agents That Act on Connected Data** first. Add **Agent Memory and Coordination** only if a fresh session demonstrably changes its next action using a prior verified investigation stored in FalkorDB. Do not enter Company Brain unless that product is actually built.

## Proposed experience

1. **Inspect:** show three real seeded experiments with measured metrics and clear validity labels. Two share contaminated source ancestry; one is a clean control.
2. **Investigate:** select a source record or experiment. The system reads FalkorDB and shows the exact training and evaluation membership paths, completeness limits, and the specific affected claims.
3. **Decide:** an agent summarizes the evidence, chooses a bounded next tool based on graph state, and proposes quarantine and a clean rerun. The user reviews the affected set and explicitly approves each mutation.
4. **Recover:** a CPU worker refits only approved affected models on a recorded clean training manifest, evaluates the held-out set, appends new versions, and displays actual results beside retained originals.
5. **Remember:** start a new agent session. It recalls the earlier verified finding from FalkorDB, cites its evidence, checks whether graph versions changed, and chooses whether to reuse or refresh the audit.

The clean control and unknown-lineage example are important: they show the product can say “not confirmed” and “I cannot tell,” not just detect the planted issue.

## Architecture sketch for the event

```text
React + Vite + TypeScript
  Opensource UI components; bounded evidence graph; typed API client
                         |
                         v
FastAPI modular monolith (Pydantic contracts)
  investigation / lineage / impact / recovery / agent modules
                         |
          +--------------+---------------+
          |                              |
      FalkorDB                     artifact directory
  relationships, findings,        data/model/manifest bytes
  approvals, memory, states            + checksums
          |
  separate Redis job broker --> CPU ML worker --> append results via services
```

Suggested event-time layout: `apps/web`, `apps/api`, `workers/ml`, `infra`, `tests`, and `docs`. Shared Python domain types should live in the API package or a small shared package only when actual reuse justifies it. Use `uv`, pinned Python dependencies, React/Vite/TypeScript, typed OpenAPI-derived client if practical, pytest/Ruff/type check, and a Compose setup with **distinct FalkorDB and Redis services**. Pin working image and package versions during the event after verification; do not preselect untested versions today. Keep services and worker small enough for an 8 GB MacBook M3.

### Planned ownership boundaries

| Component | Owns | Must not do |
|---|---|---|
| Graph repository | Allowlisted, parameterized, bounded FalkorDB queries and typed result mapping | Accept free-form agent Cypher |
| Lineage/audit | Canonical source ancestry, manifest completeness, finding classification | Infer exact identity from a shared parent dataset |
| Impact | Traverse concrete run-to-model-to-evaluation-to-metric dependencies | Mark unrelated claims affected |
| Recovery | Prepare immutable split, approval state, idempotent job request | Overwrite original model, metric, or evidence |
| ML worker | Real fit/predict/metric computation and artifact checksums | Invent a “repaired” result or accept executable user code |
| Agent | Select bounded tools, use prior verified memory, explain evidence and propose action | Decide evidence truth or self-approve mutation |
| UI | Render API state, evidence paths, approval and job progress | Display placeholder metrics as real results |

## Graph sketch and evidence contract

Keep the blueprint's entity list as a candidate, with one crucial refinement: **the actual `TrainingRun` and `EvaluationRun` must point to the exact `DatasetVersion` they consumed**. `Experiment` groups configuration and versions; an intended `TRAINS_ON` edge alone is insufficient proof of actual training inputs. A `ModelVersion` points to the producing training run; a `Metric` points to the evaluating run and metric definition. Findings and actions point to immutable evidence and affected claims.

Evidence for `confirmed` requires the same canonical source identity reachable through recorded sample-level derivations from both an actual training membership and a held-out evaluation membership for the model being scored. The response should include both path IDs, dataset manifest hashes, run IDs, graph/query version, whether analysis was complete, and the resulting impact set. Identical content alone may warrant a different, explicitly documented policy; near matches remain suspected. A disjoint source set from the same dataset family is a clean control.

Every graph read should be bounded by an allowlisted query, fixed maximum derivation depth, result cap, and timeout. Input values are parameters; labels, relationship names, and path bounds come from code. A result that hits a cap reports truncation. Exact Cypher and index choices are event-time work to verify against the running FalkorDB version.

## Agent plan

Build one task-focused investigation agent, not a general chatbot. Its tools are typed reads such as `audit_experiment`, `trace_source`, `list_impacted_evaluations`, `recall_verified_findings`, and `get_job_status`, plus proposal creation through domain services. It should maintain a short graph-backed session state: user goal, tool calls, evidence IDs, completeness, proposal, human decision, and outcome. Only verified findings/decisions become durable reusable memory; free text stays labeled as interpretation.

For the required offline demo, a bounded policy can choose the next allowed tool from graph state: recall prior work, verify its data version, audit if stale, inspect impact, then propose a decision. A small local model may be explored only after the complete flow works and only if it runs acceptably on the 8 GB Mac; it must not be required. The deterministic domain services classify evidence and calculate impact. Adopt LangGraph only if it improves observable state and retries within the time budget; a simple typed controller may be easier to verify. The agent must never generate executable Cypher, Python, or shell commands.

## Frontend and Opensource UI

Assume “opensourceui” means [Opensource UI](https://opensourceui.in/) until the user confirms the exact library. Its official site describes **copy-paste React/TypeScript components under MIT**, rather than an npm package, and a Tailwind-based visual language. Select only components that work in Vite without Next.js-specific behavior; review each copied component's dependencies and accessibility. Record attribution/license information in the repository even if not required. [Component catalogue](https://opensourceui.in/components).

Use its restrained cards, buttons, inputs, tables, loaders, and notification patterns for the product shell. Cytoscape.js is a separate evidence visualization choice. The visual hierarchy should favor an evidence path and decision state over a generic KPI dashboard. A useful laptop view is:

```text
Run list / validity       Evidence path + selected node details
Actual scores             Impacted claims and proof completeness
Agent trace               Proposal -> approval -> job -> measured rerun
```

Show visible states for `confirmed`, `suspected`, `unknown`, `incomplete`, `quarantined`, and `revalidated`; do not use color alone. Keep the approval control outside chat and spell out which claims and run versions it affects. Graph nodes/edges must come from the evidence API, with a source-record-to-claim path highlighted. Include keyboard focus, readable contrast, reduced-motion behavior, and clear failure states when graph or worker is unavailable.

## Business case and judging story

**Buyer/user split:** evaluation engineering or benchmark owners feel the pain; an ML platform lead may approve adoption. The initial product wedge is a pre-publication integrity check and incident investigation for teams already recording dataset manifests. A later business could sell integration, policy reporting, or managed graph operations, but this hackathon should prove the workflow before pricing or market-size claims.

**Proof to collect during the event:** count actual affected claims found from one source, false positives on the disjoint clean control, unknowns on missing provenance, actual before/after metrics, time to run an audit, worker duration, graph unavailability behavior, and a fresh-session memory retrieval. Report measurements with methodology and scope. Do not claim general benchmark gains from a synthetic scenario.

**Judge-facing differentiation:** the evidence path is inspectable; graph traversal determines impact rather than decorating a dashboard; an agent's action changes with graph evidence and remembered decisions; recovery is approved, versioned, and measured. A 3-minute demo should show those claims in that order, ending with the clean control and limitations.

## Event-time delivery gates

| Time (IST) | Slice | Acceptance gate |
|---|---|---|
| Oct 15 | Repo/Compose/API readiness, then source/sample/dataset graph ingestion and audit | Real FalkorDB test confirms a duplicated source and rejects disjoint membership |
| Oct 16 | Actual training/evaluation artifacts, impact propagation, approval and worker repair | One source affects multiple measured claims; approved clean rerun appends versions, originals retained |
| Oct 17 | Graph-driven agent, verified cross-session memory, Opensource UI investigation flow | A judge can complete investigation and approval from UI; new session cites earlier evidence |
| Oct 18 | Fresh-volume run, failure checks, docs, video, public repo and submission | Full demo runs from documented setup; all required submission artifacts reviewed and submitted before 23:59 IST |

Follow the existing [CODEX_KICKOFF_PROMPT.md](CODEX_KICKOFF_PROMPT.md) for **Milestone 1 only** once the human starts work after the opening time. Stop at each milestone for review. Reserve the last day for validation and submission; cut extra model types, broad imports, optional local-model inference, and animation before cutting evidence, a real rerun, approval, or cross-session memory. Budget no time or money for hosted deployment; the documented local setup and recorded demo satisfy the rules.

## Decisions to revisit with the human at kickoff

- Confirm the exact Opensource UI project/link and which components fit the evidence workflow.
- Check whether a small free local model adds demonstrable value after the graph-driven agent and recovery work end to end; keep it optional.
- Review the synthetic scenario and approval wording before treating them as the product's canonical demo.

**Source of truth:** these are planning hypotheses. The working code, real graph tests, measured worker output, and event-time rule check will determine the final architecture and claims.
