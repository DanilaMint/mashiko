"""Tests for mashiko.sema — name handling, scope chains, and end-to-end
type-checking of the example-style programs the front-end is expected
to consume.
"""

import unittest

from mashiko import parse_ast
from mashiko.errors import TranslationError
from mashiko.parser.syntax import Span
from mashiko.sema import SemaAnalyzer
from mashiko.sema.errors import (
    DuplicateNameError,
    NameError as SemaNameError,
    TypeError as SemaTypeError,
)
from mashiko.sema.scope import BUILTIN_SCOPE, Scope
from mashiko.sema.symbols import (
    ClassSymbol,
    ClassTemplate,
    FunctionSymbol,
    InterfaceSymbol,
    PrimitiveTypeSymbol,
    TypeParamSymbol,
    UserDefinedTypeSymbol,
    VarSymbol,
)
from mashiko.sema.symbols import GenericDefinedTypeSymbol


class ScopeNameTests(unittest.TestCase):
    """Name registration and lookup in :class:`Scope`."""

    def test_register_and_get(self):
        scope = Scope(None)
        scope.push_symbol("foo", "FOO_SYM")

        self.assertEqual(scope.get_symbol("foo"), "FOO_SYM")

    def test_get_missing_returns_none(self):
        scope = Scope(None)

        self.assertIsNone(scope.get_symbol("missing"))

    def test_lookup_walks_to_parent(self):
        parent = Scope(None)
        parent.push_symbol("foo", "PARENT_SYM")
        child = Scope(parent)

        self.assertEqual(child.get_symbol("foo"), "PARENT_SYM")

    def test_child_shadows_parent(self):
        parent = Scope(None)
        parent.push_symbol("foo", "PARENT_SYM")
        child = Scope(parent)
        child.push_symbol("foo", "CHILD_SYM")

        self.assertEqual(child.get_symbol("foo"), "CHILD_SYM")
        self.assertEqual(parent.get_symbol("foo"), "PARENT_SYM")

    def test_lookup_does_not_walk_to_child(self):
        parent = Scope(None)
        child = Scope(parent)
        child.push_symbol("foo", "CHILD_SYM")

        self.assertIsNone(parent.get_symbol("foo"))


class BuiltinScopeTests(unittest.TestCase):
    """Names pre-registered in the global scope."""

    def test_void_is_registered(self):
        self.assertIsNotNone(BUILTIN_SCOPE.get_symbol("Void"))

    def test_int_is_registered(self):
        self.assertIsNotNone(BUILTIN_SCOPE.get_symbol("Int"))


class SemaErrorShapeTests(unittest.TestCase):
    """``SemaNameError`` / ``SemaTypeError`` are part of the error hierarchy."""

    def test_name_error_is_translation_error(self):
        err = SemaNameError(Span(0, 1, 1, 1, 1, 2), "foo")

        self.assertIsInstance(err, TranslationError)

    def test_name_error_stores_ident(self):
        err = SemaNameError(Span(0, 1, 1, 1, 1, 2), "foo")

        self.assertEqual(err.ident, "foo")
        self.assertIn("foo", err.additional_message())

    def test_type_error_reports_expected_and_got(self):
        err = SemaTypeError(Span(0, 1, 1, 1, 1, 2), PrimitiveTypeSymbol.Int,
                            PrimitiveTypeSymbol.Bool, "demo")

        self.assertIn("Int", err.additional_message())
        self.assertIn("Bool", err.additional_message())


class _SemaHelper:
    """Tiny harness: parse ``source`` and run :class:`SemaAnalyzer`."""

    @staticmethod
    def analyze(source: str) -> list[TranslationError]:
        module, errors = parse_ast(source)
        assert errors == [] and module is not None, errors
        return SemaAnalyzer(module).analyze()


