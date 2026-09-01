#!/usr/bin/env python3
"""Backward-compatible wrapper for the public fixture validator."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research_semantic_ledger.validation import validate_path  # noqa: E402


def main() -> int:
    result = validate_path(ROOT / "examples" / "synthetic-group-reference.json")
    print(json.dumps(result.as_dict(), ensure_ascii=False))
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
