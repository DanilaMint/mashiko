"""Statement and expression type checking.

Two entry points:

* :func:`check_block` — type-check a sequence of statements in a fresh
  lexical scope. Recursively descends into nested blocks, ``if``,
  ``while``, ``for`` and ``return`` statements.
* :func:`get_expression_type` — return the :class:`TypeSymbol` of a
  single expression, or ``None`` if it could not be determined. When
  the result is ``None`` the function has already pushed a
  :class:`TypeError` or :class:`NameError` onto ``analyzer.errors``
  describing why, so callers do not need to re-report.

The analyzer carries small mutable fields (:attr:`loop_depth`,
:attr:`current_return_type`) that the surrounding
:class:`~mashiko.sema.core.SemaAnalyzer` orchestrator is responsible
for pushing and popping around function/method bodies. The helpers
here only read them.
"""

from typing import Dict, Optional

from .errors import NameError, TypeError, UseAfterDestructError
from .coercions import common_numeric_type, types_compatible
from .op_method import binary_op_method, unary_op_method
from ..parser.syntax import (
    ArrayLiteral,
    AssignStatement,
    AssignTarget,
    BinaryOp,
    Block,
    BoolLiteral,
    BreakStatement,
    CharLiteral,
    Conditional,
    ConstParam,
    ContinueStatement,
    Expression,
    ExpressionStatement as ExpressionStatementType,
    FloatLiteral,
    ForStatement,
    FunctionCall,
    IfStatement,
    Indexing,
    InlinedCall,
    IntLiteral,
    IterationVariable,
    MaybeUnwrap,
    MemberAccess,
    MemberLValue,
    MethodCall,
    Name,
    ParenExpr,
    ReturnStatement,
    Statement,
    StringLiteral,
    UnaryOp,
    WhileStatement,
)
from .scope import Scope
from .symbols import (
    ClassSymbol,
    ClassTemplate,
    FunctionSymbol,
    FunctionTemplate,
    GenericDefinedTypeSymbol,
    InterfaceTemplate,
    MaybeTypeSymbol,
    MethodSymbol,
    PrimitiveTypeSymbol,
    TypeParamSymbol,
    TypeSymbol,
    UserDefinedTypeSymbol,
    VarSymbol,
    substitute_type,
)
from .templates import infer_template_args, substitute_type, type_param_mapping


# ---------------------------------------------------------------------------
# Block / statement checking
# ---------------------------------------------------------------------------


def check_block(analyzer, ast: Block):
    """Open a new lexical scope around ``ast`` and type-check each statement.

    A new :class:`Scope` is pushed for the block's bindings. A new
    empty set is also pushed onto ``analyzer.scope_destructs`` so
    destruct tracking (Phase 3) is per-block: names destructed
    inside the block are added to this set, and the destruct-mark
    disappears when the block exits (the popped set is unioned into
    ``analyzer.function_destructs`` for the cross-function summary,
    but no longer blocks later reads in the outer scope).
    """
    parent = analyzer.current_scope
    analyzer.current_scope = Scope(parent)
    analyzer.scope_destructs.append(set())
    try:
        for stmt in ast.statements:
            check_statement(analyzer, stmt)
    finally:
        popped = analyzer.scope_destructs.pop()
        analyzer.function_destructs |= popped
        analyzer.current_scope = parent


def _name_is_destructed(analyzer, name: str) -> bool:
    """True if ``name`` has been destructed in any enclosing block.

    Walks the ``scope_destructs`` stack (innermost block first). A
    mark in an outer block also counts — a name in a parent block is
    destructed at the parent's scope exit, and any use before that
    exit in a nested block is still a use-after-destruct.
    """
    for s in reversed(analyzer.scope_destructs):
        if name in s:
            return True
    return False


def _check_not_destructed(analyzer, expr) -> None:
    """Emit :class:`UseAfterDestructError` if ``expr`` names a
    destructed local/param.

    Only :class:`Name` references are tracked; ``MemberAccess``,
    ``Indexing``, etc. are never destructed in the v1 model
    (only locals and params can be the LHS of ``.destruct()``).
    The function pushes the diagnostic onto ``analyzer.errors`` and
    does not return a value — the caller has its own return path.
    """
    if not isinstance(expr, Name):
        return
    if _name_is_destructed(analyzer, expr.name):
        analyzer.errors.append(UseAfterDestructError(expr.span, expr.name))


