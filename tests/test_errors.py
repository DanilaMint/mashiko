from pathlib import Path

from mashiko import errors
from mashiko.parser import parse_ast
from mashiko.parser.syntax import Span

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def example_path(file: str) -> Path:
    return EXAMPLES_DIR / file


if __name__ == "__main__":
    with open(example_path("find_super_prime.msk"), "rt", encoding="utf-8") as file:
        code = file.read()

    ast, parse_errors = parse_ast(code)
    assert not parse_errors, parse_errors

    err = errors.TranslationError(Span(152, 178, 13, 5, 18, 2))

    print(err.into_str(code))
