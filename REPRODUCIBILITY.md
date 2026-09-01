# Reproducibility

Research Semantic Ledger separates deterministic replay from nondeterministic provider inference.

## Level 1: synthetic conformance

Requirements: Python 3.11 or newer; no third-party Python packages.

```bash
python -m research_semantic_ledger doctor
python -m research_semantic_ledger validate examples/synthetic-group-reference.json
python -m research_semantic_ledger summary examples/synthetic-group-reference.json
python -m unittest discover -s tests -v
```

These commands diagnose the checkout, validate evidence spans and relation endpoints, emit a structural summary, and run fail-closed regressions. The legacy command `python scripts/validate_synthetic_fixture.py` remains supported. This demonstrates contracts and gates, not model quality.

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

The dependency-free Agent quick start passes in the working tree, the standalone repository, and GitHub Actions. This is the public reproduction claim made by the current MVP.

The provider runners, licensed source, provider payloads, human Gold, audit database, and dashboard are intentionally deferred. Their existing internal implementations still have machine-specific paths and private-artifact dependencies; each component requires a separate portability and publication review before it can be added.

The owner selected Apache-2.0 and authorized the first minimal push. Initial commit `0117566` was published to `main`, and GitHub Actions conformance run `33460073495` completed successfully. The release evidence is tracked in `release-manifest.json`.
