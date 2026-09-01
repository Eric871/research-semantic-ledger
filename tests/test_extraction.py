from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research_semantic_ledger.evaluation import evaluate_paths
from research_semantic_ledger.extraction import (
    ExtractionConfig,
    SourceChunk,
    SourceDocument,
    _drop_blank_line_dispositions,
    _deterministic_overflow_split_line,
    _repair_binding_entity_name_mismatches,
    _repair_inexact_claim_quotes,
    _repair_inexact_binding_surfaces,
    _repair_relation_evidence_coverage,
    run_extraction,
)
from research_semantic_ledger.provider import SequenceProvider
from research_semantic_ledger.validation import validate_path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "examples" / "synthetic-research-note.md"
LEDGER = ROOT / "examples" / "synthetic-extracted-ledger.json"
GOLD = ROOT / "examples" / "synthetic-extraction-gold.json"


class ExtractionTests(unittest.TestCase):
    def test_inexact_binding_surface_uses_unique_long_exact_substring(self) -> None:
        text = "市场上存在许多中小型公司可以提供代工服务"
        document = SourceDocument(
            document_id="DOC",
            source_path=Path("fixture.md"),
            raw_sha256="raw",
            normalized_sha256="normalized",
            lines=(text,),
        )
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=1,
            numbered_lines=({"line": 1, "text": text},),
        )
        payload = {
            "mention_bindings": [
                {"binding_id": "B1", "surface": "市场上许多中小型公司", "evidence_lines": [1]}
            ]
        }
        repaired, repairs = _repair_inexact_binding_surfaces(payload, chunk, document)
        self.assertEqual(repaired["mention_bindings"][0]["surface"], "许多中小型公司")
        self.assertEqual(repairs[0]["repair_type"], "replace_surface_with_unique_longest_exact_substring")

    def test_unanchored_binding_is_dropped_from_claim_references(self) -> None:
        text = "长光华芯的EML和CW产品预计何时能产生收入?"
        document = SourceDocument(
            document_id="DOC",
            source_path=Path("fixture.md"),
            raw_sha256="raw",
            normalized_sha256="normalized",
            lines=(text,),
        )
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=1,
            numbered_lines=({"line": 1, "text": text},),
        )
        payload = {
            "mention_bindings": [
                {"binding_id": "B1", "surface": "其", "evidence_lines": [1]}
            ],
            "claims": [{"claim_id": "C1", "mention_binding_ids": ["B1"]}],
        }
        repaired, repairs = _repair_inexact_binding_surfaces(payload, chunk, document)
        self.assertEqual(repaired["mention_bindings"], [])
        self.assertEqual(repaired["claims"][0]["mention_binding_ids"], [])
        self.assertEqual(repairs[0]["repair_type"], "drop_unanchored_binding")

    def test_inexact_claim_quote_is_replaced_with_exact_evidence_line(self) -> None:
        document = SourceDocument(
            document_id="DOC",
            source_path=Path("fixture.md"),
            raw_sha256="raw",
            normalized_sha256="normalized",
            lines=("Exact source sentence.",),
        )
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=1,
            numbered_lines=({"line": 1, "text": "Exact source sentence."},),
        )
        payload = {
            "claims": [
                {"claim_id": "C1", "evidence_lines": [1], "evidence_quotes": ["Approximate sentence."]}
            ]
        }
        repaired, repairs = _repair_inexact_claim_quotes(payload, chunk, document)
        self.assertEqual(repaired["claims"][0]["evidence_quotes"], ["Exact source sentence."])
        self.assertFalse(repairs[0]["semantic_fields_changed"])

    def test_relation_evidence_is_extended_from_endpoint_claims(self) -> None:
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=2,
            numbered_lines=({"line": 1, "text": "cause"}, {"line": 2, "text": "effect"}),
        )
        payload = {
            "claims": [
                {"claim_id": "C1", "evidence_lines": [1]},
                {"claim_id": "C2", "evidence_lines": [2]},
            ],
            "relations": [
                {
                    "relation_id": "R1",
                    "source_claim_ids": ["C1"],
                    "target_claim_ids": ["C2"],
                    "evidence_lines": [2],
                }
            ],
        }
        repaired, repairs = _repair_relation_evidence_coverage(payload, chunk)
        self.assertEqual(repaired["relations"][0]["evidence_lines"], [1, 2])
        self.assertEqual(repairs[0]["added_source_lines"], [1])

    def test_claim_overflow_gets_deterministic_line_split(self) -> None:
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=31,
            end_line=37,
            numbered_lines=tuple({"line": line, "text": f"line {line}"} for line in range(31, 38)),
        )
        payload = {"split_required": False, "claims": [{} for _ in range(30)]}
        self.assertEqual(_deterministic_overflow_split_line(payload, chunk), 34)

    def test_binding_without_frame_id_is_conservatively_downgraded(self) -> None:
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=1,
            numbered_lines=({"line": 1, "text": "the latest information"},),
        )
        payload = {
            "mention_bindings": [
                {
                    "binding_id": "B1",
                    "resolution_status": "resolved",
                    "canonical_entity_ids": [],
                    "canonical_names": ["latest information"],
                    "confidence": "high",
                    "resolution_basis": "provider",
                }
            ]
        }
        repaired, repairs = _repair_binding_entity_name_mismatches(payload, {"entity_candidates": []}, chunk)
        binding = repaired["mention_bindings"][0]
        self.assertEqual(binding["resolution_status"], "unresolved")
        self.assertEqual(binding["canonical_entity_ids"], [])
        self.assertEqual(binding["canonical_names"], [])
        self.assertTrue(repairs[0]["semantic_fields_changed"])

    def test_group_binding_with_one_member_is_conservatively_downgraded(self) -> None:
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=1,
            numbered_lines=({"line": 1, "text": "the companies"},),
        )
        frame = {
            "entity_candidates": [
                {"candidate_id": "E1", "canonical_name": "Alpha"}
            ]
        }
        payload = {
            "mention_bindings": [
                {
                    "binding_id": "B1",
                    "resolution_status": "group_resolved",
                    "canonical_entity_ids": ["E1"],
                    "canonical_names": ["Alpha"],
                    "confidence": "high",
                    "resolution_basis": "provider",
                }
            ]
        }
        repaired, repairs = _repair_binding_entity_name_mismatches(payload, frame, chunk)
        binding = repaired["mention_bindings"][0]
        self.assertEqual(binding["resolution_status"], "unresolved")
        self.assertEqual(binding["canonical_entity_ids"], [])
        self.assertTrue(repairs[0]["semantic_fields_changed"])

    def test_blank_line_disposition_is_removed_without_semantic_changes(self) -> None:
        document = SourceDocument(
            document_id="DOC",
            source_path=Path("fixture.md"),
            raw_sha256="raw",
            normalized_sha256="normalized",
            lines=("claim", "", "claim two"),
        )
        chunk = SourceChunk(
            chunk_id="CH-0001",
            start_line=1,
            end_line=3,
            numbered_lines=(
                {"line": 1, "text": "claim"},
                {"line": 2, "text": ""},
                {"line": 3, "text": "claim two"},
            ),
        )
        payload = {
            "segment_dispositions": [
                {"source_lines": [1], "status": "consumed", "claim_ids": ["C1"], "relation_ids": []},
                {
                    "source_lines": [2],
                    "status": "ignored_with_reason",
                    "claim_ids": [],
                    "relation_ids": [],
                    "reason": "blank separator",
                },
                {"source_lines": [3], "status": "consumed", "claim_ids": ["C2"], "relation_ids": []},
            ]
        }

        repaired, repairs = _drop_blank_line_dispositions(payload, chunk, document)

        self.assertEqual([row["source_lines"] for row in repaired["segment_dispositions"]], [[1], [3]])
        self.assertEqual(repairs[0]["source_lines"], [2])
        self.assertFalse(repairs[0]["semantic_fields_changed"])

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

    def test_reuses_validated_document_frame_without_provider_frame_call(self) -> None:
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
        provider = SequenceProvider([chunk])
        outputs = ROOT / "outputs"
        outputs.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=outputs) as parent:
            parent_path = Path(parent)
            frame_path = parent_path / "document-frame.json"
            frame_path.write_text(
                json.dumps(fixture["document_frame"], ensure_ascii=False),
                encoding="utf-8",
            )
            result = run_extraction(
                SOURCE,
                parent_path / "run",
                provider=provider,
                provider_name="sequence",
                model_name="fixture",
                document_id="SYNTHETIC-EXTRACTION-001",
                config=ExtractionConfig(
                    max_chunk_chars=20_000,
                    max_calls=2,
                    reuse_document_frame_path=frame_path,
                ),
            )
            self.assertEqual(provider.calls, 1)
            self.assertEqual(result["lineage"]["document_frame_source"]["type"], "reused_validated_artifact")

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
