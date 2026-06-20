"""Семантический анализатор"""

from dataclasses import dataclass
from typing import Dict, List

from mashiko import syntax


@dataclass
class SemaInterface:
    methods: List["SemaFunction"]


@dataclass
class SemaClass:
    interfaces: List[SemaInterface]
    name: str
    methods: List["SemaFunction"]
    ...


@dataclass
class SemaFunction:
    pass


class SemanticAnalyzer:
    pre_functions: Dict[str, syntax.FunctionDef]
    functions: Dict[str, SemaFunction]
    interfaces: Dict[str, SemaInterface]
    classes: Dict[str, SemaClass]

    def __init__(self):
        self.functions = {}
        self.interfaces = {}
        self.classes = {}

    def register(self, ast: syntax.Module):
        self._pre_register_functions([i.node for i in ast.functions])

    def _pre_register_functions(self, funcs: List[syntax.FunctionDef]):
        for func in funcs:
            self._pre_register_function(func)

    def _pre_register_function(self, funcs: syntax.FunctionDef):
        self.pre_functions[funcs.name] = funcs

    def _register_function(self, func: syntax.FunctionDef):
        pass
