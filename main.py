import sys
from typing import List

import parser


def main() -> None:
    argv = sys
    print("hello, mashiko")


def compile(source_code: str, flags: List[str]) -> str | None:
    ast = parser.parse(source_code)
    pass


if __name__ == "__main__":
    main()
