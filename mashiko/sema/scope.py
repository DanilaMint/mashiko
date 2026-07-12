from typing import Dict, Optional

from .symbols import PrimitiveTypeSymbol, Symbol


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


BUILTIN_SCOPE = Scope(None)
BUILTIN_SCOPE.push_symbol("Void", PrimitiveTypeSymbol.Void)
BUILTIN_SCOPE.push_symbol("Int", PrimitiveTypeSymbol.Int)