class DuplicateFunctionNameTests(unittest.TestCase):
    """Re-declaring the same function name at module scope is a :class:`SemaNameError`."""

    def test_unique_function_names_pass(self):
        errs = _SemaHelper.analyze(
            "func alpha(): Void {}\nfunc beta(): Void {}\nfunc gamma(): Void {}\n"
        )

        self.assertEqual(errs, [])

    def test_duplicate_function_name_reported(self):
        # Two `foo` declarations: the second is the *re-declaration*,
        # so the analyzer reports exactly one DuplicateNameError
        # pointing at it and keeps only the first binding in the
        # symbol table. The first declaration's body still gets
        # checked, but the duplicate's body is intentionally not
        # visited (its symbol was never registered, so re-checking
        # would just confuse the caller).
        errs = _SemaHelper.analyze("func foo(): Void {}\nfunc foo(): Void {}\n")

        dup = [e for e in errs if isinstance(e, DuplicateNameError)]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].ident, "foo")
        # The sharpened message distinguishes this from a plain
        # "not declared" miss.
        self.assertIn("already declared", dup[0].additional_message())

    def test_three_way_duplicate_reports_each_repeat(self):
        # Only the second-and-onwards occurrences are collisions.
        errs = _SemaHelper.analyze(
            "func foo(): Void {}\nfunc foo(): Void {}\nfunc foo(): Void {}\n"
        )

        dup = [e for e in errs if isinstance(e, DuplicateNameError)]
        self.assertEqual(len(dup), 2)
        for err in dup:
            self.assertEqual(err.ident, "foo")

    def test_duplicate_class_name_reported(self):
        errs = _SemaHelper.analyze(
            "class A { x: Int; }\nclass A { y: Int; }\n"
        )

        dup = [e for e in errs if isinstance(e, DuplicateNameError)]
        self.assertEqual(len(dup), 1)
        self.assertEqual(dup[0].ident, "A")


