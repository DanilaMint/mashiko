"""Lark-based parser for the mashiko language.

Each public function returns ``(result, errors)`` rather than raising:

* on success — ``(tree_or_module, [])``
* on failure — ``(None, [ParseError(...), ...])``

Callers iterate ``errors`` (it is a list, so multiple errors from the
recovery loop can all be surfaced in a single pass) and inspect
``result`` only when ``errors`` is empty. ``FileNotFoundError`` is
still raised from the ``parse_file*`` variants because it is an I/O
issue, not a parsing issue.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from lark import Lark
from lark.exceptions import LarkError

from ..errors import ParseError
from ..span import Span
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

# Parsing-error recovery bounds. Lark's Earley parser with
# ``ambiguity='explicit'`` has no built-in recovery — a ``LarkError``
# raises on the first unexpected input. ``parse_string`` masks each
# offending region with a block comment and re-parses to surface
# subsequent errors in a single sweep.
_RECOVERY_MAX_PASSES = 16
_RECOVERY_MASK = "/*!s*/"
_RECOVERY_RESCAN_WINDOW = 8192


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
            # Populate Tree.meta with start_pos/end_pos/line/column/...
            # so the transformer can attach a Span to every AST node.
            propagate_positions=True,
        )
    return _PARSER


def _pos_to_line_col(source: str, pos: int) -> tuple[int, int]:
    """Translate a 0-based character offset in ``source`` to a
    1-based ``(line, column)`` pair.
    """
    line = column = 1
    for ch in source[: min(pos, len(source))]:
        if ch == "\n":
            line += 1
            column = 1
        else:
            column += 1
    return line, column


def _next_resync_point(source: str, after_pos: int) -> int | None:
    """Find the position after ``after_pos`` where the parser can
    plausibly resume after a recovery mask.

    Two statement/block terminators mark safe resync points:
    ``;`` (statement end) and ``}`` (block end). Newlines are skipped
    intentionally — masking them would shift later line numbers, which
    is more confusing than a slightly longer masked region.

    Returns ``None`` if no such boundary is found within
    ``_RECOVERY_RESCAN_WINDOW`` characters, indicating the parser has
    hit unbalanced-brace territory where further recovery would only
    produce noise.
    """
    end = min(len(source), after_pos + _RECOVERY_RESCAN_WINDOW)
    for i in range(after_pos, end):
        if source[i] in (";", "}"):
            return i + 1
    return None


def parse_string(source: str) -> ParserResult:
    """Parse a mashiko source string.

    Returns ``(tree, errors)``. On full success ``errors`` is empty
    and ``tree`` is the parsed Lark tree. If the source has syntax
    errors the parser performs up to :data:`_RECOVERY_MAX_PASSES`
    recovery passes: each pass masks the offending region with a
    block comment (which the lexer treats as whitespace) and
    re-parses, accumulating one :class:`~mashiko.errors.ParseError`
    per failure. The returned ``tree`` (if any) is best-effort and
    may not represent the source faithfully — callers that need a
    coherent AST should ensure ``errors`` is empty before using it.

    Position accuracy note: positions on errors from the second and
    later passes are translated back from the masked source into the
    *original* source by subtracting the cumulative size of all
    masks inserted so far. Line and column numbers are recomputed
    against the un-masked source.
    """
    errors: list[ParseError] = []
    masked = source
    mask_extra = 0  # bytes the masked source has grown past the original
    mask_len = len(_RECOVERY_MASK)

    for _ in range(_RECOVERY_MAX_PASSES):
        try:
            tree = _get_parser().parse(masked, start="start")
            return tree, errors
        except LarkError as exc:
            masked_pos = getattr(exc, "pos_in_stream", None)
            if masked_pos is None:
                errors.append(ParseError(exc))
                return None, errors

            if mask_extra == 0:
                # First pass — no recovery has been applied yet, so the
                # LarkError's pos/line/column already point into the
                # original source. Wrap it directly to keep Lark's
                # detailed diagnostic message ("No terminal matches '@'
                # ...") instead of replacing it with a generic
                # "recovered region" placeholder.
                errors.append(ParseError(exc))
            else:
                # Recovery pass — the LarkError's positions live in the
                # masked source. Translate them back so the diagnostic
                # points at the corresponding position in the original.
                original_pos = max(0, masked_pos - mask_extra)
                line, column = _pos_to_line_col(source, original_pos)
                span = Span(
                    original_pos, original_pos, line, column, line, column
                )
                errors.append(ParseError(span))

            next_pos = _next_resync_point(masked, masked_pos)
            if next_pos is None:
                return None, errors

            masked = masked[:masked_pos] + _RECOVERY_MASK + masked[next_pos:]
            mask_extra += mask_len - (next_pos - masked_pos)

    return None, errors


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
    except Exception as exc:
        errors.append(ParseError(exc))
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
