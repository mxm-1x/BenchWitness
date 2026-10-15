# BenchWitness — dataset inventory and sourcing notes

**Status:** pre-event research only. Do not download, generate, transform, or seed data until **15 October 2026, 00:01 IST** and an explicit human kickoff. The figures below are planning targets, not generated data or measured outcomes.

## Finding: one source dataset is enough

The required demo needs **one small synthetic tabular classification source**, then several *versioned views and manifests derived from it*. It does not need Kaggle, a paid API, or private data. [scikit-learn's `make_classification`](https://scikit-learn.org/stable/modules/generated/sklearn.datasets.make_classification.html) can generate labeled samples with a fixed random state; [stratified `train_test_split`](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.train_test_split.html) can define the initial held-out partition. scikit-learn itself is [BSD-3-Clause licensed](https://github.com/scikit-learn/scikit-learn). The [hackathon rules](https://www.wemakedevs.org/hackathons/falkordb/rules) permit synthetic data.

Generate this source **during the event** with a committed recipe, fixed seed, pinned package version, and recorded feature/label schema. An illustrative scale is 400–800 rows and a 75/25 stratified train/evaluation split; choose the exact shape after timing the MacBook. Assign each source row a stable opaque ID from the recipe/version and row index. Keep IDs separate from feature-content hashes: equal feature values alone do not prove that two rows are the same source record.

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
2. Make two contaminated training versions. Copy one held-out source record into **both**, recording real `DERIVED_FROM` edges; a few additional copied IDs are acceptable if needed for a visible measured effect, but report the actual count.
3. Train two small configurations on their actual contaminated manifests and one control configuration on its clean manifest. Evaluate each on the same held-out version. A 1-nearest-neighbor model may make a copied evaluation row influential, but the score change is **not promised**; metrics come from real predictions. See the [official estimator documentation](https://scikit-learn.org/stable/modules/generated/sklearn.neighbors.KNeighborsClassifier.html).
4. Run the graph audit: the common leaked source ID must produce training and evaluation membership paths for A and B, and no confirmed path for C. Missing ancestry stays unknown.
5. After explicit approval, create clean training versions for A and B, refit, and evaluate the unchanged held-out set. Preserve the old models, predictions, metrics, and manifests; compare only measured values.

Avoid tuning algorithms, feature transforms, copied-ID selection, or hyperparameters against the held-out results to force a score change. If preprocessing learns statistics, fit it on the relevant training version and apply it to evaluation, never fit it on held-out rows. Record the code revision, package versions, seeds, hyperparameters, feature schema, transformation details, manifest digests, and metric definition with every run.

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

No files or rows described here exist yet. They are the dataset plan for the event-time implementation and must be verified once created.
