"""Top-level semantic analyzer driver.

The orchestrator opens a fresh module-level :class:`Scope`, registers
each top-level declaration, and then type-checks any function or
method bodies. Class members (fields, methods, constructors,
destructors, cloners) are recorded but their bodies are *not* yet
visited — the analyzer can introspect signatures to resolve
expressions like ``primes.len()`` even without executing methods.

Two mutable fields carry transient state while a function or method
body is being checked:

* :attr:`loop_depth` — incremented around ``while``/``for`` bodies
  so :func:`mashiko.sema.expressions.check_statement` can reject
  ``break``/``continue`` that escape a loop.
* :attr:`current_return_type` — pushed around function/method/constructor
  bodies so a bare ``return;`` knows whether it is legal.
"""

from typing import List, Optional, Tuple

from ..parser.syntax import (
    Block,
    ClassDecl,
    Constructor,
    Destructor,
    Cloner,
    Expression,
    FunctionDecl,
    InterfaceDecl,
    Method,
    Module,
)
from ..errors import TranslationError
from . import declarations, expressions
from .scope import Scope
from .symbols import (
    ClassSymbol,
    ClassTemplate,
    FunctionSymbol,
    FunctionTemplate,
    InterfaceTemplate,
    MethodSymbol,
    PrimitiveTypeSymbol,
    TemplateParamSymbol,
    TypeSymbol,
    UserDefinedTypeSymbol,
    VarSymbol,
)
from .templates import (
    pop_type_param_placeholders,
    push_type_param_placeholders,
)
from .type_lowering import type_to_symbol


