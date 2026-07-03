from typing import Dict, List, Optional

from mashiko.errors import TranslationError
from tests.test_errors import ast

from ..parser.syntax import (
    ClassDecl,
    Declaration,
    Field,
    FunctionDecl,
    GenericType,
    InterfaceDecl,
    MaybeType,
    Method,
    Module,
    SimpleType,
    TupleType,
    Type,
)
from .symbol import (
    FunctionSymbol,
    MaybeTypeSymbol,
    PrimitiveTypeSymbol,
    Symbol,
    TupleTypeSymbol,
    TypeSymbol,
    UserDefinedTypeSymbol,
)

GENERIC_EXCEPTION = Exception("GENERICS ARE NOT READY NOW!!!")


def type_to_symbol(t: Type) -> TypeSymbol:
    if isinstance(t, SimpleType):
        primitive = PrimitiveTypeSymbol.from_str(t.name)
        if primitive is not None:
            return primitive
        else:
            return UserDefinedTypeSymbol(t.name)

    elif isinstance(t, TupleType):
        types = tuple([type_to_symbol(i) for i in t.types])

        return TupleTypeSymbol(types)

    elif isinstance(t, GenericType):
        raise GENERIC_EXCEPTION

    elif isinstance(t, MaybeType):
        return MaybeTypeSymbol(type_to_symbol(t.inner))

    else:
        return None


class Scope:
    symbols: Dict[str, Symbol]
    parent_scope: Optional["Scope"]

    def __init__(self, parent_scope: Optional["Scope"]):
        self.parent_scope = parent_scope
        self.symbols = {}

    def push_symbol(self, ident: str, sym: Symbol) -> Optional[Symbol]:
        """Push symbol to current scope and returns old symbol"""
        prev = self.symbols.get(ident)
        self.symbols[ident] = sym
        return prev

    def get_symbol(self, ident: str) -> Optional[Symbol]:
        curr = self._get_symbol_current(ident)
        if curr is not None:
            return curr

        else:
            return self._get_symbol_parent(ident)

    def _get_symbol_current(self, ident: str) -> Optional[Symbol]:
        return self.symbols.get(ident)

    def _get_symbol_parent(self, ident: str) -> Optional[Symbol]:
        if self.parent_scope is not None:
            return self.parent_scope.get_symbol(ident)
        return None

    def get_parent_scope(self) -> Optional["Scope"]:
        return self.parent_scope


class SemaAnalyzer:
    current_scope: Scope
    ast: Module
    errors: List[TranslationError]

    def __init__(self, ast: Module):
        self.ast = ast
        self.current_scope = Scope(None)

    def register_declarations(self):
        # Preregister
        prereg: Dict[str, Declaration] = {}
        for decl in self.ast.declarations:
            prereg[decl.name] = decl

        for i in prereg.values():
            if isinstance(i, FunctionDecl):
                self.register_function(i)

            elif isinstance(i, ClassDecl):
                self.register_class(i)

            elif isinstance(i, InterfaceDecl):
                self.register_interface(i)

            else:
                raise TranslationError(i.span)

    def register_function(self, f: FunctionDecl):
        if f.template is None:
            types = [type_to_symbol(p.type) for p in f.params]
            return_type = (
                type_to_symbol(f.return_type)
                if f.return_type is not None
                else PrimitiveTypeSymbol.Void
            )
            sym = FunctionSymbol(types, return_type)

            self.current_scope.push_symbol(f.name, sym)
        else:
            raise GENERIC_EXCEPTION

    def register_class(self, c: ClassDecl):
        if c.template is None:
            names = set()
            public_fields = {}
            private_fields = {}
            public_methods = {}
            private_methods = {}
            for member in c.body.members:
                if isinstance(member, Field):
                    if member.visibility:
                        public_fields[member.name] = type_to_symbol(member.type)
                    else:
                        private_fields[member.name] = type_to_symbol(member.type)
                if isinstance(member, Method):
                    if member.visibility:
                        public_methods[member.name]
        else:
            raise GENERIC_EXCEPTION

    def register_interface(self, i: InterfaceDecl):
        if i.template is None:
            ...
        else:
            raise GENERIC_EXCEPTION
