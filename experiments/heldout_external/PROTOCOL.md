# Held-out external-transform validation protocol

Recorded before native execution on September 19, 2026.

## Research question

When structured tool output is transformed by an independently versioned compressor, can an external executable verifier preserve declared task obligations without replacing the transformation with a task-specific projection, while retaining more undeclared future-useful context than direct projection?

## Why this differs from the earlier benchmark

The earlier fixed-task benchmark allowed the recovery transform to act as a correct direct projection. On the original 960 cases, that projection was both smaller and faster than the gate.

This follow-up therefore changes the evaluation target:

- the external transform is Headroom, unchanged;
- the verifier may accept the transformed candidate or fall back to the complete original only;
- it may not recover with a task projection;
- declared contracts cover safety/task obligations;
- separate future-utility queries depend on fields not named in those contracts.

A direct projection is still included as a lower-bound compression baseline, but it is intentionally not a substitute for the general context representation because it discards fields used by the predeclared future-utility queries.

## Frozen held-out corpus

Two new schemas, neither used by the manuscript seeded benchmark:

1. incident_board
2. payment_ledger

For each schema:

- sizes: 80, 240, 600 rows
- seeds: 2026092001, 2026092002, 2026092003, 2026092004
- total: 24 payloads

All generators, contracts, future-utility queries, target IDs, tie-breaking rules, and methods are fixed in code before the first native run.

## Declared contracts

Incident board: exact row count, exact open-critical ID set, exact open-cost sum, latest status for two fixed services, and exact provenance URI set for open-critical incidents. Contract fields exclude owner, region, and summary.

Payment ledger: exact row count, exact pending-amount sum, exact high-risk declined ID set, latest state for two fixed accounts, and exact evidence URI set for very-high-risk payments. Contract fields exclude country, channel, and memo.

## Predeclared future-utility queries

These are scored after transformation but are not checked by the verifier.

Incident board:
- owner with highest total incident cost
- exact summary for a deterministic target incident
- full region-count distribution

Payment ledger:
- country with highest pending amount
- exact memo for a deterministic target payment
- full channel-count distribution

The utility score is the fraction of these three exact answers preserved.

## Methods

1. Raw input
2. Contract-only direct projection
3. Headroom default
4. Headroom strict lossless
5. Headroom default + external verifier, with original-input fallback only

No task-aware recovery is allowed in method 5.

## External runtimes

- Headroom PyPI 0.37.0
- Headroom source pinned to commit 67eb910e38b9879bb0bcbacdc36db69e36901075

No LLM/provider API calls are made.

## Measurements

Per payload and method:
- declared-contract preservation
- exact future-utility score
- byte reduction
- cl100k_base payload-token reduction
- warm median implementation latency
- verifier decision
- decode/runtime status

Cross-runtime non-timing agreement is checked.

## Decision rule

The narrower research direction is worth pursuing only if the external verifier shows a meaningful reliability benefit on held-out schemas and preserves materially more future utility than direct projection at bounded overhead.

If strict-lossless/native safeguards already dominate the verifier on preservation, future utility, and practical reduction, or if the verifier only catches representation quirks without meaningful task-property failures, the result argues against further paper investment.

This protocol must not be edited after results are observed except through an explicitly labeled amendment.
