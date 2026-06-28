from .syntax import Span

_SEPARATOR = "-" * 80


def _span_from_lark_error(e: Exception) -> Span:
    pos = getattr(e, "pos_in_stream", 0) or 0
    line = getattr(e, "line", 1) or 1
    column = getattr(e, "column", 1) or 1
    return Span(pos, pos, line, column, line, column)


class TranslationError(Exception):
    """Common type for error cathed dyring translation process"""

    span: Span

    def __init__(self, span: Span) -> None:
        self.span = span

    def into_str(self, src_code: str) -> str:
        lines = src_code.split("\n")
        line_idx = self.span.start_line - 1
        start_col = max(0, self.span.start_column - 1)

        result = f"{_SEPARATOR}\n"
        result += (
            f"Error: {self.__class__.__name__} "
            f"at line {self.span.start_line}, column {self.span.start_column}: "
            f"{self.additional_message()}\n"
        )

        context_start = max(0, line_idx - 2)
        context_end = min(len(lines), line_idx + 3)

        for i in range(context_start, context_end):
            line_num = i + 1
            line_text = lines[i] if i < len(lines) else ""
            prefix = f"{line_num}: "

            if i == line_idx:
                result += f"{prefix}{line_text}\n"

                indent = " " * len(prefix)
                column_padding = " " * start_col

                if (
                    self.span.end_line > self.span.start_line
                    or self.span.end_column > self.span.start_column
                ):
                    span_width = max(1, self.span.end_column - self.span.start_column)
                    marker = "^" * span_width + " here"
                else:
                    marker = "<-- here"

                result += f"{indent}{column_padding}{marker}\n"
            else:
                result += f"{prefix}{line_text}\n"

        result += f"{_SEPARATOR}\n"
        return result

    def additional_message(self) -> str:
        return "place holder"


class ParseError(TranslationError):
    """Raised when source code fails to parse.

    Wraps a Lark ``LarkError`` (or a more specific subclass such as
    ``UnexpectedToken`` / ``UnexpectedCharacters`` / ``UnexpectedEOF``)
    and preserves its message and source-position information via
    ``__str__``. The original exception is reachable as ``self.lark_error``
    for callers that want to call ``Lark``'s ``get_context()`` or inspect
    the offending token directly.
    """

    def __init__(self, lark_error: Exception) -> None:
        self.lark_error = lark_error
        super().__init__(_span_from_lark_error(lark_error))

    def __str__(self) -> str:
        return str(self.lark_error)

    def additional_message(self) -> str:
        return str(self.lark_error).split("\n", 1)[0]


class NameError(TranslationError):
    """Raised when source code fails to semantic analyze.

    Means, that a name used several times.
    """

    ident: str

    def __init__(self, span: Span, ident: str):
        self.span = span

    def additional_message(self) -> str:
        return f"`{self.ident}` is already declared"
