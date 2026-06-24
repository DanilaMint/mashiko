"""Tests for mashiko.parser.

KNOWN_FAILURES below maps example filenames to a short reason for why they
currently fail to parse. The test suite will skip those (so it goes green
in known-bad states) but will **fail red** on any new breakage. When the
grammar is fixed and an example starts parsing, delete its entry from
KNOWN_FAILURES and the test flips from ``skipped`` to ``ok``.

## Grammar gaps still open (not exercised by current examples/)

- ``enum`` declarations (``enum Name { A, B, C }``) — used by
  ``bootstrap/lexer.msk`` but not by any ``examples/*.msk`` file.
- ``system`` / ``value`` template parameter kinds — declared in
  ``bootstrap/lexer.msk`` comments; not yet in grammar.
- Shift operators (``<<``, ``>>``) and bitwise compound assignment
  (``|=``, ``^=``, ``<<=``, ``>>=``) — not used by any current example.
- ``const`` local declarations (``const x = ...;``) — not used by any
  current example.
"""

import unittest
from pathlib import Path

from mashiko import ParseError, parse_string
from mashiko.parser import parse_file

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

KNOWN_FAILURES: dict[str, str] = {}


def _example_path(name: str) -> Path:
    return EXAMPLES_DIR / name


class ExampleParseTests(unittest.TestCase):
    """Each .msk example in examples/ must parse, unless listed in KNOWN_FAILURES."""

    def _check(self, name: str) -> None:
        path = _example_path(name)
        if name in KNOWN_FAILURES:
            self.skipTest(KNOWN_FAILURES[name])
        tree = parse_file(path)
        self.assertEqual(tree.data, "module")

    def test_box(self):
        self._check("box.msk")

    def test_find_super_prime(self):
        self._check("find_super_prime.msk")

    def test_interfaces(self):
        self._check("interfaces.msk")

    def test_template(self):
        self._check("template.msk")


class APITests(unittest.TestCase):
    """Smoke tests for the parser API itself."""

    def test_parser_constructs(self):
        from mashiko.parser import _get_parser

        _get_parser()

    def test_parse_string_simple(self):
        tree = parse_string("func f() { x = 1; }")
        self.assertEqual(tree.data, "module")

    def test_parse_string_empty(self):
        tree = parse_string("")
        self.assertEqual(tree.data, "module")

    def test_parse_string_invalid_raises(self):
        with self.assertRaises(ParseError):
            parse_string("@@@")


class CommentTests(unittest.TestCase):
    """Line (//) and block (/* */) comments are skipped during lexing."""

    def test_line_comment_between_tokens(self):
        tree = parse_string("func f() { // ignore me\n  x = 1; }")
        self.assertEqual(tree.data, "module")

    def test_block_comment_between_tokens(self):
        tree = parse_string("func f() { /* ignore me */ x = 1; }")
        self.assertEqual(tree.data, "module")

    def test_line_comment_only(self):
        tree = parse_string("// just a comment\n")
        self.assertEqual(tree.data, "module")

    def test_block_comment_only(self):
        tree = parse_string("/* just a comment */")
        self.assertEqual(tree.data, "module")

    def test_multiline_block_comment(self):
        tree = parse_string("/* line1\nline2\nline3 */ func f() { x = 1; }")
        self.assertEqual(tree.data, "module")

    def test_trailing_line_comment(self):
        tree = parse_string("func f() { x = 1; // trailing\n }")
        self.assertEqual(tree.data, "module")

    def test_multiple_line_comments(self):
        tree = parse_string("// one\n// two\n// three\n")
        self.assertEqual(tree.data, "module")

    def test_empty_block_comment(self):
        tree = parse_string("/**/")
        self.assertEqual(tree.data, "module")


if __name__ == "__main__":
    unittest.main()
