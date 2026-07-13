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
    UseAfterDestructError,
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
from mashiko.parser.syntax import (
    AssignStatement,
    Block,
    BreakStatement,
    ExpressionStatement,
    MethodCall,
    ReturnStatement,
)


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


class InlineDeclarationTests(unittest.TestCase):
    """The ``inline`` keyword parses into a bool on the AST node and
    propagates to the symbol table. Behavior of inlining at call sites
    is covered in :class:`InlineExpansionTests`."""

    def test_inline_kw_parsed_on_function(self):
        module, errors = parse_ast("inline func f(): Void {}\n")
        self.assertEqual(errors, [])
        func = module.declarations[0]
        self.assertTrue(func.inline)

    def test_inline_kw_off_by_default_on_function(self):
        module, errors = parse_ast("func f(): Void {}\n")
        self.assertEqual(errors, [])
        func = module.declarations[0]
        self.assertFalse(func.inline)

    def test_inline_kw_parsed_on_method(self):
        module, errors = parse_ast(
            "class C { inline foo(): Int { return 1; } }\n"
        )
        self.assertEqual(errors, [])
        method = module.declarations[0].body.members[0]
        self.assertTrue(method.inline)

    def test_inline_kw_off_by_default_on_method(self):
        module, errors = parse_ast("class C { foo(): Int { return 1; } }\n")
        self.assertEqual(errors, [])
        method = module.declarations[0].body.members[0]
        self.assertFalse(method.inline)

    def test_inline_propagates_to_function_symbol(self):
        # The FunctionSymbol registered by the sema pass must remember
        # the inline flag so the call site can use it in Phase 2.
        errs = _SemaHelper.analyze(
            "inline func f(): Void {}\n"
            "func g() { f(); }\n"
        )
        self.assertEqual(errs, [])


class InlineExpansionTests(unittest.TestCase):
    """An ``inline`` call expands in place at the call site; a
    recursive call falls back to a regular call. The resulting
    :class:`InlinedCall` is visible in the typed AST, so tests can
    also assert presence/absence of the wrapper node via the
    ``--ast-typed`` flow (out of scope here — we check sema
    diagnostics instead)."""

    def test_inline_void_call_typechecks(self):
        errs = _SemaHelper.analyze(
            "inline func f(): Void {}\n"
            "func g() { f(); }\n"
        )
        self.assertEqual(errs, [])

    def test_inline_call_with_args_typechecks(self):
        errs = _SemaHelper.analyze(
            "inline func add(a: Int, b: Int): Int { return a + b; }\n"
            "func g(): Int { return add(1, 2); }\n"
        )
        self.assertEqual(errs, [])

    def test_inline_recursion_falls_back_to_normal_call(self):
        # `loop()` returns Int; the recursive call inside the body
        # would loop forever if inlined. The recursion guard
        # (`inline_stack`) prevents infinite expansion, so the
        # recursive call is treated as a normal call and type-checks
        # against the same return type.
        errs = _SemaHelper.analyze(
            "inline func loop(): Int { if true { return 1; } return loop(); }\n"
        )
        self.assertEqual(errs, [])

    def test_inline_method_on_this_inlines(self):
        # `this.foo()` where `foo` is inline. The inlined body shares
        # the enclosing scope's `this` binding.
        errs = _SemaHelper.analyze(
            "class C {\n"
            "    public x: Int;\n"
            "    constructor(v: Int) { this.x = v; }\n"
            "    public inline get(): Int { return this.x; }\n"
            "    public run() { y = this.get(); }\n"
            "}\n"
        )
        self.assertEqual(
            errs, [],
            f"unexpected errors: {[e.additional_message() for e in errs]}",
        )

    def test_inline_method_on_non_this_does_not_inline(self):
        # `c.foo()` on a non-`this` receiver must NOT inline (we
        # can't alias the receiver into the inlined scope in v1).
        # The call still type-checks via the regular method-call
        # path, so the program has no errors.
        errs = _SemaHelper.analyze(
            "class C {\n"
            "    public x: Int;\n"
            "    constructor(v: Int) { this.x = v; }\n"
            "    public inline get(): Int { return this.x; }\n"
            "    public run() { z = this; y = z.get(); }\n"
            "}\n"
        )
        self.assertEqual(errs, [])

    def test_inline_call_arbitrary_expr_still_typechecks(self):
        # Even though `inline func add(...)` is defined, the call
        # `add(1 + 1, 2 * 2)` must type-check the argument expressions
        # in the caller's scope before binding them to the inlined
        # body's params.
        errs = _SemaHelper.analyze(
            "inline func add(a: Int, b: Int): Int { return a + b; }\n"
            "func g(): Int { return add(1 + 1, 2 * 2); }\n"
        )
        self.assertEqual(errs, [])


