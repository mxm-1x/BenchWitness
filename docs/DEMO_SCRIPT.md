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
| 0:00–0:25 | Introduce the problem: a benchmark score cannot be trusted if held-out source records also appear in training. Explain that the graph stores sample lineage and that this demo uses generated synthetic records. |
| 0:25–0:50 | Click **Seed graph** and **Run baseline evaluations**. Show the methodology note: 400 rows, a 300/100 split, 20 copied held-out rows, and random labels independent of features. Show the four lineage states: two confirmed overlaps, a clean control, and unknown lineage. |
| 0:50–1:20 | Investigate the automatically selected canonical source ID. Show the exact training and evaluation sample IDs, derivation-hop counts, and dependent claims. Switch between affected runs to show the graph-backed paths. |
| 1:20–1:45 | Explain that the confirmed finding comes from canonical source identity and verified sample ancestry. A shared dataset-family label alone does not confirm leakage. The measured contaminated runs score 58.0% accuracy, while the clean control scores 48.0% on the same held-out set. |
| 1:45–2:20 | Propose a clean repair. Read the target claim IDs, enter a separate approval reason, and approve. Show the Redis-backed job reaching a terminal state and the new measured run versions. The clean rerun removes the copied rows and measures the same held-out set; describe the measured accuracy and F1 deltas as leakage sensitivity in this synthetic probe. |
| 2:20–2:50 | Start an agent session and investigate the source. Start a fresh session and repeat. Show the tool trace revalidating the prior investigation from FalkorDB memory. |
| 2:50–3:00 | Close with the local architecture: FalkorDB holds lineage and decisions, Redis is only the job broker, and model/prediction artifacts remain local. |

## Recording checklist

- Show the working UI and actual graph-backed sample paths.
- Show separate proposal and approval actions, followed by a real worker result.
- Show the new-session memory status and tools used.
- Keep all displayed metrics and statuses sourced from the running app; explain the synthetic memorization setup and avoid presenting it as general model quality.
- Keep the finished recording near three minutes and review playback before uploading it to the hackathon submission.
