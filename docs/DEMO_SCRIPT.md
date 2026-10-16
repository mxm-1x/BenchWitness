# Three-minute BenchWitness demo

Use this with a fresh local dataset and the documented setup in the README. Record the browser at a readable desktop size. Use the actual local app and leave the visible score values unchanged. The token field is password-masked; do not show `.env` contents in a terminal capture.

## Before recording

1. Run `cp .env.example .env`, generate a token with `openssl rand -hex 32`, and set `BENCHWITNESS_API_TOKEN` in `.env`.
2. Start FalkorDB and the separate Redis broker with `docker compose up -d`.
3. Start the API and `uv run benchwitness-worker` in separate terminals after sourcing `.env`; start the Vite frontend in a third terminal.
4. Open the local Vite URL and paste the token into the masked field.
5. Close unrelated tabs and ensure no private data is visible.

## Narration and actions

| Time | Show and say |
|---|---|
| 0:00–0:25 | Introduce the problem: a benchmark score cannot be trusted if a held-out source record also appears in training. Explain that the graph stores sample lineage and that the demo uses generated synthetic records. |
| 0:25–0:50 | Click **Seed graph** and **Run baseline evaluations**. Show the four lineage states: two confirmed overlaps, a clean control within recorded lineage, and unknown lineage. Point out that unknown is not treated as clean. |
| 0:50–1:20 | Investigate `source:synthetic-v1:0003`. Show the source, exact training and evaluation sample IDs, derivation-hop counts, and dependent claims. Switch between affected runs to show each graph-backed path. |
| 1:20–1:45 | Explain that the confirmed finding comes from canonical source identity and verified sample ancestry. A shared dataset-family label alone does not confirm leakage. |
| 1:45–2:20 | Propose a clean repair. Read the target claim IDs, enter a separate approval reason, and approve. Show the Redis-backed job reaching a terminal state and the new measured run versions. State what the screen actually reports; equal scores are a valid result and do not imply the leakage had no integrity impact. |
| 2:20–2:50 | Start an agent session and investigate the source. Start a fresh session and repeat. Show the tool trace revalidating the prior investigation from FalkorDB memory. |
| 2:50–3:00 | Close with the local architecture: FalkorDB holds lineage and decisions, Redis is only the job broker, and model/prediction artifacts remain local. |

## Recording checklist

- Show the working UI and actual graph-backed sample paths.
- Show separate proposal and approval actions, followed by a real worker result.
- Show the new-session memory status and tools used.
- Keep all displayed metrics and statuses sourced from the running app; do not add overlays that imply a score improvement.
- Keep the finished recording near three minutes and review playback before uploading it to the hackathon submission.
