from typing import Dict, List, Optional

from ..parser.syntax import ConstParam, TemplateDecl, TypeParam
from .scope import Scope
from .symbols import (
    ClassSymbol,
    ClassTemplate,
    ConstParamSymbol,
    FunctionSymbol,
    FunctionTemplate,
    GenericDefinedTypeSymbol,
    InterfaceSymbol,
    InterfaceTemplate,
    MaybeTypeSymbol,
    MethodSymbol,
    PrimitiveTypeSymbol,
    Symbol,
    TemplateParamSymbol,
    TupleTypeSymbol,
    TypeParamSymbol,
    TypeSymbol,
    UserDefinedTypeSymbol,
    substitute_type,
)
from .type_lowering import type_to_symbol


def template_type_params(
    template: TemplateDecl, scope: Scope
) -> tuple[TemplateParamSymbol, ...]:
    """Convert AST :class:`TemplateDecl` members to template-param symbols.

    Each :class:`TypeParam` becomes a :class:`TypeParamSymbol`; each
    :class:`ConstParam` becomes a :class:`ConstParamSymbol` whose
    ``default`` is the AST expression from the declaration. The result
    preserves declaration order so callers can match template args
    positionally against the template's parameter list.
    """
    out: List[TemplateParamSymbol] = []
    for m in template.members:
        match m:
            case TypeParam(name=name, interfaces=interfaces):
                out.append(TypeParamSymbol(name=name, interfaces=interfaces))
            case ConstParam(name=name, type=type_node, default=default):
                declared = type_to_symbol(type_node, scope)
                if declared is None:
                    # The const-param's declared type couldn't be
                    # resolved (it's typically a primitive, so this
                    # should be rare); skip the param rather than
                    # fabricate an unknown type.
                    continue
                out.append(
                    ConstParamSymbol(name=name, type=declared, default=default)
                )
    return tuple(out)


def type_param_mapping(
    template_params: tuple[TemplateParamSymbol, ...],
    type_args: tuple[TypeSymbol, ...],
) -> Dict[str, TypeSymbol]:
    """Build a name→TypeSymbol mapping from type-position template params.

    Walks ``template_params`` and ``type_args`` together; non-type
    params (e.g. const params) are skipped without consuming an entry
    from ``type_args``. Because args are matched positionally against
    the template's full param list, this helper assumes the caller has
    already verified arity.
    """
    mapping: Dict[str, TypeSymbol] = {}
    type_idx = 0
    for p in template_params:
        if isinstance(p, TypeParamSymbol):
            mapping[p.name] = type_args[type_idx]
            type_idx += 1
    return mapping


def contains_unbound(
    t: TypeSymbol, type_params: tuple[TypeParamSymbol, ...]
) -> bool:
    """True if ``t`` references a :class:`TypeParamSymbol` not in ``type_params``.

    Used to bail out of registering a generic declaration whose body
    types the analyzer couldn't fully lower.
    """
    names = {p.name for p in type_params}
    match t:
        case TypeParamSymbol(name=name):
            return name not in names
        case TupleTypeSymbol(content=types):
            return any(contains_unbound(x, type_params) for x in types)
        case MaybeTypeSymbol(content=inner):
            return contains_unbound(inner, type_params)
        case GenericDefinedTypeSymbol(type_args=type_args):
            return any(contains_unbound(a, type_params) for a in type_args)
        case _:
            return False


def push_type_param_placeholders(
    type_params: tuple[TypeParamSymbol, ...], scope: Scope
) -> Dict[str, Symbol]:
    """Push each type-param as a placeholder symbol into ``scope``.

    Returns a snapshot of the previous bindings under those names so
    :func:`pop_type_param_placeholders` can restore them. Empty
    ``type_params`` is a no-op.
    """
    saved: Dict[str, Symbol] = {}
    for tp in type_params:
        saved[tp.name] = scope.push_symbol(tp.name, tp)
    return saved


def pop_type_param_placeholders(
    saved: Dict[str, Symbol], scope: Scope
) -> None:
    """Restore the bindings captured by :func:`push_type_param_placeholders`."""
    for name, prev in saved.items():
        if prev is None:
            scope.symbols.pop(name, None)
        else:
            scope.symbols[name] = prev