def check_statement(analyzer, stmt: Statement):
    if isinstance(stmt, AssignStatement):
        _check_assign(analyzer, stmt.target, stmt.op, stmt.value)
        return

    if isinstance(stmt, ExpressionStatementType):
        get_expression_type(analyzer, stmt.expression)
        return

    if isinstance(stmt, IfStatement):
        cond_type = get_expression_type(analyzer, stmt.condition)
        if cond_type != PrimitiveTypeSymbol.Bool:
            analyzer.errors.append(
                TypeError(stmt.condition.span, PrimitiveTypeSymbol.Bool, cond_type,
                          "if-condition must be Bool")
            )
        check_statement(analyzer, stmt.then_branch)
        if stmt.else_branch is not None:
            check_statement(analyzer, stmt.else_branch)
        return

    if isinstance(stmt, WhileStatement):
        cond_type = get_expression_type(analyzer, stmt.condition)
        if cond_type != PrimitiveTypeSymbol.Bool:
            analyzer.errors.append(
                TypeError(stmt.condition.span, PrimitiveTypeSymbol.Bool, cond_type,
                          "while-condition must be Bool")
            )
        analyzer.loop_depth += 1
        try:
            check_statement(analyzer, stmt.body)
        finally:
            analyzer.loop_depth -= 1
        return

    if isinstance(stmt, ForStatement):
        iter_type = get_expression_type(analyzer, stmt.iterable)
        if iter_type is None:
            analyzer.loop_depth += 1
            try:
                check_statement(analyzer, stmt.body)
            finally:
                analyzer.loop_depth -= 1
            return

        analyzer.loop_depth += 1
        parent = analyzer.current_scope
        analyzer.current_scope = Scope(parent)
        try:
            _bind_for_variable(analyzer, stmt.variable, iter_type)
            check_statement(analyzer, stmt.body)
        finally:
            analyzer.current_scope = parent
            analyzer.loop_depth -= 1
        return

    if isinstance(stmt, BreakStatement):
        if analyzer.loop_depth == 0:
            analyzer.errors.append(
                TypeError(stmt.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                          "`break` outside a loop")
            )
        return

    if isinstance(stmt, ContinueStatement):
        if analyzer.loop_depth == 0:
            analyzer.errors.append(
                TypeError(stmt.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                          "`continue` outside a loop")
            )
        return

    if isinstance(stmt, ReturnStatement):
        expected = analyzer.current_return_type
        if stmt.value is None:
            if expected != PrimitiveTypeSymbol.Void:
                analyzer.errors.append(
                    TypeError(stmt.span, expected, PrimitiveTypeSymbol.Void,
                              "return without value from non-Void function")
                )
            return
        got = get_expression_type(analyzer, stmt.value)
        if expected is not None and got is not None and not types_compatible(got, expected):
            analyzer.errors.append(
                TypeError(stmt.value.span, expected, got, "return type mismatch")
            )
        return

    if isinstance(stmt, Block):
        check_block(analyzer, stmt)
        return


def _bind_for_variable(
    analyzer, var: IterationVariable, iter_type: TypeSymbol
) -> None:
    """Bind the iteration variable(s) of a ``for`` to the element type of ``iter``.

    A :class:`~mashiko.parser.syntax.ForStatement` over an
    ``Array<T>`` binds a single ``Name`` to ``T``. Without a richer
    "iterator" interface the iterable must already be a container with
    a known element type — for non-container iterables we silently
    skip the binding and let later checks (a use of the variable)
    surface an error.
    """
    elem_type = _element_type_of(iter_type, analyzer)
    if elem_type is None:
        return
    match var:
        case Name(name=n):
            analyzer.current_scope.push_symbol(n, VarSymbol(type=elem_type))
        case _:
            # Tuple destructuring: not yet implemented.
            pass


def _element_type_of(t: TypeSymbol, analyzer) -> Optional[TypeSymbol]:
    """Return the element type of ``t`` if it looks like an ``Array<T>``."""
    if not isinstance(t, GenericDefinedTypeSymbol):
        return None
    if t.name != "Array":
        return None
    if not t.type_args:
        return None
    return t.type_args[0]


def _check_assign(
    analyzer, target: AssignTarget, op: str, value: Expression
) -> None:
    """Type-check an assignment of ``value`` to ``target`` under ``op``.

    Plain ``=`` is treated as a declaration when ``target`` introduces a
    new name in the current scope. Compound assignment (``+=`` etc.)
    is rewritten as ``target = target <op> value`` and validates the
    left-hand side against its previously-declared type.
    """
    target_type, name_node = _assign_target_type(analyzer, target)

    if op == "=":
        value_type = get_expression_type(analyzer, value)
        if value_type is None:
            return
        if target_type is None and isinstance(target, Name):
            analyzer.current_scope.push_symbol(target.name, VarSymbol(type=value_type))
            # A fresh binding is a new object: clear any prior
            # use-after-destruct mark for this name. The mark may
            # live in any set pushed for a nested block; drop it
            # from each of them and from the cumulative set.
            for s in analyzer.scope_destructs:
                s.discard(target.name)
            analyzer.function_destructs.discard(target.name)
            return
        if not types_compatible(value_type, target_type):
            analyzer.errors.append(
                TypeError(value.span, target_type or value_type, value_type,
                          "assignment type mismatch")
            )
            return
        # Existing binding with matching type: a plain `=` rebinds
        # the name to a fresh value, so clear any prior destruct
        # mark the same way a declaration would.
        if isinstance(target, Name):
            for s in analyzer.scope_destructs:
                s.discard(target.name)
            analyzer.function_destructs.discard(target.name)
        return

    # Compound assignment. target must already be declared.
    if target_type is None:
        analyzer.errors.append(
            TypeError(target.span, PrimitiveTypeSymbol.Int, PrimitiveTypeSymbol.Void,
                      f"`{op}` requires an existing binding")
        )
        return

    binop_kind = _compound_op_kind(op)
    if binop_kind is None:
        analyzer.errors.append(
            TypeError(target.span, target_type, target_type,
                      f"unknown compound assignment operator {op!r}")
        )
        return

    value_type = get_expression_type(analyzer, value)
    if value_type is None:
        return

    # Try primitive built-ins first — `Int += Int` works because
    # `_primitive_binary_result` accepts same-shape numeric operands,
    # even though `Int` itself carries no public methods. This is
    # what `examples/find_super_prime.msk` relies on for `acc += 1`.
    prim = _primitive_binary_result(binop_kind, target_type, value_type)
    if prim is _PRIM_OK:
        return  # valid; same-type arithmetic / Bool comparison
    if prim is _PRIM_MISMATCH:
        analyzer.errors.append(
            TypeError(value.span, target_type, value_type,
                      f"`{binop_kind.value}` requires compatible right-hand side")
        )
        return
    if prim is not None:
        return  # some concrete primitive result type — also fine

    methods = get_type_public_methods(analyzer, target_type)
    if methods is None:
        analyzer.errors.append(
            TypeError(value.span, target_type, target_type,
                      f"`{binop_kind.value}` not defined for {target_type}")
        )
        return
    method = methods.get(binary_op_method(binop_kind))
    if method is None:
        analyzer.errors.append(
            TypeError(value.span, target_type, target_type,
                      f"`{binop_kind.value}` not defined for {target_type}")
        )
        return
    if not method.params or method.params[0] != value_type:
        analyzer.errors.append(
            TypeError(value.span, method.params[0], value_type,
                      f"`{binop_kind.value}` argument type mismatch")
        )


