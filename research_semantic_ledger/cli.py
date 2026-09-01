"""Command-line entry point for the public Research Semantic Ledger MVP."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .validation import validate_path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "examples" / "synthetic-group-reference.json"
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "REPRODUCIBILITY.md",
    "SECURITY_AND_DATA.md",
    "examples/synthetic-group-reference.json",
)


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="research-semantic-ledger")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check the public checkout and its synthetic fixture")
    validate = commands.add_parser("validate", help="validate a semantic-ledger JSON file")
    validate.add_argument("path", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    summary = commands.add_parser("summary", help="validate and summarize a semantic-ledger JSON file")
    summary.add_argument("path", nargs="?", type=Path, default=DEFAULT_FIXTURE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return _doctor()
    if args.command == "validate":
        return _validate(args.path)
    if args.command == "summary":
        return _summary(args.path)
    raise AssertionError(f"unhandled command: {args.command}")
