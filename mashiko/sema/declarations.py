from typing import Dict

from ..parser.syntax import (
    ClassDecl,
    Declaration,
    Field,
    FunctionDecl,
    InterfaceDecl,
    Method,
)
from .errors import DuplicateNameError, TranslationError
from .symbols import (
    ClassSymbol,
    ClassTemplate,
    FunctionSymbol,
    FunctionTemplate,
    InterfaceSymbol,
    InterfaceTemplate,
    MethodSymbol,
    PrimitiveTypeSymbol,
    TemplateParamSymbol,
    TypeParamSymbol,
    TypeSymbol,
)
from .templates import (
    contains_unbound,
    pop_type_param_placeholders,
    push_type_param_placeholders,
    template_type_params,
)
from .type_lowering import type_to_symbol


def register_declarations(analyzer):
    """Register every top-level declaration in the current scope.

    Re-declaring a name that has already been registered (in this same
    pass) is reported as a :class:`NameError` and the duplicate is
    skipped — only the first occurrence binds the name. The first
    declaration's body still gets checked by :meth:`SemaAnalyzer.analyze`
    (which iterates :attr:`SemaAnalyzer.registered_decls`, not the raw
    AST list), so the duplicate's body is intentionally *not* visited.

    Anything that falls through the ``match`` (e.g. a future
    declaration kind the front-end produces but the analyzer doesn't
    know yet) is reported as a generic :class:`TranslationError` and
    skipped, instead of raising — the surrounding
    :meth:`~mashiko.sema.core.SemaAnalyzer.analyze` keeps collecting
    errors for the remaining declarations.
    """
    ordered: list[Declaration] = []
    seen: Dict[str, Declaration] = {}

    for decl in analyzer.ast.declarations:
        name = getattr(decl, "name", None)
        if name is None:
            # No `name` field at all — surface as a generic translation
            # error and skip rather than raising and aborting the pass.
            analyzer.errors.append(TranslationError(decl.span))
            continue
        if name in seen:
            analyzer.errors.append(DuplicateNameError(decl.span, name))
            continue
        seen[name] = decl
        ordered.append(decl)

    analyzer.registered_decls = ordered

    for i in ordered:
        match i:
            case FunctionDecl():
                register_function(analyzer, i)

            case ClassDecl():
                register_class(analyzer, i)

            case InterfaceDecl():
                register_interface(analyzer, i)

            case _:
                analyzer.errors.append(TranslationError(i.span))


def register_function(analyzer, f: FunctionDecl):
    if f.template is None:
        params = [type_to_symbol(p.type, analyzer.current_scope) for p in f.params]
        return_type = (
            type_to_symbol(f.return_type, analyzer.current_scope)
            if f.return_type is not None
            else PrimitiveTypeSymbol.Void
        )
        if any(p is None for p in params) or return_type is None:
            return
        sym = FunctionSymbol(params, return_type)
    else:
        template_params = template_type_params(f.template, analyzer.current_scope)
        # Make type-param placeholders visible to type_to_symbol
        # while lowering the signature so `T` resolves to
        # TypeParamSymbol, not to UserDefinedTypeSymbol("T"). Const
        # params don't appear in type position (only in
        # GenericDefinedTypeSymbol.const_args) so they're not pushed.
        saved = push_type_param_placeholders(template_params, analyzer.current_scope)
        try:
            params = [type_to_symbol(p.type, analyzer.current_scope) for p in f.params]
            return_type = (
                type_to_symbol(f.return_type, analyzer.current_scope)
                if f.return_type is not None
                else PrimitiveTypeSymbol.Void
            )
        finally:
            pop_type_param_placeholders(saved, analyzer.current_scope)
        if any(p is None for p in params) or return_type is None:
            return
        type_params = tuple(
            p for p in template_params if isinstance(p, TypeParamSymbol)
        )
        if any(contains_unbound(p, type_params) for p in params):
            return
        if contains_unbound(return_type, type_params):
            return
        sym = FunctionTemplate(
            template_params=template_params,
            params=params,
            return_type=return_type,
        )

    analyzer.current_scope.push_symbol(f.name, sym)