def _compound_op_kind(op: str):
    """Map a compound assignment operator (e.g. ``+=``) to its
    :class:`BinaryOpKind`. Returns ``None`` for unknown operators.
    """
    from ..parser.syntax import BinaryOpKind

    return {
        "+=": BinaryOpKind.ADD,
        "-=": BinaryOpKind.SUBTRACT,
        "*=": BinaryOpKind.MULTIPLY,
        "/=": BinaryOpKind.DIVIDE,
        "%=": BinaryOpKind.MODULO,
    }.get(op)


def _assign_target_type(
    analyzer, target: AssignTarget
) -> tuple[Optional[TypeSymbol], Optional[Name]]:
    """Return the declared :class:`TypeSymbol` of an assignment target.

    For a plain :class:`Name` the symbol table is consulted. For a
    :class:`MemberLValue` (e.g. ``this.x = ...``) the receiver's
    type is resolved and the member is looked up in the receiver's
    public field table. For an indexed/tuple access we return
    ``(None, None)`` — those l-values can only appear in plain
    assignment, never as a declaration site.
    """
    if isinstance(target, Name):
        sym = analyzer.current_scope.get_symbol(target.name)
        if sym is None:
            return None, target
        if isinstance(sym, VarSymbol):
            return sym.type, target
        if isinstance(sym, FunctionSymbol):
            # functions are not assignable
            return sym.return_type, target  # best-effort, may produce a confusing error
        return None, target
    if isinstance(target, MemberLValue):
        obj_type = get_expression_type(analyzer, target.obj)
        if obj_type is None:
            return None, None
        fields = get_type_public_fields(analyzer, obj_type)
        if fields is None:
            return None, None
        return fields.get(target.name), None
    return None, None


# ---------------------------------------------------------------------------
# Expression typing
# ---------------------------------------------------------------------------


def get_expression_type(analyzer, expr: Expression) -> Optional[TypeSymbol]:
    match expr:
        case IntLiteral():
            return PrimitiveTypeSymbol.Int

        case FloatLiteral():
            return PrimitiveTypeSymbol.Float64

        case StringLiteral():
            return UserDefinedTypeSymbol("String")

        case CharLiteral():
            return PrimitiveTypeSymbol.Char32

        case BoolLiteral():
            return PrimitiveTypeSymbol.Bool

        case ParenExpr():
            return get_expression_type(analyzer, expr.expr)

        case Name():
            return _resolve_name(analyzer, expr)

        case FunctionCall():
            return _type_check_call(analyzer, expr)

        case MethodCall():
            return _type_check_method_call(analyzer, expr)

        case Indexing():
            return _type_check_indexing(analyzer, expr)

        case MaybeUnwrap(expr=inner):
            inner_type = get_expression_type(analyzer, inner)
            if isinstance(inner_type, MaybeTypeSymbol):
                return inner_type.content
            return inner_type

        case MemberAccess():
            return _type_check_member_access(analyzer, expr)

        case BinaryOp():
            return _type_check_binary(analyzer, expr)

        case UnaryOp():
            return _type_check_unary(analyzer, expr)

        case Conditional():
            return _type_check_conditional(analyzer, expr)

        case ArrayLiteral():
            return _type_check_array_literal(analyzer, expr)

        case InlinedCall():
            return _type_check_inlined_call(analyzer, expr)

        case _:
            return None


def _resolve_name(analyzer, expr: Name) -> Optional[TypeSymbol]:
    _check_not_destructed(analyzer, expr)
    sym = analyzer.current_scope.get_symbol(expr.name)
    if sym is None:
        analyzer.errors.append(NameError(expr.span, expr.name))
        return None
    if isinstance(sym, FunctionSymbol):
        return sym.return_type
    if isinstance(sym, VarSymbol):
        return sym.type
    if isinstance(sym, FunctionTemplate):
        # A generic function reference without explicit type arguments has
        # no fixed return type at this AST position. Defer until call sites
        # provide context.
        analyzer.errors.append(
            TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"generic function `{expr.name}` needs explicit type arguments")
        )
        return None
    if isinstance(sym, (ClassSymbol, ClassTemplate, InterfaceSymbol, InterfaceTemplate)):
        # Types used in value position (e.g. ``DynArray()`` as a
        # constructor-style call). The actual receiver check happens in
        # FunctionCall's symbol lookup, so just return None here.
        return None
    return None


