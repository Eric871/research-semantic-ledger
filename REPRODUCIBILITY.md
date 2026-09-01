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
3. explicitly disables DeepSeek V4 thinking mode for strict JSON extraction;
4. records every request, response, usage receipt, finish reason, and observed model locally, including parse failures;
5. forbids automatic retries;
6. requires an explicit split response rather than accepting truncated chunks;
7. applies recorded, conservative repairs only when source evidence or contract cardinality determines the result;
8. validates exact evidence, binding states, atomicity fields, relation endpoints, relation vocabulary, and line dispositions;
9. writes a candidate JSON ledger and deterministic Markdown projection;
10. performs zero formal database writes.

This is procedural reproduction, not byte-for-byte reproduction. Hosted-model behavior may change even when the visible model name and Prompt are unchanged.

If `--max-cost-cny` is used, current input and output prices must also be supplied. The project does not hard-code a price that may become stale.

### Resume without repurchasing successful work

A validated document frame can be reused after the current source is checked against it:

```bash
python -m research_semantic_ledger extract path/to/document.md \
  --authorize-external-send \
  --reuse-document-frame path/to/prior/document-frame.json
```

Successful responses from one or more prior run directories can be replayed only when the system Prompt and canonical JSON request payload match exactly:

```bash
python -m research_semantic_ledger extract path/to/document.md \
  --authorize-external-send \
  --replay-successful-calls path/to/prior/run
```

An exact replay records zero billable usage for the resumed run and retains the original usage for audit. A replay miss becomes a new external call and remains subject to authorization, call, and cost ceilings. Prior run directories contain source-bearing material and must stay private.

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
| DeepSeek request, failure-receipt, frame-reuse, and exact-replay procedure | Runnable with authorization and credentials |
| Exact provider output | Nondeterministic; not promised |
| Internal single-document aggregate metrics | Reported, but licensed artifacts are private |
| General unseen-document semantic accuracy | Unproven |
| Automatic database promotion | Not implemented |
