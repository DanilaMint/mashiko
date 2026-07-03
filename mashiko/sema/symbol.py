from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Tuple

from typing_extensions import Dict

from ..errors import TranslationError
from ..span import Span


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
            case "Char8":
                return PrimitiveTypeSymbol.Char8
            case "Char32":
                return PrimitiveTypeSymbol.Char32
            case "Bool":
                return PrimitiveTypeSymbol.Bool
            case "Void":
                return PrimitiveTypeSymbol.Void


@dataclass
class PointerTypeSymbol:
    inner: "TypeSymbol"


@dataclass
class TupleTypeSymbol:
    content: Tuple["TypeSymbol", ...]


@dataclass
class UserDefinedTypeSymbol:
    ident: str


@dataclass
class GenericDefinedTypeSymbol:
    name: str
    generics: Tuple["TypeSymbol", ...]


@dataclass
class MaybeTypeSymbol:
    content: "TypeSymbol"


TypeSymbol = (
    PrimitiveTypeSymbol
    | PointerTypeSymbol
    | TupleTypeSymbol
    | GenericDefinedTypeSymbol
    | UserDefinedTypeSymbol
    | MaybeTypeSymbol
)


@dataclass
class FunctionSymbol:
    params: List[TypeSymbol]
    return_type: TypeSymbol


@dataclass
class FunctionGenericSymbol:
    generic_types: List


@dataclass
class MethodSymbol:
    params: List[TypeSymbol]
    return_type: TypeSymbol
    is_static: bool


@dataclass
class ClassSymbol:
    parent_interfaces: List[str]

    public_methods: Dict[str, MethodSymbol]
    private_methods: Dict[str, MethodSymbol]
    public_fields: Dict[str, TypeSymbol]
    private_fields: Dict[str, TypeSymbol]


Symbol = FunctionSymbol | FunctionGenericSymbol


class NameError(TranslationError):
    """Raised when source code fails to semantic analyze.

    Means, that a name used several times.
    """

    ident: str

    def __init__(self, span: Span, ident: str):
        self.span = span

    def additional_message(self) -> str:
        return f"`{self.ident}` is already declared"


class TypeError(TranslationError):
    """Raised when a programm got an another type of data that it expect"""

    except_type: TypeSymbol
    got_type: TypeSymbol
