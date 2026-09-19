# Native Headroom comparison: follow-up protocol

This experiment is separate from the submitted manuscript and its reported results. No prior benchmark, manuscript, figure, or result file is changed. Headroom is an unchanged third-party dependency, not an implementation copied into this repository.

## Question

Does an external task-equivalence gate improve the preservation/cost trade-off over native Headroom, its strict lossless and audit-safe modes, and correct direct task-aware projection? A null or negative finding is an acceptable result. This experiment cannot establish general research novelty.

## Frozen pilot design

Specified before inspecting native comparison results:

- Headroom PyPI 0.36.0, matching the manuscript boundary.
- Headroom PyPI 0.37.0, evaluated separately.
- An unchanged source install of commit `bc21c9370793f7e4aa94ac4c5d9a67a8d2dd0df9`, if the hosted build succeeds. A 0.37.0 wheel is not a substitute for that commit. Source-install failure is reported as unavailable, not compression failure.
- 96 seeded pilot tasks: all six original domains, sizes 50 and 250, repetition zero, all eight original contracts.
- 64 identity stress tasks: two new fixed seeds, four variants (shuffled records, exact duplicate rows, tied timestamps, Unicode/CSV-special text), eight original contracts. These are related synthetic data, not independent real-world validation.
- Eight tasks over the existing 24-record public issue snapshot.
- 168 cases per runtime, seven methods, three warm timing repetitions after one separately recorded cold call.
- An optional `--full` rerun expands the seeded group to 960 original tasks, keeping stress/public groups separate. It is not needed to reinterpret the pilot.

## Methods

1. Raw canonical records.
2. Correct task-aware projection, using the existing `contract_safe_transform` or public equivalent directly.
3. That projection plus verification.
4. Native Headroom default.
5. The exact same native default candidate plus the external gate.
6. Native Headroom `lossless_only=True`.
7. Native Headroom `audit_safe=True` with task-derived protected patterns and fail-closed protection enabled.

All methods receive the same task parameters. Audit patterns are set from the task before viewing its compressed output. Negative-evidence patterns protect the full relevant population, not just positive matches. Numeric predicates that cannot be represented simply in the public-snapshot patterns use conservative full retention. This is not an optimized custom Rust `Constraint` baseline; that extension point remains outside this pilot.

## Execution boundary

The native entry point is `SmartCrusher.apply` on a valid tool-message envelope. This exercises Python audit-safe postprocessing and measures the text actually returned in the tool message, including digest and CCR markers. It does not score hidden `items` fields instead of the visible compacted representation. The runtime retains default selection/compaction settings; all native arms disable TOIN observation writes via the same read-only policy. Only core dependencies are installed. No LLM provider, paid model call, proxy deployment, or agent loop is involved.

`engine.py` decodes JSON records and the supported CSV-schema/JSON-table forms from visible output without consulting the original. It decodes only declared task fields but measures all visible bytes/tokens. Unsupported shapes, ambiguous nullable string cells, runtime exceptions, and invariant mismatches have distinct statuses. An unsupported decoder is not proof that Headroom lost information.

The original benchmark module is executed unchanged with writes redirected to a temporary directory, outside experiment timing. Contracts retain their original definitions, including first-in-input tie resolution for equal maximum timestamps. The public latest-actor task uses greatest issue number, not a newly introduced timestamp definition.

## Gate and measurement

The gate computes the original reference, validates the candidate, performs task-aware recovery when needed, validates recovery, and returns the exact original canonical text on failure. Timings include all gate work. The combined native-plus-gate figure adds the measured native and gate stages for the same candidate. Warm samples and cold setup time are retained separately; no fastest-run selection or fabricated timing is used. Correct projection receives its own measured cost.

Primary outcomes: exact deterministic answer preservation, declared-invariant preservation, actual tool-content UTF-8 bytes, `cl100k_base` payload tokens, latency, recovery, and original fallback. Token counts are encoding-specific payload counts, not provider-billed usage. Unsupported/error denominators must be reported, never silently dropped. All source batches are treated as complete supplied inputs; this gate cannot establish upstream completeness, freshness, or current authorization.

CCR retrieval is probed through the unchanged runtime store and recorded with availability and returned byte/token counts. This is an oracle-assisted diagnostic, not an agent's choice to retrieve, an end-to-end success rate, or total API cost. No general claim against CCR is supported by inline preservation alone.

## Run

```sh
python -m pip install --only-binary=:all: headroom-ai==0.36.0 tiktoken==0.14.0
HEADROOM_TEST_NATIVE=1 python -m unittest discover -s experiments/headroom_compare -p 'test_*.py' -v
python experiments/headroom_compare/compare.py --runtime 0.36.0 --output experiments/headroom_compare/runs/0.36.0
```

GitHub Actions runs the version matrix in isolated jobs. Hugging Face/model downloads are disabled. The named tokenizer may load its public encoding before the measured workload. No API credentials are supplied.

Artifacts contain exact inputs and outputs (`evidence.jsonl.gz`), per-case CSVs, grouped summaries, environment versions, install report, source/binary hashes, corpus hashes, and raw timing samples. Historical file hashes and installed third-party code hashes are checked again after the run. Results are not automatically added to the paper or committed as established claims.

## Limitations and authorship

The corpora are small or synthetic and use closely related answer/invariant functions from the research artifact. Passing them is not proof of arbitrary LLM answer equality. The six domain labels share one synthetic schema. Compression representations unsupported by this adapter require separate work. These limitations apply even when all cases pass.

Pramod Ubbala directed this follow-up. ChatGPT generated and reviewed the experimental adapter, tests, workflow, and explanatory text. Automated tests and native runtime executions, rather than assistant assertions, provide the execution evidence. This disclosure does not imply upstream maintainer endorsement.
