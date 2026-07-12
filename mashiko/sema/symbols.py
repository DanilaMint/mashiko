from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple, Union

from typing_extensions import Dict

from ..parser.syntax import Expression


class PrimitiveTypeSymbol(Enum):
    Int = auto()
    Int8 = auto()
    Int16 = auto()
    Int32 = auto()
    Int64 = auto()

    Uint = auto()
    Uint8 = auto()
    Uint16 = auto()
    Uint32 = auto()
    Uint64 = auto()

    Float32 = auto()
    Float64 = auto()

    Char8 = auto()
    Char32 = auto()

    Bool = auto()

    Void = auto()

    @staticmethod
    def from_str(name: str) -> Optional["PrimitiveTypeSymbol"]:
        match name:
            case "Int":
                return PrimitiveTypeSymbol.Int
            case "Int8":
                return PrimitiveTypeSymbol.Int8
            case "Int16":
                return PrimitiveTypeSymbol.Int16
            case "Int32":
                return PrimitiveTypeSymbol.Int32
            case "Int64":
                return PrimitiveTypeSymbol.Int64
            case "Uint":
                return PrimitiveTypeSymbol.Uint
            case "Uint8":
                return PrimitiveTypeSymbol.Uint8
            case "Uint16":
                return PrimitiveTypeSymbol.Uint16
            case "Uint32":
                return PrimitiveTypeSymbol.Uint32
            case "Uint64":
                return PrimitiveTypeSymbol.Uint64
            case "Float32" | "Float":
                return PrimitiveTypeSymbol.Float32
            case "Float64":
                return PrimitiveTypeSymbol.Float64
            case "Char8":
                return PrimitiveTypeSymbol.Char8
            case "Char32":
                return PrimitiveTypeSymbol.Char32
            case "Bool":
                return PrimitiveTypeSymbol.Bool
            case "Void":
                return PrimitiveTypeSymbol.Void


@dataclass(frozen=True)
class PointerTypeSymbol:
    inner: "TypeSymbol"


@dataclass(frozen=True)
class TupleTypeSymbol:
    content: Tuple["TypeSymbol", ...]


@dataclass(frozen=True)
class UserDefinedTypeSymbol:
    ident: str


@dataclass(frozen=True)
class TypeParamSymbol:
    """Placeholder for a template type parameter (e.g. ``T`` in ``Box<T>``).

    Replaced with a concrete ``TypeSymbol`` once a generic template is
    instantiated. ``interfaces`` lists upper-bound interface constraints
    that the substituted type must implement.
    """

    name: str
    interfaces: Tuple[str, ...] = ()


@dataclass
class ConstParamSymbol:
    """A template const parameter (e.g. ``const N: UInt``).

    ``type`` is the declared type. ``default`` is the AST expression
    providing the default value when the param is omitted at the
    instantiation site; ``None`` means the param is required.
    """

    name: str
    type: "TypeSymbol"
    default: Optional[Expression] = None


TemplateParamSymbol = Union[TypeParamSymbol, ConstParamSymbol]


@dataclass(frozen=True)
class GenericDefinedTypeSymbol:
    """An instantiated generic type, e.g. ``Box<Int>`` or ``Array<Int, 5>``.

    Type-position arguments land in ``type_args``; const-position
    arguments land in ``const_args`` as :class:`Expression` AST nodes
    so that downstream passes can either substitute them into other
    generic instantiations or evaluate them as compile-time constants.
    """

    name: str
    type_args: Tuple["TypeSymbol", ...] = ()
    const_args: Tuple[Expression, ...] = ()


@dataclass(frozen=True)
class MaybeTypeSymbol:
    content: "TypeSymbol"


TypeSymbol = (
    PrimitiveTypeSymbol
    | PointerTypeSymbol
    | TupleTypeSymbol
    | GenericDefinedTypeSymbol
    | UserDefinedTypeSymbol
    | MaybeTypeSymbol
    | TypeParamSymbol
)


@dataclass
class FunctionSymbol:
    params: List[TypeSymbol]
    return_type: TypeSymbol


@dataclass
class FunctionTemplate:
    """Generic function template.

    ``template_params`` lists the placeholders visible in ``params`` and
    ``return_type`` (as :class:`TypeParamSymbol` / :class:`ConstParamSymbol`
    instances, in declaration order). Callers substitute concrete values
    for those placeholders when resolving a call site.
    """

    template_params: Tuple[TemplateParamSymbol, ...]
    params: List[TypeSymbol]
    return_type: TypeSymbol


@dataclass
class MethodSymbol:
    params: List[TypeSymbol]
    return_type: TypeSymbol
    is_static: bool


@dataclass
class VarSymbol:
    """Local / parameter binding produced by the analyzer.

    The same :class:`Scope` chain stores these alongside
    :class:`FunctionSymbol` etc.; only this kind introduces the "name
    has a value" interpretation that
    :func:`mashiko.sema.expressions.get_expression_type` needs for an
    r-value :class:`~mashiko.sema.syntax.Name`.
    """

    type: TypeSymbol


@dataclass
class ClassSymbol:
    parent_interfaces: List[str]

    public_methods: Dict[str, MethodSymbol]
    private_methods: Dict[str, MethodSymbol]
    public_fields: Dict[str, TypeSymbol]
    private_fields: Dict[str, TypeSymbol]


@dataclass
class ClassTemplate:
    """Generic class template.

    Field/method types reference :class:`TypeParamSymbol` placeholders
    from ``template_params``. They are substituted when an instantiation
    (a :class:`GenericDefinedTypeSymbol`) is resolved.
    """

    template_params: Tuple[TemplateParamSymbol, ...]
    parent_interfaces: List[str]

    public_methods: Dict[str, MethodSymbol]
    private_methods: Dict[str, MethodSymbol]
    public_fields: Dict[str, TypeSymbol]
    private_fields: Dict[str, TypeSymbol]


@dataclass
class InterfaceSymbol:
    parent_interfaces: List[str]

    public_methods: Dict[str, MethodSymbol]


@dataclass
class InterfaceTemplate:
    template_params: Tuple[TemplateParamSymbol, ...]
    parent_interfaces: List[str]

    public_methods: Dict[str, MethodSymbol]


Symbol = (
    FunctionSymbol
    | FunctionTemplate
    | ClassSymbol
    | ClassTemplate
    | InterfaceSymbol
    | InterfaceTemplate
    | VarSymbol
)


def substitute_type(t: TypeSymbol, mapping: Dict[str, TypeSymbol]) -> TypeSymbol:
    """Recursively replace :class:`TypeParamSymbol` placeholders in ``t``.

    Anything not containing a placeholder (primitives, user-defined types,
    unbound placeholders) is returned unchanged. The result is a fresh
    tree: the original ``t`` is not mutated.
    """
    match t:
        case TypeParamSymbol(name=name):
            return mapping.get(name, t)

        case TupleTypeSymbol(content=types):
            return TupleTypeSymbol(tuple(substitute_type(x, mapping) for x in types))

        case MaybeTypeSymbol(content=inner):
            return MaybeTypeSymbol(substitute_type(inner, mapping))

        case GenericDefinedTypeSymbol(name=name, type_args=type_args, const_args=const_args):
            return GenericDefinedTypeSymbol(
                name,
                type_args=tuple(substitute_type(a, mapping) for a in type_args),
                const_args=const_args,
            )

        case _:
            return t
