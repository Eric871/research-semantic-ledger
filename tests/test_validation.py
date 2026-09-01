from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path

from research_semantic_ledger.validation import validate_document, validate_path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "synthetic-group-reference.json"


class ValidationTests(unittest.TestCase):
    def test_public_fixture_passes(self) -> None:
        result = validate_path(FIXTURE)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual(result.summary["claims"], 2)
        self.assertEqual(result.summary["relations"], 2)

    def test_invalid_evidence_line_fails_closed(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        broken = copy.deepcopy(data)
        broken["claims"][0]["evidence_lines"] = [999]
        result = validate_document(broken)
        self.assertFalse(result.valid)
        self.assertIn("claim_evidence_invalid:C-001", result.errors)

    def test_malformed_member_type_fails_closed(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        broken = copy.deepcopy(data)
        broken["group_bindings"][0]["member_ids"] = 7
        result = validate_document(broken)
        self.assertFalse(result.valid)
        self.assertIn("resolved_group_requires_members:G-001", result.errors)

    def test_malformed_relation_endpoint_fails_closed(self) -> None:
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        broken = copy.deepcopy(data)
        broken["relations"][0]["source_claim_ids"] = [{}]
        result = validate_document(broken)
        self.assertFalse(result.valid)
        self.assertIn("relation_source_missing:R-001", result.errors)

    def test_doctor_runs_without_install(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_semantic_ledger", "doctor"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "pass")

    def test_validate_command_fails_closed_for_missing_file(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "research_semantic_ledger", "validate", "examples/missing.json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "fail")


if __name__ == "__main__":
    unittest.main()
