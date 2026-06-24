"""Exceptions raised by the mashiko parser."""


class ParseError(Exception):
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
        super().__init__(str(lark_error))