def _collect_param_refs(param_type: TypeSymbol) -> List[str]:
    """Walk a single param type and return the names of every
    :class:`TypeParamSymbol` referenced inside it.

    For now only the trivial case is supported: the param type is
    itself a single :class:`TypeParamSymbol`. Nested references (a
    param typed as ``Tuple<T>``, ``T?`` or ``Box<T>``) are left for a
    later iteration — the conservative inference below only fires
    when each type-param appears at most once and in a direct
    position.
    """
    if isinstance(param_type, TypeParamSymbol):
        return [param_type.name]
    return []


def infer_template_args(
    template_params: tuple[TemplateParamSymbol, ...],
    param_types: tuple[TypeSymbol, ...],
    arg_types: tuple[TypeSymbol, ...],
) -> Optional[Dict[str, TypeSymbol]]:
    """Build a name→TypeSymbol mapping by unifying arg types against
    ``param_types``.

    Walks ``param_types`` / ``arg_types`` in lock-step. A param type
    of ``TypeParamSymbol(T)`` binds ``T`` to the corresponding arg's
    static type; if ``T`` already has a binding, the two inferred
    types must be structurally equal (a conflict means the call is
    ambiguous and we return ``None``).

    Params that aren't :class:`TypeParamSymbol` are skipped — they
    contribute no binding. The caller (typically
    :func:`infer_and_instantiate`) is responsible for verifying
    arity and bounds after this returns.
    """
    mapping: Dict[str, TypeSymbol] = {}
    for param_type, arg_type in zip(param_types, arg_types):
        for name in _collect_param_refs(param_type):
            existing = mapping.get(name)
            if existing is None:
                mapping[name] = arg_type
            elif existing != arg_type:
                return None
    # Param-template params (const params) are not inferred from
    # types — leave their entries absent so the caller can fall back
    # to a default or surface a clear "needs explicit args" error.
    return mapping


def substitute_mapping_into_template(
    template,
    mapping: Dict[str, TypeSymbol],
):
    """Project a template down to a fresh non-generic shape with
    type-param placeholders replaced by ``mapping``.

    Returns a ``ClassSymbol`` / ``InterfaceSymbol`` / ``FunctionSymbol``
    with the substitution applied to every field, method param, and
    method return type. Used by the call-site inference path to
    produce a concrete value the rest of the analyzer can treat like
    any non-generic symbol.
    """
    from .symbols import FunctionSymbol

    if isinstance(template, FunctionTemplate):
        return FunctionSymbol(
            params=[substitute_type(p, mapping) for p in template.params],
            return_type=substitute_type(template.return_type, mapping),
        )
    if isinstance(template, ClassTemplate):
        return _materialize_class_template(template, mapping)
    if isinstance(template, InterfaceTemplate):
        return _materialize_interface_template(template, mapping)
    raise TypeError(f"cannot substitute into {type(template).__name__}")


# ---------------------------------------------------------------------------
# Monomorphization: turn an explicit ``Foo<Int>`` instantiation into a
# concrete ``Foo-Int`` ClassSymbol / InterfaceSymbol registered in the
# current scope. The mangled name uses ``-`` as a separator because the
# mashiko identifier grammar excludes it, so a user-declared type can
# never collide with a mangled name.
# ---------------------------------------------------------------------------


_MANGLE_SEP = "-"


def _mangle_type_arg(t: TypeSymbol) -> str:
    """Stringify a single type argument for name mangling.

    The result is a deterministic, human-readable fragment that is then
    joined with ``_MANGLE_SEP``. :class:`PrimitiveTypeSymbol` uses its
    enum member name (e.g. ``Int``); user-defined types use their
    ``ident``; nested generics recurse via :func:`mangle_type_name`;
    ``Maybe`` types are wrapped to disambiguate from their content.
    """
    match t:
        case PrimitiveTypeSymbol() if t.name is not None:
            return t.name
        case UserDefinedTypeSymbol(ident=ident):
            return ident
        case GenericDefinedTypeSymbol(name=name, type_args=type_args):
            return mangle_type_name(name, type_args)
        case MaybeTypeSymbol(content=inner):
            return "Maybe" + _MANGLE_SEP + _mangle_type_arg(inner)
        case TypeParamSymbol(name=name):
            # A still-unbound placeholder; should have been rejected
            # by ``_has_unbound_placeholder`` before we get here, but
            # keep the mangle stable if it slips through.
            return name
        case TupleTypeSymbol():
            return "Tuple"
        case _:
            return "_"


