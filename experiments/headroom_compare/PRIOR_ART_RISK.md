# Prior-art risk assessment for a future revision

Recorded September 19, 2026. This note is a follow-up research assessment. It does not modify the submitted manuscript or its original evidence.

## Bottom line

The manuscript should **not** claim broad novelty for "verifiable context compression", "post-compression verification", or "verification plus conservative fallback".

Two lines of prior work materially constrain those claims:

1. **Context Codec** (Trukhina & Vashkelis, arXiv:2605.17304, submitted May 17, 2026) explicitly frames LLM context compression as preserving semantic commitments. It represents context as typed, source-grounded semantic atoms, separates extraction/normalization/representation/rendering/verification, defines preservation metrics and error classes, and includes conservative fallback rules. Its stated context includes goals, constraints, tool results, retrieved evidence, artifacts, and safety boundaries.
2. **Translation Validation** (Pnueli, Siegel & Singerman, TACAS 1998, DOI 10.1007/BFB0054170) established the general architecture of validating each individual transformation result against its source rather than proving the transformer correct for every input.

Those works predate the September 2026 manuscript. The paper can still study a narrower application and contract design, but it should present that as an application/specialization, not as invention of the general verification pattern.

## Most relevant prior work

### Context Codec

**Citation:** Natalia Trukhina and Vadim Vashkelis. *Compress the Context, Keep the Commitments: A Formal Framework for Verifiable LLM Context Compression*. arXiv:2605.17304, May 17, 2026.

Source: https://arxiv.org/abs/2605.17304

Direct overlap:

- LLM context compression is treated as preservation of things that future responses must keep.
- Tool results and retrieved evidence are explicitly within the motivating context.
- Preservation obligations are represented explicitly rather than assuming generic summarization faithfulness.
- Verification is a distinct stage.
- Conservative fallback is part of the framework.
- The paper proposes explicit preservation/recoverability metrics.

Difference that remains worth testing:

- Context Codec's abstraction is **typed semantic atoms extracted from conversational context**.
- This repository's verifier operates over **structured tool-output records with application-declared executable task invariants**.
- Current contracts include exact counts/sums, negative evidence with population obligations, temporal maxima, cross-record relations, thresholds, provenance signatures, and exact lookup values.
- The candidate transformation can be an unchanged external compressor; the verifier need not share the compressor's representation or selector.
- For the declared structured contracts, verification is deterministic code rather than semantic-atom extraction/equivalence judged from free-form dialogue.

This is a narrower difference. It is not yet evidence that the structured specialization is sufficiently novel or useful for publication.

### Translation validation

**Citation:** Amir Pnueli, Michael Siegel, Eli Singerman. *Translation Validation*. TACAS 1998, LNCS 1384, pp. 151–166. DOI 10.1007/BFB0054170.

Source: https://weizmann.elsevierpure.com/en/publications/translation-validation-2/

The central idea is especially relevant: rather than proving a transformer correct in advance, validate the output of each particular run against the corresponding source under a defined correctness relation.

Mapping to this project:

| Translation-validation concept | Structured-context analogue |
|---|---|
| source program | original structured tool output |
| target program | compressed/transformed candidate |
| compiler/translator | arbitrary compressor/context optimizer |
| refinement/correctness relation | executable task-equivalence invariant vector |
| validation of each run | candidate acceptance check |
| reject invalid translation | recovery or fail-open to original |

Therefore, "wrap an arbitrary compressor with a verifier" should be described as **translation-validation-inspired**, not as a new general architecture.

### ACON

**Citation:** Minki Kang et al. *ACON: Optimizing Context Compression for Long-horizon LLM Agents*. arXiv:2510.00615, October 2025.

Source: https://arxiv.org/abs/2510.00615

ACON compresses both environment observations and interaction histories for long-horizon agents and adapts compression guidelines from paired trajectories where full context succeeds and compressed context fails. It reports lower memory use while largely preserving task performance.

Relevance:

- Strong evidence that agent context compression should be evaluated at task level, not just by byte/token savings.
- Compresses observations as well as history, making it closer to agent tool-output use than ordinary prompt-only compression.
- Its learned/guideline-optimized compressor is exactly the kind of changing external transformation for which an independent validator could be interesting.

Difference:

- ACON optimizes the compressor from task failures; this project validates a candidate against explicit structured contracts before accepting it.
- That difference needs an experiment, not a prose novelty claim.

### LLMLingua-2

