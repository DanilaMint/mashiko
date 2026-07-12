from ..errors import TranslationError
from ..span import Span
from .symbols import TypeSymbol


class NameError(TranslationError):
    """Raised when a name lookup in the symbol table fails.

    Distinct from the language's :class:`TypeError`: a ``NameError``
    reports that an identifier used at some source position was never
    declared (or is out of scope). Re-declaration errors live in the
    :class:`DuplicateNameError` subclass — same diagnostic family,
    different cause and message.
    """

    ident: str

    def __init__(self, span: Span, ident: str):
        self.span = span
        self.ident = ident

    def additional_message(self) -> str:
        return f"name `{self.ident}` is not declared in this scope"


class DuplicateNameError(NameError):
    """Raised when a name is being bound to a symbol that is already
    bound in the same scope (re-declaration of a top-level function,
    class, or interface).

    Subclasses :class:`NameError` so existing handlers keep working
    while the diagnostic message is sharpened to point at the real
    cause.
    """

    def additional_message(self) -> str:
        return f"name `{self.ident}` is already declared in this scope"


class TypeError(TranslationError):
    """Raised when an expression has a type different from what the
    surrounding context requires (assignment, return, condition, etc.).
    """

    expected: TypeSymbol
    got: TypeSymbol
    comment: str

    def __init__(
        self, span: Span, expected: TypeSymbol, got: TypeSymbol, comment: str
    ):
        self.span = span
        self.expected = expected
        self.got = got
        self.comment = comment

    def additional_message(self) -> str:
        return f"expected {self.expected}, got {self.got}. {self.comment}"
