# Invariant-Preserving Compression Reproducibility Package

This package accompanies the manuscript **Invariant-Preserving Compression of Structured Tool Outputs for LLM Agents** by Pramod Ubbala.

The manuscript PDF is available at [`Invariant_Preserving_Tool_Output_Compression.pdf`](Invariant_Preserving_Tool_Output_Compression.pdf). The code and reported result files are released under the MIT License.

## Paper evidence map

Run `python make_paper_claims.py` to regenerate `results/paper_claims.csv`. That file maps the manuscript's reported measurements to the committed source data and records each derivation.

| Manuscript item | Produced by | Evidence |
| --- | --- | --- |
| Table 3, primary benchmark | `python invariant_compression_benchmark.py --output-dir reproduced_results` | `results/summary.csv`, `results/results.csv` |
| Figure 1, reduction versus preservation | `python make_ipc_figures.py` | `results/summary.csv` |
| Figure 2, preservation by task | `python make_ipc_figures.py` | `results/task_breakdown.csv` |
| Figure 3, gate reduction and recovery | `python make_ipc_figures.py` | `results/task_breakdown.csv` |
| Fault-injection results | `python invariant_compression_benchmark.py --output-dir reproduced_results` | `results/corruption_tests.csv` |
| Table 4, public issue validation | `python external_validation/real_issue_snapshot_benchmark.py` | `external_validation/results/real_issue_summary.csv`, `external_validation/results/real_issue_results.csv` |
| Table 5, sensitivity sweep | `python robustness/sensitivity_and_uncertainty.py --output-dir robustness/reproduced_results` | `robustness/sensitivity_summary.csv`, `robustness/sensitivity_raw.csv` |
| Bootstrap and Wilson intervals | `python robustness/sensitivity_and_uncertainty.py --output-dir robustness/reproduced_results` | `robustness/primary_uncertainty.csv`, `robustness/public_uncertainty.csv` |

## Reported experiments

### 1. Seeded structured-tool benchmark

Files:

- `invariant_compression_benchmark.py` contains the seeded workload generator, seven evaluated methods, contract verifier, recovery logic, fault injection, and CSV export.
- `results/results.csv` contains 6,720 method-case observations from 960 benchmark cases and seven methods.
- `results/summary.csv` contains overall method aggregates from the packaged benchmark run.
- `results/task_breakdown.csv` contains task-family aggregates.
- `results/corruption_tests.csv` contains 900 contract-relevant fault-injection checks.
- `make_ipc_figures.py` regenerates the three manuscript figures from the packaged result files.
- `figures/` contains the rendered manuscript figures.

Reproduce the default benchmark with Python 3.13+:

```bash
python invariant_compression_benchmark.py --output-dir reproduced_results
```

Expected non-timing results:

- 960 benchmark cases.
- 6,720 method-case rows.
- Invariant-preserving gate: 90.23% mean serialized-context reduction.
- Invariant-preserving gate: 100.00% exact task-answer and invariant preservation.
- Pattern-retention guard: 70.51% mean reduction with 100.00% exact task-answer and invariant preservation.
- Task-aware unverified reducer: 99.76% mean reduction with 78.54% exact task-answer preservation.
- Fault injection: 900/900 declared contract-relevant corruptions detected.

The workload seed is `20260907`. Non-timing benchmark outputs are deterministic. Microsecond timings vary by interpreter, host load, and hardware. The manuscript reports latency from the benchmark run shipped in `results/`.

### 2. Public GitHub issue snapshot

`external_validation/real_issue_snapshot.json` contains 24 public issue-list records from the Headroom GitHub issue tracker, captured on September 7, 2026. This is a public structured-data validation set. It is not Headroom runtime output and it is not a native Headroom compressor benchmark.

Run:

```bash
python external_validation/real_issue_snapshot_benchmark.py
```

The script writes:

- `external_validation/results/real_issue_results.csv`
- `external_validation/results/real_issue_summary.csv`

Reported secondary results across eight deterministic issue-tracker tasks:

- Invariant-preserving gate: 81.47% mean serialized-context reduction with 100.00% answer and invariant preservation.
- Pattern-retention guard: 26.42% mean reduction with 87.50% answer and invariant preservation.
- Task-aware unverified reducer: 88.66% mean reduction with 62.50% answer preservation.
- The invariant gate used recovery on 87.50% of the eight tasks.

### 3. Sensitivity and uncertainty

`robustness/sensitivity_and_uncertainty.py` reruns the seeded benchmark under nine candidate-aggressiveness settings:

- boundary parameter `k` in `{2, 5, 10}`
- outlier threshold `z` in `{1.5, 2.5, 3.5}`

The full sweep can take several minutes because it executes the 960-case benchmark nine times. Run:

```bash
python robustness/sensitivity_and_uncertainty.py --output-dir robustness/reproduced_results
```

Reported outputs are also shipped directly under `robustness/`:

- `sensitivity_raw.csv`
- `sensitivity_summary.csv`
- `primary_uncertainty.csv`
- `public_uncertainty.csv`

All nine configurations preserve 100% of seeded task answers and declared invariants. Mean reduction ranges from 84.83% to 92.21%. For the reported `k=5`, `z=2.5` setting, a deterministic 1,000-resample case-level bootstrap with seed 42 gives a 95% interval of 89.42% to 91.00% for mean reduction. The 960/960 answer-preservation result has a Wilson 95% interval of 99.60% to 100.00%.

The analysis script requires NumPy. Figure generation requires NumPy and Matplotlib. See `requirements-analysis.txt`.

## Optional external evaluations. Not included in reported results

These harnesses are supplied for follow-up replication. Their outputs are not used in the manuscript because the build environment did not contain the required native Headroom installation or an authenticated external model API credential.

### Native Headroom SmartCrusher comparison

The harness is aligned to released Headroom **v0.36.0** and its public `SmartCrusher.crush_array_json()` path.

```bash
pip install headroom-ai==0.36.0
python external_validation/headroom_external_eval.py
```

It evaluates two paths on the same public issue snapshot:

1. Native Headroom 0.36.0 SmartCrusher candidate.
2. The same candidate wrapped by the manuscript's external invariant gate.

Results, when run, are written to `external_validation/results/headroom_036_external_results.csv`.

Do not cite this optional comparison until that file has been generated in a valid external environment and inspected.

### Raw-versus-gated LLM evaluation

Set an API credential and choose a model available to that account:

```bash
pip install openai
export OPENAI_API_KEY="..."
python external_validation/llm_pair_eval.py --model <model-name> --repeats 3
```

The script records exact-answer correctness and API-reported input/output token counts. Those measurements are not part of the reported manuscript results.

## Measurement boundary

The reported compression metric is canonical compact-JSON **UTF-8 byte reduction**. It is not presented as an exact tokenizer-specific token-saving percentage. Field and row removal normally reduce model input tokens as well, but tokenizer-specific savings require measurement with the intended model tokenizer or API. The optional model harness records API-reported token usage when run.

## Data provenance and privacy

The primary benchmark is synthetic. The secondary snapshot contains public GitHub issue-list metadata only. The package contains no employer data, private logs, proprietary source code, internal URLs, or production records.

## Research boundary relative to Headroom

Headroom v0.36.0 exposes audit-safe protected-pattern retention. The study-owned `Pattern-retention guard` is not Headroom code and does not reproduce Headroom's selector, compaction, CCR retrieval, or native runtime. It isolates protected-row retention as a baseline. The manuscript's research claim is narrower: executable task-equivalence contracts sit outside an arbitrary candidate compressor and can express obligations such as exact aggregates, negative evidence, temporal maxima, cross-record relations, thresholds, and provenance.
