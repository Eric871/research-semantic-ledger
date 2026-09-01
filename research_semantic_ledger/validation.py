"""Dependency-free validation for Research Semantic Ledger documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GENERIC_SCHEMA_VERSION = "research_semantic_ledger_v0.2"
ALLOWED_RELATION_TYPES = frozenset(
    {
        "causes",
        "enables",
        "constrains",
        "qualifies",
        "depends_on",
        "compares",
        "contrasts",
        "supports",
        "precedes",
        "elaborates",
        "exemplifies",
    }
)
VAGUE_CANONICAL_SUBJECTS = frozenset(
    {"公司", "其", "该公司", "该政策", "这", "此", "他们", "它们", "双方", "两者"}
)


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]
    summary: dict[str, int | bool | str]

    @property
    def valid(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "pass" if self.valid else "fail",
            "errors": list(self.errors),
            "summary": self.summary,
        }


def _unique_rows(rows: Any, key: str, label: str, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        errors.append(f"{label}_must_be_array")
        return {}
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"{label}_{index}_must_be_object")
            continue
        identifier = row.get(key)
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{label}_{index}_missing_{key}")
            continue
        if identifier in result:
            errors.append(f"duplicate_{key}:{identifier}")
            continue
        result[identifier] = row
    return result


def _valid_lines(values: Any, line_count: int, *, allow_empty: bool = False) -> bool:
    return (
        isinstance(values, list)
        and (allow_empty or bool(values))
        and all(isinstance(value, int) and 1 <= value <= line_count for value in values)
    )


def _validate_legacy_group_fixture(data: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    document = data.get("document")
    lines = document.get("lines") if isinstance(document, dict) else None
    if not isinstance(lines, list) or not lines or not all(isinstance(line, str) and line for line in lines):
        errors.append("document_lines_must_be_nonempty_strings")
        lines = []
    line_count = len(lines)

    bindings = _unique_rows(data.get("group_bindings"), "binding_id", "binding", errors)
    for binding_id, row in bindings.items():
        source_line = row.get("source_line")
        surface = row.get("surface")
        if not isinstance(source_line, int) or not 1 <= source_line <= line_count:
            errors.append(f"binding_source_line_invalid:{binding_id}")
        elif not isinstance(surface, str) or surface not in lines[source_line - 1]:
            errors.append(f"binding_surface_not_in_evidence:{binding_id}")

        status = row.get("resolution_status")
        member_ids = row.get("member_ids")
        member_names = row.get("member_names")
        excluded_ids = row.get("excluded_ids")
        if status == "resolved_group":
            if not isinstance(member_ids, list) or len(member_ids) < 2:
                errors.append(f"resolved_group_requires_members:{binding_id}")
            member_count = len(member_ids) if isinstance(member_ids, list) else -1
            if not isinstance(member_names, list) or len(member_names) != member_count:
                errors.append(f"resolved_group_member_names_mismatch:{binding_id}")
        elif status == "scoped_open_group":
            if member_ids or member_names:
                errors.append(f"scoped_open_group_must_not_enumerate_members:{binding_id}")
            if not isinstance(excluded_ids, list) or not excluded_ids:
                errors.append(f"scoped_open_group_requires_exclusions:{binding_id}")
        else:
            errors.append(f"binding_status_unsupported:{binding_id}")

    claims = _unique_rows(data.get("claims"), "claim_id", "claim", errors)
    for claim_id, row in claims.items():
        if row.get("group_binding_id") not in bindings:
            errors.append(f"claim_binding_missing:{claim_id}")
        if not isinstance(row.get("predicate"), str) or not row["predicate"]:
            errors.append(f"claim_predicate_missing:{claim_id}")
        if not _valid_lines(row.get("evidence_lines"), line_count):
            errors.append(f"claim_evidence_invalid:{claim_id}")

    relations = _unique_rows(data.get("relations"), "relation_id", "relation", errors)
    claim_ids = set(claims)
    for relation_id, row in relations.items():
        source_ids = row.get("source_claim_ids")
        target_ids = row.get("target_claim_ids")
        if (
            not isinstance(source_ids, list)
            or not all(isinstance(value, str) for value in source_ids)
            or any(value not in claim_ids for value in source_ids)
        ):
            errors.append(f"relation_source_missing:{relation_id}")
        if (
            not isinstance(target_ids, list)
            or not target_ids
            or not all(isinstance(value, str) for value in target_ids)
            or any(value not in claim_ids for value in target_ids)
        ):
            errors.append(f"relation_target_missing:{relation_id}")
        if not _valid_lines(row.get("evidence_lines"), line_count):
            errors.append(f"relation_evidence_invalid:{relation_id}")

    return ValidationResult(
        tuple(errors),
        {
            "schema_version": str(data.get("schema_version") or "legacy"),
            "synthetic": data.get("synthetic") is True,
            "lines": line_count,
            "bindings": len(bindings),
            "claims": len(claims),
            "relations": len(relations),
        },
    )


def _validate_generic_document(data: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    document = data.get("document")
    lines = document.get("lines") if isinstance(document, dict) else None
    if not isinstance(lines, list) or not lines or not all(isinstance(line, str) for line in lines):
        errors.append("document_lines_must_be_string_array")
        lines = []
    line_count = len(lines)
    source_hash = document.get("source_sha256") if isinstance(document, dict) else None
    if not isinstance(source_hash, str) or len(source_hash) != 64:
        errors.append("document_source_sha256_invalid")

    bindings = _unique_rows(data.get("mention_bindings"), "binding_id", "binding", errors)
    allowed_binding_status = {"resolved", "group_resolved", "ambiguous", "unresolved", "class_not_unique"}
    for binding_id, row in bindings.items():
        evidence_lines = row.get("evidence_lines")
        if not _valid_lines(evidence_lines, line_count):
            errors.append(f"binding_evidence_invalid:{binding_id}")
        surface = row.get("surface")
        if not isinstance(surface, str) or not surface:
            errors.append(f"binding_surface_missing:{binding_id}")
        elif _valid_lines(evidence_lines, line_count) and not any(
            surface in lines[number - 1] for number in evidence_lines
        ):
            errors.append(f"binding_surface_not_in_evidence:{binding_id}")
        status = row.get("resolution_status")
        if status not in allowed_binding_status:
            errors.append(f"binding_status_unsupported:{binding_id}")
        entity_ids = row.get("canonical_entity_ids")
        entity_names = row.get("canonical_names")
        if not isinstance(entity_names, list) or not isinstance(entity_ids, list) or len(entity_names) != len(entity_ids):
            errors.append(f"binding_entity_names_mismatch:{binding_id}")
        if status == "resolved" and (not isinstance(entity_ids, list) or len(entity_ids) != 1):
            errors.append(f"resolved_binding_requires_one_entity:{binding_id}")
        if status == "group_resolved" and (not isinstance(entity_ids, list) or len(entity_ids) < 2):
            errors.append(f"group_binding_requires_two_entities:{binding_id}")
        if status in {"ambiguous", "unresolved", "class_not_unique"} and entity_ids:
            errors.append(f"unresolved_binding_must_not_assign_entity:{binding_id}")

    claims = _unique_rows(data.get("claims"), "claim_id", "claim", errors)
    for claim_id, row in claims.items():
        if not isinstance(row.get("predicate"), str) or not row["predicate"].strip():
            errors.append(f"claim_predicate_missing:{claim_id}")
        if not _valid_lines(row.get("evidence_lines"), line_count):
            errors.append(f"claim_evidence_invalid:{claim_id}")
        canonical_subject = row.get("canonical_subject")
        unresolved_fields = row.get("unresolved_fields")
        if not isinstance(unresolved_fields, list):
            errors.append(f"claim_unresolved_fields_must_be_array:{claim_id}")
            unresolved_fields = []
        if canonical_subject in VAGUE_CANONICAL_SUBJECTS and "canonical_subject" not in unresolved_fields:
            errors.append(f"claim_vague_canonical_subject:{claim_id}")
        if canonical_subject is None and "canonical_subject" not in unresolved_fields:
            errors.append(f"claim_null_canonical_subject_not_marked_unresolved:{claim_id}")
        binding_ids = row.get("mention_binding_ids")
        if not isinstance(binding_ids, list) or any(value not in bindings for value in binding_ids):
            errors.append(f"claim_binding_reference_invalid:{claim_id}")
        evidence_quotes = row.get("evidence_quotes")
        if not isinstance(evidence_quotes, list) or not evidence_quotes:
            errors.append(f"claim_evidence_quotes_missing:{claim_id}")
        elif _valid_lines(row.get("evidence_lines"), line_count):
            evidence_text = "\n".join(lines[number - 1] for number in row["evidence_lines"])
            if any(not isinstance(quote, str) or not quote or quote not in evidence_text for quote in evidence_quotes):
                errors.append(f"claim_evidence_quote_not_exact:{claim_id}")

    relations = _unique_rows(data.get("relations"), "relation_id", "relation", errors)
    claim_ids = set(claims)
    for relation_id, row in relations.items():
        source_ids = row.get("source_claim_ids")
        target_ids = row.get("target_claim_ids")
        if (
            not isinstance(source_ids, list)
            or not source_ids
            or not all(isinstance(value, str) and value in claim_ids for value in source_ids)
        ):
            errors.append(f"relation_source_missing:{relation_id}")
        if (
            not isinstance(target_ids, list)
            or not target_ids
            or not all(isinstance(value, str) and value in claim_ids for value in target_ids)
        ):
            errors.append(f"relation_target_missing:{relation_id}")
        if isinstance(source_ids, list) and isinstance(target_ids, list) and set(source_ids) & set(target_ids):
            errors.append(f"relation_self_loop:{relation_id}")
        if row.get("relation_type") not in ALLOWED_RELATION_TYPES:
            errors.append(f"relation_type_unsupported:{relation_id}")
        if not _valid_lines(row.get("evidence_lines"), line_count):
            errors.append(f"relation_evidence_invalid:{relation_id}")
        elif isinstance(source_ids, list) and isinstance(target_ids, list):
            endpoint_lines = {
                number
                for claim_id in source_ids + target_ids
                for number in (claims.get(claim_id) or {}).get("evidence_lines") or []
            }
            if not endpoint_lines.issubset(set(row["evidence_lines"])):
                errors.append(f"relation_evidence_does_not_cover_endpoints:{relation_id}")
        if not isinstance(row.get("unresolved_fields"), list):
            errors.append(f"relation_unresolved_fields_must_be_array:{relation_id}")

    dispositions = data.get("segment_dispositions")
    disposition_rows = dispositions if isinstance(dispositions, list) else []
    if not isinstance(dispositions, list):
        errors.append("segment_dispositions_must_be_array")
    seen_lines: list[int] = []
    for index, row in enumerate(disposition_rows):
        if not isinstance(row, dict):
            errors.append(f"segment_disposition_{index}_must_be_object")
            continue
        source_lines = row.get("source_lines")
        if not _valid_lines(source_lines, line_count):
            errors.append(f"segment_disposition_evidence_invalid:{index}")
            continue
        seen_lines.extend(source_lines)
        if row.get("status") not in {"consumed", "ignored_with_reason", "unresolved_for_replay"}:
            errors.append(f"segment_disposition_status_invalid:{index}")
        if row.get("status") != "consumed" and not row.get("reason"):
            errors.append(f"segment_disposition_reason_required:{index}")
        claim_refs = row.get("claim_ids")
        relation_refs = row.get("relation_ids")
        if not isinstance(claim_refs, list) or any(value not in claims for value in claim_refs):
            errors.append(f"segment_disposition_claim_reference_invalid:{index}")
        if not isinstance(relation_refs, list) or any(value not in relations for value in relation_refs):
            errors.append(f"segment_disposition_relation_reference_invalid:{index}")
    expected_lines = {number for number, line in enumerate(lines, start=1) if line.strip()}
    if set(seen_lines) != expected_lines or len(seen_lines) != len(set(seen_lines)):
        errors.append("segment_disposition_coverage_invalid")
    lineage = data.get("lineage")
    if not isinstance(lineage, dict) or lineage.get("formal_database_writes") != 0:
        errors.append("formal_database_writes_must_be_zero")

    return ValidationResult(
        tuple(errors),
        {
            "schema_version": GENERIC_SCHEMA_VERSION,
            "synthetic": data.get("synthetic") is True,
            "lines": line_count,
            "bindings": len(bindings),
            "claims": len(claims),
            "relations": len(relations),
            "segment_dispositions": len(disposition_rows),
        },
    )


def validate_document(data: Any) -> ValidationResult:
    if not isinstance(data, dict):
        return ValidationResult(("root_must_be_object",), {})
    if data.get("schema_version") == GENERIC_SCHEMA_VERSION:
        return _validate_generic_document(data)
    return _validate_legacy_group_fixture(data)


def load_and_validate_path(path: Path) -> tuple[Any | None, ValidationResult]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, ValidationResult((f"file_not_found:{path}",), {})
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return None, ValidationResult((f"file_read_error:{type(exc).__name__}",), {})
    return data, validate_document(data)


def validate_path(path: Path) -> ValidationResult:
    _, result = load_and_validate_path(path)
    return result
