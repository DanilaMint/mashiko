"""Lark-based parser for the mashiko language.

Each public function returns ``(result, errors)`` rather than raising:

* on success — ``(tree_or_module, [])``
* on failure — ``(None, [ParseError(...)])``

Callers iterate ``errors`` (it is a list for forward compatibility, even
though the Earley parser produces at most one error per attempt) and
inspect ``result`` only when ``errors`` is empty. ``FileNotFoundError``
is still raised from the ``parse_file*`` variants because it is an I/O
issue, not a parsing issue.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from lark import Lark
from lark.exceptions import LarkError

from ..errors import ParseError
from .transformer import TreeToAST

__all__ = ["parse_file", "parse_string", "parse_ast", "parse_ast_file"]

if TYPE_CHECKING:
    from lark import Tree

    from .syntax import Module

ParserResult = tuple["Tree | None", list[ParseError]]
ASTResult = tuple["Module | None", list[ParseError]]


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
    "%ignore LINE_COMMENT\n"
    "%ignore BLOCK_COMMENT\n"
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


def parse_string(source: str) -> ParserResult:
    """Parse a mashiko source string.

    Returns ``(tree, errors)``. On success ``errors`` is empty; on a
    syntax error ``tree`` is ``None`` and ``errors`` contains a single
    :class:`~mashiko.errors.ParseError`.
    """
    errors: list[ParseError] = []
    try:
        tree: Tree | None = _get_parser().parse(source, start="start")
    except LarkError as e:
        errors.append(ParseError(e))
        return None, errors
    return tree, errors


def parse_file(path: str | Path) -> ParserResult:
    """Read ``path`` and parse it as mashiko source.

    See :func:`parse_string` for the return shape. Raises
    ``FileNotFoundError`` (and other I/O errors) — those are not parsing
    errors.
    """
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    return parse_string(source)


def parse_ast(source: str) -> ASTResult:
    """Parse ``source`` and build the typed AST.

    Returns ``(module, errors)`` where ``errors`` aggregates parse
    failures (and any unexpected transformer errors) into the list.
    """
    tree, errors = parse_string(source)
    if errors:
        return None, errors
    try:
        module: Module | None = TreeToAST().transform(tree)
    except Exception as e:
        # The transformer should normally succeed on a valid Lark tree;
        # wrap any unexpected failure as a ParseError so the caller's
        # uniform error-handling path still applies.
        errors.append(ParseError(e))
        return None, errors
    return module, errors


def parse_ast_file(path: str | Path) -> ASTResult:
    """Read ``path`` and return its typed AST.

    See :func:`parse_ast` for the return shape. Raises
    ``FileNotFoundError`` for I/O errors.
    """
    p = Path(path)
    source = p.read_text(encoding="utf-8")
    return parse_ast(source)
