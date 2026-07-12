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

    def __init__(self, ast: Module):
        self.ast = ast
        self.current_scope = Scope(None)
        self.errors = []
        self.loop_depth = 0
        self.current_return_type = None
        self.registered_decls = []

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
            type_params, ret_type, f.params, lambda: self.check_block(f.body)
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
        self._check_in_function_scope(
            class_type_params, ret, m.params,
            lambda: self._bind_self_and_visit(c.name, self_type, m.body),
        )

    def check_constructor(
        self, c: ClassDecl, m: Constructor, class_type_params: Tuple[TemplateParamSymbol, ...]
    ):
        self_type = self._self_type_of(c, class_type_params)
        self._check_in_function_scope(
            class_type_params, PrimitiveTypeSymbol.Void, m.params,
            lambda: self._bind_self_and_visit(c.name, self_type, m.body),
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

    def _check_in_function_scope(
        self,
        type_params: Tuple[TemplateParamSymbol, ...],
        ret_type: TypeSymbol,
        params,
        visit,
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
        """
        prev_return = self.current_return_type
        prev_scope = self.current_scope

        self.current_return_type = ret_type
        self.current_scope = Scope(prev_scope)
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
            pop_type_param_placeholders(type_saved, self.current_scope)
            self.current_scope = prev_scope
            self.current_return_type = prev_return