def register_class(analyzer, c: ClassDecl):
    template_params: tuple[TemplateParamSymbol, ...] = ()
    if c.template is not None:
        template_params = template_type_params(c.template, analyzer.current_scope)

    type_params = tuple(p for p in template_params if isinstance(p, TypeParamSymbol))

    # Make placeholders visible to type_to_symbol while lowering
    # the body so `T` resolves to TypeParamSymbol, not to
    # UserDefinedTypeSymbol("T"). For non-template classes this is
    # a no-op (empty tuple → no pushes).
    saved = push_type_param_placeholders(type_params, analyzer.current_scope)

    public_fields: Dict[str, TypeSymbol] = {}
    private_fields: Dict[str, TypeSymbol] = {}
    public_methods: Dict[str, MethodSymbol] = {}
    private_methods: Dict[str, MethodSymbol] = {}

    try:
        for member in c.body.members:
            match member:
                case Field():
                    field_type = type_to_symbol(member.type, analyzer.current_scope)
                    if field_type is None:
                        continue
                    if member.visibility:
                        public_fields[member.name] = field_type
                    else:
                        private_fields[member.name] = field_type

                case Method():
                    params = [
                        type_to_symbol(p.type, analyzer.current_scope)
                        for p in member.params
                    ]
                    return_type = (
                        type_to_symbol(member.return_type, analyzer.current_scope)
                        if member.return_type is not None
                        else PrimitiveTypeSymbol.Void
                    )
                    if any(p is None for p in params) or return_type is None:
                        continue
                    method_sym = MethodSymbol(params, return_type, member.static)
                    if member.visibility:
                        public_methods[member.name] = method_sym
                    else:
                        private_methods[member.name] = method_sym
    finally:
        pop_type_param_placeholders(saved, analyzer.current_scope)

    parent_interfaces = [iface.name for iface in c.interfaces]

    if c.template is None:
        sym = ClassSymbol(
            parent_interfaces,
            public_methods,
            private_methods,
            public_fields,
            private_fields,
        )
    else:
        if any(
            contains_unbound(t, type_params)
            for t in (*public_fields.values(), *private_fields.values())
        ):
            return
        if any(
            contains_unbound(m.return_type, type_params)
            for m in (*public_methods.values(), *private_methods.values())
        ):
            return
        sym = ClassTemplate(
            template_params=template_params,
            parent_interfaces=parent_interfaces,
            public_methods=public_methods,
            private_methods=private_methods,
            public_fields=public_fields,
            private_fields=private_fields,
        )

    analyzer.current_scope.push_symbol(c.name, sym)


def register_interface(analyzer, i: InterfaceDecl):
    template_params: tuple[TemplateParamSymbol, ...] = ()
    if i.template is not None:
        template_params = template_type_params(i.template, analyzer.current_scope)

    type_params = tuple(p for p in template_params if isinstance(p, TypeParamSymbol))

    saved = push_type_param_placeholders(type_params, analyzer.current_scope)

    public_methods: Dict[str, MethodSymbol] = {}
    try:
        for method in i.body.methods:
            params = [
                type_to_symbol(p.type, analyzer.current_scope) for p in method.params
            ]
            return_type = (
                type_to_symbol(method.return_type, analyzer.current_scope)
                if method.return_type is not None
                else PrimitiveTypeSymbol.Void
            )
            if any(p is None for p in params) or return_type is None:
                continue
            public_methods[method.name] = MethodSymbol(
                params, return_type, method.static
            )
    finally:
        pop_type_param_placeholders(saved, analyzer.current_scope)

    parent_interfaces = [iface.name for iface in i.interfaces]

    if i.template is None:
        sym = InterfaceSymbol(parent_interfaces, public_methods)
    else:
        if any(
            contains_unbound(m.return_type, type_params)
            for m in public_methods.values()
        ):
            return
        sym = InterfaceTemplate(
            template_params=template_params,
            parent_interfaces=parent_interfaces,
            public_methods=public_methods,
        )

    analyzer.current_scope.push_symbol(i.name, sym)
