"""Command-line entry point for the public Research Semantic Ledger MVP."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .rendering import render_document
from .validation import load_and_validate_path, validate_path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "examples" / "synthetic-group-reference.json"
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "REPRODUCIBILITY.md",
    "SECURITY_AND_DATA.md",
    "examples/synthetic-group-reference.json",
)


def _emit(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def _doctor() -> int:
    missing = [relative for relative in REQUIRED_FILES if not (REPO_ROOT / relative).is_file()]
    fixture = validate_path(DEFAULT_FIXTURE)
    python_ok = sys.version_info >= (3, 11)
    errors = [f"missing_required_file:{relative}" for relative in missing]
    if not python_ok:
        errors.append("python_3_11_or_newer_required")
    errors.extend(fixture.errors)
    _emit(
        {
            "status": "pass" if not errors else "fail",
            "project": "research-semantic-ledger",
            "version": __version__,
            "python": platform.python_version(),
            "fixture": fixture.summary,
            "errors": errors,
            "next_command": "python -m research_semantic_ledger summary examples/synthetic-group-reference.json",
            "markdown_command": "python -m research_semantic_ledger render examples/synthetic-group-reference.json",
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
    raise AssertionError(f"unhandled command: {args.command}")
