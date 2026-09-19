# Revision impact from follow-up baselines

Recorded September 19, 2026. This note does not modify the submitted manuscript or its original evidence.

## New same-case baseline

The follow-up reran the original 960 seeded cases and the original task contracts with three safe methods:

| Method | Mean byte reduction | Answer preservation | Invariant preservation | Recovery | Median implementation latency |
|---|---:|---:|---:|---:|---:|
| Correct task-aware projection | 99.7078% | 100% | 100% | 0% | 16.91 us |
| Projection plus verification | 99.7078% | 100% | 100% | 0% | 37.91 us |
| Original invariant-preserving gate | 90.2300% | 100% | 100% | 60.21% | 277.10 us |

These are the exact original 960 seeded cases and byte metric, so the 99.7078% direct-projection result is directly comparable with the manuscript's 90.2300% gate result. Timing is an implementation measurement on one CI run, not a hardware-independent performance claim.

## Interpretation

For these fixed tasks, the contract already identifies the rows and fields needed to answer the question. The existing recovery transform therefore acts as a correct direct task-aware projection. Running that projection directly preserves the benchmark answers and declared invariants while removing more bytes than first running the generic candidate compressor and then verifying/recovering its output.

This is a meaningful negative result for any claim that the gate itself improves compression efficiency when a correct task-aware projection is already available.

It does **not** make the external gate useless. The narrower role still worth studying is translation-style validation around a transformation that is external, heuristic, learned, version-changing, or otherwise not replaceable by a trusted task-specific projection. The current experiments do not yet establish the practical advantage of that role.

## Claims that remain supported by the existing experiment

- The implemented gate checks declared task properties on the supplied original and candidate.
- On the reported seeded cases, it preserved every declared invariant and exact deterministic benchmark answer.
- Its recovery/fail-open behavior detected the injected contract-relevant corruptions tested by the original artifact.
- The follow-up native Headroom experiment shows that the same verifier can wrap an unchanged third-party compressor and recover when its immediate output does not satisfy the declared contract.

These are implementation/evaluation findings under the tested contracts, not universal guarantees.

## Claims that should be narrowed or avoided

- Do not claim the gate is a better general compressor than Headroom.
- Do not imply that Headroom lacks preservation checks, recovery, strict-lossless compaction, or configurable must-keep constraints.
- Do not present Headroom CCR pointers as irreversible information loss when the original remains retrievable.
- Do not use the gate's 90.23% byte reduction as evidence that it is more efficient than a known correct task-specific transform. On the same 960 cases, direct projection reached 99.71%.
- Do not claim general research novelty from the broad idea of checking a transformation after it runs. The contribution, if retained, needs to be framed around the specific task-equivalence contract, structured-tool boundary, recovery policy, and empirical setting, with related validation literature treated fairly.

## Manuscript revision plan

If the paper enters revision, add the correct direct-projection baseline to the main evaluation rather than hiding it in supplemental material. Reframe the research question from "can a gate constrain compression?" toward the narrower question: "when is an independent executable task-equivalence verifier useful compared with directly applying a trusted contract-aware projection?"

A stronger future evaluation would use transformations that cannot simply be replaced by the contract-safe projection, such as an independently versioned third-party compressor, a learned compressor, or a multi-purpose context optimizer. It should include held-out schemas/contracts and an independently implemented semantic oracle where practical.

## Separate Headroom finding

A distinct upstream issue was found while testing strict-lossless table rendering: in a nullable string column, JSON null and the empty string can map to the same empty CSV cell. Swapping which row contains null versus empty string produced byte-identical strict-lossless outputs in Headroom 0.36.0 and 0.37.0. This is an upstream representation issue, not evidence for the manuscript's gate claim. Keep it separate from the research comparison.
