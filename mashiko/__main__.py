"""CLI entry point: ``python -m mashiko FILE.msk [--ast|--ast-typed]``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import ParseError
from .parser import parse_ast_file, parse_file


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mashiko",
        description="Parse a mashiko (.msk) source file and report the result.",
    )
    p.add_argument("file", type=Path, help="path to a .msk source file")
    p.add_argument(
        "--ast",
        action="store_true",
        help="print the raw Lark parse tree to stdout",
    )
    p.add_argument(
        "--ast-typed",
        action="store_true",
        help="print the typed AST (frozen-dataclass form) to stdout",
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"mashiko {__version__}",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.ast_typed:
            module = parse_ast_file(args.file)
        else:
            tree = parse_file(args.file)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except ParseError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 1
    if args.ast_typed:
        print(module)
    elif args.ast:
        print(tree.pretty())
    else:
        print(f"OK: {args.file}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
