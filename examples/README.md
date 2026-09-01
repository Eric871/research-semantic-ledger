# Synthetic examples

Every file in this directory is fabricated for contract and gate demonstration. None contains a company, policy, metric, document identifier, or wording copied from the licensed internal source.

The fixture demonstrates two entity-set reference structures:

- a plural anaphor that must resolve to two explicitly named organizations;
- an open-scope entity set represented by explicit exclusions.

`synthetic-research-note.md` is the portable source example. `synthetic-extracted-ledger.json` is its generic candidate ledger, and `synthetic-extraction-gold.json` freezes six public-safe evaluation cases spanning reference resolution, atomic claims, and narrative relations.

Run from the repository root:

```bash
python -m research_semantic_ledger doctor
python -m research_semantic_ledger evaluate examples/synthetic-extracted-ledger.json --gold examples/synthetic-extraction-gold.json
python -m research_semantic_ledger extract examples/synthetic-research-note.md --dry-run
```