def _type_check_call(analyzer, expr: FunctionCall) -> Optional[TypeSymbol]:
    sym = analyzer.current_scope.get_symbol(expr.name)
    if sym is None:
        analyzer.errors.append(NameError(expr.span, expr.name))
        return None

    # Phase 2: try to inline-expand before doing the normal call
    # checks. If the symbol is inline and not recursing, this re-checks
    # the body in a fresh scope and returns an `InlinedCall`. The
    # recursion guard in `_try_inline_expand_call` ensures mutual
    # recursion falls back to the normal call path.
    inlined = _try_inline_expand_call(analyzer, expr)
    if inlined is not None:
        return inlined.return_type

    if isinstance(sym, FunctionSymbol):
        _check_arity(analyzer, expr.span, len(sym.params), len(expr.args), expr.name)
        for arg, param_type in zip(expr.args, sym.params):
            at = get_expression_type(analyzer, arg)
            if at is None:
                continue
            if not types_compatible(at, param_type):
                analyzer.errors.append(
                    TypeError(arg.span, param_type, at,
                              f"argument of `{expr.name}` has wrong type")
                )
        # Phase 3: cross-function use-after-destruct. If the callee
        # destructed any of its params, the caller's argument at the
        # corresponding position is marked destructed in the caller's
        # scope. Only :class:`Name` args are marked — composite
        # expressions are not tracked.
        _propagate_callee_destructs(
            analyzer, sym, sym.ast_params, expr.args
        )
        return sym.return_type

    if isinstance(sym, FunctionTemplate):
        # Try to infer template type-params from the arg types. Const
        # params stay un-inferred; if any are required (no default)
        # the call falls through to the explicit-args error.
        arg_types: list[Optional[TypeSymbol]] = [
            get_expression_type(analyzer, a) for a in expr.args
        ]
        mapping = infer_template_args(
            sym.template_params, tuple(sym.params), tuple(arg_types)
        )
        if mapping is None:
            analyzer.errors.append(
                TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                          f"cannot infer template args for `{expr.name}` from call")
            )
            return None
        # A type-position template param that never appears in any
        # parameter cannot be inferred — refuse to guess.
        type_param_names = {
            tp.name for tp in sym.template_params
            if isinstance(tp, TypeParamSymbol)
        }
        if not type_param_names.issubset(mapping.keys()):
            analyzer.errors.append(
                TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                          f"generic call `{expr.name}` needs explicit type arguments")
            )
            return None
        # Bounds check: every inferred type-arg must satisfy its
        # declared interface constraints.
        from .type_lowering import type_satisfies_interfaces

        for tp in sym.template_params:
            if not isinstance(tp, TypeParamSymbol) or not tp.interfaces:
                continue
            inferred = mapping[tp.name]
            if not type_satisfies_interfaces(inferred, tp.interfaces, analyzer.current_scope):
                analyzer.errors.append(
                    TypeError(expr.span, tp, inferred,
                              f"type argument for `{expr.name}` does not satisfy bound "
                              f"{list(tp.interfaces)}")
                )
                return None
        _check_arity(analyzer, expr.span, len(sym.params), len(expr.args), expr.name)
        substituted_params = [substitute_type(p, mapping) for p in sym.params]
        for arg, param_type in zip(expr.args, substituted_params):
            at = get_expression_type(analyzer, arg)
            if at is None:
                continue
            if not types_compatible(at, param_type):
                analyzer.errors.append(
                    TypeError(arg.span, param_type, at,
                              f"argument of `{expr.name}` has wrong type")
                )
        return substitute_type(sym.return_type, mapping)

    if isinstance(sym, (ClassSymbol, ClassTemplate)):
        # Treated as a 0-ary constructor; arity check below.
        if expr.args:
            analyzer.errors.append(
                TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                          f"`{expr.name}` is a type, not a callable")
            )
            return None
        return _materialize_from_class(sym)

    analyzer.errors.append(
        TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                  f"`{expr.name}` is not callable")
    )
    return None


def _materialize_from_class(sym) -> TypeSymbol:
    """Return the value-level type produced by ``sym`` used as a constructor."""
    if isinstance(sym, ClassSymbol):
        return UserDefinedTypeSymbol(sym.__class__.__name__)  # placeholder
    if isinstance(sym, ClassTemplate):
        # No instantiation site => return a generic with no args. The
        # caller's expected type is rarely this, so we surface a soft
        # signal by leaving the type opaque.
        return GenericDefinedTypeSymbol(name="?", type_args=())
    return PrimitiveTypeSymbol.Void


def _check_arity(analyzer, span, expected: int, got: int, name: str) -> None:
    if expected != got:
        analyzer.errors.append(
            TypeError(span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"`{name}` expects {expected} args, got {got}")
        )


