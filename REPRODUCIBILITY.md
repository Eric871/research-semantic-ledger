# Reproducibility

Research Semantic Ledger separates deterministic replay from nondeterministic provider inference.

## Level 1: synthetic conformance

Requirements: Python 3.11 or newer; no third-party Python packages.

```powershell
python scripts/validate_synthetic_fixture.py
```

This validates evidence spans, entity-set membership, scope exclusions, claim references, and relation endpoints in the public-safe fixture. It demonstrates contracts and gates, not model quality.

## Level 2: internal offline replay

The internal replay starts from preserved provider responses and frozen manifests. It can deterministically reproduce normalization, ID namespacing, cue accounting, evaluation, and audit-bundle generation.

The private artifact pack must include:

- immutable source plus SHA-256;
- chunk and cue manifests;
- prompt and provider contracts;
- raw provider responses and usage receipts;
- validator and repair versions;
- expected result hashes.

Licensed source text and raw provider payloads are intentionally absent from the GitHub preparation bundle. The future repository should accept their location through configuration rather than hard-coded machine paths.

## Level 3: online provider replay

Online replay requires an explicitly authorized provider, model, endpoint, credential, and cost ceiling. It is a procedural reproduction, not a byte-for-byte reproduction: hosted model behavior may change even when the visible model name and prompt are unchanged.

The runner must:

1. freeze the exact source and contract hashes;
2. estimate and enforce the cost ceiling before the request;
3. record request, response, provider usage, finish reason, and observed model ID;
4. forbid blind retries;
5. keep provider, JSON-contract, and semantic-Gold gates separate;
6. write zero formal database records without a separate promotion authorization.

## Current public-export status

The dependency-free synthetic conformance check passes both in the working tree and in a fresh clone of the empty target repository. This is the only public reproduction claim made by the initial export.

The provider runners, licensed source, provider payloads, human Gold, audit database, and dashboard are intentionally deferred. Their existing internal implementations still have machine-specific paths and private-artifact dependencies; each component requires a separate portability and publication review before it can be added.

The owner selected Apache-2.0 and authorized the first minimal push. Initial commit `0117566` was published to `main`, and GitHub Actions conformance run `33460073495` completed successfully. The release evidence is tracked in `release-manifest.json`.
