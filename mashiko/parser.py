"""Lark-based parser for the mashiko language."""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from lark import Lark
from lark.exceptions import LarkError

from .errors import ParseError
from .transformer import TreeToAST

__all__ = ["parse_file", "parse_string", "parse_ast", "parse_ast_file"]

if TYPE_CHECKING:
    from lark import Tree

    from .syntax import Module


_GRAMMAR_NAME = "grammar.lark"
_PARSER: Lark | None = None

# Lark 1.3.1 does not auto-skip whitespace; the grammar must opt in via
# `%ignore` directives. mashiko/grammar.lark does not declare them, so we
# prepend the standard whitespace ignores here. If/when the grammar grows
# its own `%ignore` block, these will be redundant but not conflicting.
_GRAMMAR_PREFIX = (
    '%ignore " "\n'
    '%ignore "\\t"\n'
    '%ignore "\\n"\n'
    '%ignore "\\r"\n'
    '%ignore LINE_COMMENT\n'
    '%ignore BLOCK_COMMENT\n'
    "\n"
)


def _load_grammar() -> str:
    return _GRAMMAR_PREFIX + (
        importlib.resources.files(__package__)
        .joinpath(_GRAMMAR_NAME)
        .read_text(encoding="utf-8")
    )


def _get_parser() -> Lark:
    global _PARSER
    if _PARSER is None:
        _PARSER = Lark(
            _load_grammar(),
            parser="earley",
            ambiguity="explicit",
            # Populate Tree.meta with start_pos/end_pos/line/column/... so
            # the transformer can attach a Span to every AST node.
            propagate_positions=True,
        )
    return _PARSER


def parse_string(source: str) -> "Tree":
    """Parse a mashiko source string and return the Lark ``Tree``.

    Raises :class:`~mashiko.errors.ParseError` on syntax errors.
    """
    try:
        return _get_parser().parse(source, start="start")
    except LarkError as e:
        raise ParseError(e) from e


def parse_file(path: str | Path) -> "Tree":
    """Read ``path`` and parse it as mashiko source.

    Raises :class:`~mashiko.errors.ParseError` on syntax errors and
    ``FileNotFoundError`` if the file does not exist.
    """
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    try:
        return _get_parser().parse(source, start="start")
    except LarkError as e:
        raise ParseError(e) from e


def parse_ast(source: str) -> "Module":
    """Parse ``source`` and return the typed AST (:class:`~mashiko.syntax.Module`).

    The tree is transformed by :class:`~mashiko.transformer.TreeToAST`;
    the returned value is a tree of frozen dataclasses (not a Lark ``Tree``).
    """
    tree = parse_string(source)
    return TreeToAST().transform(tree)


def parse_ast_file(path: str | Path) -> "Module":
    """Read ``path`` and return its typed AST (:class:`~mashiko.syntax.Module`)."""
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    return parse_ast(source)
