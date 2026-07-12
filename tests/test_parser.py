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

from mashiko.parser import parse_file, parse_string

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
        tree, errors = parse_file(path)
        self.assertEqual(errors, [])
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
        from mashiko.parser.parser import _get_parser

        _get_parser()

    def test_parse_string_simple(self):
        tree, errors = parse_string("func f() { x = 1; }")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_parse_string_empty(self):
        tree, errors = parse_string("")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_parse_string_invalid_returns_error_in_list(self):
        tree, errors = parse_string("@@@")
        self.assertIsNone(tree)
        self.assertEqual(len(errors), 1)
        self.assertIn("ParseError", type(errors[0]).__name__)


class RecoveryTests(unittest.TestCase):
    """The parser collects multiple syntax errors in a single pass
    instead of bailing on the first one. Earley with
    ``ambiguity='explicit'`` has no built-in recovery, so the parser
    recovers by masking each offending region with a block comment and
    re-parsing. Each subsequent error's position is translated back
    to the original source.
    """

    def test_two_independent_errors_both_reported(self):
        src = (
            "func a() {\n"
            "    @@@ bad token;\n"
            "}\n"
            "func b() {\n"
            "    ### also bad;\n"
            "}\n"
        )
        _, errors = parse_string(src)

        # Both errors must be in the list (Earley without recovery
        # would only surface the first).
        self.assertGreaterEqual(
            len(errors), 2,
            f"expected >= 2 parse errors, got {len(errors)}",
        )

    def test_first_error_keeps_larks_diagnostic(self):
        # The first reported error should preserve Lark's detailed
        # message ("No terminal matches '@'..."); only the
        # translated-pos recovery errors get the generic
        # "recovered region" placeholder.
        _, errors = parse_string("@@@")
        self.assertEqual(len(errors), 1)
        msg = errors[0].additional_message()
        self.assertIn("@", msg)
        self.assertNotIn("recovered region", msg)

    def test_recovered_error_points_into_original_source(self):
        src = (
            "func a() {\n"           # line 1
            "    @@@ bad;\n"         # line 2, col 5
            "}\n"
            "func b() {\n"           # line 4
            "    ### also bad;\n"    # line 5, col 5
            "}\n"
        )
        _, errors = parse_string(src)
        # Find the error on line 5.
        line5 = [e for e in errors if e.span.start_line == 5]
        self.assertTrue(
            line5,
            f"no error on line 5; got "
            f"{[(e.span.start_line, e.span.start_column) for e in errors]}",
        )
        self.assertEqual(line5[0].span.start_column, 5)


class CommentTests(unittest.TestCase):
    """Line (//) and block (/* */) comments are skipped during lexing."""

    def test_line_comment_between_tokens(self):
        tree, errors = parse_string("func f() { // ignore me\n  x = 1; }")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_block_comment_between_tokens(self):
        tree, errors = parse_string("func f() { /* ignore me */ x = 1; }")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_line_comment_only(self):
        tree, errors = parse_string("// just a comment\n")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_block_comment_only(self):
        tree, errors = parse_string("/* just a comment */")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_multiline_block_comment(self):
        tree, errors = parse_string("/* line1\nline2\nline3 */ func f() { x = 1; }")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_trailing_line_comment(self):
        tree, errors = parse_string("func f() { x = 1; // trailing\n }")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_multiple_line_comments(self):
        tree, errors = parse_string("// one\n// two\n// three\n")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")

    def test_empty_block_comment(self):
        tree, errors = parse_string("/**/")
        self.assertEqual(errors, [])
        self.assertEqual(tree.data, "module")


if __name__ == "__main__":
    unittest.main()
