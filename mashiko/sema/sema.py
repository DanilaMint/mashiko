from typing import Dict, Optional

from tests.test_errors import ast

from ..parser.syntax import Declaration, FunctionDecl, Module
from .symbol import Symbol


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

    def __init__(self, ast: Module):
        self.ast = ast
        self.current_scope = Scope(None)

    def register_declarations(self):
        # Preregister
        prereg: Dict[str, Declaration] = {}
        for decl in self.ast.declarations:
            prereg[decl.name] = decl

        for k, v in prereg.items():
            ...
