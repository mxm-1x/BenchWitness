# Submission checklist

This is a preparation sheet. The human participant reviews the final artifacts, selects tracks in the submission portal, uploads the demo, and submits the entry.

## Project details

- Public repository: <https://github.com/mxm-1x/BenchWitness>
- Suggested primary track: **Agents That Act on Connected Data** — graph traversal proves sample overlap, computes affected claims, and gates recovery on explicit approval.
- Suggested additional track: **Agent Memory and Coordination** — a new agent session recalls and revalidates a prior investigation stored in FalkorDB. Include this track only if the participant can reproduce and explain the memory demo.
- Data: locally generated synthetic records and manifests; no restricted external dataset.
- Runtime: complete local setup with Docker Compose; no hosted runtime, paid service, API credit, or paid model.
- AI disclosure: [AI assistance disclosure](AI_ASSISTANCE_DISCLOSURE.md).
- Demo plan: [three-minute demo script](DEMO_SCRIPT.md).

## Before submitting

- [ ] Human participant reviewed the current main branch and can explain the graph schema, Cypher, API/worker flow, approval gate, and test evidence.
- [ ] Run `./scripts/verify_fresh_start.sh` and retain its output with the submission notes.
- [ ] Run the documented browser workflow from a fresh synthetic seed; confirm no stale browser state or extra demo records obscure the story.
- [ ] Record the demo using the script; review the exported video and confirm the visible UI shows real paths, approval, measured recovery, and fresh-session memory.
- [ ] Check that no `.env`, credentials, generated artifacts, or private user data are in Git or the recording.
- [ ] Verify the repository URL and reviewed commit in a logged-out browser.
- [ ] Select the final track or tracks in the official submission form; use the suggested tracks above only if the human participant agrees.
- [ ] Upload the reviewed video and submit before the official deadline.
- [ ] Record the final submission URL, video URL, selected tracks, tag, commit SHA, and submission time here or in the portal.

## Current release evidence

- Fresh-volume run: `./scripts/verify_fresh_start.sh` (run on 16 October 2026; 13 tests passed, Python checks and frontend build passed, FalkorDB restart persistence verified).
- Current milestone implementation SHA before Milestone 8 release-prep changes: `126f0a4c8d80b49f47e0fc24b90c5ff1c4d3edf2`.
- Video and portal submission: pending human recording, review, and upload.
