"""Portable, fail-closed full-document extraction orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

from .provider import JsonProvider, ProviderError, ProviderResponse
from .validation import ALLOWED_RELATION_TYPES, GENERIC_SCHEMA_VERSION, validate_document


class ExtractionError(RuntimeError):
    """A terminal preflight, provider-contract, or validation failure."""


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    source_path: Path
    raw_sha256: str
    normalized_sha256: str
    lines: tuple[str, ...]


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    start_line: int
    end_line: int
    numbered_lines: tuple[dict[str, Any], ...]


@dataclass
class Budget:
    max_calls: int
    max_cost_cny: float | None = None
    input_price_cny_per_million: float | None = None
    output_price_cny_per_million: float | None = None
    calls: int = 0
    replayed_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_cny: float = 0.0

    def _price_ready(self) -> bool:
        return self.input_price_cny_per_million is not None and self.output_price_cny_per_million is not None

    def authorize_call(self, system_prompt: str, user_payload: dict[str, Any], max_output_tokens: int) -> None:
        if self.calls >= self.max_calls:
            raise ExtractionError("max_calls_would_be_exceeded")
        if self.max_cost_cny is None:
            return
        if not self._price_ready():
            raise ExtractionError("cost_ceiling_requires_input_and_output_prices")
        serialized_input = system_prompt + json.dumps(user_payload, ensure_ascii=False)
        conservative_input_tokens = len(serialized_input.encode("utf-8"))
        upper_cost = (
            conservative_input_tokens * float(self.input_price_cny_per_million)
            + max_output_tokens * float(self.output_price_cny_per_million)
        ) / 1_000_000
        if self.estimated_cost_cny + upper_cost > self.max_cost_cny:
            raise ExtractionError("cost_ceiling_would_be_exceeded")

    def record(self, response: ProviderResponse) -> None:
        self.calls += 1
        if response.replayed:
            self.replayed_calls += 1
        prompt_tokens = int(response.usage.get("prompt_tokens") or 0)
        completion_tokens = int(response.usage.get("completion_tokens") or 0)
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        if self._price_ready():
            self.estimated_cost_cny += (
                prompt_tokens * float(self.input_price_cny_per_million)
                + completion_tokens * float(self.output_price_cny_per_million)
            ) / 1_000_000
        if self.max_cost_cny is not None and self.estimated_cost_cny > self.max_cost_cny:
            raise ExtractionError("observed_cost_ceiling_exceeded")

    def receipt(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "external_calls": self.calls - self.replayed_calls,
            "replayed_calls": self.replayed_calls,
            "max_calls": self.max_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "estimated_cost_cny": round(self.estimated_cost_cny, 9) if self._price_ready() else None,
            "max_cost_cny": self.max_cost_cny,
            "input_price_cny_per_million": self.input_price_cny_per_million,
            "output_price_cny_per_million": self.output_price_cny_per_million,
        }


@dataclass(frozen=True)
class ExtractionConfig:
    max_chunk_chars: int = 6_000
    max_context_chars: int = 120_000
    max_output_tokens: int = 12_000
    max_calls: int = 100
    max_cost_cny: float | None = None
    input_price_cny_per_million: float | None = None
    output_price_cny_per_million: float | None = None
    reuse_document_frame_path: Path | None = None
    replay_receipt_dirs: tuple[Path, ...] = ()


@dataclass
class ExtractionState:
    output_dir: Path
    run_id: str
    provider_name: str
    model_name: str
    budget: Budget
    raw_receipts: list[dict[str, Any]] = field(default_factory=list)
    local_repairs: list[dict[str, Any]] = field(default_factory=list)


def _prompt(name: str) -> str:
    return resources.files("research_semantic_ledger").joinpath("prompts", name).read_text(encoding="utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def load_source(path: Path, document_id: str | None = None) -> SourceDocument:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ExtractionError(f"source_read_error:{type(exc).__name__}:{exc}") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ExtractionError("source_must_be_utf8") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines or not any(line.strip() for line in lines):
        raise ExtractionError("source_has_no_nonblank_lines")
    return SourceDocument(
        document_id=document_id or path.stem,
        source_path=path.resolve(),
        raw_sha256=_sha256_bytes(raw),
        normalized_sha256=_sha256_text("\n".join(lines)),
        lines=tuple(lines),
    )


def plan_chunks(document: SourceDocument, max_chunk_chars: int) -> list[SourceChunk]:
    if max_chunk_chars < 256:
        raise ExtractionError("max_chunk_chars_must_be_at_least_256")
    chunks: list[SourceChunk] = []
    start = 1
    current: list[dict[str, Any]] = []
    current_chars = 0
    for number, line in enumerate(document.lines, start=1):
        line_cost = len(line) + 24
        if current and current_chars + line_cost > max_chunk_chars:
            chunks.append(
                SourceChunk(
                    chunk_id=f"CH-{len(chunks) + 1:04d}",
                    start_line=start,
                    end_line=int(current[-1]["line"]),
                    numbered_lines=tuple(current),
                )
            )
            start = number
            current = []
            current_chars = 0
        current.append({"line": number, "text": line})
        current_chars += line_cost
    if current:
        chunks.append(
            SourceChunk(
                chunk_id=f"CH-{len(chunks) + 1:04d}",
                start_line=start,
                end_line=int(current[-1]["line"]),
                numbered_lines=tuple(current),
            )
        )
    return chunks


def _validate_support_lines(values: Any, document: SourceDocument, label: str) -> None:
    if not isinstance(values, list) or not values or not all(
        isinstance(number, int) and 1 <= number <= len(document.lines) for number in values
    ):
        raise ExtractionError(f"document_frame_support_lines_invalid:{label}")


def _validate_document_frame(payload: dict[str, Any], document: SourceDocument) -> None:
    required = {
        "document_frame",
        "entity_candidates",
        "event_candidates",
        "discourse_segments",
        "unresolved_document_questions",
    }
    if not required.issubset(payload):
        raise ExtractionError(f"document_frame_fields_missing:{sorted(required - set(payload))}")
    frame = payload.get("document_frame")
    if not isinstance(frame, dict) or frame.get("document_id") != document.document_id:
        raise ExtractionError("document_frame_identity_invalid")
    for key in ("entity_candidates", "event_candidates", "discourse_segments", "unresolved_document_questions"):
        if not isinstance(payload.get(key), list):
            raise ExtractionError(f"document_frame_{key}_must_be_array")
    for index, row in enumerate(payload["entity_candidates"]):
        if not isinstance(row, dict) or not row.get("candidate_id") or not row.get("canonical_name"):
            raise ExtractionError(f"document_frame_entity_invalid:{index}")
        _validate_support_lines(row.get("support_lines"), document, f"entity:{index}")
    for index, row in enumerate(payload["event_candidates"]):
        if not isinstance(row, dict) or not row.get("candidate_id") or not row.get("canonical_name"):
            raise ExtractionError(f"document_frame_event_invalid:{index}")
        _validate_support_lines(row.get("support_lines"), document, f"event:{index}")


def _invoke(
    provider: JsonProvider,
    state: ExtractionState,
    *,
    call_role: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    max_output_tokens: int,
) -> dict[str, Any]:
    state.budget.authorize_call(system_prompt, user_payload, max_output_tokens)
    call_number = state.budget.calls + 1
    try:
        response = provider.complete_json(
            system_prompt=system_prompt,
            user_payload=user_payload,
            max_output_tokens=max_output_tokens,
        )
    except ProviderError as exc:
        raw_response = getattr(exc, "raw_response", None)
        receipt = {
            "call_number": call_number,
            "call_role": call_role,
            "status": "provider_error",
            "error": str(exc),
            "request": {"system_prompt": system_prompt, "user_payload": user_payload},
        }
        budget_error: str | None = None
        if isinstance(raw_response, dict):
            usage_raw = raw_response.get("usage")
            usage = {
                "prompt_tokens": int((usage_raw or {}).get("prompt_tokens") or 0),
                "completion_tokens": int((usage_raw or {}).get("completion_tokens") or 0),
                "total_tokens": int((usage_raw or {}).get("total_tokens") or 0),
            }
            choices = raw_response.get("choices")
            choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
            observed_model = raw_response.get("model")
            response_for_budget = ProviderResponse(
                payload={},
                raw_response=raw_response,
                usage=usage,
                observed_model=observed_model if isinstance(observed_model, str) else None,
                finish_reason=choice.get("finish_reason") if isinstance(choice.get("finish_reason"), str) else None,
            )
            try:
                state.budget.record(response_for_budget)
            except ExtractionError as budget_exc:
                budget_error = str(budget_exc)
            receipt.update(
                {
                    "response": raw_response,
                    "usage": usage,
                    "observed_model": response_for_budget.observed_model,
                    "finish_reason": response_for_budget.finish_reason,
                }
            )
        if budget_error is not None:
            receipt["budget_error"] = budget_error
        state.raw_receipts.append(receipt)
        _write_json(state.output_dir / "raw" / f"call-{call_number:04d}.json", receipt)
        if budget_error is not None:
            raise ExtractionError(budget_error) from exc
        raise ExtractionError(str(exc)) from exc
    state.budget.record(response)
    receipt = {
        "call_number": call_number,
        "call_role": call_role,
        "status": "success",
        "request": {"system_prompt": system_prompt, "user_payload": user_payload},
        "response": response.raw_response,
        "usage": response.usage,
        "observed_model": response.observed_model,
        "finish_reason": response.finish_reason,
        "replayed": response.replayed,
        "replay_original_usage": response.replay_original_usage,
    }
    state.raw_receipts.append(receipt)
    _write_json(state.output_dir / "raw" / f"call-{call_number:04d}.json", receipt)
    return response.payload


def _ids(rows: Any, key: str, label: str) -> set[str]:
    if not isinstance(rows, list):
        raise ExtractionError(f"chunk_{label}_must_be_array")
    result: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ExtractionError(f"chunk_{label}_{index}_must_be_object")
        value = row.get(key)
        if not isinstance(value, str) or not value or value in result:
            raise ExtractionError(f"chunk_{label}_{key}_invalid:{index}")
        result.add(value)
    return result


def _validate_chunk_payload(payload: dict[str, Any], chunk: SourceChunk, document: SourceDocument) -> None:
    required = {
        "chunk_id",
        "mention_bindings",
        "claims",
        "relations",
        "segment_dispositions",
        "split_required",
        "split_after_line",
        "unresolved_items",
    }
    if not required.issubset(payload):
        raise ExtractionError(f"chunk_fields_missing:{sorted(required - set(payload))}")
    if payload.get("chunk_id") != chunk.chunk_id:
        raise ExtractionError("chunk_identity_mismatch")
    if payload.get("split_required") is True:
        for key in ("mention_bindings", "claims", "relations", "segment_dispositions"):
            if payload.get(key) != []:
                raise ExtractionError("split_response_must_not_contain_candidates")
        split_line = payload.get("split_after_line")
        if not isinstance(split_line, int) or not chunk.start_line <= split_line < chunk.end_line:
            raise ExtractionError("split_after_line_invalid")
        return
    if payload.get("split_required") is not False or payload.get("split_after_line") is not None:
        raise ExtractionError("chunk_split_contract_invalid")

    binding_ids = _ids(payload.get("mention_bindings"), "binding_id", "bindings")
    claim_ids = _ids(payload.get("claims"), "claim_id", "claims")
    _ids(payload.get("relations"), "relation_id", "relations")
    if len(claim_ids) > 24:
        raise ExtractionError("chunk_candidate_limit_exceeded")
    chunk_lines = set(range(chunk.start_line, chunk.end_line + 1))
    for row in payload["mention_bindings"]:
        evidence_lines = row.get("evidence_lines")
        if not isinstance(evidence_lines, list) or not evidence_lines or not set(evidence_lines).issubset(chunk_lines):
            raise ExtractionError(f"chunk_binding_evidence_invalid:{row['binding_id']}")
        surface = row.get("surface")
        if not isinstance(surface, str) or not any(surface in document.lines[number - 1] for number in evidence_lines):
            raise ExtractionError(f"chunk_binding_surface_not_exact:{row['binding_id']}")
        entity_ids = row.get("canonical_entity_ids")
        entity_names = row.get("canonical_names")
        if not isinstance(entity_ids, list) or not isinstance(entity_names, list) or len(entity_ids) != len(entity_names):
            raise ExtractionError(f"chunk_binding_entity_names_mismatch:{row['binding_id']}")
    for row in payload["claims"]:
        evidence_lines = row.get("evidence_lines")
        if not isinstance(evidence_lines, list) or not evidence_lines or not set(evidence_lines).issubset(chunk_lines):
            raise ExtractionError(f"chunk_claim_evidence_invalid:{row['claim_id']}")
        quotes = row.get("evidence_quotes")
        evidence_text = "\n".join(document.lines[number - 1] for number in evidence_lines)
        if not isinstance(quotes, list) or not quotes or any(
            not isinstance(quote, str) or not quote or quote not in evidence_text for quote in quotes
        ):
            raise ExtractionError(f"chunk_claim_quote_not_exact:{row['claim_id']}")
        references = row.get("mention_binding_ids")
        if not isinstance(references, list) or any(value not in binding_ids for value in references):
            raise ExtractionError(f"chunk_claim_binding_invalid:{row['claim_id']}")
        unresolved = row.get("unresolved_fields")
        if not isinstance(unresolved, list):
            raise ExtractionError(f"chunk_claim_unresolved_fields_invalid:{row['claim_id']}")
        if row.get("canonical_subject") is None and "canonical_subject" not in unresolved:
            raise ExtractionError(f"chunk_claim_null_subject_not_marked_unresolved:{row['claim_id']}")
    for row in payload["relations"]:
        if row.get("relation_type") not in ALLOWED_RELATION_TYPES:
            raise ExtractionError(f"chunk_relation_type_invalid:{row['relation_id']}")
        source_ids = row.get("source_claim_ids")
        target_ids = row.get("target_claim_ids")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or not set(source_ids).issubset(claim_ids)
            or not isinstance(target_ids, list)
            or not target_ids
            or not set(target_ids).issubset(claim_ids)
            or set(source_ids) & set(target_ids)
        ):
            raise ExtractionError(f"chunk_relation_endpoint_invalid:{row['relation_id']}")
        evidence_lines = row.get("evidence_lines")
        if not isinstance(evidence_lines, list) or not evidence_lines or not set(evidence_lines).issubset(chunk_lines):
            raise ExtractionError(f"chunk_relation_evidence_invalid:{row['relation_id']}")
        endpoint_lines = {
            number
            for endpoint_id in source_ids + target_ids
            for number in next(claim for claim in payload["claims"] if claim["claim_id"] == endpoint_id)["evidence_lines"]
        }
        if not endpoint_lines.issubset(set(evidence_lines)):
            raise ExtractionError(f"chunk_relation_evidence_does_not_cover_endpoints:{row['relation_id']}")
    seen: list[int] = []
    if not isinstance(payload.get("segment_dispositions"), list):
        raise ExtractionError("chunk_segment_dispositions_must_be_array")
    for row in payload["segment_dispositions"]:
        if not isinstance(row, dict) or not isinstance(row.get("source_lines"), list):
            raise ExtractionError("chunk_segment_disposition_invalid")
        seen.extend(row["source_lines"])
        if any(value not in claim_ids for value in row.get("claim_ids") or []):
            raise ExtractionError("chunk_segment_disposition_claim_reference_invalid")
        relation_ids = {relation["relation_id"] for relation in payload["relations"]}
        if any(value not in relation_ids for value in row.get("relation_ids") or []):
            raise ExtractionError("chunk_segment_disposition_relation_reference_invalid")
    expected = {number for number in chunk_lines if document.lines[number - 1].strip()}
    if set(seen) != expected or len(seen) != len(set(seen)):
        raise ExtractionError("chunk_segment_disposition_coverage_invalid")


def _split_chunk(chunk: SourceChunk, split_after_line: int, suffix: str) -> tuple[SourceChunk, SourceChunk]:
    left_lines = tuple(row for row in chunk.numbered_lines if int(row["line"]) <= split_after_line)
    right_lines = tuple(row for row in chunk.numbered_lines if int(row["line"]) > split_after_line)
    return (
        SourceChunk(f"{chunk.chunk_id}-{suffix}A", chunk.start_line, split_after_line, left_lines),
        SourceChunk(f"{chunk.chunk_id}-{suffix}B", split_after_line + 1, chunk.end_line, right_lines),
    )


def _drop_blank_line_dispositions(
    payload: dict[str, Any], chunk: SourceChunk, document: SourceDocument
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Remove semantically empty dispositions emitted only for blank lines.

    The Prompt requires dispositions for nonblank lines only. A provider may
    nevertheless mark a blank separator as ignored. Removing that row does not
    change any extracted claim, relation, or evidence and is therefore a safe,
    deterministic repair. Any row carrying semantic references still fails
    closed in the normal validator.
    """

    dispositions = payload.get("segment_dispositions")
    if not isinstance(dispositions, list):
        return payload, []
    chunk_lines = {int(row["line"]) for row in chunk.numbered_lines}
    kept: list[Any] = []
    removed_lines: list[int] = []
    for row in dispositions:
        source_lines = row.get("source_lines") if isinstance(row, dict) else None
        safe_blank_only = (
            isinstance(source_lines, list)
            and bool(source_lines)
            and all(
                isinstance(number, int)
                and number in chunk_lines
                and not document.lines[number - 1].strip()
                for number in source_lines
            )
            and row.get("status") == "ignored_with_reason"
            and not (row.get("claim_ids") or [])
            and not (row.get("relation_ids") or [])
        )
        if safe_blank_only:
            removed_lines.extend(source_lines)
        else:
            kept.append(row)
    if not removed_lines:
        return payload, []
    repaired = dict(payload)
    repaired["segment_dispositions"] = kept
    return repaired, [
        {
            "repair_type": "drop_blank_line_dispositions",
            "chunk_id": chunk.chunk_id,
            "source_lines": sorted(removed_lines),
            "semantic_fields_changed": False,
        }
    ]


