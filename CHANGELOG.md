# Changelog

## 0.3.1 - 2026-09-01

- Explicitly disable DeepSeek V4 thinking mode for strict JSON extraction.
- Preserve provider envelopes and billable usage when response parsing fails.
- Reuse a validated document frame and replay successful calls by exact request fingerprint.
- Record conservative deterministic repairs for evidence, relation coverage, binding cardinality, and recoverable mention surfaces.
- Add provider and repair regressions; 27 dependency-free unit tests and GitHub conformance pass.

## 0.3.0 - 2026-09-01

- Add the authorized DeepSeek full-document runner, frozen Prompt contracts, source and chunk manifests, and configurable call/cost ceilings.
- Add evidence-linked candidate JSON, deterministic Markdown rendering, public synthetic Gold, and fail-closed validation.
- Add cross-agent onboarding, security boundaries, and reproducibility tiers.