**Citation:** Zhuoshi Pan et al. *LLMLingua-2: Data Distillation for Efficient and Faithful Task-Agnostic Prompt Compression*. Findings of ACL 2024, pp. 963–981. DOI 10.18653/v1/2024.findings-acl.57.

Source: https://aclanthology.org/2024.findings-acl.57/

LLMLingua-2 formulates prompt compression as token classification and targets faithful task-agnostic compression. It is important prior art for learned compression/fidelity and an appropriate external candidate class, but it does not by itself supply this project's application-specific structured invariant checker.

## What the follow-up experiments changed

The same-case 960-case baseline shows:

- Correct direct task-aware projection: **99.7078% mean byte reduction**, 100% declared answer/invariant preservation.
- Projection plus verification: **99.7078% mean byte reduction**, 100% preservation.
- Original gate: **90.2300% mean byte reduction**, 100% preservation, with recovery on 60.21% of cases.

This means the current benchmark does **not** establish a benefit for "compress first, then verify" when the exact trusted task-specific projection is already known. The direct transform is both simpler and smaller on these fixed tasks.

The Headroom pilot establishes a narrower engineering fact: the external verifier can sit around an unchanged third-party transformation and recover when the immediate representation does not satisfy the declared contract. It does not establish superiority over Headroom or over a custom Headroom `Constraint`.

## Claims to remove or rewrite

Avoid:

- "We introduce verifiable context compression."
- "We introduce post-compression semantic verification."
- "We are the first to verify that compression preserves task-critical context."
- "The gate is a better compression method."
- "Existing compressors do not support preservation/recovery."
- "A verifier around an arbitrary compressor is a novel architecture."

Safer:

- "We study translation-validation-style checking for structured LLM tool outputs."
- "We instantiate task equivalence as executable invariants over structured records."
- "We evaluate whether a candidate representation preserves declared data obligations before it is released to the agent."
- "The approach is most relevant when the transformer is external or cannot be replaced by a trusted task-specific projection."

Even those statements should be accompanied by the cited prior art and the negative direct-projection baseline.

## Research question that is still defensible

A sharper question is:

> **When an LLM agent's structured tool output is transformed by an independently versioned or learned context optimizer, can executable task-specific invariants provide useful translation validation at acceptable cost, compared with relying on the optimizer's own preservation mechanisms or using a trusted direct projection?**

That question is narrower than the submitted manuscript's broad framing and is not answered by the current experiments.

## Evidence needed before a strong revision

1. **External/changeable transformer.** Use a compressor whose behavior the contract does not implement directly. Headroom is one candidate; a learned compressor is stronger.
2. **Held-out contracts and schemas.** Do not define all tasks and recovery logic over one synthetic schema family.
3. **Independent oracle.** Separate the benchmark answer/oracle implementation from the recovery implementation where practical.
4. **Useful failures beyond retrieval pointers.** Demonstrate contract violations that matter for aggregate completeness, negative evidence, temporal state, relations, or provenance, not only a string moved behind a retrievable marker.
5. **Baseline with native safeguards.** Include the transformer's strict-lossless / preservation configuration and direct projection.
6. **End-to-end agent evaluation.** Only if it answers a remaining question; do not spend API money merely to decorate an already-resolved fixed-task result.
7. **Failure-policy evaluation.** Measure how often the verifier accepts, recovers, or falls back under transformer/version changes and what cost that imposes.

## Publication decision rule

Before revising the paper around this narrower contribution, require at least one experiment where:

- direct task-aware projection is not a valid substitute for the transformation under test;
- the external/native safeguard does not already guarantee the declared contract;
- the verifier catches meaningful task-property violations;
- recovery/fallback produces a measurable reliability benefit at bounded overhead; and
- the result holds on held-out structured schemas/contracts.

If that cannot be demonstrated, the responsible conclusion is that the current artifact is a useful reproducibility/engineering study but not yet evidence for a distinct research contribution.

## Sources checked

- Trukhina & Vashkelis, Context Codec: https://arxiv.org/abs/2605.17304
- Pnueli, Siegel & Singerman, Translation Validation: https://weizmann.elsevierpure.com/en/publications/translation-validation-2/
- Kang et al., ACON: https://arxiv.org/abs/2510.00615
- Pan et al., LLMLingua-2: https://aclanthology.org/2024.findings-acl.57/

AI assistance: Pramod Ubbala directed the research follow-up. ChatGPT performed the prior-art search and drafted this risk assessment. It is a working research note, not a peer-reviewed novelty opinion.