def _repair_binding_entity_name_mismatches(
    payload: dict[str, Any], frame_payload: dict[str, Any], chunk: SourceChunk
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Repair only structurally provable binding/name mismatches.

    Existing frame IDs may deterministically supply their canonical names. A
    provider-assigned name without any frame ID is not a resolved entity, so it
    is conservatively downgraded instead of manufacturing a new identity.
    """

    bindings = payload.get("mention_bindings")
    if not isinstance(bindings, list):
        return payload, []
    frame_names = {
        row["candidate_id"]: row["canonical_name"]
        for row in frame_payload.get("entity_candidates") or []
        if isinstance(row, dict)
        and isinstance(row.get("candidate_id"), str)
        and isinstance(row.get("canonical_name"), str)
    }
    repaired_bindings: list[Any] = []
    repair_rows: list[dict[str, Any]] = []
    changed = False
    for source in bindings:
        if not isinstance(source, dict):
            repaired_bindings.append(source)
            continue
        entity_ids = source.get("canonical_entity_ids")
        entity_names = source.get("canonical_names")
        status = source.get("resolution_status")
        row = dict(source)
        binding_id = row.get("binding_id")
        ids_are_known = (
            isinstance(entity_ids, list)
            and bool(entity_ids)
            and all(isinstance(value, str) and value in frame_names for value in entity_ids)
        )
        valid_resolved = status == "resolved" and ids_are_known and len(entity_ids) == 1
        valid_group = status == "group_resolved" and ids_are_known and len(entity_ids) >= 2
        valid_unresolved = (
            status in {"ambiguous", "unresolved", "class_not_unique"}
            and isinstance(entity_ids, list)
            and not entity_ids
        )
        if valid_resolved or valid_group:
            expected_names = [frame_names[value] for value in entity_ids]
            if isinstance(entity_names, list) and entity_names == expected_names:
                repaired_bindings.append(source)
                continue
            row["canonical_names"] = expected_names
            action = "fill_names_from_document_frame_ids"
            semantic_change = False
        elif valid_unresolved:
            if isinstance(entity_names, list) and not entity_names:
                repaired_bindings.append(source)
                continue
            row["canonical_names"] = []
            action = "clear_names_from_unresolved_binding"
            semantic_change = False
        else:
            row["resolution_status"] = "unresolved"
            row["canonical_entity_ids"] = []
            row["canonical_names"] = []
            row["confidence"] = "low"
            basis = row.get("resolution_basis")
            suffix = "Downgraded locally because the document-frame entity IDs do not support the declared resolution status."
            row["resolution_basis"] = f"{basis} {suffix}".strip() if isinstance(basis, str) else suffix
            action = "downgrade_unsupported_resolved_binding"
            semantic_change = True
        repaired_bindings.append(row)
        repair_rows.append(
            {
                "repair_type": action,
                "chunk_id": chunk.chunk_id,
                "binding_id": binding_id,
                "semantic_fields_changed": semantic_change,
            }
        )
        changed = True
    if not changed:
        return payload, []
    repaired = dict(payload)
    repaired["mention_bindings"] = repaired_bindings
    return repaired, repair_rows


def _deterministic_overflow_split_line(payload: dict[str, Any], chunk: SourceChunk) -> int | None:
    """Choose a stable line-boundary split when a provider ignores the 24-claim cap."""

    claims = payload.get("claims")
    if payload.get("split_required") is not False or not isinstance(claims, list) or len(claims) <= 24:
        return None
    line_numbers = [int(row["line"]) for row in chunk.numbered_lines]
    if len(line_numbers) < 2:
        return None
    return line_numbers[(len(line_numbers) - 1) // 2]


def _repair_relation_evidence_coverage(
    payload: dict[str, Any], chunk: SourceChunk
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Union endpoint claim evidence into relation evidence when provable locally."""

    claims = payload.get("claims")
    relations = payload.get("relations")
    if not isinstance(claims, list) or not isinstance(relations, list):
        return payload, []
    claim_lines = {
        row["claim_id"]: row.get("evidence_lines")
        for row in claims
        if isinstance(row, dict)
        and isinstance(row.get("claim_id"), str)
        and isinstance(row.get("evidence_lines"), list)
    }
    repaired_relations: list[Any] = []
    repairs: list[dict[str, Any]] = []
    changed = False
    for source in relations:
        if not isinstance(source, dict) or not isinstance(source.get("evidence_lines"), list):
            repaired_relations.append(source)
            continue
        endpoint_ids = (source.get("source_claim_ids") or []) + (source.get("target_claim_ids") or [])
        if not endpoint_ids or any(value not in claim_lines for value in endpoint_ids):
            repaired_relations.append(source)
            continue
        required_lines = {line for claim_id in endpoint_ids for line in claim_lines[claim_id]}
        current_lines = set(source["evidence_lines"])
        missing_lines = sorted(required_lines - current_lines)
        if not missing_lines:
            repaired_relations.append(source)
            continue
        row = dict(source)
        row["evidence_lines"] = sorted(current_lines | required_lines)
        repaired_relations.append(row)
        repairs.append(
            {
                "repair_type": "extend_relation_evidence_to_endpoint_claims",
                "chunk_id": chunk.chunk_id,
                "relation_id": row.get("relation_id"),
                "added_source_lines": missing_lines,
                "semantic_fields_changed": False,
            }
        )
        changed = True
    if not changed:
        return payload, []
    repaired = dict(payload)
    repaired["relations"] = repaired_relations
    return repaired, repairs


def _repair_inexact_claim_quotes(
    payload: dict[str, Any], chunk: SourceChunk, document: SourceDocument
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Replace inexact model quotes with the exact cited source lines."""

    claims = payload.get("claims")
    if not isinstance(claims, list):
        return payload, []
    chunk_lines = {int(row["line"]) for row in chunk.numbered_lines}
    repaired_claims: list[Any] = []
    repairs: list[dict[str, Any]] = []
    changed = False
    for source in claims:
        if not isinstance(source, dict):
            repaired_claims.append(source)
            continue
        evidence_lines = source.get("evidence_lines")
        quotes = source.get("evidence_quotes")
        if not isinstance(evidence_lines, list) or not evidence_lines or not set(evidence_lines).issubset(chunk_lines):
            repaired_claims.append(source)
            continue
        evidence_text = "\n".join(document.lines[number - 1] for number in evidence_lines)
        quotes_are_exact = isinstance(quotes, list) and bool(quotes) and all(
            isinstance(quote, str) and bool(quote) and quote in evidence_text for quote in quotes
        )
        if quotes_are_exact:
            repaired_claims.append(source)
            continue
        exact_lines = list(dict.fromkeys(document.lines[number - 1] for number in evidence_lines if document.lines[number - 1]))
        if not exact_lines:
            repaired_claims.append(source)
            continue
        row = dict(source)
        row["evidence_quotes"] = exact_lines
        repaired_claims.append(row)
        repairs.append(
            {
                "repair_type": "replace_inexact_quote_with_full_evidence_line",
                "chunk_id": chunk.chunk_id,
                "claim_id": row.get("claim_id"),
                "source_lines": evidence_lines,
                "semantic_fields_changed": False,
            }
        )
        changed = True
    if not changed:
        return payload, []
    repaired = dict(payload)
    repaired["claims"] = repaired_claims
    return repaired, repairs


def _longest_common_substring(left: str, right: str) -> str:
    previous = [0] * (len(right) + 1)
    best_length = 0
    best_end = 0
    for left_index, left_char in enumerate(left, start=1):
        current = [0] * (len(right) + 1)
        for right_index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                current[right_index] = previous[right_index - 1] + 1
                if current[right_index] > best_length:
                    best_length = current[right_index]
                    best_end = left_index
        previous = current
    return left[best_end - best_length : best_end]


def _repair_inexact_binding_surfaces(
    payload: dict[str, Any], chunk: SourceChunk, document: SourceDocument
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Use only a unique, sufficiently long exact substring to repair a surface."""

    bindings = payload.get("mention_bindings")
    if not isinstance(bindings, list):
        return payload, []
    chunk_lines = {int(row["line"]) for row in chunk.numbered_lines}
    repaired_bindings: list[Any] = []
    repairs: list[dict[str, Any]] = []
    dropped_binding_ids: set[str] = set()
    changed = False
    for source in bindings:
        if not isinstance(source, dict):
            repaired_bindings.append(source)
            continue
        surface = source.get("surface")
        evidence_lines = source.get("evidence_lines")
        if (
            not isinstance(surface, str)
            or not isinstance(evidence_lines, list)
            or not evidence_lines
            or not set(evidence_lines).issubset(chunk_lines)
        ):
            repaired_bindings.append(source)
            continue
        evidence_texts = [document.lines[number - 1] for number in evidence_lines]
        if any(surface in text for text in evidence_texts):
            repaired_bindings.append(source)
            continue
        candidates = [_longest_common_substring(surface, text) for text in evidence_texts]
        best_length = max((len(value) for value in candidates), default=0)
        best_values = {value for value in candidates if len(value) == best_length and value}
        minimum_length = max(4, (len(surface) + 1) // 2)
        evidence_text = "\n".join(evidence_texts)
        replacement = next(iter(best_values)) if len(best_values) == 1 else ""
        if best_length < minimum_length or not replacement or evidence_text.count(replacement) != 1:
            binding_id = source.get("binding_id")
            if isinstance(binding_id, str):
                dropped_binding_ids.add(binding_id)
            repairs.append(
                {
                    "repair_type": "drop_unanchored_binding",
                    "chunk_id": chunk.chunk_id,
                    "binding_id": binding_id,
                    "source_lines": evidence_lines,
                    "original_surface": surface,
                    "semantic_fields_changed": True,
                }
            )
            changed = True
            continue
        row = dict(source)
        row["surface"] = replacement
        repaired_bindings.append(row)
        repairs.append(
            {
                "repair_type": "replace_surface_with_unique_longest_exact_substring",
                "chunk_id": chunk.chunk_id,
                "binding_id": row.get("binding_id"),
                "source_lines": evidence_lines,
                "original_surface": surface,
                "replacement_surface": replacement,
                "semantic_fields_changed": False,
            }
        )
        changed = True
    if not changed:
        return payload, []
    repaired = dict(payload)
    repaired["mention_bindings"] = repaired_bindings
    if dropped_binding_ids and isinstance(payload.get("claims"), list):
        repaired_claims: list[Any] = []
        for source in payload["claims"]:
            if not isinstance(source, dict) or not isinstance(source.get("mention_binding_ids"), list):
                repaired_claims.append(source)
                continue
            row = dict(source)
            row["mention_binding_ids"] = [
                value for value in source["mention_binding_ids"] if value not in dropped_binding_ids
            ]
            repaired_claims.append(row)
        repaired["claims"] = repaired_claims
    return repaired, repairs


def _namespace_chunk(payload: dict[str, Any], chunk_id: str) -> dict[str, list[dict[str, Any]]]:
    binding_map = {row["binding_id"]: f"{chunk_id}::{row['binding_id']}" for row in payload["mention_bindings"]}
    claim_map = {row["claim_id"]: f"{chunk_id}::{row['claim_id']}" for row in payload["claims"]}
    relation_map = {row["relation_id"]: f"{chunk_id}::{row['relation_id']}" for row in payload["relations"]}
    bindings: list[dict[str, Any]] = []
    for source in payload["mention_bindings"]:
        row = dict(source)
        row["binding_id"] = binding_map[source["binding_id"]]
        bindings.append(row)
    claims: list[dict[str, Any]] = []
    for source in payload["claims"]:
        row = dict(source)
        row["claim_id"] = claim_map[source["claim_id"]]
        row["mention_binding_ids"] = [binding_map[value] for value in source.get("mention_binding_ids") or []]
        claims.append(row)
    relations: list[dict[str, Any]] = []
    for source in payload["relations"]:
        row = dict(source)
        row["relation_id"] = relation_map[source["relation_id"]]
        row["source_claim_ids"] = [claim_map[value] for value in source["source_claim_ids"]]
        row["target_claim_ids"] = [claim_map[value] for value in source["target_claim_ids"]]
        relations.append(row)
    dispositions: list[dict[str, Any]] = []
    for source in payload["segment_dispositions"]:
        row = dict(source)
        row["claim_ids"] = [claim_map[value] for value in source.get("claim_ids") or []]
        row["relation_ids"] = [relation_map[value] for value in source.get("relation_ids") or []]
        dispositions.append(row)
    return {
        "mention_bindings": bindings,
        "claims": claims,
        "relations": relations,
        "segment_dispositions": dispositions,
    }


def prepare_run(
    source_path: Path,
    output_dir: Path,
    *,
    document_id: str | None,
    config: ExtractionConfig,
    provider_name: str,
    model_name: str,
) -> tuple[SourceDocument, list[SourceChunk], str]:
    document = load_source(source_path, document_id)
    if sum(len(line) for line in document.lines) > config.max_context_chars:
        raise ExtractionError("document_exceeds_max_context_chars")
    chunks = plan_chunks(document, config.max_chunk_chars)
    run_id = f"RSL-{document.document_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    frame_prompt = _prompt("document-frame-v0.1.txt")
    chunk_prompt = _prompt("chunk-extraction-v0.1.txt")
    manifest = {
        "schema_version": "research_semantic_ledger_run_manifest_v0.1",
        "run_id": run_id,
        "status": "preflight",
        "source": {
            "document_id": document.document_id,
            "path": str(document.source_path),
            "raw_sha256": document.raw_sha256,
            "normalized_sha256": document.normalized_sha256,
            "line_count": len(document.lines),
        },
        "provider": {"name": provider_name, "model": model_name},
        "prompts": {
            "document_frame": {"version": "v0.1", "sha256": _sha256_text(frame_prompt)},
            "chunk_extraction": {"version": "v0.1", "sha256": _sha256_text(chunk_prompt)},
        },
        "config": {
            "max_chunk_chars": config.max_chunk_chars,
            "max_context_chars": config.max_context_chars,
            "max_output_tokens": config.max_output_tokens,
            "max_calls": config.max_calls,
            "max_cost_cny": config.max_cost_cny,
            "input_price_cny_per_million": config.input_price_cny_per_million,
            "output_price_cny_per_million": config.output_price_cny_per_million,
            "reuse_document_frame_path": (
                config.reuse_document_frame_path.resolve().as_posix()
                if config.reuse_document_frame_path is not None
                else None
            ),
            "replay_receipt_dirs": [path.resolve().as_posix() for path in config.replay_receipt_dirs],
        },
        "chunks": [
            {"chunk_id": row.chunk_id, "start_line": row.start_line, "end_line": row.end_line}
            for row in chunks
        ],
        "external_transmission_authorized": False,
        "formal_database_writes": 0,
    }
    _write_json(output_dir / "run-manifest.json", manifest)
    _write_json(
        output_dir / "source-manifest.json",
        {
            "document_id": document.document_id,
            "raw_sha256": document.raw_sha256,
            "normalized_sha256": document.normalized_sha256,
            "lines": list(document.lines),
        },
    )
    return document, chunks, run_id


def run_extraction(
    source_path: Path,
    output_dir: Path,
    *,
    provider: JsonProvider,
    provider_name: str,
    model_name: str,
    document_id: str | None = None,
    config: ExtractionConfig | None = None,
) -> dict[str, Any]:
    config = config or ExtractionConfig()
    document, chunks, run_id = prepare_run(
        source_path,
        output_dir,
        document_id=document_id,
        config=config,
        provider_name=provider_name,
        model_name=model_name,
    )
    budget = Budget(
        max_calls=config.max_calls,
        max_cost_cny=config.max_cost_cny,
        input_price_cny_per_million=config.input_price_cny_per_million,
        output_price_cny_per_million=config.output_price_cny_per_million,
    )
    state = ExtractionState(output_dir, run_id, provider_name, model_name, budget)
    frame_prompt = _prompt("document-frame-v0.1.txt")
    chunk_prompt = _prompt("chunk-extraction-v0.1.txt")
    frame_source: dict[str, Any]
    if config.reuse_document_frame_path is not None:
        frame_path = config.reuse_document_frame_path.resolve()
        try:
            frame_bytes = frame_path.read_bytes()
            frame_payload = json.loads(frame_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ExtractionError(f"reused_document_frame_invalid:{type(exc).__name__}") from exc
        if not isinstance(frame_payload, dict):
            raise ExtractionError("reused_document_frame_root_must_be_object")
        frame_source = {
            "type": "reused_validated_artifact",
            "path": frame_path.as_posix(),
            "sha256": _sha256_bytes(frame_bytes),
        }
    else:
        frame_payload = _invoke(
            provider,
            state,
            call_role="document_frame",
            system_prompt=frame_prompt,
            user_payload={
                "document_id": document.document_id,
                "source_sha256": document.normalized_sha256,
                "numbered_lines": [
                    {"line": number, "text": text} for number, text in enumerate(document.lines, start=1)
                ],
            },
            max_output_tokens=config.max_output_tokens,
        )
        frame_source = {"type": "provider_call"}
    _validate_document_frame(frame_payload, document)
    _write_json(output_dir / "document-frame.json", frame_payload)

    queue: list[tuple[SourceChunk, int]] = [(chunk, 0) for chunk in chunks]
    accepted: list[tuple[SourceChunk, dict[str, Any]]] = []
    while queue:
        chunk, depth = queue.pop(0)
        payload = _invoke(
            provider,
            state,
            call_role=f"chunk:{chunk.chunk_id}",
            system_prompt=chunk_prompt,
            user_payload={
                "document_id": document.document_id,
                "source_sha256": document.normalized_sha256,
                "chunk_id": chunk.chunk_id,
                "chunk_range": {"start_line": chunk.start_line, "end_line": chunk.end_line},
                "document_frame": frame_payload,
                "numbered_lines": list(chunk.numbered_lines),
            },
            max_output_tokens=config.max_output_tokens,
        )
        payload, surface_repairs = _repair_inexact_binding_surfaces(payload, chunk, document)
        payload, binding_repairs = _repair_binding_entity_name_mismatches(payload, frame_payload, chunk)
        payload, quote_repairs = _repair_inexact_claim_quotes(payload, chunk, document)
        payload, relation_repairs = _repair_relation_evidence_coverage(payload, chunk)
        payload, disposition_repairs = _drop_blank_line_dispositions(payload, chunk, document)
        state.local_repairs.extend(surface_repairs)
        state.local_repairs.extend(binding_repairs)
        state.local_repairs.extend(quote_repairs)
        state.local_repairs.extend(relation_repairs)
        state.local_repairs.extend(disposition_repairs)
        overflow_split_line = _deterministic_overflow_split_line(payload, chunk)
        if overflow_split_line is not None:
            state.local_repairs.append(
                {
                    "repair_type": "force_split_after_claim_overflow",
                    "chunk_id": chunk.chunk_id,
                    "source_lines": [chunk.start_line, chunk.end_line],
                    "split_after_line": overflow_split_line,
                    "discarded_claim_count": len(payload["claims"]),
                    "provider_payload_accepted": False,
                    "semantic_fields_changed": False,
                }
            )
            left, right = _split_chunk(chunk, overflow_split_line, f"S{depth + 1}")
            queue[0:0] = [(left, depth + 1), (right, depth + 1)]
            continue
        _validate_chunk_payload(payload, chunk, document)
        if payload["split_required"]:
            left, right = _split_chunk(chunk, int(payload["split_after_line"]), f"S{depth + 1}")
            queue[0:0] = [(left, depth + 1), (right, depth + 1)]
            continue
        accepted.append((chunk, payload))

    mention_bindings: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    relations: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []
    for chunk, payload in sorted(accepted, key=lambda pair: pair[0].start_line):
        namespaced = _namespace_chunk(payload, chunk.chunk_id)
        mention_bindings.extend(namespaced["mention_bindings"])
        claims.extend(namespaced["claims"])
        relations.extend(namespaced["relations"])
        dispositions.extend(namespaced["segment_dispositions"])

    ledger = {
        "schema_version": GENERIC_SCHEMA_VERSION,
        "synthetic": False,
        "document": {
            "document_id": document.document_id,
            "source_sha256": document.normalized_sha256,
            "lines": list(document.lines),
        },
        "document_frame": frame_payload,
        "mention_bindings": mention_bindings,
        "claims": claims,
        "relations": relations,
        "segment_dispositions": dispositions,
        "lineage": {
            "run_id": run_id,
            "provider": provider_name,
            "requested_model": model_name,
            "document_frame_prompt_sha256": _sha256_text(frame_prompt),
            "chunk_prompt_sha256": _sha256_text(chunk_prompt),
            "document_frame_source": frame_source,
            "budget": budget.receipt(),
            "local_repairs": state.local_repairs,
            "formal_database_writes": 0,
        },
    }
    _write_json(output_dir / "candidate-ledger.json", ledger)
    validation = validate_document(ledger)
    _write_json(output_dir / "validation.json", validation.as_dict())
    manifest_path = output_dir / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "candidate_valid" if validation.valid else "candidate_invalid"
    manifest["external_transmission_authorized"] = True
    manifest["budget_receipt"] = budget.receipt()
    manifest["document_frame_source"] = frame_source
    manifest["local_repairs"] = state.local_repairs
    manifest["accepted_leaf_chunks"] = [chunk.chunk_id for chunk, _ in accepted]
    _write_json(manifest_path, manifest)
    if not validation.valid:
        raise ExtractionError(f"candidate_ledger_validation_failed:{validation.errors[:10]}")
    return ledger
