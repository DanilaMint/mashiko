"""CLI entry point: ``python -m mashiko FILE.msk [--ast|--ast-typed]``.

Pipeline:

1. parse the source into a typed AST
2. on success, run :class:`~mashiko.sema.core.SemaAnalyzer` over the
   AST to surface name / type errors
3. print any diagnostics, in the order they were produced (parse
   errors first, then semantic errors).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .parser import parse_ast, parse_ast_file
from .print_ast import print_ast
from .sema.core import SemaAnalyzer


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mashiko",
        description="Parse a mashiko (.msk) source file and run semantic analysis.",
    )
    p.add_argument("file", type=Path, help="path to a .msk source file")
    p.add_argument(
        "--log",
        choices=["quiet", "standart", "big"],
        default="standart",
        help="print translation status and metadata",
    )
    p.add_argument(
        "--ast-typed",
        action="store_true",
        help="print the typed AST (frozen-dataclass form) to stdout",
    )
    p.add_argument(
        "--no-sema",
        action="store_true",
        help="skip semantic analysis (only parse the file)",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"mashiko {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        with open(args.file, "rt", encoding="utf-8") as file:
            src_code = file.read()
    except FileNotFoundError as e:
        print(e)
        return 1

    ast, errors = parse_ast(src_code)

    if errors:
        for err in errors:
            print(err.into_str(src_code))
        return 1

    if args.ast_typed:
        print_ast(ast)

    if not args.no_sema:
        sema_errors = SemaAnalyzer(ast).analyze()
        for err in sema_errors:
            print(err.into_str(src_code))
        if sema_errors:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
