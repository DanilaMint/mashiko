"""AST языка mashiko.

Все узлы — frozen dataclass'ы со слотами. Каждый узел несёт `line` и `col`
(позиция первого токена конструкции) — нужно семантике и codegen для
диагностик. Имена бинарных/унарных операторов хранятся как строки,
совпадающие с shape-токенами лексера ("+", "==", "&&", ...).

Группировочные классы (`Type`, `Expr`, `Stmt`, `Lvalue`, `Iterable`)
служат для isinstance-проверок и type hints.
"""

from __future__ import annotations

from dataclasses import dataclass


# =============================================================
# Маркеры групп
# =============================================================

class Type:
    """Маркер типовых узлов (simple/tuple/generic/maybe/refinement)."""
    __slots__ = ()


class Expr:
    """Маркер выражений."""
    __slots__ = ()


class Stmt:
    """Маркер инструкций."""
    __slots__ = ()


class Lvalue:
    """Маркер целей присваивания."""
    __slots__ = ()


class Iterable:
    """Маркер iterable-целей for-цикла."""
    __slots__ = ()


# =============================================================
# Types
# =============================================================

@dataclass(frozen=True, slots=True)
class SimpleType(Type):
    name: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class TupleType(Type):
    items: tuple[Type, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class GenericType(Type):
    name: str
    args: tuple[Type, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class MaybeType(Type):
    inner: Type
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class RefinementType(Type):
    inner: Type
    predicate: Expr
    line: int
    col: int


# =============================================================
# Lvalues и Iterables
# =============================================================

@dataclass(frozen=True, slots=True)
class LvalueIdent(Lvalue):
    name: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class LvalueTuple(Lvalue):
    items: tuple[Lvalue, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class LvalueIndex(Lvalue):
    obj: Lvalue
    index: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class IterableIdent(Iterable):
    name: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class IterableTuple(Iterable):
    items: tuple[Lvalue, ...]
    line: int
    col: int


# =============================================================
# Statements
# =============================================================

@dataclass(frozen=True, slots=True)
class Block(Stmt):
    stmts: tuple[Stmt, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class ExpressionStmt(Stmt):
    expr: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class AssignStmt(Stmt):
    target: Lvalue
    op: str
    value: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class IfStmt(Stmt):
    cond: Expr
    then_branch: Stmt
    else_branch: Stmt | None
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class WhileStmt(Stmt):
    cond: Expr
    body: Stmt
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class ForStmt(Stmt):
    targets: Iterable
    iterable: Expr
    body: Stmt
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class BreakStmt(Stmt):
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class ContinueStmt(Stmt):
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class ReturnStmt(Stmt):
    value: Expr | None
    line: int
    col: int


# =============================================================
# Expressions
# =============================================================

@dataclass(frozen=True, slots=True)
class IntLiteral(Expr):
    value: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class FloatLiteral(Expr):
    value: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class StringLiteral(Expr):
    value: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class CharLiteral(Expr):
    value: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class BoolLiteral(Expr):
    value: bool
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class Name(Expr):
    identifier: str
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class BinaryOp(Expr):
    op: str
    left: Expr
    right: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class UnaryPreOp(Expr):
    op: str
    operand: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class FunctionCall(Expr):
    callee: str
    args: tuple[Expr, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class MethodCall(Expr):
    obj: Expr
    method: str
    args: tuple[Expr, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class Index(Expr):
    obj: Expr
    index: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class MaybeUnwrap(Expr):
    operand: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class Conditional(Expr):
    cond: Expr
    then_branch: Expr
    else_branch: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class ParenExpr(Expr):
    inner: Expr
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class TupleExpr(Expr):
    items: tuple[Expr, ...]
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class ArrayLiteral(Expr):
    items: tuple[Expr, ...]
    line: int
    col: int


# =============================================================
# Param, FunctionDef, Module
# =============================================================

@dataclass(frozen=True, slots=True)
class Param:
    name: str
    type: Type
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class FunctionDef:
    name: str
    params: tuple[Param, ...]
    return_type: Type | None
    body: Block
    line: int
    col: int


@dataclass(frozen=True, slots=True)
class Module:
    functions: tuple[FunctionDef, ...]
    line: int
    col: int
