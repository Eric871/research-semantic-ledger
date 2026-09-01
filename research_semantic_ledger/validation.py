"""Dependency-free validation for public semantic-ledger fixtures."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    errors: tuple[str, ...]
    summary: dict[str, int | bool]

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


def _valid_lines(values: Any, line_count: int) -> bool:
    return (
        isinstance(values, list)
        and bool(values)
        and all(isinstance(value, int) and 1 <= value <= line_count for value in values)
    )


def validate_document(data: Any) -> ValidationResult:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ValidationResult(("root_must_be_object",), {})

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
            "synthetic": data.get("synthetic") is True,
            "lines": line_count,
            "bindings": len(bindings),
            "claims": len(claims),
            "relations": len(relations),
        },
    )


def validate_path(path: Path) -> ValidationResult:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ValidationResult((f"file_not_found:{path}",), {})
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return ValidationResult((f"file_read_error:{type(exc).__name__}",), {})
    return validate_document(data)
