"""AST языка mashiko.

Все узлы — frozen dataclass'ы со слотами. Span отделён от самих узлов
и приклеивается через обёртку `Spanned[T]`: `Spanned(node, span)`.
Так узел сам по себе не несёт информации о позиции — span добавляется
в момент парсинга. Это убирает повторяющееся поле `span` из каждого
класса и делает span явной частью структуры данных.

Группировочные классы (`Type`, `Expr`, `Stmt`, `Lvalue`, `Iterable`)
живут на самих узлах — нужны для isinstance-проверок и type hints.
Поскольку span приклеивается через `Spanned`, проверки маркера
делаются на `.node`, а не на самом `Spanned`:

    spanned = Spanned(IntLiteral("42"), span)
    isinstance(spanned.node, Expr)   # True
    isinstance(spanned, Expr)        # False

Имена бинарных/унарных операторов — строки, совпадающие с shape-токенами
лексера ("+", "==", "&&", ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


# =============================================================
# Span: позиции в исходнике
# =============================================================

@dataclass(frozen=True, slots=True)
class Span:
    """Позиция конструкции в исходнике: start и end (index, line, col).

    `index` — символьный offset в исходнике (0-based).
    `line`, `col` — 1-based; `col` — символ в строке (после \\n сбрасывается в 1).
    End — exclusive: указывает на позицию СРАЗУ ПОСЛЕ последнего символа
    конструкции. Так `src[span.start_index:span.end_index]` — это ровно
    текст конструкции (Python-стиль срезов). Аналогично end_line/end_col —
    это line/col позиции "следующего за последним символом" (для
    однострочной конструкции end_col = start_col + длина).
    """
    start_index: int
    start_line: int
    start_col: int
    end_index: int
    end_line: int
    end_col: int


# =============================================================
# Spanned: обёртка узла + span
# =============================================================

@dataclass(frozen=True, slots=True)
class Spanned(Generic[T]):
    """Узел AST с прикреплённым span.

    `node` — сам узел (любой, реализующий один из маркеров Expr/Stmt/
    Lvalue/Iterable, либо Param/FunctionDef/Module/Block — без маркера).
    `span` — его позиция в исходнике.
    """
    node: T
    span: Span


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
# Операторы (shape-имена, как в лексере)
# =============================================================

class BinOp(Enum):
    """Бинарные операторы в `BinaryOp.op`.

    Имена — shape (как в lexer.TokenType), а не семантика:
    `+` это `PLUS`, `<` это `LANGLE`, `&&` это `AMP_AMP`.
    `value` — исходная запись в исходнике.
    """
    PIPE_PIPE = "||"
    AMP_AMP = "&&"
    PIPE = "|"
    CARET = "^"
    AMP = "&"
    EQEQ = "=="
    BANG_EQ = "!="
    LANGLE = "<"
    RANGLE = ">"
    LE = "<="
    GE = ">="
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"


class UnaryOp(Enum):
    """Префиксные унарные операторы в `UnaryPreOp.op`.

    Постфиксные (`?` — MaybeUnwrap) — отдельный AST-узел, не сюда.
    """
    MINUS = "-"
    BANG = "!"


class AssignOp(Enum):
    """Операторы в `AssignStmt.op`."""
    EQ = "="
    PLUS_EQ = "+="
    MINUS_EQ = "-="
    STAR_EQ = "*="
    SLASH_EQ = "/="
    PERCENT_EQ = "%="


# =============================================================
# Types
# =============================================================

@dataclass(frozen=True, slots=True)
class SimpleType(Type):
    name: str


@dataclass(frozen=True, slots=True)
class TupleType(Type):
    items: tuple[Spanned[Type], ...]


@dataclass(frozen=True, slots=True)
class GenericType(Type):
    name: str
    args: tuple[Spanned[Type], ...]


@dataclass(frozen=True, slots=True)
class MaybeType(Type):
    inner: Spanned[Type]


@dataclass(frozen=True, slots=True)
class RefinementType(Type):
    inner: Spanned[Type]
    predicate: Spanned[Expr]


# =============================================================
# Lvalues
# =============================================================

@dataclass(frozen=True, slots=True)
class LvalueIdent(Lvalue):
    name: str


@dataclass(frozen=True, slots=True)
class LvalueTuple(Lvalue):
    items: tuple[Spanned[Lvalue], ...]


@dataclass(frozen=True, slots=True)
class LvalueIndex(Lvalue):
    obj: Spanned[Lvalue]
    index: Spanned[Expr]


# =============================================================
# Iterables
# =============================================================

@dataclass(frozen=True, slots=True)
class IterableIdent(Iterable):
    name: str


@dataclass(frozen=True, slots=True)
class IterableTuple(Iterable):
    items: tuple[Spanned[Lvalue], ...]


# =============================================================
# Statements
# =============================================================

@dataclass(frozen=True, slots=True)
class Block(Stmt):
    stmts: tuple[Spanned[Stmt], ...]


@dataclass(frozen=True, slots=True)
class ExpressionStmt(Stmt):
    expr: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class AssignStmt(Stmt):
    target: Spanned[Lvalue]
    op: AssignOp
    value: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class IfStmt(Stmt):
    cond: Spanned[Expr]
    then_branch: Spanned[Stmt]
    else_branch: Spanned[Stmt] | None


@dataclass(frozen=True, slots=True)
class WhileStmt(Stmt):
    cond: Spanned[Expr]
    body: Spanned[Stmt]


@dataclass(frozen=True, slots=True)
class ForStmt(Stmt):
    targets: Spanned[Iterable]
    iterable: Spanned[Expr]
    body: Spanned[Stmt]


@dataclass(frozen=True, slots=True)
class BreakStmt(Stmt):
    pass


@dataclass(frozen=True, slots=True)
class ContinueStmt(Stmt):
    pass


@dataclass(frozen=True, slots=True)
class ReturnStmt(Stmt):
    value: Spanned[Expr] | None


# =============================================================
# Expressions
# =============================================================

@dataclass(frozen=True, slots=True)
class IntLiteral(Expr):
    value: str


@dataclass(frozen=True, slots=True)
class FloatLiteral(Expr):
    value: str


@dataclass(frozen=True, slots=True)
class StringLiteral(Expr):
    value: str


@dataclass(frozen=True, slots=True)
class CharLiteral(Expr):
    value: str


@dataclass(frozen=True, slots=True)
class BoolLiteral(Expr):
    value: bool


@dataclass(frozen=True, slots=True)
class Name(Expr):
    identifier: str


@dataclass(frozen=True, slots=True)
class BinaryOp(Expr):
    op: BinOp
    left: Spanned[Expr]
    right: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class UnaryPreOp(Expr):
    op: UnaryOp
    operand: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class FunctionCall(Expr):
    callee: str
    args: tuple[Spanned[Expr], ...]


@dataclass(frozen=True, slots=True)
class MethodCall(Expr):
    obj: Spanned[Expr]
    method: str
    args: tuple[Spanned[Expr], ...]


@dataclass(frozen=True, slots=True)
class Index(Expr):
    obj: Spanned[Expr]
    index: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class MaybeUnwrap(Expr):
    operand: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class Conditional(Expr):
    cond: Spanned[Expr]
    then_branch: Spanned[Expr]
    else_branch: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class ParenExpr(Expr):
    inner: Spanned[Expr]


@dataclass(frozen=True, slots=True)
class TupleExpr(Expr):
    items: tuple[Spanned[Expr], ...]


@dataclass(frozen=True, slots=True)
class ArrayLiteral(Expr):
    items: tuple[Spanned[Expr], ...]


# =============================================================
# Param, FunctionDef, Module
# =============================================================

@dataclass(frozen=True, slots=True)
class Param:
    name: str
    type: Spanned[Type]


@dataclass(frozen=True, slots=True)
class FunctionDef:
    name: str
    params: tuple[Spanned[Param], ...]
    return_type: Spanned[Type] | None
    body: Spanned[Block]


@dataclass(frozen=True, slots=True)
class Module:
    functions: tuple[Spanned[FunctionDef], ...]
    classes: tuple[Spanned[ClassDef], ...]
    interfaces: tuple[Spanned[InterfaceDef], ...]


@dataclass(frozen=True, slots=True)
class ConstructorDef:
    """Конструктор класса: `constructor(params) { body }`."""
    params: tuple[Spanned[Param], ...]
    body: Spanned[Block]


@dataclass(frozen=True, slots=True)
class InterfaceMethodDef:
    """Объявление метода интерфейса: `name(types): RetType;`.

    В отличие от методов класса, параметры интерфейса безымянные — только
    типы (по грамматике `INTERFACE LPAREN TYPE* RPAREN`). Имена параметров
    остаются на совести реализующего класса.
    """
    name: str
    param_types: tuple[Spanned[Type], ...]
    return_type: Spanned[Type] | None


@dataclass(frozen=True, slots=True)
class InterfaceDef:
    """Объявление интерфейса: `interface Name [: Parent1, Parent2, ...] { methods }`.

    `parents` — список имён родительских интерфейсов (наследование интерфейсов),
    `methods` — только сигнатуры (тела нет, класс-реализатор их определяет).
    """
    name: str
    parents: tuple[str, ...]
    methods: tuple[Spanned[InterfaceMethodDef], ...]


@dataclass(frozen=True, slots=True)
class ClassDef:
    """Объявление класса: `class Name [: Iface1, Iface2, ...] { fields; methods; constructors }`.

    `fields` — поля класса (`name: Type;`), `methods` — обычные методы как
    `FunctionDef` без `func`-префикса, `constructors` — список конструкторов
    (грамматика допускает ноль и более), `parents` — имена реализуемых
    интерфейсов.
    """
    name: str
    parents: tuple[str, ...]
    fields: tuple[Spanned[Param], ...]
    methods: tuple[Spanned[FunctionDef], ...]
    constructors: tuple[Spanned[ConstructorDef], ...]
