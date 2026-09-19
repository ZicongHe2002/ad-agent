# Agent pipeline

Model output is advisory and structured. Deterministic identity, capability, claim, duplication, and hard-risk gates remain authoritative.

## Stages

```text
Normalized post
→ concrete anchor extraction
→ opportunity components and deterministic score
→ strategy selection
→ 2 candidate comments in one structured response
→ authenticity and quality evaluation
→ rule risk engine
→ semantic risk only when rules leave uncertainty
→ allow, human review, or block
```

FAST mode may skip full video, full ASR, and large multimodal analysis. It may not skip capability, identity, anchor, approved-claim, duplicate, disclosure, or hard-risk checks. If context is insufficient, the workflow falls back to deeper analysis or skips; it never publishes a generic template.

## Prompt and output provenance

Persist the prompt name/version/hash, provider, model, provider request ID, referenced anchors, referenced approved claims, generation reason, and content provenance. Invalid structured output receives at most one approved repair attempt.

## Content rules

- Speak only as the declared account identity.
- Ground each candidate in at least one supported post anchor.
- Never invent purchase, use, demographic, professional, or personal experience.
- Use only approved product claims.
- Avoid generic praise, competitor attacks, off-platform contact, and intentional typo patterns.
- Never optimize against an AI detector or conceal required disclosure.

Human-edited text must return through all mandatory checks before it can become publish-ready.