class SemaAnalyzer:
    current_scope: Scope
    ast: Module
    errors: List[TranslationError]
    loop_depth: int
    current_return_type: Optional[TypeSymbol]
    registered_decls: List
    # Phase 0+: a stack of function/method symbols currently being
    # inlined at the call site. Empty in the normal pass; pushed when
    # an `inline` callee is being expanded (Phase 2), used as a
    # recursion guard.
    inline_stack: list
    # Phase 0+: per-callee summary of which parameter names were
    # destructed inside the body. Keyed by `id(callee_sym)` because
    # function names are not unique (overloads, methods). Consulted
    # by call-site logic in `_type_check_call` to propagate the
    # use-after-destruct mark to the caller's arguments (Phase 3).
    destructed_params: dict
    # Phase 0+: a stack of `set[str]`, one per nested lexical block.
    # Each set contains the names that have been destructed in that
    # block (locals + params, explicit or implicit). Pushed/popped by
    # :func:`mashiko.sema.expressions.check_block`. A `Name` is
    # reported as use-after-destruct if it appears in *any* set on
    # the stack (any enclosing block in the current function).
    scope_destructs: list
    # Phase 3: cumulative set of names destructed anywhere in the
    # current function body. Updated by :func:`check_block` as each
    # nested block is checked (its popped set is unioned in). Used
    # by :meth:`_check_in_function_scope` to compute the
    # destructed-params summary at the end of the function body
    # check — we can't just read ``scope_destructs`` at that point
    # because the body's own set has already been popped.
    function_destructs: set

    def __init__(self, ast: Module):
        self.ast = ast
        self.current_scope = Scope(None)
        self.errors = []
        self.loop_depth = 0
        self.current_return_type = None
        self.registered_decls = []
        self.inline_stack = []
        self.destructed_params = {}
        self.scope_destructs = []
        self.function_destructs = set()

    # ---- Driving pass ----------------------------------------------------

    def analyze(self) -> List[TranslationError]:
        """Register all declarations, then visit function/method bodies.

        The two phases are kept separate so :meth:`register_declarations`
        populates the symbol table before any body is visited — and so
        duplicate-name diagnostics from phase one are surfaced before
        phase two starts producing name/type errors that would
        otherwise cascade from "not declared" misdiagnoses.

        :attr:`registered_decls` (populated by
        :meth:`register_declarations`) is the iteration source for
        phase two, not the raw AST list — duplicates were already
        reported and skipped in phase one, and re-checking their
        bodies against the surviving declaration's signature would
        produce confusing false positives.

        Each declaration's body check is wrapped in a broad
        ``try/except`` so an internal failure in one declaration
        doesn't suppress diagnostics on the others. The pass collects
        as many errors as it can in a single sweep.
        """
        self.register_declarations()
        for decl in self.registered_decls:
            try:
                if isinstance(decl, FunctionDecl):
                    self.check_function(decl)
                elif isinstance(decl, ClassDecl):
                    self.check_class(decl)
            except Exception as exc:
                self.errors.append(
                    TranslationError(decl.span)
                )
        return self.errors

    # ---- Pass-throughs to declarations / expressions --------------------

    def register_declarations(self):
        return declarations.register_declarations(self)

    def register_function(self, f):
        return declarations.register_function(self, f)

    def register_class(self, c):
        return declarations.register_class(self, c)

    def register_interface(self, i):
        return declarations.register_interface(self, i)

    def check_block(self, ast: Block):
        return expressions.check_block(self, ast)

    def get_expression_type(self, expr: Expression) -> Optional[TypeSymbol]:
        return expressions.get_expression_type(self, expr)

    def get_type_public_methods(
        self, type: TypeSymbol
    ) -> Optional[dict[str, MethodSymbol]]:
        return expressions.get_type_public_methods(self, type)

    def get_type_public_fields(
        self, type: TypeSymbol
    ) -> Optional[dict[str, TypeSymbol]]:
        return expressions.get_type_public_fields(self, type)

    # ---- Function / method body checking --------------------------------

    def check_function(self, f: FunctionDecl):
        sym = self.current_scope.get_symbol(f.name)
        ret_type = self._symbol_return_type(sym)
        if ret_type is None:
            return
        type_params = (
            sym.template_params if isinstance(sym, FunctionTemplate) else ()
        )
        self._check_in_function_scope(
            type_params, ret_type, f.params, lambda: self.check_block(f.body),
            callee_sym=sym,
        )

    def check_class(self, c: ClassDecl):
        # ClassSymbol / ClassTemplate registered by register_class.
        # We still want to traverse member bodies so methods that
        # mention each other type-check.
        class_sym = self.current_scope.get_symbol(c.name)
        type_params = (
            class_sym.template_params if isinstance(class_sym, ClassTemplate) else ()
        )
        for member in c.body.members:
            if isinstance(member, Method):
                self.check_method(c, member, type_params)
            elif isinstance(member, Constructor):
                self.check_constructor(c, member, type_params)
            elif isinstance(member, (Destructor, Cloner)):
                # No params, no type-params beyond the class's.
                self._check_in_function_scope(
                    type_params, PrimitiveTypeSymbol.Void, (), member.body
                )

    def check_method(
        self, c: ClassDecl, m: Method, class_type_params: Tuple[TemplateParamSymbol, ...]
    ):
        ret = (
            type_to_symbol(m.return_type, self.current_scope)
            if m.return_type is not None
            else PrimitiveTypeSymbol.Void
        )
        if ret is None:
            return
        self_type = self._self_type_of(c, class_type_params)
        method_sym = self._lookup_method_symbol(c.name, m.name)
        self._check_in_function_scope(
            class_type_params, ret, m.params,
            lambda: self._bind_self_and_visit(c.name, self_type, m.body),
            callee_sym=method_sym,
        )

    def check_constructor(
        self, c: ClassDecl, m: Constructor, class_type_params: Tuple[TemplateParamSymbol, ...]
    ):
        self_type = self._self_type_of(c, class_type_params)
        method_sym = self._lookup_method_symbol(c.name, "constructor")
        self._check_in_function_scope(
            class_type_params, PrimitiveTypeSymbol.Void, m.params,
            lambda: self._bind_self_and_visit(c.name, self_type, m.body),
            callee_sym=method_sym,
        )

    def _self_type_of(
        self, c: ClassDecl, type_params: Tuple[TemplateParamSymbol, ...]
    ) -> Optional[TypeSymbol]:
        """Compute the type symbol that ``this`` should have inside a method.

        For a non-generic class this is ``UserDefinedTypeSymbol(c.name)``.
        For a generic class this is
        ``GenericDefinedTypeSymbol(c.name, type_args=...)`` — but each
        :class:`TemplateParamSymbol` has no type-arg source, so the
        call site cannot supply concrete type arguments. We return
        ``None`` and let ``MemberAccess`` resolution fail with a clear
        message, rather than fabricate an instantiation.
        """
        if not type_params:
            return UserDefinedTypeSymbol(c.name)
        # Generic classes' `this` is unrepresentable without instantiation.
        # Returning None leaves the analyser to surface a NameError on
        # the first use of `this`.
        return None

    def _bind_self_and_visit(
        self,
        class_name: str,
        self_type: Optional[TypeSymbol],
        body: Block,
    ) -> None:
        if self_type is not None:
            self.current_scope.push_symbol("this", VarSymbol(type=self_type))
        self.check_block(body)

    # ---- Helpers --------------------------------------------------------

    def _symbol_return_type(self, sym) -> Optional[TypeSymbol]:
        if isinstance(sym, FunctionSymbol):
            return sym.return_type
        if isinstance(sym, FunctionTemplate):
            return sym.return_type
        return None

    def _lookup_method_symbol(self, class_name: str, method_name: str):
        """Find the :class:`MethodSymbol` registered under
        ``(class_name, method_name)`` in the current scope.

        Used by :meth:`check_method` and :meth:`check_constructor` to
        pass the method's symbol through to
        :meth:`_check_in_function_scope` so the destructed-params
        summary can be keyed by the right ``id()``. Returns ``None``
        when the class is a :class:`ClassTemplate` (we don't
        instantiate it here, so the per-instantiation method symbol
        doesn't exist) or when the method genuinely isn't registered
        — both cases fall back to no summary, which is fine for the v1
        pass because templated methods aren't a primary use case.
        """
        sym = self.current_scope.get_symbol(class_name)
        if sym is None or not isinstance(sym, ClassSymbol):
            return None
        method = sym.public_methods.get(method_name)
        if method is None:
            method = sym.private_methods.get(method_name)
        return method

    def _check_in_function_scope(
        self,
        type_params: Tuple[TemplateParamSymbol, ...],
        ret_type: TypeSymbol,
        params,
        visit,
        callee_sym=None,
    ) -> None:
        """Open a fresh scope, install params + type-param placeholders,
        call ``visit``, then restore the previous scope/return-type.

        ``type_params`` are :class:`TemplateParamSymbol` instances
        collected from the surrounding template (function or class).
        They are pushed as placeholders into the *new* scope so the
        body sees ``T`` as :class:`TypeParamSymbol(T)` — matching the
        type already stored on the function/method's symbol. Without
        that, a generic signature like ``func identity(x: T): T``
        would store ``TypeParamSymbol(T)`` but the body's
        ``return x;`` would compare against ``UserDefinedTypeSymbol("T")``.

        ``callee_sym`` is the function/method symbol being checked
        (used to key the destructed-params summary in Phase 3). When
        ``None`` — for destructors, cloners, and other contexts where
        the body has no associated callable — no summary is recorded.
        """
        prev_return = self.current_return_type
        prev_scope = self.current_scope
        prev_destructs = self.scope_destructs
        prev_function_destructs = self.function_destructs

        self.current_return_type = ret_type
        self.current_scope = Scope(prev_scope)
        self.scope_destructs = []
        self.function_destructs = set()
        type_saved = push_type_param_placeholders(
            tuple(type_params), self.current_scope
        )
        try:
            for p in params:
                ptype = type_to_symbol(p.type, self.current_scope)
                if ptype is None:
                    continue
                self.current_scope.push_symbol(p.name, VarSymbol(type=ptype))
            visit()
        finally:
            if callee_sym is not None and params:
                param_names = {p.name for p in params}
                self.destructed_params[id(callee_sym)] = frozenset(
                    self.function_destructs & param_names
                )
            pop_type_param_placeholders(type_saved, self.current_scope)
            self.current_scope = prev_scope
            self.current_return_type = prev_return
            self.scope_destructs = prev_destructs
            self.function_destructs = prev_function_destructs
