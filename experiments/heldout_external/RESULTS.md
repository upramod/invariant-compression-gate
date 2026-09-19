# Held-out external-transform validation: result

Recorded September 19, 2026 from the frozen protocol in this directory.

## Decision

**This experiment does not support further investment in the current invariant-gate paper direction.**

Under the preregistered decision rule, the external verifier needed to provide a meaningful reliability benefit on held-out schemas while retaining materially more future utility than direct projection.

It did not.

Across all 24 held-out payloads in both tested Headroom runtimes:

- Headroom default preserved every declared contract: 24/24.
- Headroom strict-lossless preserved every declared contract: 24/24.
- Both preserved all three predeclared future-utility answers on every payload: mean future utility 1.0.
- Headroom default + verifier accepted every candidate: 24/24 accepted, 0 fallbacks.
- The verifier therefore changed no output bytes and produced no reliability or future-utility improvement.
- Headroom default and strict-lossless produced byte-identical outputs for all 24 payloads in both runtimes.
- Direct contract projection preserved the declared contracts but scored 0.0 future utility because it intentionally discarded the undeclared fields used by the frozen future queries.

This validates the experiment's distinction between a task contract and a general context representation, but it does **not** demonstrate a practical need for the verifier around Headroom on these held-out cases.

## Frozen corpus

- schemas: incident_board, payment_ledger
- sizes: 80, 240, 600
- seeds: 2026092001, 2026092002, 2026092003, 2026092004
- total payloads: 24
- five methods per payload
- no LLM/provider API calls
- verifier recovery policy: original-input fallback only; no task-aware projection recovery

Protocol: PROTOCOL.md.

## Non-timing results

The non-timing results were identical between Headroom PyPI 0.37.0 and source commit 67eb910e38b9879bb0bcbacdc36db69e36901075.

| Method | Contract preserved | Future utility | Mean byte reduction | Mean cl100k token reduction | Verifier decisions |
|---|---:|---:|---:|---:|---:|
| Raw | 24/24 | 1.000 | 0.00% | 0.00% | n/a |
| Contract-only projection | 24/24 | 0.000 | 33.00% | 32.06% | n/a |
| Headroom default | 24/24 | 1.000 | 46.07% | 31.87% | n/a |
| Headroom strict lossless | 24/24 | 1.000 | 46.07% | 31.87% | n/a |
| Headroom default + verifier | 24/24 | 1.000 | 46.07% | 31.87% | 24 accepted, 0 fallback |

There were zero contract failures and zero not-evaluable cases in every method.

## Runtime measurements

These are implementation timings on separate shared GitHub runners and must not be interpreted as version regressions.

| Method | PyPI 0.37.0 median ms | Source 67eb910 median ms |
|---|---:|---:|
| Contract-only projection | 0.609 | 0.472 |
| Headroom default | 37.738 | 30.413 |
| Headroom strict lossless | 37.924 | 30.376 |
| Headroom default + verifier | 39.328 | 31.648 |

The verifier added roughly 1-2 ms to the configured Headroom path in these runs, but because every candidate already satisfied the contract, that overhead bought no measured reliability benefit.

## Interpretation

The direct-projection baseline behaved as intended: it retained the declared contract and removed the fields required by the predeclared future queries. That demonstrates why task projection is not an interchangeable substitute for a general context representation.

However, Headroom's ordinary output already retained both the declared obligations and all frozen future utility while achieving useful compression. Its strict-lossless configuration produced the same output on this corpus.

Therefore this experiment did not reveal the failure mode the verifier would need to justify itself.

The responsible conclusion is:

1. Do not claim the verifier improves Headroom reliability from this experiment.
2. Do not tune the corpus after seeing this result in search of failures.
3. Do not spend paid LLM/API evaluation budget on this paper direction merely to manufacture another evaluation layer.
4. Preserve the result as a negative finding.
5. Reopen the research direction only if an independently motivated transformer or deployment setting presents real contract-relevant failures that native safeguards do not already prevent.

## Reproducibility

Accepted workflow run: https://github.com/upramod/invariant-compression-gate/actions/runs/35466105837

All three jobs succeeded:
- frozen protocol/unit tests
- Headroom PyPI 0.37.0
- Headroom source pinned to 67eb910e38b9879bb0bcbacdc36db69e36901075

Artifacts:
- heldout-external-0.37.0
  - digest: sha256:2971ca759e1d3f06b7db3bdc309d2ac979819023c9704d353f3390b9014437c2
- heldout-external-source-67eb910
  - digest: sha256:1c3c46e1461f358fa4b3b3f297c95ad1536a8124a401b626f1f0f83349df8207

The submitted manuscript and its historical evidence remain unchanged.

AI assistance: Pramod Ubbala directed the follow-up. ChatGPT designed and implemented the frozen experiment, ran the GitHub workflow, audited the outputs, and drafted this result note.
