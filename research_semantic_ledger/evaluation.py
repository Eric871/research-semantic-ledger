"""Dependency-free Gold evaluation for candidate ledgers."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .validation import load_and_validate_path


class EvaluationError(RuntimeError):
    """An invalid Gold contract or ledger evaluation request."""


TARGETS = {
    "mention_bindings": "binding_id",
    "claims": "claim_id",
    "relations": "relation_id",
}


def _matches(row: dict[str, Any], case: dict[str, Any]) -> bool:
    exact = case.get("exact") or {}
    contains = case.get("contains") or {}
    list_contains = case.get("list_contains") or {}
    if not all(row.get(key) == value for key, value in exact.items()):
        return False
    for key, value in contains.items():
        actual = row.get(key)
        if not isinstance(actual, str) or not isinstance(value, str) or value not in actual:
            return False
    for key, expected_values in list_contains.items():
        actual = row.get(key)
        if not isinstance(actual, list) or not isinstance(expected_values, list) or not set(expected_values).issubset(actual):
            return False
    return True


def evaluate_ledger(ledger: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    if gold.get("schema_version") != "research_semantic_ledger_gold_v0.1":
        raise EvaluationError("gold_schema_version_unsupported")
    if gold.get("document_id") != (ledger.get("document") or {}).get("document_id"):
        raise EvaluationError("gold_document_id_mismatch")
    cases = gold.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvaluationError("gold_cases_must_be_nonempty_array")
    results: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise EvaluationError(f"gold_case_{index}_must_be_object")
        case_id = case.get("case_id")
        target = case.get("target")
        if not isinstance(case_id, str) or not case_id or case_id in seen_case_ids:
            raise EvaluationError(f"gold_case_id_invalid:{index}")
        seen_case_ids.add(case_id)
        if target not in TARGETS:
            raise EvaluationError(f"gold_target_invalid:{case_id}")
        for field in ("exact", "contains", "list_contains"):
            if field in case and not isinstance(case[field], dict):
                raise EvaluationError(f"gold_{field}_must_be_object:{case_id}")
        rows = ledger.get(target)
        if not isinstance(rows, list):
            raise EvaluationError(f"ledger_target_missing:{target}")
        matched = [row for row in rows if isinstance(row, dict) and _matches(row, case)]
        minimum = case.get("minimum_matches", 1)
        maximum = case.get("maximum_matches")
        if not isinstance(minimum, int) or minimum < 0:
            raise EvaluationError(f"gold_minimum_matches_invalid:{case_id}")
        passed = len(matched) >= minimum and (maximum is None or len(matched) <= maximum)
        results.append(
            {
                "case_id": case_id,
                "dimension": str(case.get("dimension") or target),
                "target": target,
                "passed": passed,
                "match_count": len(matched),
                "matched_ids": [str(row.get(TARGETS[target])) for row in matched],
            }
        )
    by_dimension = Counter(row["dimension"] for row in results)
    passed_by_dimension = Counter(row["dimension"] for row in results if row["passed"])
    passed = sum(row["passed"] for row in results)
    return {
        "schema_version": "research_semantic_ledger_evaluation_v0.1",
        "status": "pass" if passed == len(results) else "semantic_partial",
        "document_id": gold["document_id"],
        "passed": passed,
        "total": len(results),
        "by_dimension": {
            dimension: {"passed": passed_by_dimension[dimension], "total": total}
            for dimension, total in sorted(by_dimension.items())
        },
        "cases": results,
    }


def evaluate_paths(ledger_path: Path, gold_path: Path) -> dict[str, Any]:
    ledger, validation = load_and_validate_path(ledger_path)
    if not validation.valid or not isinstance(ledger, dict):
        raise EvaluationError(f"ledger_validation_failed:{validation.errors}")
    try:
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EvaluationError(f"gold_file_not_found:{gold_path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"gold_read_error:{type(exc).__name__}") from exc
    if not isinstance(gold, dict):
        raise EvaluationError("gold_root_must_be_object")
    return evaluate_ledger(ledger, gold)
