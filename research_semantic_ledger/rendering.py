"""Human-readable Markdown rendering for validated semantic ledgers."""

from __future__ import annotations

from typing import Any


STATUS_LABELS = {
    "resolved_group": "Resolved entity set",
    "scoped_open_group": "Scoped open entity set",
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


def render_document(data: dict[str, Any]) -> str:
    document = data.get("document") or {}
    lines = document.get("lines") or []
    bindings = data.get("group_bindings") or []
    claims = data.get("claims") or []
    relations = data.get("relations") or []
    document_id = _inline(document.get("document_id") or "Untitled document")

    output = [
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
        f"| Entity-set bindings | {len(bindings)} |",
        f"| Claims | {len(claims)} |",
        f"| Relations | {len(relations)} |",
        "",
        "## Entity-set bindings",
        "",
    ]

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

    output.extend(["## Source lines", "", "| Line | Text |", "|---:|---|"])
    output.extend(f"| L{index} | {_inline(text)} |" for index, text in enumerate(lines, start=1))
    output.append("")
    return "\n".join(output)