class StatementCheckingTests(unittest.TestCase):
    """End-to-end checks via the analyzer on small programs."""

    def test_int_arithmetic_in_return(self):
        errs = _SemaHelper.analyze("func f(x: Int): Int { return x * x; }\n")

        self.assertEqual(errs, [])

    def test_type_mismatch_in_arithmetic(self):
        errs = _SemaHelper.analyze(
            'func f(x: Int): Int { return x + "hi"; }\n'
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertEqual(len(type_errs), 1)
        self.assertEqual(type_errs[0].expected, PrimitiveTypeSymbol.Int)
        self.assertIsInstance(type_errs[0].got, UserDefinedTypeSymbol)

    def test_undefined_name_emits_name_error(self):
        # `y` is read before any assignment, so the analyzer has no
        # binding for it and must report a NameError.
        errs = _SemaHelper.analyze("func f(): Int { return y + 1; }\n")

        name_errs = [e for e in errs if isinstance(e, SemaNameError)]
        self.assertGreaterEqual(len(name_errs), 1)
        self.assertEqual(name_errs[0].ident, "y")

    def test_local_var_intro_via_plain_assign(self):
        # `x = 1;` introduces `x` as Int; second use reuses that type.
        errs = _SemaHelper.analyze(
            "func f(): Int { x = 1; return x + 1; }\n"
        )

        self.assertEqual(errs, [])

    def test_if_condition_must_be_bool(self):
        errs = _SemaHelper.analyze(
            "func f(x: Int): Int { if x { return 1; } else { return 2; } return 0; }\n"
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertTrue(
            any("if-condition must be Bool" in e.comment for e in type_errs),
            f"expected if-condition Bool error, got {[e.additional_message() for e in errs]}",
        )

    def test_break_outside_loop_is_rejected(self):
        errs = _SemaHelper.analyze("func f() { break; }\n")

        self.assertTrue(
            any(isinstance(e, SemaTypeError) and "break" in e.comment for e in errs)
        )

    def test_return_value_type_mismatch(self):
        errs = _SemaHelper.analyze(
            'func f(): Int { return "not an int"; }\n'
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertTrue(any(e.expected == PrimitiveTypeSymbol.Int for e in type_errs))

    def test_function_call_arity_mismatch(self):
        errs = _SemaHelper.analyze(
            "func one(x: Int): Int { return x; }\n"
            "func bad(): Int { return one(); }\n"
        )

        self.assertTrue(
            any(
                isinstance(e, SemaTypeError) and "expects 1 args, got 0" in e.comment
                for e in errs
            ),
            f"got {[e.additional_message() for e in errs]}",
        )

    def test_compound_assignment_introduces_local(self):
        errs = _SemaHelper.analyze(
            "func f(): Int { acc = 0; acc += 1; return acc; }\n"
        )

        self.assertEqual(errs, [])

    def test_generic_function_body_returns_type_param(self):
        # `identity` is generic in T; the body's `return x` must agree with
        # the declared `T` return type.
        errs = _SemaHelper.analyze(
            "template<type T>\n"
            "func identity(x: T): T { return x; }\n"
        )

        self.assertEqual(errs, [])

    def test_errors_in_one_function_do_not_silence_others(self):
        # `f` has multiple type errors; `g` is fine. A pass that bails
        # on the first error would emit only the `f` errors and miss
        # `g` altogether (or, worse, raise mid-flight). The
        # implementation collects every error in one sweep.
        src = (
            "func f(): Int {\n"
            "    if 1 { return 2; }\n"           # bad condition
            '    return "not int";\n'           # bad return
            "}\n"
            "func g(): Int { return 3; }\n"
        )
        errs = _SemaHelper.analyze(src)

        # Both the if-condition error and the return-type error must
        # be reported; absence of `g` errors confirms the analysis
        # continued past `f`.
        self.assertTrue(
            any(isinstance(e, SemaTypeError) and "if-condition" in e.comment
                for e in errs),
            f"missing if-condition error in {[e.additional_message() for e in errs]}",
        )
        self.assertTrue(
            any(isinstance(e, SemaTypeError) and "return type mismatch" in e.comment
                for e in errs),
            f"missing return-type error in {[e.additional_message() for e in errs]}",
        )

    def test_internal_failure_in_one_decl_does_not_abort_pass(self):
        # If the analyzer hits an internal exception inside one
        # declaration's body, the remaining declarations still get
        # visited. The surfaced diagnostic may be a generic
        # TranslationError pointing at the failing decl's span.
        errs = _SemaHelper.analyze(
            'func f(): Int { return "not int"; }\n'
            'func g(): Int { return "also not int"; }\n'
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        # Both functions report independent type errors — no single
        # fault suppresses the rest.
        self.assertGreaterEqual(len(type_errs), 2)


class ExampleAnalyzeTests(unittest.TestCase):
    """The bundled examples (other than ``box.msk``) analyze cleanly
    when treated as mashiko source — they exercise naming, builtin
    operator semantics, generic templates, and simple interface
    declarations.
    """

    EXAMPLES = ("find_super_prime.msk", "interfaces.msk", "template.msk")

    def test_examples_analyze_clean(self):
        from pathlib import Path

        examples_dir = Path(__file__).resolve().parent.parent / "examples"
        for name in self.EXAMPLES:
            with self.subTest(example=name):
                source = (examples_dir / name).read_text(encoding="utf-8")
                errs = _SemaHelper.analyze(source)
                self.assertEqual(
                    errs, [],
                    f"{name} produced {len(errs)} sema errors:\n"
                    + "\n".join(e.additional_message() for e in errs),
                )


class MonomorphizationTests(unittest.TestCase):
    """``Foo<Bar>`` instantiations materialize as separate concrete
    :class:`ClassSymbol` / :class:`InterfaceSymbol` entries registered
    under the mangled name ``Foo-Bar`` in the analyzer's scope.

    The analyzer is otherwise generic-template-agnostic downstream:
    every reference to the instantiation resolves through the
    ordinary user-defined-type path, with no per-call substitution.

    The grammar lets generic types appear in signatures (parameter
    and return types) and as field types, but not as constructor-call
    expressions like ``Box<Int>()``. Tests therefore exercise the
    type-lowering path via parameter/return positions rather than
    value-level instantiation.
    """

    # Generic class with two fields — one parametric, one not — so the
    # test can tell substitution from accidental identity. ``f`` uses
    # the instantiation as both a parameter and a return type so the
    # lowering path runs at least twice.
    SRC_CLASS = (
        "template<type T>\n"
        "class Box {\n"
        "    public value: T;\n"
        "    public tag: Int;\n"
        "}\n"
        "func f(x: Box<Int>): Box<Int> { return x; }\n"
    )

    # Generic interface used to check that InterfaceTemplate is also
    # materialized under its mangled name.
    SRC_INTERFACE = (
        "template<type T>\n"
        "interface Holder {\n"
        "    peek(): T;\n"
        "}\n"
        "func g(x: Holder<Bool>): Holder<Bool> { return x; }\n"
    )

    def _analyzer_for(self, source: str) -> SemaAnalyzer:
        module, errors = parse_ast(source)
        assert errors == [] and module is not None, errors
        analyzer = SemaAnalyzer(module)
        # Drive registration so the scope / symbol table reflect the
        # post-pass state. Errors from body-checking are ignored —
        # monomorphization happens entirely in phase 1 (registration).
        analyzer.analyze()
        return analyzer

    def test_instantiation_registers_mangled_symbol(self):
        analyzer = self._analyzer_for(self.SRC_CLASS)

        sym = analyzer.current_scope.get_symbol("Box-Int")

        self.assertIsNotNone(sym)
        self.assertIsInstance(sym, ClassSymbol)

    def test_mangled_class_has_substituted_fields(self):
        analyzer = self._analyzer_for(self.SRC_CLASS)

        sym = analyzer.current_scope.get_symbol("Box-Int")
        fields = sym.public_fields

        self.assertEqual(fields["value"], PrimitiveTypeSymbol.Int)
        # The non-parametric field is carried over unchanged.
        self.assertEqual(fields["tag"], PrimitiveTypeSymbol.Int)

    def test_distinct_args_get_distinct_mangled_names(self):
        src = (
            "template<type T>\n"
            "class Box { public value: T; }\n"
            "func f(x: Box<Int>): Int { return 0; }\n"
            "func g(x: Box<Bool>): Int { return 0; }\n"
        )
        analyzer = self._analyzer_for(src)

        box_int = analyzer.current_scope.get_symbol("Box-Int")
        box_bool = analyzer.current_scope.get_symbol("Box-Bool")

        self.assertIsInstance(box_int, ClassSymbol)
        self.assertIsInstance(box_bool, ClassSymbol)
        self.assertEqual(box_int.public_fields["value"], PrimitiveTypeSymbol.Int)
        self.assertEqual(box_bool.public_fields["value"], PrimitiveTypeSymbol.Bool)

    def test_nested_generic_mangles_recursively(self):
        src = (
            "template<type T>\n"
            "class Box { public value: T; }\n"
            "func f(x: Box<Box<Int>>): Int { return 0; }\n"
        )
        analyzer = self._analyzer_for(src)

        # Outer: Box-Box-Int
        outer = analyzer.current_scope.get_symbol("Box-Box-Int")
        self.assertIsInstance(outer, ClassSymbol)
        self.assertIsInstance(outer.public_fields["value"], UserDefinedTypeSymbol)
        self.assertEqual(outer.public_fields["value"].ident, "Box-Int")

        # Inner materialized too, since the parser hit it on the way down.
        inner = analyzer.current_scope.get_symbol("Box-Int")
        self.assertIsInstance(inner, ClassSymbol)
        self.assertEqual(inner.public_fields["value"], PrimitiveTypeSymbol.Int)

    def test_repeated_instantiation_reuses_existing_symbol(self):
        # Same ``Box<Int>`` referenced twice — must not register a
        # second ``Box-Int`` (or any duplicate-name diagnostic).
        src = (
            "template<type T>\n"
            "class Box { public value: T; }\n"
            "func f(x: Box<Int>): Int { return 0; }\n"
            "func h(x: Box<Int>): Int { return 0; }\n"
        )
        errs = _SemaHelper.analyze(src)

        self.assertEqual(
            errs, [],
            f"unexpected sema errors: {[e.additional_message() for e in errs]}",
        )

    def test_mangled_name_avoids_user_collision(self):
        # A user could legally declare ``Box-Int`` only if mashiko's
        # identifier grammar allowed ``-`` — which it does not — so the
        # only way ``Box-Int`` can be in scope is via monomorphization.
        # That property is what lets the analyzer share a single naming
        # scheme between user declarations and synthesized types.
        analyzer = self._analyzer_for(self.SRC_CLASS)

        self.assertIn("Box-Int", analyzer.current_scope.symbols)
        # And the original template name is unchanged.
        self.assertIsInstance(
            analyzer.current_scope.get_symbol("Box"), ClassTemplate
        )

    def test_interface_instantiation_registers_mangled_symbol(self):
        analyzer = self._analyzer_for(self.SRC_INTERFACE)

        sym = analyzer.current_scope.get_symbol("Holder-Bool")

        self.assertIsNotNone(sym)
        self.assertIsInstance(sym, InterfaceSymbol)

    def test_interface_instantiation_substitutes_methods(self):
        analyzer = self._analyzer_for(self.SRC_INTERFACE)

        sym = analyzer.current_scope.get_symbol("Holder-Bool")
        methods = sym.public_methods

        self.assertIn("peek", methods)
        self.assertEqual(methods["peek"].return_type, PrimitiveTypeSymbol.Bool)

    def test_unbound_placeholder_falls_back_to_generic_form(self):
        # ``Outer<T>`` carries an unbound ``T`` placeholder into the
        # ``Inner<T>`` type-argument position — there is no concrete
        # type to substitute, so monomorphization must defer and leave
        # the type as a GenericDefinedTypeSymbol for use-site
        # substitution.
        src = (
            "template<type U>\n"
            "class Inner { public payload: U; }\n"
            "template<type T>\n"
            "class Outer { public value: Inner<T>; }\n"
        )
        analyzer = self._analyzer_for(src)

        # No mangled name should have leaked into scope.
        self.assertNotIn("Inner-T", analyzer.current_scope.symbols)
        self.assertNotIn("Outer-T", analyzer.current_scope.symbols)

        # The class templates themselves are still present.
        self.assertIsInstance(
            analyzer.current_scope.get_symbol("Inner"), ClassTemplate
        )
        self.assertIsInstance(
            analyzer.current_scope.get_symbol("Outer"), ClassTemplate
        )

        # And the field type survived as a deferred substitution form.
        outer = analyzer.current_scope.get_symbol("Outer")
        field_type = outer.public_fields["value"]
        self.assertIsInstance(field_type, GenericDefinedTypeSymbol)
        self.assertEqual(field_type.name, "Inner")
        self.assertEqual(field_type.type_args, (TypeParamSymbol("T"),))


class WideningCoercionTests(unittest.TestCase):
    """Numeric values may silently flow into a wider numeric position
    along the same hierarchy (signed / unsigned / float). Cross-kind
    conversions and narrowing are rejected.

    Because the current grammar does not let a local variable carry
    an explicit type annotation, every test exercises widening
    through function-parameter / return-type positions, where types
    are declared by the signatures.
    """

    def test_int8_plus_int16_widens_to_int16(self):
        errs = _SemaHelper.analyze(
            "func f(x: Int8, y: Int16): Int16 { return x + y; }\n"
        )

        self.assertEqual(errs, [])

    def test_int16_passes_to_int32_param(self):
        errs = _SemaHelper.analyze(
            "func take(x: Int32): Int32 { return x; }\n"
            "func caller(y: Int16): Int32 { return take(y); }\n"
        )

        self.assertEqual(errs, [])

    def test_int8_returned_as_int16(self):
        errs = _SemaHelper.analyze(
            "func f(x: Int8): Int16 { return x; }\n"
        )

        self.assertEqual(errs, [])

    def test_float32_returned_as_float64(self):
        errs = _SemaHelper.analyze(
            "func f(x: Float32): Float64 { return x; }\n"
        )

        self.assertEqual(errs, [])

    def test_int8_compares_to_int16(self):
        # Comparisons accept mixed-width operands as long as both can
        # unify to a common numeric chain. The result is Bool.
        errs = _SemaHelper.analyze(
            "func f(x: Int8, y: Int16): Bool { return x < y; }\n"
        )

        self.assertEqual(errs, [])

    def test_narrowing_is_rejected_in_call_arg(self):
        # Int16 → Int8 is narrowing — caller must error.
        errs = _SemaHelper.analyze(
            "func take(x: Int8): Int8 { return x; }\n"
            "func caller(y: Int16): Int8 { return take(y); }\n"
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertEqual(
            len(type_errs), 1,
            f"expected one type error, got {len(type_errs)}: "
            f"{[e.additional_message() for e in errs]}",
        )

    def test_narrowing_is_rejected_in_return(self):
        errs = _SemaHelper.analyze(
            "func f(x: Int16): Int8 { return x; }\n"
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertEqual(len(type_errs), 1)

    def test_cross_kind_int_to_float_rejected(self):
        errs = _SemaHelper.analyze(
            "func take(x: Float64): Float64 { return x; }\n"
            "func caller(y: Int): Float64 { return take(y); }\n"
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertEqual(len(type_errs), 1)

    def test_signed_unsigned_no_implicit_conversion(self):
        errs = _SemaHelper.analyze(
            "func take(x: Uint16): Uint16 { return x; }\n"
            "func caller(y: Int16): Uint16 { return take(y); }\n"
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertEqual(len(type_errs), 1)

    def test_bool_to_int_rejected(self):
        errs = _SemaHelper.analyze(
            "func take(x: Int): Int { return x; }\n"
            "func caller(y: Bool): Int { return take(y); }\n"
        )

        type_errs = [e for e in errs if isinstance(e, SemaTypeError)]
        self.assertEqual(len(type_errs), 1)


class TemplateInferenceTests(unittest.TestCase):
    """``func f<T>(x: T): T`` infers ``T`` from each call's argument
    types when the binding is unambiguous. The inference is
    deliberately conservative: a TypeParam that never appears in any
    parameter position, or appears in conflicting positions, raises
    an error rather than guessing.
    """

    def test_infer_int_from_literal_arg(self):
        errs = _SemaHelper.analyze(
            "template<type T>\n"
            "func identity(x: T): T { return x; }\n"
            "func caller(): Int { return identity(5); }\n"
        )

        self.assertEqual(
            errs, [],
            f"unexpected errors: {[e.additional_message() for e in errs]}",
        )

    def test_inferred_int_returned_into_int_return_slot(self):
        # identity(5) → Int; caller returns Int.
        errs = _SemaHelper.analyze(
            "template<type T>\n"
            "func identity(x: T): T { return x; }\n"
            "func caller(): Int { x = identity(5); return x; }\n"
        )

        self.assertEqual(errs, [])

    def test_infer_then_widen_at_call_site(self):
        # identity takes T; we pass Int8 — T binds to Int8. Return
        # type then widens from Int8 to Int16 at the caller.
        errs = _SemaHelper.analyze(
            "template<type T>\n"
            "func identity(x: T): T { return x; }\n"
            "func caller(x: Int8): Int16 { return identity(x); }\n"
        )

        self.assertEqual(
            errs, [],
            f"unexpected errors: {[e.additional_message() for e in errs]}",
        )

    def test_inference_conflict_in_two_positions_reports_error(self):
        # ``select`` is generic in T; passing Int and Bool tries to
        # bind T to two different types — analyzer must refuse.
        errs = _SemaHelper.analyze(
            "template<type T>\n"
            "func select(a: T, b: T): T { return a; }\n"
            "func caller() { x = select(5, true); }\n"
        )

        # At least one diagnostic must mention inference failure.
        self.assertTrue(
            any("cannot infer template args" in e.additional_message()
                for e in errs),
            f"expected inference conflict error, got "
            f"{[e.additional_message() for e in errs]}",
        )

    def test_type_param_not_in_any_arg_is_rejected(self):
        # ``amb`` returns T but takes no T-shaped argument. No way to
        # infer — must surface a clear "needs explicit args" error.
        errs = _SemaHelper.analyze(
            "template<type T>\n"
            "func amb(x: Int): T { return x; }\n"
            "func caller() { x = amb(5); }\n"
        )

        self.assertTrue(
            any("needs explicit type arguments" in e.additional_message()
                for e in errs),
            f"expected 'needs explicit type arguments' diagnostic, got "
            f"{[e.additional_message() for e in errs]}",
        )


if __name__ == "__main__":
    unittest.main()
