from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_semantic_ledger.evaluation import evaluate_paths
from research_semantic_ledger.extraction import ExtractionConfig, run_extraction
from research_semantic_ledger.provider import SequenceProvider
from research_semantic_ledger.validation import validate_path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "synthetic-research-note.md"
LEDGER = ROOT / "examples" / "synthetic-extracted-ledger.json"
GOLD = ROOT / "examples" / "synthetic-extraction-gold.json"


class ExtractionTests(unittest.TestCase):
    def test_generic_fixture_and_gold_pass(self) -> None:
        validation = validate_path(LEDGER)
        self.assertTrue(validation.valid, validation.errors)
        evaluation = evaluate_paths(LEDGER, GOLD)
        self.assertEqual(evaluation["status"], "pass")
        self.assertEqual(evaluation["passed"], 6)

    def test_offline_sequence_provider_runs_full_pipeline(self) -> None:
        fixture = json.loads(LEDGER.read_text(encoding="utf-8"))
        chunk = {
            "chunk_id": "CH-0001",
            "mention_bindings": fixture["mention_bindings"],
            "claims": fixture["claims"],
            "relations": fixture["relations"],
            "segment_dispositions": fixture["segment_dispositions"],
            "split_required": False,
            "split_after_line": None,
            "unresolved_items": [],
        }
        provider = SequenceProvider([fixture["document_frame"], chunk])
        outputs = ROOT / "outputs"
        outputs.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=outputs) as directory:
            result = run_extraction(
                SOURCE,
                Path(directory),
                provider=provider,
                provider_name="sequence",
                model_name="fixture",
                document_id="SYNTHETIC-EXTRACTION-001",
                config=ExtractionConfig(max_chunk_chars=20_000, max_calls=3),
            )
            self.assertEqual(provider.calls, 2)
            self.assertEqual(len(result["mention_bindings"]), 2)
            self.assertEqual(len(result["claims"]), 5)
            self.assertEqual(len(result["relations"]), 2)
            validation = validate_path(Path(directory) / "candidate-ledger.json")
            self.assertTrue(validation.valid, validation.errors)
            manifest = json.loads((Path(directory) / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "candidate_valid")
            self.assertEqual(manifest["formal_database_writes"], 0)

    def test_cli_refuses_online_send_without_explicit_authorization(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "research_semantic_ledger",
                "extract",
                SOURCE.as_posix(),
            ],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stderr)
        self.assertIn("online_extraction_requires_--authorize-external-send", payload["errors"])


if __name__ == "__main__":
    unittest.main()
