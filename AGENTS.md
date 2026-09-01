# Agent operating guide

## Start here

1. Run `python -m research_semantic_ledger doctor` from the repository root.
2. Read `README.md`, then `SECURITY_AND_DATA.md` before using non-synthetic data.
3. Validate and evaluate `examples/synthetic-extracted-ledger.json` before using non-synthetic input.

Python 3.11 or newer is the only runtime requirement. Do not install dependencies or request credentials for the public conformance workflow.

## Commands

- Doctor: `python -m research_semantic_ledger doctor`
- Validate: `python -m research_semantic_ledger validate <ledger.json>`
- Summarize: `python -m research_semantic_ledger summary <ledger.json>`
- Render Markdown: `python -m research_semantic_ledger render <ledger.json> --output <ledger.md>`
- Extraction preflight: `python -m research_semantic_ledger extract <document.md> --dry-run`
- Authorized DeepSeek extraction: `python -m research_semantic_ledger extract <document.md> --authorize-external-send`
- Gold evaluation: `python -m research_semantic_ledger evaluate <ledger.json> --gold <gold.json>`
- Tests: `python -m unittest discover -s tests -v`
- Legacy fixture check: `python scripts/validate_synthetic_fixture.py`

## Hard boundaries

- Treat generated records as candidates; this repository performs no formal database writes.
- Never commit licensed source text, source-bearing provider payloads, licensed-document Gold, credentials, audit databases, or reviewer identities.
- Online extraction requires explicit source-transmission authorization. Never add the authorization flag on the user's behalf.
- Treat online extraction as nondeterministic candidate generation, not provider-quality proof.
- The public checkout does not include licensed artifacts, private audit data, database promotion, or an audit dashboard.
- Keep public examples synthetic and evidence-linked.
- Fail closed on invalid evidence lines, missing relation endpoints, unsupported binding states, relation-vocabulary drift, and budget/call-ceiling violations.

## Definition of done

A change is ready only when doctor, unittest, the legacy fixture check, secret/path scans, and GitHub Actions all pass. See `AGENT_HANDOFF.md` for the copyable onboarding prompt and `REPRODUCIBILITY.md` for capability tiers.