def mangle_type_name(
    template_name: str, type_args: tuple[TypeSymbol, ...]
) -> str:
    """Build the mangled name for ``template_name<type_args...>``.

    Examples::

        mangle_type_name("DynArray", (PrimitiveTypeSymbol.Int,)) == "DynArray-Int"
        mangle_type_name("Map", (Int, String)) == "Map-Int-String"
        mangle_type_name("Box", (Box_Int,)) == "Box-Box-Int"
    """
    return _MANGLE_SEP.join(
        [template_name, *(_mangle_type_arg(a) for a in type_args)]
    )


def _has_unbound_placeholder(t: TypeSymbol) -> bool:
    """True if ``t`` still references a :class:`TypeParamSymbol`.

    A :class:`TypeParamSymbol` only escapes into a type-argument
    position when the analyzer is lowering a generic *body* whose
    surrounding placeholders haven't been substituted yet (e.g. a
    method's return type inside ``template<type T> class Foo``). We
    cannot monomorphize such instantiations, so we fall back to the
    deferred-substitution path.
    """
    match t:
        case TypeParamSymbol():
            return True
        case TupleTypeSymbol(content=types):
            return any(_has_unbound_placeholder(x) for x in types)
        case MaybeTypeSymbol(content=inner):
            return _has_unbound_placeholder(inner)
        case GenericDefinedTypeSymbol(type_args=type_args):
            return any(_has_unbound_placeholder(a) for a in type_args)
        case _:
            return False


def _substitute_method(
    m: MethodSymbol, mapping: Dict[str, TypeSymbol]
) -> MethodSymbol:
    return MethodSymbol(
        params=[substitute_type(p, mapping) for p in m.params],
        return_type=substitute_type(m.return_type, mapping),
        is_static=m.is_static,
    )


def _materialize_class_template(
    template: ClassTemplate, mapping: Dict[str, TypeSymbol]
) -> ClassSymbol:
    return ClassSymbol(
        parent_interfaces=list(template.parent_interfaces),
        public_methods={
            n: _substitute_method(m, mapping)
            for n, m in template.public_methods.items()
        },
        private_methods={
            n: _substitute_method(m, mapping)
            for n, m in template.private_methods.items()
        },
        public_fields={
            n: substitute_type(t, mapping)
            for n, t in template.public_fields.items()
        },
        private_fields={
            n: substitute_type(t, mapping)
            for n, t in template.private_fields.items()
        },
    )


def _materialize_interface_template(
    template: InterfaceTemplate, mapping: Dict[str, TypeSymbol]
) -> InterfaceSymbol:
    return InterfaceSymbol(
        parent_interfaces=list(template.parent_interfaces),
        public_methods={
            n: _substitute_method(m, mapping)
            for n, m in template.public_methods.items()
        },
    )


def materialize_instantiation(
    scope: Scope,
    template_name: str,
    template: Symbol,
    type_args: tuple[TypeSymbol, ...],
) -> Optional[TypeSymbol]:
    """Monomorphize an explicit ``template_name<type_args...>`` instantiation.

    On success, builds a concrete :class:`ClassSymbol` or
    :class:`InterfaceSymbol` with type parameters substituted, registers
    it under the mangled name in ``scope``, and returns a
    :class:`UserDefinedTypeSymbol` referring to that mangled name so
    downstream code can look up the concrete type like any non-generic
    user-defined type.

    Returns ``None`` (and registers nothing) when:

    * any ``type_args`` element still references an unbound
      :class:`TypeParamSymbol` — there is no concrete type to
      substitute, so defer to the existing
      :class:`GenericDefinedTypeSymbol` path;
    * ``template`` is neither a :class:`ClassTemplate` nor an
      :class:`InterfaceTemplate` — the caller is misusing this
      helper.

    Subsequent instantiations with the same arguments return the
    already-registered mangled symbol without rebuilding it.
    """
    if not isinstance(template, (ClassTemplate, InterfaceTemplate)):
        return None

    if any(_has_unbound_placeholder(a) for a in type_args):
        return None

    mangled = mangle_type_name(template_name, type_args)
    existing = scope.get_symbol(mangled)
    if isinstance(existing, (ClassSymbol, InterfaceSymbol)):
        return UserDefinedTypeSymbol(mangled)

    mapping = type_param_mapping(template.template_params, type_args)

    if isinstance(template, ClassTemplate):
        concrete = _materialize_class_template(template, mapping)
    else:
        concrete = _materialize_interface_template(template, mapping)

    scope.push_symbol(mangled, concrete)
    return UserDefinedTypeSymbol(mangled)
