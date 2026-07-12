from typing import List, Optional

from ..parser.syntax import (
    Expression,
    GenericType,
    MaybeType,
    Name,
    SimpleType,
    TupleType,
    Type,
)
from .scope import Scope
from .symbols import (
    ClassSymbol,
    ClassTemplate,
    ConstParamSymbol,
    GenericDefinedTypeSymbol,
    InterfaceTemplate,
    MaybeTypeSymbol,
    PrimitiveTypeSymbol,
    TupleTypeSymbol,
    TypeParamSymbol,
    TypeSymbol,
    UserDefinedTypeSymbol,
)


def type_to_symbol(t: Type, scope) -> Optional[TypeSymbol]:
    """Lower an AST ``Type`` node to a :class:`TypeSymbol`.

    ``scope`` is consulted for named user-defined types and generic
    templates; pass the analyzer's :class:`Scope` for context-dependent
    resolution (currently only used for generic instantiation).
    """
    match t:
        case SimpleType(name=name):
            primitive = PrimitiveTypeSymbol.from_str(name)
            if primitive is not None:
                return primitive
            # If the scope has a TypeParamSymbol placeholder under
            # `name` (because we're lowering a template body), preserve
            # it so the surrounding register_*_template caller can
            # substitute it later.
            placeholder = scope.get_symbol(name)
            if isinstance(placeholder, TypeParamSymbol):
                return placeholder
            return UserDefinedTypeSymbol(name)

        case TupleType(types=types):
            inner = tuple(type_to_symbol(i, scope) for i in types)
            if any(x is None for x in inner):
                return None
            return TupleTypeSymbol(inner)

        case GenericType(name=name, args=args):
            sym = scope.get_symbol(name)
            if not isinstance(sym, (ClassTemplate, InterfaceTemplate)):
                return None

            # Split args by the corresponding template-param kind: a
            # type-param expects a Type AST node, a const-param expects
            # an Expression (which the caller can later evaluate as a
            # compile-time constant).
            if len(args) != len(sym.template_params):
                return None

            type_args: List[TypeSymbol] = []
            const_args: List[Expression] = []
            for arg, param in zip(args, sym.template_params):
                match param:
                    case TypeParamSymbol():
                        if not isinstance(arg, Type):
                            return None
                        lowered = type_to_symbol(arg, scope)
                        if lowered is None:
                            return None
                        type_args.append(lowered)

                    case ConstParamSymbol():
                        # Const args come through as Expression AST
                        # nodes (literals, names). The grammar also
                        # lets a SimpleType appear here when the const
                        # reference happens to be capitalised — treat
                        # that as a Name ref to the same ident.
                        if isinstance(arg, Expression):
                            const_args.append(arg)
                        elif isinstance(arg, SimpleType):
                            const_args.append(Name(span=arg.span, name=arg.name))
                        else:
                            return None

            # Verify interface bounds on type-args.
            for tp, ta in zip(sym.template_params, type_args):
                if not isinstance(tp, TypeParamSymbol):
                    continue
                if not tp.interfaces:
                    continue
                if not type_satisfies_interfaces(ta, tp.interfaces, scope):
                    return None

            # Monomorphize: when every type-arg is concrete (no
            # unbound TypeParamSymbol placeholders), build a fresh
            # concrete ClassSymbol/InterfaceSymbol under the mangled
            # name (e.g. ``DynArray-Int``) and return a
            # UserDefinedTypeSymbol referring to it. Downstream code
            # then resolves it like any non-generic user-defined type
            # without needing per-call substitution.
            if not const_args and isinstance(
                sym, (ClassTemplate, InterfaceTemplate)
            ):
                # Defer the import to break the templates<->type_lowering
                # circular dependency — by the time this code runs,
                # ``mashiko.sema.templates`` is fully loaded.
                from .templates import materialize_instantiation

                concrete = materialize_instantiation(
                    scope, name, sym, tuple(type_args)
                )
                if concrete is not None:
                    return concrete

            return GenericDefinedTypeSymbol(
                name=name,
                type_args=tuple(type_args),
                const_args=tuple(const_args),
            )

        case MaybeType(inner=inner):
            lowered = type_to_symbol(inner, scope)
            if lowered is None:
                return None
            return MaybeTypeSymbol(lowered)

        case _:
            return None


def type_satisfies_interfaces(
    t: TypeSymbol, interfaces: tuple[str, ...], scope
) -> bool:
    """Best-effort check that ``t`` implements every interface in ``interfaces``.

    Resolves ``t`` to its class symbol (transitively unwrapping generic
    instantiations to the underlying template) and compares its
    declared ``parent_interfaces`` against the constraint set. Returns
    ``True`` if any of the constraint interfaces match, which is enough
    to flag obviously wrong bounds without a full graph search.
    """
    base = resolve_base_class(t, scope)
    if base is None:
        return False
    declared = set(base.parent_interfaces)
    return any(iface in declared for iface in interfaces)


def resolve_base_class(t: TypeSymbol, scope) -> Optional[ClassSymbol]:
    """Return the concrete :class:`ClassSymbol` behind ``t``.

    For ``GenericDefinedTypeSymbol`` this is the template's fields/methods
    (substitution happens at use sites, not here). For everything else,
    returns ``None``.
    """
    match t:
        case UserDefinedTypeSymbol(ident=name):
            sym = scope.get_symbol(name)
            if isinstance(sym, ClassSymbol):
                return sym
            return None
        case GenericDefinedTypeSymbol(name=name):
            sym = scope.get_symbol(name)
            if isinstance(sym, ClassTemplate):
                # We don't materialize a ClassSymbol; the caller can
                # substitute type params on the template directly.
                return template_to_class_symbol(sym)
            return None
        case _:
            return None


def template_to_class_symbol(template: ClassTemplate) -> ClassSymbol:
    """Project a :class:`ClassTemplate` down to a :class:`ClassSymbol`.

    Drops the type-param metadata. Use sites that need substitution
    (looking up a field/method on an instantiated generic) operate on
    the template directly.
    """
    return ClassSymbol(
        parent_interfaces=template.parent_interfaces,
        public_methods=template.public_methods,
        private_methods=template.private_methods,
        public_fields=template.public_fields,
        private_fields=template.private_fields,
    )
