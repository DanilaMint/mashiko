from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """Source range covered by an AST node.

    ``start_pos``/``end_pos`` are zero-based character offsets in the
    original source string (``end_pos`` is exclusive). ``start_line`` /
    ``start_column`` / ``end_line`` / ``end_column`` are 1-based.
    """

    start_pos: int
    end_pos: int
    start_line: int
    start_column: int
    end_line: int
    end_column: int
