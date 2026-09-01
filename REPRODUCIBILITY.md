# Reproducibility

Research Semantic Ledger separates deterministic preparation and validation from nondeterministic provider inference.

## Level 1: synthetic conformance

Requirements: Python 3.11 or newer; no third-party Python packages.

```bash
python -m research_semantic_ledger doctor
python -m research_semantic_ledger validate examples/synthetic-extracted-ledger.json
python -m research_semantic_ledger evaluate examples/synthetic-extracted-ledger.json --gold examples/synthetic-extraction-gold.json
python -m research_semantic_ledger render examples/synthetic-extracted-ledger.json --output outputs/example.md
python -m unittest discover -s tests -v
```

These commands validate exact evidence, binding states, relation endpoints, the closed relation vocabulary, source-line dispositions, public Gold, and deterministic Markdown rendering. This demonstrates contracts and gates, not provider quality.

## Level 2: extraction preflight

```bash
python -m research_semantic_ledger extract path/to/document.md --dry-run
```

Preflight normalizes UTF-8 newlines, records original and normalized SHA-256 values, freezes line anchors and chunk boundaries, records Prompt hashes and model settings, and makes zero network calls. Documents larger than the configured context boundary fail before transmission.

## Level 3: online DeepSeek extraction

Online extraction requires an explicitly authorized source, endpoint, model, credential, and call/cost ceiling as appropriate.

```bash
python -m research_semantic_ledger extract path/to/document.md \
  --authorize-external-send \
  --model deepseek-v4-flash \
  --max-calls 100
```

The runner:

1. freezes source, chunk, Prompt, model, and budget lineage;
2. builds a document frame before occurrence-level extraction;
3. records every request, response, usage receipt, finish reason, and observed model locally;
4. forbids automatic retries;
5. requires an explicit split response rather than accepting truncated chunks;
6. validates exact evidence, binding states, atomicity fields, relation endpoints, relation vocabulary, and line dispositions;
7. writes a candidate JSON ledger and deterministic Markdown projection;
8. performs zero formal database writes.

This is procedural reproduction, not byte-for-byte reproduction. Hosted-model behavior may change even when the visible model name and Prompt are unchanged.

If `--max-cost-cny` is used, current input and output prices must also be supplied. The project does not hard-code a price that may become stale.

## Level 4: private semantic audit

Auditing a licensed document requires a private artifact pack containing:

- immutable source plus SHA-256;
- chunk and source-line manifests;
- exact Prompt and provider contracts;
- raw provider responses and usage receipts;
- validator versions and validation receipts;
- human Gold frozen before judging model output;
- expected result hashes and adjudication notes.

Licensed source text, source-bearing provider payloads, reviewer identities, private Gold, and audit databases must remain outside the public repository.

## What can and cannot be reproduced

| Capability | Current status |
|---|---|
| Public synthetic validation, Gold, tests, and Markdown | Deterministically reproducible |
| Source hashing and chunk preflight | Deterministically reproducible |
| DeepSeek request procedure and receipts | Runnable with authorization and credentials |
| Exact provider output | Nondeterministic; not promised |
| Internal single-document aggregate metrics | Reported, but licensed artifacts are private |
| General unseen-document semantic accuracy | Unproven |
| Automatic database promotion | Not implemented |