def _propagate_callee_destructs(
    analyzer, callee_sym, callee_ast_params, call_args
) -> None:
    """Mark the caller's args destructed if the callee destructed
    the corresponding param.

    Reads ``analyzer.destructed_params[id(callee_sym)]`` — the
    summary recorded by :meth:`_check_in_function_scope` after the
    callee's body was checked. For each param name in that summary
    at position ``i``, if ``call_args[i]`` is a :class:`Name`, that
    name is added to the *current* block's destruct set in the
    caller's :attr:`scope_destructs` stack.

    For a non-Name arg (``f(g())`` where ``g()`` returns a fresh
    value) we don't mark anything — the result is a temporary and
    has no destruct lifetime to track.
    """
    summary = analyzer.destructed_params.get(id(callee_sym))
    if not summary:
        return
    for i, arg in enumerate(call_args):
        if i >= len(callee_ast_params):
            break
        param_name = callee_ast_params[i].name
        if param_name in summary and isinstance(arg, Name):
            analyzer.scope_destructs[-1].add(arg.name)


def _type_check_method_call(
    analyzer, expr: MethodCall
) -> Optional[TypeSymbol]:
    # Phase 3: ``.destruct()`` is a well-known method that every
    # type has by default. Special-case it before the regular
    # method-resolution path so we don't require the type to actually
    # declare a method with that name. The call takes no arguments
    # and returns Void; calling it on a local/param (a :class:`Name`)
    # adds the name to the current block's destruct set so any
    # later use produces a :class:`UseAfterDestructError`. On a
    # non-:class:`Name` receiver (e.g. ``obj.field.destruct()``) the
    # call is a default no-op — the mark only tracks locals/params.
    if expr.name == "destruct":
        _check_arity(analyzer, expr.span, 0, len(expr.args), "destruct")
        if isinstance(expr.obj, Name):
            analyzer.scope_destructs[-1].add(expr.obj.name)
        return PrimitiveTypeSymbol.Void

    obj_type = get_expression_type(analyzer, expr.obj)
    if obj_type is None:
        return None
    methods = get_type_public_methods(analyzer, obj_type)
    if methods is None:
        analyzer.errors.append(
            TypeError(expr.obj.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"no public methods on {obj_type}")
        )
        return None
    method = methods.get(expr.name)

    # Phase 2: try to inline-expand the method call. Gated to
    # `this.foo()` so the inlined body shares the enclosing scope's
    # `this` binding. The recursion guard in
    # `_try_inline_expand_method_call` ensures mutual recursion falls
    # back to the normal call path.
    inlined = _try_inline_expand_method_call(analyzer, expr, method)
    if inlined is not None:
        return inlined.return_type
    if method is None:
        analyzer.errors.append(
            TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"`{expr.name}` is not a method of {obj_type}")
        )
        return None
    _check_arity(analyzer, expr.span, len(method.params), len(expr.args), expr.name)
    for arg, param_type in zip(expr.args, method.params):
        at = get_expression_type(analyzer, arg)
        if at is None:
            continue
        if not types_compatible(at, param_type):
            analyzer.errors.append(
                TypeError(arg.span, param_type, at,
                          f"argument of `{expr.name}` has wrong type")
            )
    # Phase 3: cross-function use-after-destruct propagation for
    # methods. Only fires for non-inline methods (inline methods
    # already do their destruct work in the inlined body, where the
    # param bindings are local to the inlined scope).
    if method is not None and not method.inline:
        _propagate_callee_destructs(
            analyzer, method, method.ast_params, expr.args
        )
    return method.return_type


def _type_check_indexing(analyzer, expr: Indexing) -> Optional[TypeSymbol]:
    obj_type = get_expression_type(analyzer, expr.obj)
    if obj_type is None:
        return None
    methods = get_type_public_methods(analyzer, obj_type)
    if methods is None:
        return None
    at = methods.get("at")
    if at is not None:
        idx_type = get_expression_type(analyzer, expr.index)
        if (
            idx_type is not None
            and at.params
            and not types_compatible(idx_type, at.params[0])
        ):
            analyzer.errors.append(
                TypeError(expr.index.span, at.params[0], idx_type,
                          "index type mismatch")
            )
        return at.return_type

    get_ = methods.get("get")
    if get_ is not None:
        idx_type = get_expression_type(analyzer, expr.index)
        if (
            idx_type is not None
            and get_.params
            and not types_compatible(idx_type, get_.params[0])
        ):
            analyzer.errors.append(
                TypeError(expr.index.span, get_.params[0], idx_type,
                          "index type mismatch")
            )
        return get_.return_type

    return None


def _type_check_member_access(
    analyzer, expr: MemberAccess
) -> Optional[TypeSymbol]:
    obj_type = get_expression_type(analyzer, expr.obj)
    if obj_type is None:
        return None
    fields = get_type_public_fields(analyzer, obj_type)
    if fields is None:
        analyzer.errors.append(
            TypeError(expr.obj.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"no public fields on {obj_type}")
        )
        return None
    field_type = fields.get(expr.name)
    if field_type is None:
        analyzer.errors.append(
            TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"`{expr.name}` is not a public field of {obj_type}")
        )
        return None
    return field_type


# ---------------------------------------------------------------------------
# Inline expansion (Phase 2)
# ---------------------------------------------------------------------------


