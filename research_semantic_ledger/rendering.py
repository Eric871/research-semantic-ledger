"""Human-readable Markdown rendering for validated semantic ledgers."""

from __future__ import annotations

from typing import Any

from .validation import GENERIC_SCHEMA_VERSION


STATUS_LABELS = {
    "resolved_group": "Resolved entity set",
    "scoped_open_group": "Scoped open entity set",
    "resolved": "Resolved entity",
    "group_resolved": "Resolved entity set",
    "class_not_unique": "Non-unique class",
    "ambiguous": "Ambiguous",
    "unresolved": "Unresolved",
}


def _inline(value: Any) -> str:
    if value is None or value == "":
        return "(none)"
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|").strip()


def _code_list(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "(none)"
    return ", ".join(f"`{_inline(value)}`" for value in values)


def _line_refs(values: Any) -> str:
    if not isinstance(values, list) or not values:
        return "(none)"
    return ", ".join(f"L{value}" for value in values)


def _evidence(lines: list[str], line_numbers: Any) -> list[str]:
    if not isinstance(line_numbers, list):
        return []
    rendered: list[str] = []
    for number in line_numbers:
        if isinstance(number, int) and 1 <= number <= len(lines):
            rendered.append(f"> **L{number}:** {_inline(lines[number - 1])}")
    return rendered


def _start(data: dict[str, Any], bindings: list[Any], claims: list[Any], relations: list[Any]) -> list[str]:
    document = data.get("document") or {}
    lines = document.get("lines") or []
    document_id = _inline(document.get("document_id") or "Untitled document")
    return [
        f"# Semantic Ledger: {document_id}",
        "",
        "> Deterministic Markdown projection of a validated semantic-ledger JSON document.",
        "",
        "## Summary",
        "",
        "| Field | Value |",
        "|---|---:|",
        f"| Schema | `{_inline(data.get('schema_version'))}` |",
        f"| Synthetic | `{str(data.get('synthetic') is True).lower()}` |",
        f"| Source lines | {len(lines)} |",
        f"| Reference bindings | {len(bindings)} |",
        f"| Claims | {len(claims)} |",
        f"| Relations | {len(relations)} |",
        "",
    ]


def _append_source(output: list[str], lines: list[str]) -> None:
    output.extend(["## Source lines", "", "| Line | Text |", "|---:|---|"])
    output.extend(f"| L{index} | {_inline(text)} |" for index, text in enumerate(lines, start=1))
    output.append("")


def _render_generic(data: dict[str, Any]) -> str:
    document = data.get("document") or {}
    lines = document.get("lines") or []
    bindings = data.get("mention_bindings") or []
    claims = data.get("claims") or []
    relations = data.get("relations") or []
    output = _start(data, bindings, claims, relations)
    output.extend(["## Reference bindings", ""])
    if not bindings:
        output.extend(["No reference bindings.", ""])
    for row in bindings:
        output.extend(
            [
                f"### `{_inline(row.get('binding_id'))}` - {_inline(row.get('surface'))}",
                "",
                f"- Status: {STATUS_LABELS.get(row.get('resolution_status'), _inline(row.get('resolution_status')))}",
                f"- Canonical entities: {_code_list(row.get('canonical_names'))}",
                f"- Evidence: {_line_refs(row.get('evidence_lines'))}",
                f"- Basis: {_inline(row.get('resolution_basis'))}",
                "",
            ]
        )
        output.extend(_evidence(lines, row.get("evidence_lines")))
        output.append("")

    output.extend(["## Atomic claims", ""])
    if not claims:
        output.extend(["No claims.", ""])
    for row in claims:
        output.extend(
            [
                f"### `{_inline(row.get('claim_id'))}`",
                "",
                f"- Subject: {_inline(row.get('canonical_subject'))}",
                f"- Predicate: {_inline(row.get('predicate'))}",
                f"- Object: {_inline(row.get('object'))}",
                f"- Kind: `{_inline(row.get('claim_kind'))}`; modality `{_inline(row.get('modality'))}`",
                f"- Time: {_inline(row.get('time_surface'))}",
                f"- Condition: {_inline(row.get('condition'))}",
                f"- Evidence: {_line_refs(row.get('evidence_lines'))}",
                f"- Unresolved: {_code_list(row.get('unresolved_fields'))}",
                "",
            ]
        )
        output.extend(_evidence(lines, row.get("evidence_lines")))
        output.append("")

    output.extend(["## Narrative relations", ""])
    if not relations:
        output.extend(["No narrative relations.", ""])
    for row in relations:
        output.extend(
            [
                f"### `{_inline(row.get('relation_id'))}` - {_inline(row.get('relation_type'))}",
                "",
                f"- From: {_code_list(row.get('source_claim_ids'))}",
                f"- To: {_code_list(row.get('target_claim_ids'))}",
                f"- Condition: {_inline(row.get('condition'))}",
                f"- Evidence: {_line_refs(row.get('evidence_lines'))}",
                f"- Unresolved: {_code_list(row.get('unresolved_fields'))}",
                "",
            ]
        )
        output.extend(_evidence(lines, row.get("evidence_lines")))
        output.append("")
    _append_source(output, lines)
    return "\n".join(output)


def _render_legacy(data: dict[str, Any]) -> str:
    document = data.get("document") or {}
    lines = document.get("lines") or []
    bindings = data.get("group_bindings") or []
    claims = data.get("claims") or []
    relations = data.get("relations") or []
    output = _start(data, bindings, claims, relations)
    output.extend(["## Entity-set bindings", ""])
    if not bindings:
        output.extend(["No entity-set bindings.", ""])
    for row in bindings:
        output.extend(
            [
                f"### `{_inline(row.get('binding_id'))}` - {_inline(row.get('surface'))}",
                "",
                f"- Status: {STATUS_LABELS.get(row.get('resolution_status'), _inline(row.get('resolution_status')))}",
                f"- Source: L{_inline(row.get('source_line'))}",
                f"- Members: {_code_list(row.get('member_names'))}",
                f"- Exclusions: {_code_list(row.get('excluded_ids'))}",
                "",
            ]
        )

    output.extend(["## Claims", ""])
    if not claims:
        output.extend(["No claims.", ""])
    for row in claims:
        output.extend(
            [
                f"### `{_inline(row.get('claim_id'))}`",
                "",
                f"- Entity set: `{_inline(row.get('group_binding_id'))}`",
                f"- Predicate: {_inline(row.get('predicate'))}",
            ]
        )
        if row.get("object") not in (None, ""):
            output.append(f"- Object: {_inline(row.get('object'))}")
        output.extend([f"- Evidence: {_line_refs(row.get('evidence_lines'))}", ""])
        output.extend(_evidence(lines, row.get("evidence_lines")))
        output.append("")

    output.extend(["## Narrative relations", ""])
    if not relations:
        output.extend(["No narrative relations.", ""])
    for row in relations:
        output.extend(
            [
                f"### `{_inline(row.get('relation_id'))}` - {_inline(row.get('relation_type'))}",
                "",
                f"- From: {_code_list(row.get('source_claim_ids'))}",
                f"- To: {_code_list(row.get('target_claim_ids'))}",
                f"- Evidence: {_line_refs(row.get('evidence_lines'))}",
                "",
            ]
        )
        output.extend(_evidence(lines, row.get("evidence_lines")))
        output.append("")
    _append_source(output, lines)
    return "\n".join(output)


def render_document(data: dict[str, Any]) -> str:
    if data.get("schema_version") == GENERIC_SCHEMA_VERSION:
        return _render_generic(data)
    return _render_legacy(data)
