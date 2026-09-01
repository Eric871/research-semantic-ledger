# Agent handoff

Use this prompt after cloning the repository:

```text
Open this repository and read AGENTS.md first. Run:

python -m research_semantic_ledger doctor

If doctor passes, validate the generic fixture and its frozen Gold:

python -m research_semantic_ledger validate examples/synthetic-extracted-ledger.json
python -m research_semantic_ledger evaluate examples/synthetic-extracted-ledger.json --gold examples/synthetic-extraction-gold.json

Then run:

python -m unittest discover -s tests -v

Render the generic fixture with `python -m research_semantic_ledger render examples/synthetic-extracted-ledger.json --output outputs/example.md` and inspect the Markdown. Run `python -m research_semantic_ledger extract examples/synthetic-research-note.md --dry-run` to verify the no-network preflight. Report the verified capabilities and boundaries before making changes. Never run online extraction, request credentials, or add `--authorize-external-send` unless the user explicitly authorizes sending the named source to the named endpoint/model. For an interrupted authorized run, inspect `--reuse-document-frame` and `--replay-successful-calls` before purchasing duplicate work; prior run directories remain private and replay misses are new external calls. Preserve evidence links, keep generated records in candidate state, use the closed relation vocabulary, add or update dependency-free tests, and rerun doctor plus unittest before declaring completion.
```

Expected first-run outcome: doctor returns JSON with `status: "pass"`; generic validation and six public Gold cases pass; preflight makes zero provider calls; the Markdown file is created; and all unit tests pass.
