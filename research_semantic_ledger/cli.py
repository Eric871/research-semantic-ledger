"""Command-line entry point for the public Research Semantic Ledger MVP."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .evaluation import EvaluationError, evaluate_paths
from .extraction import ExtractionConfig, ExtractionError, prepare_run, run_extraction
from .provider import (
    DEFAULT_DEEPSEEK_ENDPOINT,
    DEFAULT_DEEPSEEK_MODEL,
    DeepSeekProvider,
    ProviderError,
    ReplayThenProvider,
)
from .rendering import render_document
from .validation import load_and_validate_path, validate_path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "examples" / "synthetic-group-reference.json"
DEFAULT_GENERIC_FIXTURE = REPO_ROOT / "examples" / "synthetic-extracted-ledger.json"
DEFAULT_GOLD = REPO_ROOT / "examples" / "synthetic-extraction-gold.json"
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "REPRODUCIBILITY.md",
    "SECURITY_AND_DATA.md",
    "examples/synthetic-group-reference.json",
    "examples/synthetic-research-note.md",
    "examples/synthetic-extracted-ledger.json",
    "examples/synthetic-extraction-gold.json",
    "contracts/semantic-ledger-v0.2.schema.json",
    "contracts/gold-v0.1.schema.json",
    "research_semantic_ledger/prompts/document-frame-v0.1.txt",
    "research_semantic_ledger/prompts/chunk-extraction-v0.1.txt",
)


def _emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def _doctor() -> int:
    missing = [relative for relative in REQUIRED_FILES if not (REPO_ROOT / relative).is_file()]
    legacy_fixture = validate_path(DEFAULT_FIXTURE)
    fixture = validate_path(DEFAULT_GENERIC_FIXTURE)
    python_ok = sys.version_info >= (3, 11)
    errors = [f"missing_required_file:{relative}" for relative in missing]
    if not python_ok:
        errors.append("python_3_11_or_newer_required")
    errors.extend(legacy_fixture.errors)
    errors.extend(fixture.errors)
    gold_summary: dict[str, Any] = {}
    if fixture.valid:
        try:
            gold_summary = evaluate_paths(DEFAULT_GENERIC_FIXTURE, DEFAULT_GOLD)
            if gold_summary["status"] != "pass":
                errors.append("public_gold_did_not_pass")
        except EvaluationError as exc:
            errors.append(f"public_gold_error:{exc}")
    _emit(
        {
            "status": "pass" if not errors else "fail",
            "project": "research-semantic-ledger",
            "version": __version__,
            "python": platform.python_version(),
            "fixture": fixture.summary,
            "gold": {"passed": gold_summary.get("passed", 0), "total": gold_summary.get("total", 0)},
            "errors": errors,
            "next_command": "python -m research_semantic_ledger summary examples/synthetic-extracted-ledger.json",
            "markdown_command": "python -m research_semantic_ledger render examples/synthetic-extracted-ledger.json",
        }
    )
    return 0 if not errors else 2


def _validate(path: Path) -> int:
    result = validate_path(path)
    _emit(result.as_dict())
    return 0 if result.valid else 2


def _summary(path: Path) -> int:
    result = validate_path(path)
    payload = result.as_dict()
    payload["path"] = path.as_posix()
    _emit(payload)
    return 0 if result.valid else 2


def _render(path: Path, output: Path | None, force: bool) -> int:
    data, result = load_and_validate_path(path)
    if not result.valid or not isinstance(data, dict):
        _emit(result.as_dict(), stream=sys.stderr)
        return 2
    markdown = render_document(data)
    if output is None:
        print(markdown)
        return 0
    if output.exists() and not force:
        _emit({"status": "fail", "errors": [f"output_exists:{output}"]}, stream=sys.stderr)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8", newline="\n")
    _emit(
        {
            "status": "pass",
            "input": path.as_posix(),
            "output": output.as_posix(),
            "bytes": output.stat().st_size,
        }
    )
    return 0


def _default_output_dir(source: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return REPO_ROOT / "outputs" / f"{source.stem}-{stamp}"


def _extract(args: argparse.Namespace) -> int:
    output_dir = args.output_dir or _default_output_dir(args.path)
    if not args.dry_run and not args.authorize_external_send:
        _emit(
            {
                "status": "fail",
                "errors": ["online_extraction_requires_--authorize-external-send"],
            },
            stream=sys.stderr,
        )
        return 2
    if output_dir.exists() and any(output_dir.iterdir()):
        _emit({"status": "fail", "errors": [f"output_directory_not_empty:{output_dir}"]}, stream=sys.stderr)
        return 2
    config = ExtractionConfig(
        max_chunk_chars=args.max_chunk_chars,
        max_context_chars=args.max_context_chars,
        max_output_tokens=args.max_output_tokens,
        max_calls=args.max_calls,
        max_cost_cny=args.max_cost_cny,
        input_price_cny_per_million=args.input_price_cny_per_million,
        output_price_cny_per_million=args.output_price_cny_per_million,
        reuse_document_frame_path=args.reuse_document_frame,
        replay_receipt_dirs=tuple(args.replay_successful_calls),
    )
    try:
        if args.dry_run:
            document, chunks, run_id = prepare_run(
                args.path,
                output_dir,
                document_id=args.document_id,
                config=config,
                provider_name="deepseek",
                model_name=args.model,
            )
            _emit(
                {
                    "status": "preflight_pass",
                    "run_id": run_id,
                    "document_id": document.document_id,
                    "source_sha256": document.normalized_sha256,
                    "chunks": len(chunks),
                    "planned_minimum_calls": len(chunks) + 1,
                    "output_dir": output_dir.as_posix(),
                    "external_transmission": False,
                }
            )
            return 0
        provider = DeepSeekProvider(
            endpoint=args.endpoint,
            model=args.model,
            timeout_seconds=args.timeout_seconds,
        )
        if args.replay_successful_calls:
            provider = ReplayThenProvider(provider, args.replay_successful_calls)
        ledger = run_extraction(
            args.path,
            output_dir,
            provider=provider,
            provider_name="deepseek",
            model_name=args.model,
            document_id=args.document_id,
            config=config,
        )
        markdown_path = output_dir / "candidate-ledger.md"
        markdown_path.write_text(render_document(ledger), encoding="utf-8", newline="\n")
        _emit(
            {
                "status": "pass",
                "output_dir": output_dir.as_posix(),
                "ledger": (output_dir / "candidate-ledger.json").as_posix(),
                "markdown": markdown_path.as_posix(),
                "bindings": len(ledger["mention_bindings"]),
                "claims": len(ledger["claims"]),
                "relations": len(ledger["relations"]),
                "formal_database_writes": 0,
            }
        )
        return 0
    except (ExtractionError, ProviderError, OSError) as exc:
        manifest_path = output_dir / "run-manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    manifest["status"] = "failed"
                    manifest["terminal_error"] = str(exc)
                    manifest_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                        newline="\n",
                    )
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        _emit({"status": "fail", "errors": [str(exc)], "output_dir": output_dir.as_posix()}, stream=sys.stderr)
        return 2


def _evaluate(ledger: Path, gold: Path, output: Path | None) -> int:
    try:
        report = evaluate_paths(ledger, gold)
    except EvaluationError as exc:
        _emit({"status": "fail", "errors": [str(exc)]}, stream=sys.stderr)
        return 2
    if output is not None:
        if output.exists():
            _emit({"status": "fail", "errors": [f"output_exists:{output}"]}, stream=sys.stderr)
            return 2
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    _emit(report)
    return 0 if report["status"] == "pass" else 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-semantic-ledger")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check the public checkout and its synthetic fixture")
    validate = commands.add_parser("validate", help="validate a semantic-ledger JSON file")
    validate.add_argument("path", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    summary = commands.add_parser("summary", help="validate and summarize a semantic-ledger JSON file")
    summary.add_argument("path", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    render = commands.add_parser("render", help="validate and render a semantic-ledger JSON file as Markdown")
    render.add_argument("path", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    render.add_argument("--output", "-o", type=Path)
    render.add_argument("--force", action="store_true", help="replace an existing output file")
    extract = commands.add_parser("extract", help="preflight or run full-document DeepSeek extraction")
    extract.add_argument("path", type=Path, help="UTF-8 source text or Markdown file")
    extract.add_argument("--document-id")
    extract.add_argument("--output-dir", type=Path)
    extract.add_argument("--dry-run", action="store_true", help="freeze source and chunk manifests without API calls")
    extract.add_argument(
        "--authorize-external-send",
        action="store_true",
        help="confirm that the source may be sent to the configured provider",
    )
    extract.add_argument("--endpoint", default=DEFAULT_DEEPSEEK_ENDPOINT)
    extract.add_argument("--model", default=DEFAULT_DEEPSEEK_MODEL)
    extract.add_argument("--timeout-seconds", type=int, default=180)
    extract.add_argument("--max-chunk-chars", type=int, default=6_000)
    extract.add_argument("--max-context-chars", type=int, default=120_000)
    extract.add_argument("--max-output-tokens", type=int, default=12_000)
    extract.add_argument("--max-calls", type=int, default=100)
    extract.add_argument("--max-cost-cny", type=float)
    extract.add_argument("--input-price-cny-per-million", type=float)
    extract.add_argument("--output-price-cny-per-million", type=float)
    extract.add_argument(
        "--reuse-document-frame",
        type=Path,
        help="reuse and revalidate a prior document-frame.json instead of purchasing a new frame call",
    )
    extract.add_argument(
        "--replay-successful-calls",
        type=Path,
        action="append",
        default=[],
        help="replay exact successful request hashes from a prior run directory before calling the provider",
    )
    evaluate = commands.add_parser("evaluate", help="evaluate a validated ledger against frozen public-safe Gold")
    evaluate.add_argument("ledger", type=Path)
    evaluate.add_argument("--gold", required=True, type=Path)
    evaluate.add_argument("--output", "-o", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "validate":
        return _validate(args.path)
    if args.command == "summary":
        return _summary(args.path)
    if args.command == "render":
        return _render(args.path, args.output, args.force)
    if args.command == "extract":
        return _extract(args)
    if args.command == "evaluate":
        return _evaluate(args.ledger, args.gold, args.output)
    raise AssertionError(f"unhandled command: {args.command}")