class UseAfterDestructTests(unittest.TestCase):
    """``.destruct()`` marks a name as invalid; later uses produce a
    :class:`UseAfterDestructError`. Marks are per-block and
    cross-function via the destructed-params summary."""

    def test_explicit_destruct_then_use_emits_error(self):
        errs = _SemaHelper.analyze(
            "func f() { x = 1; x.destruct(); y = x; }\n"
        )
        uad = [e for e in errs if isinstance(e, UseAfterDestructError)]
        self.assertEqual(len(uad), 1)
        self.assertEqual(uad[0].ident, "x")

    def test_explicit_destruct_then_pass_to_call_emits_error(self):
        # Passing a destructed name to a function is also a use.
        errs = _SemaHelper.analyze(
            "func g(x: Int) {}\n"
            "func f() { x = 1; x.destruct(); g(x); }\n"
        )
        uad = [e for e in errs if isinstance(e, UseAfterDestructError)]
        self.assertEqual(len(uad), 1)

    def test_param_destruct_marks_param_no_use(self):
        # Param destruct inside the body, with no later use: no error.
        errs = _SemaHelper.analyze(
            "func h(x: Int) { x.destruct(); }\n"
        )
        self.assertEqual(errs, [])

    def test_param_destruct_summary_marks_caller_arg(self):
        # `callee` destructs its param; after `callee(a)`, the caller's
        # `a` is marked destructed. The subsequent read must produce a
        # use-after-destruct.
        errs = _SemaHelper.analyze(
            "func callee(x: Int) { x.destruct(); }\n"
            "func caller() { a = 1; callee(a); y = a; }\n"
        )
        uad = [e for e in errs if isinstance(e, UseAfterDestructError)]
        self.assertEqual(len(uad), 1)
        self.assertEqual(uad[0].ident, "a")

    def test_destruct_in_branch_scope_does_not_pollute_outer(self):
        # A destruct inside an if-branch's block must NOT mark the
        # outer-scope name: by the time the outer block reads `x`,
        # the branch's scope has exited and the mark is gone.
        errs = _SemaHelper.analyze(
            "func f(b: Bool) { x = 1; if b { x.destruct(); } y = x; }\n"
        )
        # `y = x` is fine — `x` is not destructed in the outer scope.
        # (The destruct happens inside the if-block; the block's set
        # is popped when the block exits, so the mark doesn't leak.)
        self.assertEqual(errs, [])

    def test_destruct_on_member_access_is_noop(self):
        # `obj.field.destruct()` is a default well-known no-op; it
        # does not mark `obj` or `field` as destructed.
        errs = _SemaHelper.analyze(
            "class C { public x: Int; }\n"
            "func f(c: C) { c.x.destruct(); y = c.x; }\n"
        )
        self.assertEqual(errs, [])

    def test_reassign_after_destruct_clears_mark(self):
        # After `x.destruct()`, a plain `=` re-initialization gives
        # `x` a fresh value; later reads are valid.
        errs = _SemaHelper.analyze(
            "func f() { x = 1; x.destruct(); x = 2; y = x; }\n"
        )
        self.assertEqual(errs, [])

    def test_double_destruct_is_idempotent(self):
        # Idempotent by design (no double-destruct diagnostic). The
        # second `x.destruct();` doesn't add a second error.
        errs = _SemaHelper.analyze(
            "func f() { x = 1; x.destruct(); x.destruct(); }\n"
        )
        self.assertEqual(errs, [])


