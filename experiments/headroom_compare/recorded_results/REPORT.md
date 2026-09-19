# Native Headroom comparison: completed pilot

Recorded September 19, 2026. This follow-up is separate from the submitted manuscript and its original evidence.

## Finding

**Correct direct task-aware projection outperformed the Headroom-plus-gate path on this fixed-task pilot.** Both preserved all 168 declared task checks, but projection reduced model-visible payload tokens by 98.97%, compared with 36.10% for Headroom plus the gate. This does not support a claim that the gate is a better general compressor. It supports a narrower use: checking declared evidence properties before accepting an external transformation.

The comparison did not show irreversible loss in the 13 evaluable default-Headroom mismatches. Those cases involved requested `details` strings replaced by CCR retrieval pointers. All 13 original strings were available byte-for-byte from the same-process Headroom retrieval store in each of the three tested runtimes.

## Execution and provenance

- Repository: `upramod/invariant-compression-gate`.
- Branch: `research/headroom-comparison-20260919`.
- Original main / paper base: `95521a1d69877d10a7cb8e7da57def0aa2c0f45e`.
- Evaluated experiment commit: `7b6239892b59f117c498b5bf8674152a46b9d777`.
- Accepted native workflow: [35427044960](https://github.com/upramod/invariant-compression-gate/actions/runs/35427044960), all three jobs passed.
- Original reproducibility workflow at that commit: [35427044934](https://github.com/upramod/invariant-compression-gate/actions/runs/35427044934), passed.
- External runtimes: unchanged PyPI Headroom 0.36.0; unchanged PyPI 0.37.0; unchanged source commit `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`. The source install's VCS provenance was checked, not inferred from its version string.
- Each runtime passed the 39-test suite, including two real native entry-point tests. The other tests exercise our parser and gate, not all of Headroom.
- Python 3.13.15, tiktoken 0.14.0, `cl100k_base` encoding; separate Ubuntu-hosted CI jobs. Full dependency resolution and installed binary hashes are in the artifacts.

The dataset contains **168 task cases over 21 distinct payloads**, not 168 independent datasets: 96 original seeded pilot tasks, 64 new-seed identity stress tasks, and eight tasks over the existing 24-record public issue snapshot. Eight methods yield 1,344 method-case observations per runtime, 4,032 across three runtimes. Seven methods were specified before the first native pilot; the eighth, value-only protection patterns, is an explicitly exploratory sensitivity check. See [VALIDATION_NOTES.md](../VALIDATION_NOTES.md).

All three runtimes produced identical non-timing output records, including model-visible text, token counts, task results, gate decisions, configuration, and retrieval diagnostics. The artifact binaries are not identical, so this is a measured agreement on the pilot, not an assumption that the versions are equivalent in general.

## Preservation and reduction

The table applies separately to each of the three runtimes. Exact deterministic answer preservation and declared-invariant preservation counts were the same in this pilot. The unresolved case is shown separately and is not counted as a proven failure. No runtime errors occurred.

| Method | Preserved | Inline mismatch | Unresolved by adapter | Mean byte reduction | Mean payload token reduction |
|---|---:|---:|---:|---:|---:|
| Raw input | 168/168 | 0 | 0 | 0.00% | 0.00% |
| Correct task-aware projection | 168/168 | 0 | 0 | 99.13% | 98.97% |
| Projection plus gate | 168/168 | 0 | 0 | 99.13% | 98.97% |
| Headroom default | 154/168 | 13 | 1 | 27.78% | 30.47% |
| Headroom plus gate | 168/168 | 0 | 0 | 33.57% | 36.10% |
| Headroom strict lossless | 167/168 | 0 | 1 | 20.90% | 28.09% |
| Headroom audit-safe, field-qualified patterns | 167/168 | 0 | 1 | 0.57% | 0.43% |
| Headroom audit-safe, value-only patterns (exploratory) | 154/168 | 13 | 1 | 24.11% | 26.51% |

Percentages are the arithmetic mean of per-task reductions in the actual tool-content text relative to canonical JSON input. Payload tokens are encoding-specific, not provider-billed usage or measured API cost. For rates, the correct native denominator is 167 evaluable cases plus one unresolved case; do not report the unresolved case as a known incorrect answer.

The Headroom-plus-gate arm accepted 154 candidates without changing their bytes and recovered 14: 13 known inline mismatches plus one adapter ambiguity. All recovered outputs passed the declared invariants; none required the final original-input fallback in this pilot. Unit tests separately exercise bad recovery, exceptions, mutation, and original fallback.

The strict-lossless arm preserved every evaluable case without the external gate. The field-qualified audit patterns usually forced the original JSON through when they no longer matched the CSV rendering, producing a conservative low-reduction baseline. The exploratory value-only patterns match across both forms but still do not establish every field's inline preservation. Both configurations are reported rather than selecting whichever makes our gate look better. Custom Rust `Constraint` implementations were not benchmarked.

## What the 13 mismatches mean

Every evaluable mismatch in `headroom_default` was a lookup task whose requested `details` field became a retrieval marker. The requested record and its other required fields survived. For example:

```text
case: seeded:incident_ops:250:0:lookup
record_id: inc-000092-1994
changed required field: details
inline value: <<ccr:659caf2c0b7a,string,269B>>
original details: available from CCR; retrieved SHA-256 matches exactly
```

The artifact audit reconstructed the requested record from visible output and matched the retrieval payload's recorded SHA-256 against the original string. The three `retrieval-proof-*.json` files preserve that check for each runtime. They contain identical checks because all three native result sets agreed. This is a same-process, immediate retrieval diagnostic. It does not test later TTL expiry, eviction, persistence across restarts, an agent noticing the omission, or the cost of a real retrieval loop.

**This pilot found retrieval-dependent inline evidence, not 13 irreversible losses and not 13 demonstrated wrong LLM answers.** It found no evaluable count, sum, latest-state, threshold, or provenance mismatch in the native default arm. That scope matters to the research interpretation.

## The unresolved case

`public:threshold` contains an empty nullable `label` field in the native table. Our adapter cannot distinguish an empty string from null in that representation without consulting the source. It refuses to guess. This remains `not_evaluable` for default, lossless, and both audit-safe configurations. The gate recovers a task projection, but that recovery is not evidence of a native Headroom error.

## Runtime cost

| Method | 0.36.0 median ms | 0.37.0 median ms | Source median ms |
|---|---:|---:|---:|
| Correct task-aware projection | 0.486 | 0.686 | 0.744 |
| Projection plus gate | 0.507 | 0.710 | 0.773 |
| Headroom default | 59.896 | 77.666 | 91.586 |
| Headroom plus gate | 71.385 | 93.355 | 111.688 |
| Headroom strict lossless | 55.587 | 73.246 | 85.281 |

Times are warm medians from three repetitions on separate shared CI runners, with cold construction/first-call costs recorded separately. The combined gate timing includes the matching native or projection stage plus reference calculation, candidate parsing, verification, and recovery as applicable. Differences between runners must not be described as version regressions.

The comparison includes Python `SmartCrusher.apply` and its envelope/token processing, while task projection is a smaller task-specific routine. Reported output token counting is outside the measured stage. Timing is an implementation measurement of these configured paths, not an optimized language/runtime contest.

## Why projection wins here

The task and needed fields are already known, and the historical recovery routine already implements a correct task-aware selection and projection. Running that routine directly removes unrelated fields and records without first building a broad compressed context. The large synthetic rows contain many irrelevant metadata fields, so a near-99% task-specific reduction is plausible within this setup.

Headroom is retaining broader context and retrieval options; projection serves only the declared task. A future question may require fields that projection discarded. The result therefore argues against claiming a compression advantage for the gate on fixed tasks. It does not rank the two approaches as interchangeable general agent products.

A defensible next research claim would need evidence that an independent verifier is useful when the transformation is external, changes over time, or cannot be replaced by a known task-specific projection. This pilot does not establish general novelty, deployment safety, or such an advantage on unseen tasks.

## Scope and limitations

This is an offline structured-evidence experiment. It made no LLM provider calls and ran no agent, deployed proxy, or paid API evaluation. It reused the original answer and contract functions, which are closely related rather than independent semantic judges. The six original domain labels share one synthetic schema. The stress group uses new seeds and controlled variants, not independent real-world traffic. No statistical independence is claimed across eight tasks on the same payload. The public snapshot is small and is issue metadata, not Headroom runtime production data.

Current authorization, upstream source completeness, source freshness, and adversarially forged input are outside this gate's guarantee. A valid invariant comparison only establishes agreement with the supplied original under the declared contract. It cannot make an incomplete or stale source authoritative.

The first native run, `35426455866` at `81248e2`, is excluded from these findings. Its evaluator did not parse Headroom's unquoted comma-containing CCR cells. We corrected our adapter and reran all arms and cases; see the amendment for exact scope. Unsupported input was never recast as proven corruption.

## Files and reproduction

- [aggregate.csv](aggregate.csv): all-runtime overall table with full precision.
- [by_corpus_nontiming.csv](by_corpus_nontiming.csv): separate seeded, stress, and public aggregates. These non-timing values apply to each runtime; per-runtime group timings are in each artifact's `summary.csv`.
- [artifacts.json](artifacts.json): run, commit, package, source, binary, and archive provenance.
- `retrieval-proof-0.36.0.json`, `retrieval-proof-0.37.0.json`, `retrieval-proof-source-bc21c93.json`: all 13 target-field checks for each runtime.
- Full workflow artifacts: exact inputs/outputs, per-case observations, raw timing samples, configs, retrieval diagnostics, dependency install reports, and historical-file hashes.

After unpacking the three verified ZIPs into separate directories, rerun the artifact audit without a Headroom installation:

```sh
python experiments/headroom_compare/audit_artifacts.py /path/to/0.36.0 /path/to/0.37.0 /path/to/source
```

The auditor checks CSV/evidence agreement, input hashes, visible-byte counts, reduction arithmetic, timing medians, method/case completeness, exact target-details retrieval evidence, and cross-runtime non-timing agreement. It writes `audit.json` and `retrieval_verification.json` into each supplied directory. It checks token arithmetic from recorded native counts, not by independently re-tokenizing text. The audit does not re-run retrieval or an LLM.

Artifact downloads use GitHub and expire December 18, 2026 under the recorded retention setting. Keep a local copy of the ZIPs and verify their SHA-256 against `artifacts.json`. No signed temporary download URLs or credentials are committed.

The manuscript, original benchmark code, original result files, figures, and evidence checksums remain unchanged. This report records a follow-up, not a silent replacement of the submitted study. No upstream Headroom source was changed.

Pramod Ubbala directed the work. ChatGPT generated the experiment, tests, artifact audit, and report. Automated native runs and preserved artifacts provide the execution evidence. No upstream maintainer endorsement is implied.
