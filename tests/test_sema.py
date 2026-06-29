"""Tests for mashiko.sema — name handling.

Covers ``Scope`` (register/get with parent chain), the built-in global
scope, the ``NameError`` shape, and duplicate function-name detection via
``SemanticAnalyzer._preregistry``. The analyzer's ``__init__`` does not
initialize ``self.preregister``, so each duplicate-name test sets it on
the instance before calling the private helper — the production module
itself is not modified.
"""

import unittest

from mashiko import parse_ast
from mashiko.errors import NameError, TranslationError
from mashiko.sema import BUILTIN_SCOPE, Scope, SemanticAnalyzer
from mashiko.syntax import Span


class ScopeNameTests(unittest.TestCase):
    """Name registration and lookup in ``Scope``."""

    def test_register_and_get(self):
        scope = Scope(None)
        scope.register_symbol("foo", "FOO_SYM")

        self.assertEqual(scope.get_symbol("foo"), "FOO_SYM")

    def test_get_missing_returns_none(self):
        scope = Scope(None)

        self.assertIsNone(scope.get_symbol("missing"))

    def test_lookup_walks_to_parent(self):
        parent = Scope(None)
        parent.register_symbol("foo", "PARENT_SYM")
        child = Scope(parent)

        self.assertEqual(child.get_symbol("foo"), "PARENT_SYM")

    def test_child_shadows_parent(self):
        parent = Scope(None)
        parent.register_symbol("foo", "PARENT_SYM")
        child = Scope(parent)
        child.register_symbol("foo", "CHILD_SYM")

        self.assertEqual(child.get_symbol("foo"), "CHILD_SYM")
        # parent still sees its own binding
        self.assertEqual(parent.get_symbol("foo"), "PARENT_SYM")

    def test_lookup_does_not_walk_to_child(self):
        parent = Scope(None)
        child = Scope(parent)
        child.register_symbol("foo", "CHILD_SYM")

        self.assertIsNone(parent.get_symbol("foo"))


class BuiltinScopeTests(unittest.TestCase):
    """Names pre-registered in the global scope."""

    def test_void_is_registered(self):
        self.assertIsNotNone(BUILTIN_SCOPE.get_symbol("Void"))

    def test_int_is_registered(self):
        self.assertIsNotNone(BUILTIN_SCOPE.get_symbol("Int"))

    def test_unknown_name_returns_none(self):
        self.assertIsNone(BUILTIN_SCOPE.get_symbol("NotABuiltin"))


class NameErrorShapeTests(unittest.TestCase):
    """``NameError`` is part of the error hierarchy."""

    def test_name_error_is_translation_error(self):
        err = NameError(Span(0, 1, 1, 1, 1, 2), "foo")

        self.assertIsInstance(err, TranslationError)

    def test_span_is_stored(self):
        err = NameError(Span(0, 1, 1, 1, 1, 2), "foo")

        self.assertEqual(err.span, Span(0, 1, 1, 1, 1, 2))


class DuplicateFunctionNameTests(unittest.TestCase):
    """``SemanticAnalyzer._preregistry`` flags duplicate function names."""

    def _check(self, source: str) -> list[TranslationError] | None:
        module, errors = parse_ast(source)
        self.assertEqual(errors, [])
        self.assertIsNotNone(module)
        return SemanticAnalyzer(module)._preregistry()

    def test_unique_function_names_pass(self):
        src = (
            "func alpha(): Void {}\n"
            "func beta(): Void {}\n"
            "func gamma(): Void {}\n"
        )

        self.assertIsNone(self._check(src))

    def test_duplicate_function_name_reported(self):
        src = (
            "func foo(): Void {}\n"
            "func foo(): Void {}\n"
        )

        errors = self._check(src)

        self.assertIsNotNone(errors)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], NameError)

    def test_three_way_collision_reports_each_duplicate(self):
        src = (
            "func foo(): Void {}\n"
            "func foo(): Void {}\n"
            "func foo(): Void {}\n"
        )

        errors = self._check(src)

        self.assertIsNotNone(errors)
        # Two duplicates beyond the first registration.
        self.assertEqual(len(errors), 2)
        for err in errors:
            self.assertIsInstance(err, NameError)


if __name__ == "__main__":
    unittest.main()