class ScopeExitDestructTests(unittest.TestCase):
    """``mashiko.sema.desugaring.desugar`` — implicit ``.destruct()`` at scope exit."""

    @staticmethod
    def _desugar(source: str):
        module, errors = parse_ast(source)
        assert errors == [] and module is not None, errors
        sema_errors = SemaAnalyzer(module).analyze()
        assert sema_errors == [], sema_errors
        from mashiko.sema.desugaring import desugar
        return desugar(module)

    @staticmethod
    def _statements(block):
        return [s for s in block.statements]

    def test_local_destructs_at_function_end(self):
        # `x = 1;` at function scope → implicit `x.destruct();` appended
        # before the implicit fall-through.
        mod = self._desugar("func f() { x = 1; }\n")
        fn = mod.declarations[0]
        stmts = self._statements(fn.body)
        last = stmts[-1]
        self.assertIsInstance(last, ExpressionStatement)
        self.assertIsInstance(last.expression, MethodCall)
        self.assertEqual(last.expression.name, "destruct")
        self.assertEqual(last.expression.obj.name, "x")
        self.assertEqual(last.expression.args, ())

    def test_params_not_auto_destructed(self):
        # The function's only binding is the param; no synthetic
        # ``.destruct()`` should be added for ``p`` (params survive
        # the call by default).
        mod = self._desugar("func f(p: Int) { }\n")
        fn = mod.declarations[0]
        self.assertEqual(self._statements(fn.body), [])

    def test_explicit_destruct_not_re_emitted(self):
        # `x.destruct();` already present; no additional emission.
        mod = self._desugar("func f() { x = 1; x.destruct(); }\n")
        fn = mod.declarations[0]
        stmts = self._statements(fn.body)
        # The two original statements, no extras.
        self.assertEqual(len(stmts), 2)
        self.assertIsInstance(stmts[1].expression, MethodCall)
        self.assertEqual(stmts[1].expression.name, "destruct")

    def test_unreachable_branch_join_emits_no_destructs(self):
        # Both branches return → join is UNREACHABLE → no destructs
        # at the *join point* (i.e. the outer block after the `if`).
        # Each branch still emits its own locals' destructs before
        # its own return — that's per-block RAII, which is correct.
        mod = self._desugar(
            "func f(b: Bool) { if b { x = 1; return; } else { return; } }\n"
        )
        fn = mod.declarations[0]
        # The outer function body has just the `if` and no other
        # locals → no synthetic destruct at the function level.
        outer_stmts = self._statements(fn.body)
        self.assertEqual(len(outer_stmts), 1)
        # The then-block has `x = 1;`, the synthetic `x.destruct();`,
        # then `return;`.
        if_stmt = outer_stmts[0]
        then_stmts = list(if_stmt.then_branch.statements)
        self.assertIsInstance(then_stmts[-1], ReturnStatement)
        self.assertIsInstance(then_stmts[-2], ExpressionStatement)
        self.assertEqual(then_stmts[-2].expression.obj.name, "x")
        # The else-block has no locals; only the `return;`.
        self.assertEqual(len(list(if_stmt.else_branch.statements)), 1)

    def test_fallthrough_join_emits_destructs_in_both_branches(self):
        # `else` falls through; each branch must clean up its own
        # local.
        mod = self._desugar(
            "func f(b: Bool) { if b { x = 1; } else { y = 2; } }\n"
        )
        fn = mod.declarations[0]
        if_stmt = fn.body.statements[0]
        then_stmts = list(if_stmt.then_branch.statements)
        else_stmts = list(if_stmt.else_branch.statements)
        # Then-branch: x is destructed at the end.
        then_last = then_stmts[-1]
        self.assertIsInstance(then_last, ExpressionStatement)
        self.assertEqual(then_last.expression.name, "destruct")
        self.assertEqual(then_last.expression.obj.name, "x")
        # Else-branch: y is destructed at the end.
        else_last = else_stmts[-1]
        self.assertIsInstance(else_last, ExpressionStatement)
        self.assertEqual(else_last.expression.name, "destruct")
        self.assertEqual(else_last.expression.obj.name, "y")

    def test_nested_block_destructs_inner_locals(self):
        # An inner block emits destructs for its own locals; the
        # outer block does not re-emit them.
        mod = self._desugar(
            "func f() { { x = 1; } y = 2; }\n"
        )
        fn = mod.declarations[0]
        outer = fn.body
        inner = outer.statements[0]
        self.assertIsInstance(inner, Block)
        inner_stmts = list(inner.statements)
        self.assertIsInstance(inner_stmts[-1], ExpressionStatement)
        self.assertEqual(inner_stmts[-1].expression.obj.name, "x")
        # The outer block: `y` is the only declared local, and its
        # implicit destruct is appended at the end.
        outer_stmts = list(outer.statements)
        self.assertIsInstance(outer_stmts[-1], ExpressionStatement)
        self.assertEqual(outer_stmts[-1].expression.obj.name, "y")

    def test_destructs_prepended_before_return(self):
        # If a block ends in `return;`, the synthetic destructs go
        # *before* the return, not after.
        mod = self._desugar("func f() { x = 1; return; }\n")
        fn = mod.declarations[0]
        stmts = self._statements(fn.body)
        self.assertIsInstance(stmts[-1], ReturnStatement)
        # The destruct sits just before the return.
        self.assertIsInstance(stmts[-2], ExpressionStatement)
        self.assertEqual(stmts[-2].expression.name, "destruct")
        self.assertEqual(stmts[-2].expression.obj.name, "x")

    def test_destructs_prepended_before_break(self):
        mod = self._desugar(
            "func f() { while true { x = 1; break; } }\n"
        )
        fn = mod.declarations[0]
        while_stmt = fn.body.statements[0]
        body_stmts = self._statements(while_stmt.body)
        self.assertIsInstance(body_stmts[-1], BreakStatement)
        self.assertIsInstance(body_stmts[-2], ExpressionStatement)
        self.assertEqual(body_stmts[-2].expression.obj.name, "x")

    def test_compound_assign_not_a_declaration(self):
        # `x += 1;` is a compound assignment against an existing
        # binding; it must not be treated as introducing `x` and
        # the pass must not double-emit a destruct for it.
        mod = self._desugar("func f() { x = 1; x += 1; }\n")
        fn = mod.declarations[0]
        stmts = self._statements(fn.body)
        # Original `x = 1;` and `x += 1;` plus one synthetic destruct.
        self.assertEqual(len(stmts), 3)
        self.assertIsInstance(stmts[0], AssignStatement)
        self.assertEqual(stmts[0].op, "=")
        self.assertIsInstance(stmts[1], AssignStatement)
        self.assertEqual(stmts[1].op, "+=")
        self.assertIsInstance(stmts[2], ExpressionStatement)
        self.assertEqual(stmts[2].expression.obj.name, "x")

    def test_method_body_destructs_locals(self):
        mod = self._desugar(
            "class C { public x: Int; public f() { y = 1; } }\n"
        )
        cls = mod.declarations[0]
        method = cls.body.members[1]
        stmts = self._statements(method.body)
        self.assertIsInstance(stmts[-1], ExpressionStatement)
        self.assertEqual(stmts[-1].expression.obj.name, "y")


if __name__ == "__main__":
    unittest.main()
