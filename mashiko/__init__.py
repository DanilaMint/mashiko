"""mashiko — programming language parser (Lark front-end)."""

from .errors import ParseError
from .parser import parse_ast, parse_ast_file, parse_file, parse_string
from .parser.syntax import Node, Span

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "parse_file",
    "parse_string",
    "parse_ast",
    "parse_ast_file",
    "ParseError",
    "Node",
    "Span",
]
