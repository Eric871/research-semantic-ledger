#!/usr/bin/env python3
"""Validate the public-safe Research Semantic Ledger synthetic fixture."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "synthetic-group-reference.json"


def main() -> int:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    lines = data["document"]["lines"]
    assert lines and all(isinstance(line, str) and line for line in lines)

    bindings = {row["binding_id"]: row for row in data["group_bindings"]}
    assert len(bindings) == len(data["group_bindings"])
    assert set(bindings) == {"G-001", "G-002"}
    for row in bindings.values():
        assert 1 <= row["source_line"] <= len(lines)
        assert row["surface"] in lines[row["source_line"] - 1]
        if row["resolution_status"] == "resolved_group":
            assert len(row["member_ids"]) >= 2
            assert len(row["member_ids"]) == len(row["member_names"])
        elif row["resolution_status"] == "scoped_open_group":
            assert not row["member_ids"] and not row["member_names"]
            assert row["excluded_ids"]
        else:
            raise AssertionError(f"unsupported group status: {row['resolution_status']}")

    claims = {row["claim_id"]: row for row in data["claims"]}
    assert len(claims) == len(data["claims"])
    for row in claims.values():
        assert row["group_binding_id"] in bindings
        assert row["evidence_lines"]
        assert all(1 <= value <= len(lines) for value in row["evidence_lines"])
    assert all(term in claims["C-002"]["object"] for term in ("design", "sampling", "yield"))

    relation_ids: set[str] = set()
    for row in data["relations"]:
        assert row["relation_id"] not in relation_ids
        relation_ids.add(row["relation_id"])
        assert set(row["target_claim_ids"]) <= set(claims)
        assert set(row["source_claim_ids"]) <= set(claims)
        assert row["evidence_lines"]

    print(
        json.dumps(
            {
                "status": "pass",
                "synthetic": True,
                "bindings": len(bindings),
                "claims": len(claims),
                "relations": len(relation_ids),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
