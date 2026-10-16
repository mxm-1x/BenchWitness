# BenchWitness — dataset inventory and sourcing notes

**Status:** As built, synthetic memorization scenario v2. Earlier planning notes remain below only where they still apply. The current generator creates a 400-row synthetic source with stable canonical IDs, random binary labels independent of features, a stratified 300/100 split, and five versioned manifests. It copies 20 held-out rows into each of two contaminated training versions. The clean control uses only the 300 training rows. Source rows and manifests live under `artifacts/demo/scenarios/synthetic-memorization-v2/`; this versioned directory preserves older v1 artifacts.

## Finding: one source dataset is enough

The required demo needs **one small synthetic tabular source**, then several *versioned views and manifests derived from it*. It does not need Kaggle, a paid API, or private data. The current generator uses Python's standard library: fixed-seed feature vectors, independently generated binary labels, and a stratified split. The [hackathon rules](https://www.wemakedevs.org/hackathons/falkordb/rules) permit synthetic data.

The active recipe is `benchwitness_api.lineage.build_demo_scenario`: 400 rows, seed `20261015`, two numeric features, independent random binary labels, and a 75/25 stratified split. It assigns stable IDs such as `source:synthetic-memorization-v2:0000`. A separate seeded sampler copies 20% of held-out IDs into both contaminated training manifests. Keep IDs separate from feature-content hashes: equal feature values alone do not prove that two rows are the same source record. The source file, split, and five manifests are immutable within the v2 namespace; a changed recipe must use a new version ID.

## Required logical datasets and fixtures

| Item | Role | Contents and provenance requirement | Needed for |
|---|---|---|---|
| Canonical source | Sole generated raw dataset | Feature vector, label, stable `source_record_id`, generator version/seed, row count and content digest | Real training and a root identity for graph paths |
| Intended split manifest | Immutable partition of source IDs | Disjoint training and held-out evaluation ID lists, split policy/seed, count and digest | Defines what “clean” means before any copy is introduced |
| Held-out evaluation version | Versioned evaluation membership | `SampleVersion` per held-out row and explicit membership to `DatasetVersion`; fixed across original and repaired comparisons | Actual evaluation runs and exact overlap proof |
| Contaminated training version A | First affected run's actual input | Intended training rows plus recorded copies or transformations of selected held-out rows; each copy links to its canonical source ID | Confirmed source overlap and first affected claim |
| Contaminated training version B | Second affected run's actual input | A distinct experiment/version that also contains **at least one of the same leaked source IDs** through recorded sample-level ancestry | One source's multi-run blast radius |
| Clean control training version C | Unaffected run's actual input | Uses only intended training IDs, while sharing the same overall source-dataset family | Proves the audit does not mistake a common parent dataset for leakage |
| Clean recovery training versions | New immutable versions after approval | Exclude every held-out source ID and its descendants from each affected training set; retain old manifests | Actual approved refits and comparable new evaluations |
| Missing-provenance fixture | Small test-only case | A sample with deliberately absent canonical ancestry, marked as incomplete metadata | Ensures result is `unknown`, never “clean” |
| Ground-truth fixture | Test-only oracle | Explicit injected source IDs and expected affected run IDs, separate from the detector's graph query | Precision/false-positive checks without hardcoded production outcomes |

The source bytes and immutable manifests live in the local artifact directory; FalkorDB stores source/sample/dataset/run identities, membership and derivation edges, hashes, findings, actions, and memory. Redis is only the transient job broker. The graph and artifact manifest must agree on membership counts and hashes before a finding can claim complete coverage.

## Planned scenario

1. Generate and version the canonical source during the event; split source IDs before introducing any contamination.
2. Make two contaminated training versions. Copy 20 held-out source records into **both**, recording real `DERIVED_FROM` edges. The count and sampler policy are written to the split manifest.
3. Train the fixed deterministic 1-nearest-neighbor implementation on the actual contaminated manifests and one control configuration on the clean manifest. Evaluate each on the same held-out version. With labels independent of features, exact copies expose memorization behavior. The test derives metrics from saved predictions and requires a visible contaminated-versus-clean difference; no metric is inserted into the graph as fixture data.
4. Run the graph audit: the common leaked source ID must produce training and evaluation membership paths for A and B, and no confirmed path for C. Missing ancestry stays unknown.
5. After explicit approval, create clean training versions for A and B, refit, and evaluate the unchanged held-out set. Preserve the old models, predictions, metrics, and manifests; compare only measured values.

The copied-ID sampler is seeded independently of labels and model outcomes. Do not change the seed, leak fraction, model, or split to chase a target score. The observed difference is an expected property of this narrow stress probe and must not be presented as a general benchmark result. Record the code revision, package versions, seeds, model configuration, feature schema, manifest digests, and metric definition with every run.

## Optional public dataset after the core demo works

[UCI Iris](https://archive.ics.uci.edu/dataset/53/iris) is a compact 150-row, 4-feature classification dataset. UCI lists it under **CC BY 4.0**, so reuse requires attribution. It could test the ingestion story using a published dataset, but it is **not required** and should be cut before any core graph, worker, or UI work. If used, preserve the downloaded file's checksum and version/source URL, cite UCI and Fisher in the README, assign stable file-row IDs, and create every split/copy/derivation record explicitly. Do not pretend its original publication supplies BenchWitness's sample-level transformation lineage; that lineage begins with the event-time import.

## Data acceptance checklist for the event

- Source and split regenerate from pinned recipe and seed; actual counts and hashes match the stored manifests.
- Intended train and held-out source ID sets are disjoint.
- Every confirmed copy has an explicit source-level derivation path, and every run points to the dataset version it actually consumed.
- One source ID is present in both affected training versions and in the held-out evaluation version; the control remains disjoint.
- Missing lineage, truncated traversal, or count/hash mismatch prevents a clean or complete claim.
- Original and repaired metrics are generated from real predictions; no expected score or job success is inserted as fixture data.
- Generated or optional public data comply with the event rules; no private, login-protected, personal, or restricted dataset enters the graph.

The seed command creates the rows and manifests reproducibly. The real-FalkorDB integration test verifies 20 confirmed source overlaps per contaminated experiment, a clean same-family control, missing and ambiguous ancestry preventing complete coverage, manifest drift preventing a clean claim, and persisted experiment runs with metrics independently recomputed from checksummed predictions. It also verifies that impact excludes the clean control, proposals leave claim values unchanged, explicit approval appends a quarantine decision, and clean findings cannot be proposed for quarantine. Approved clean recovery removes the copied rows and measures the unchanged held-out split again.