def _type_check_inlined_call(
    analyzer, expr: InlinedCall
) -> Optional[TypeSymbol]:
    """Type-check a previously-expanded :class:`InlinedCall`.

    The body has already been checked when the inline call was
    produced (or at registration time for the recursive-fallback
    path). The return type is stored on the node itself, so this is
    a one-liner. The :mod:`mashiko.sema.desugaring` pass later walks
    the inlined block to add ``.destruct()`` calls for any locals
    bound in the inlined body.
    """
    return expr.return_type


def _try_inline_expand_call(
    analyzer, expr: FunctionCall
) -> Optional[InlinedCall]:
    """Try to expand an inline function call in place at the call site.

    Returns an :class:`InlinedCall` if expansion succeeded, ``None``
    otherwise. The caller (:func:`_type_check_call`) treats ``None`` as
    a signal to fall back to the regular call path.

    Expansion is performed in five steps:

    1. Look up the symbol. Must be a :class:`FunctionSymbol`
       (templates are not inlined in the v1 — they need type-param
       substitution in the body AST, which is non-trivial for frozen
       dataclasses). Must be ``inline=True`` and have a body attached
       (populated by ``register_function``).
    2. Recursion guard: if the symbol is already on
       ``analyzer.inline_stack``, return ``None`` so the call falls
       back to a normal call. This is what makes direct self-recursion
       ``inline func loop(): Int { return loop(); }`` work — the
       inner call becomes a regular call.
    3. Push the symbol onto ``inline_stack``. Open a fresh
       :class:`Scope` and ``scope_destructs`` stack so the inlined
       body's destruct tracking is isolated from the caller's.
    4. Bind each ``Param`` to a fresh :class:`VarSymbol` whose type is
       the corresponding argument expression's type. Re-check the
       body via :func:`check_block`.
    5. Pop the inline stack, scope, and destructs; return the
       :class:`InlinedCall` wrapping the original body block.

    The body has already been checked once at registration
    (:meth:`mashiko.sema.core.SemaAnalyzer.check_function`); the
    second pass at the call site re-runs the check in a fresh scope
    so type errors specific to the inlined arguments (and the
    recursion guard) are reported. For the v1 we accept the
    duplicate diagnostics — they surface in the same order they
    were emitted, so a stable grep for ``additional_message`` still
    matches the same set of issues.
    """
    sym = analyzer.current_scope.get_symbol(expr.name)
    if sym is None or not isinstance(sym, FunctionSymbol):
        return None
    if not sym.inline or sym.body is None:
        return None
    if sym in analyzer.inline_stack:
        return None

    prev_scope = analyzer.current_scope
    prev_destructs = analyzer.scope_destructs
    prev_return = analyzer.current_return_type
    analyzer.current_scope = Scope(prev_scope)
    analyzer.scope_destructs = []
    analyzer.current_return_type = sym.return_type
    analyzer.inline_stack.append(sym)
    try:
        for param_ast, arg in zip(sym.ast_params, expr.args):
            arg_type = get_expression_type(analyzer, arg)
            if arg_type is None:
                continue
            analyzer.current_scope.push_symbol(
                param_ast.name, VarSymbol(type=arg_type)
            )
        check_block(analyzer, sym.body)
    finally:
        analyzer.inline_stack.pop()
        analyzer.current_scope = prev_scope
        analyzer.scope_destructs = prev_destructs
        analyzer.current_return_type = prev_return

    return InlinedCall(
        span=expr.span,
        callee=expr.name,
        args=tuple(expr.args),
        block=sym.body,
        return_type=sym.return_type,
    )


def _try_inline_expand_method_call(
    analyzer, expr: MethodCall, method
) -> Optional[InlinedCall]:
    """Try to expand an inline method call on ``this`` at the call site.

    Same recursion guard / template guard as
    :func:`_try_inline_expand_call`. The receiver must be
    :class:`Name` with ``name == "this"`` so the inlined body shares
    the enclosing scope's ``this`` binding without aliasing.

    ``method`` may be ``None`` if the receiver type has no such
    method (a regular :class:`TypeError` was already pushed by
    :func:`_type_check_method_call`); in that case we return
    ``None`` so the caller can fall back to its normal
    diagnostic-producing path.
    """
    if method is None:
        return None
    if not method.inline or method.body is None:
        return None
    if method in analyzer.inline_stack:
        return None
    if not (isinstance(expr.obj, Name) and expr.obj.name == "this"):
        return None

    prev_scope = analyzer.current_scope
    prev_destructs = analyzer.scope_destructs
    prev_return = analyzer.current_return_type
    analyzer.current_scope = Scope(prev_scope)
    analyzer.scope_destructs = []
    analyzer.current_return_type = method.return_type
    analyzer.inline_stack.append(method)
    try:
        for param_ast, arg in zip(method.ast_params, expr.args):
            arg_type = get_expression_type(analyzer, arg)
            if arg_type is None:
                continue
            analyzer.current_scope.push_symbol(
                param_ast.name, VarSymbol(type=arg_type)
            )
        check_block(analyzer, method.body)
    finally:
        analyzer.inline_stack.pop()
        analyzer.current_scope = prev_scope
        analyzer.scope_destructs = prev_destructs
        analyzer.current_return_type = prev_return

    return InlinedCall(
        span=expr.span,
        callee=f"this::{expr.name}",
        args=tuple(expr.args),
        block=method.body,
        return_type=method.return_type,
    )


