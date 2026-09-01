# Public contracts

- `semantic-ledger-v0.2.schema.json` documents the generic candidate-ledger envelope.
- `gold-v0.1.schema.json` documents public-safe evaluation cases.
- Runtime validation remains dependency-free and is implemented in `research_semantic_ledger/validation.py`.

The schemas are documentation and interoperability artifacts. The runtime validator additionally enforces cross-record invariants that JSON Schema alone cannot express easily: exact source quotes, evidence-line bounds, unique IDs, existing relation endpoints, no relation self-loops, binding-state cardinality, and exactly-once nonblank-line dispositions.
