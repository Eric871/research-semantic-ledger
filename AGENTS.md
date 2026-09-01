# Agent operating guide

## Start here

1. Run `python -m research_semantic_ledger doctor` from the repository root.
2. Read `README.md`, then `SECURITY_AND_DATA.md` before using non-synthetic data.
3. Use `python -m research_semantic_ledger summary examples/synthetic-group-reference.json` as the first functional example.

Python 3.11 or newer is the only runtime requirement. Do not install dependencies or request credentials for the public conformance workflow.

## Commands

- Doctor: `python -m research_semantic_ledger doctor`
- Validate: `python -m research_semantic_ledger validate <ledger.json>`
- Summarize: `python -m research_semantic_ledger summary <ledger.json>`
- Tests: `python -m unittest discover -s tests -v`
- Legacy fixture check: `python scripts/validate_synthetic_fixture.py`

## Hard boundaries

- Treat generated records as candidates; this repository performs no formal database writes.
- Never commit licensed source text, raw provider payloads, human Gold, credentials, audit databases, or reviewer identities.
- Do not claim that the public checkout includes full-document extraction, online provider replay, or the audit dashboard.
- Keep public examples synthetic and evidence-linked.
- Fail closed on invalid evidence lines, missing relation endpoints, and unsupported binding states.

## Definition of done

A change is ready only when doctor, unittest, the legacy fixture check, secret/path scans, and GitHub Actions all pass. See `AGENT_HANDOFF.md` for the copyable onboarding prompt and `REPRODUCIBILITY.md` for capability tiers.