def _type_check_binary(analyzer, expr: BinaryOp) -> Optional[TypeSymbol]:
    left_type = get_expression_type(analyzer, expr.left)
    right_type = get_expression_type(analyzer, expr.right)
    if left_type is None or right_type is None:
        return None

    # Built-in operators on primitive types are not modelled via the
    # public-methods table (that table only carries user-defined
    # methods). The semantics used here match what
    # ``find_super_prime.msk`` and other examples rely on:
    #   arithmetic/relational on same-kind numeric → numeric / Bool,
    #   logical ops on Bool → Bool,
    #   bitwise ops on same integer kind → that integer.
    prim = _primitive_binary_result(expr.op, left_type, right_type)
    if prim is _PRIM_OK:
        return left_type if not _is_comparison(expr.op) else PrimitiveTypeSymbol.Bool
    if prim is _PRIM_MISMATCH:
        analyzer.errors.append(
            TypeError(expr.span, left_type, right_type,
                      f"operator {expr.op.value}: operands must be compatible")
        )
        return None
    if prim is not None:
        return prim

    methods = get_type_public_methods(analyzer, left_type)
    if methods is None:
        analyzer.errors.append(
            TypeError(expr.left.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"no public methods on {left_type}")
        )
        return None
    method_name = binary_op_method(expr.op)
    method = methods.get(method_name)
    if method is None:
        analyzer.errors.append(
            TypeError(expr.span, PrimitiveTypeSymbol.Void, PrimitiveTypeSymbol.Void,
                      f"operator {expr.op.value} not defined for {left_type}")
        )
        return None
    if method.params and method.params[0] != right_type:
        analyzer.errors.append(
            TypeError(expr.right.span, method.params[0], right_type,
                      f"operator {expr.op.value} argument type mismatch")
        )
    return method.return_type


def _type_check_unary(analyzer, expr: UnaryOp) -> Optional[TypeSymbol]:
    operand_type = get_expression_type(analyzer, expr.operand)
    if operand_type is None:
        return None

    prim = _primitive_unary_result(expr.op, operand_type)
    if prim is not None:
        if prim is _PRIM_MISMATCH:
            analyzer.errors.append(
                TypeError(expr.span, operand_type, operand_type,
                          f"operator {expr.op.value} not defined for {operand_type}")
            )
            return None
        return prim

    methods = get_type_public_methods(analyzer, operand_type)
    if methods is None:
        return None
    method_name = unary_op_method(expr.op)
    method = methods.get(method_name)
    if method is None:
        return None
    return method.return_type


_PRIM_OK = object()
_PRIM_MISMATCH = object()
_COMPARISON = {
    __import__("mashiko.parser.syntax", fromlist=["BinaryOpKind"]).BinaryOpKind.EQUAL,
    __import__("mashiko.parser.syntax", fromlist=["BinaryOpKind"]).BinaryOpKind.NOT_EQUAL,
    __import__("mashiko.parser.syntax", fromlist=["BinaryOpKind"]).BinaryOpKind.LESS,
    __import__("mashiko.parser.syntax", fromlist=["BinaryOpKind"]).BinaryOpKind.GREATER,
    __import__("mashiko.parser.syntax", fromlist=["BinaryOpKind"]).BinaryOpKind.LESS_EQUAL,
    __import__("mashiko.parser.syntax", fromlist=["BinaryOpKind"]).BinaryOpKind.GREATER_EQUAL,
}


def _is_comparison(op) -> bool:
    return op in _COMPARISON


_NUMERIC = {
    PrimitiveTypeSymbol.Int,
    PrimitiveTypeSymbol.Int8, PrimitiveTypeSymbol.Int16,
    PrimitiveTypeSymbol.Int32, PrimitiveTypeSymbol.Int64,
    PrimitiveTypeSymbol.Uint8, PrimitiveTypeSymbol.Uint16,
    PrimitiveTypeSymbol.Uint32, PrimitiveTypeSymbol.Uint64,
    PrimitiveTypeSymbol.Float32, PrimitiveTypeSymbol.Float64,
}
_INTEGER = {
    PrimitiveTypeSymbol.Int,
    PrimitiveTypeSymbol.Int8, PrimitiveTypeSymbol.Int16,
    PrimitiveTypeSymbol.Int32, PrimitiveTypeSymbol.Int64,
    PrimitiveTypeSymbol.Uint8, PrimitiveTypeSymbol.Uint16,
    PrimitiveTypeSymbol.Uint32, PrimitiveTypeSymbol.Uint64,
}
_BUILTIN_BOOL = {PrimitiveTypeSymbol.Bool}


