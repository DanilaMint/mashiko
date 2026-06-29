from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Tuple


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


TypeSymbol = (
    PrimitiveTypeSymbol
    | PointerTypeSymbol
    | TupleTypeSymbol
    | GenericDefinedTypeSymbol
    | UserDefinedTypeSymbol
)


@dataclass
class FunctionSymbol:
    params: List[TypeSymbol]
    return_type: TypeSymbol


@dataclass
class FunctionGenericSymbol:
    generic_types: List


Symbol = FunctionSymbol | FunctionGenericSymbol