def _primitive_binary_result(op, left, right):
    """Resolve a binary op on primitive types.

    Returns:
        * ``None`` — not a primitive operator, fall through to the
          method-dispatch path;
        * :data:`_PRIM_OK` — valid, but the actual result type depends
          on whether ``op`` is a comparison (``Bool``) or arithmetic
          (the common operand type);
        * :data:`_PRIM_MISMATCH` — operand shape is wrong, an error
          has been (or will be) reported by the caller.

    Mixed-width operands coerce to the wider one (Int8 + Int16 → Int16)
    via :func:`common_numeric_type`; cross-kind pairs (e.g. Int32 vs
    Float64, signed vs unsigned) report a mismatch instead.
    """
    from ..parser.syntax import BinaryOpKind as BK

    if op in (BK.LOGICAL_OR, BK.LOGICAL_AND):
        if left in _BUILTIN_BOOL and right in _BUILTIN_BOOL:
            return PrimitiveTypeSymbol.Bool
        return _PRIM_MISMATCH

    if op in (BK.BITWISE_OR, BK.BITWISE_XOR, BK.BITWISE_AND):
        common = common_numeric_type(left, right)
        if common is not None and common in _INTEGER:
            return common
        return _PRIM_MISMATCH

    if op in (BK.EQUAL, BK.NOT_EQUAL, BK.LESS, BK.GREATER, BK.LESS_EQUAL, BK.GREATER_EQUAL):
        if left == right:
            return _PRIM_OK
        if (
            isinstance(left, PrimitiveTypeSymbol)
            and isinstance(right, PrimitiveTypeSymbol)
            and common_numeric_type(left, right) is not None
        ):
            return _PRIM_OK
        return _PRIM_MISMATCH

    if op in (BK.ADD, BK.SUBTRACT, BK.MULTIPLY, BK.DIVIDE, BK.MODULO):
        if left in _NUMERIC and right in _NUMERIC:
            common = common_numeric_type(left, right)
            if common is not None:
                return common
        return _PRIM_MISMATCH

    return None


def _primitive_unary_result(op, operand):
    from ..parser.syntax import UnaryOpKind as UK

    if op is UK.NEGATE:
        if operand in _NUMERIC:
            return operand
        return _PRIM_MISMATCH
    if op is UK.NOT:
        if operand in _BUILTIN_BOOL:
            return PrimitiveTypeSymbol.Bool
        return _PRIM_MISMATCH
    return None


def _type_check_conditional(
    analyzer, expr: Conditional
) -> Optional[TypeSymbol]:
    cond_type = get_expression_type(analyzer, expr.condition)
    if cond_type != PrimitiveTypeSymbol.Bool:
        analyzer.errors.append(
            TypeError(expr.condition.span, PrimitiveTypeSymbol.Bool, cond_type,
                      "conditional condition must be Bool")
        )
    then_type = get_expression_type(analyzer, expr.then_expr)
    else_type = get_expression_type(analyzer, expr.else_expr)
    if then_type is None or else_type is None:
        return None
    if then_type != else_type:
        analyzer.errors.append(
            TypeError(expr.span, then_type, else_type,
                      "conditional branches must have the same type")
        )
    return then_type


def _type_check_array_literal(
    analyzer, expr: ArrayLiteral
) -> Optional[TypeSymbol]:
    if not expr.elements:
        return None
    first = get_expression_type(analyzer, expr.elements[0])
    if first is None:
        return None
    for el in expr.elements[1:]:
        t = get_expression_type(analyzer, el)
        if t is None:
            continue
        if t != first:
            analyzer.errors.append(
                TypeError(el.span, first, t, "array element type mismatch")
            )
    return GenericDefinedTypeSymbol(name="Array", type_args=(first,))


# ---------------------------------------------------------------------------
# Type-member lookup helpers (unchanged from earlier draft, but exposed).
# ---------------------------------------------------------------------------


def get_type_public_methods(
    analyzer, t: TypeSymbol
) -> Optional[Dict[str, MethodSymbol]]:
    match t:
        case UserDefinedTypeSymbol(ident=name):
            sym = analyzer.current_scope.get_symbol(name)
            if isinstance(sym, ClassSymbol):
                return sym.public_methods
            return None

        case GenericDefinedTypeSymbol(name=name, type_args=type_args):
            sym = analyzer.current_scope.get_symbol(name)
            if isinstance(sym, ClassTemplate):
                mapping = type_param_mapping(sym.template_params, type_args)
                return {
                    m_name: MethodSymbol(
                        params=[substitute_type(p, mapping) for p in m.params],
                        return_type=substitute_type(m.return_type, mapping),
                        is_static=m.is_static,
                    )
                    for m_name, m in sym.public_methods.items()
                }
            if isinstance(sym, InterfaceTemplate):
                mapping = type_param_mapping(sym.template_params, type_args)
                return {
                    m_name: MethodSymbol(
                        params=[substitute_type(p, mapping) for p in m.params],
                        return_type=substitute_type(m.return_type, mapping),
                        is_static=m.is_static,
                    )
                    for m_name, m in sym.public_methods.items()
                }
            return None

        case _:
            return None


def get_type_public_fields(
    analyzer, t: TypeSymbol
) -> Optional[Dict[str, TypeSymbol]]:
    match t:
        case UserDefinedTypeSymbol(ident=name):
            sym = analyzer.current_scope.get_symbol(name)
            if isinstance(sym, ClassSymbol):
                return sym.public_fields
            return None

        case GenericDefinedTypeSymbol(name=name, type_args=type_args):
            sym = analyzer.current_scope.get_symbol(name)
            if isinstance(sym, ClassTemplate):
                mapping = type_param_mapping(sym.template_params, type_args)
                return {
                    f_name: substitute_type(f_type, mapping)
                    for f_name, f_type in sym.public_fields.items()
                }
            return None

        case _:
            return None
