"""Печатает AST-узел mashiko в виде дерева (как bash `tree`)."""

from __future__ import annotations

import dataclasses
import os
import sys
from enum import Enum
from typing import IO, Any

from . import syntax as ast


# =============================================================
# Объявление цветов раскраски (ANSI).
# Уважаем NO_COLOR и не-TTY stdout — иначе escape-коды попадут в файл.
# =============================================================

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"

_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_CYAN = "\033[36m"

_BR_RED = "\033[91m"
_BR_GREEN = "\033[92m"
_BR_YELLOW = "\033[93m"
_BR_BLUE = "\033[94m"
_BR_MAGENTA = "\033[95m"
_BR_CYAN = "\033[96m"

# Имя класса → цвет самого узла.
_NODE_COLORS: dict[str, str] = {
    # Декларации
    "Module": _BOLD + _BR_GREEN,
    "FunctionDef": _BOLD + _BR_GREEN,
    "Param": _BR_GREEN,
    # Типы
    "SimpleType": _GREEN,
    "TupleType": _GREEN,
    "GenericType": _GREEN,
    "MaybeType": _GREEN,
    "RefinementType": _GREEN,
    # Lvalues / Iterables
    "LvalueIdent": _YELLOW,
    "LvalueTuple": _YELLOW,
    "LvalueIndex": _YELLOW,
    "IterableIdent": _YELLOW,
    "IterableTuple": _YELLOW,
    # Statements
    "Block": _BLUE,
    "ExpressionStmt": _BLUE,
    "AssignStmt": _BR_BLUE,
    "IfStmt": _BLUE,
    "WhileStmt": _BLUE,
    "ForStmt": _BLUE,
    "BreakStmt": _BLUE,
    "ContinueStmt": _BLUE,
    "ReturnStmt": _BR_BLUE,
    # Литералы
    "IntLiteral": _BR_RED,
    "FloatLiteral": _BR_RED,
    "StringLiteral": _BR_RED,
    "CharLiteral": _BR_RED,
    "BoolLiteral": _BR_RED,
    # Бинарные/унарные операторы
    "BinaryOp": _MAGENTA,
    "UnaryPreOp": _MAGENTA,
    # Вызовы
    "FunctionCall": _BR_MAGENTA,
    "MethodCall": _BR_MAGENTA,
    # Остальные выражения
    "Name": _CYAN,
    "Index": _CYAN,
    "MaybeUnwrap": _CYAN,
    "Conditional": _CYAN,
    "ParenExpr": _CYAN,
    "TupleExpr": _CYAN,
    "ArrayLiteral": _CYAN,
}

# Цвета для скаляров в полях узла.
_OP_NAME_COLOR = _BR_MAGENTA          # поле op= в BinaryOp/UnaryPreOp
_IDENT_COLOR = _BR_YELLOW             # строковые имена (name/identifier/callee/method/...)
_NUM_COLOR = _BR_CYAN                 # числа/булеаны
_FIELD_NAME_COLOR = "\033[90m"        # dim gray — имя поля
_TREE_COLOR = "\033[90m"              # приглушённые box-drawing символы


def _use_color(file: IO[str]) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return getattr(file, "isatty", lambda: False)()


def _paint(text: str, color_on: bool, color: str = "") -> str:
    if not color_on or not color or not text:
        return text
    return f"{color}{text}{_RESET}"


def _unwrap(node: Any) -> Any:
    """Если node — Spanned, вернуть .node; иначе сам node.

    `Spanned` — обёртка, невидимая при печати: имя класса и поля берутся
    из вложенного узла.
    """
    return node.node if isinstance(node, ast.Spanned) else node


# Символы box-drawing — те же, что у bash `tree`.
_LAST = "└── "
_BRANCH = "├── "
_VERT = "│   "
_BLANK = "    "


def print_ast(node: Any, file: IO[str] | None = None) -> None:
    """Печатает `node` (любой ast.* из `syntax.py` или ast.Spanned) в `file`.

    Узел выводится одной строкой `ClassName field=value field=value …`:
    скаляры — через пробел; AST-дети опускаются (рисуются ниже с отступом
    и угловыми/прямыми ветками). Цвет имени класса берётся из
    _NODE_COLORS; скаляры подсвечиваются по типу (op/идентификатор/число).
    `ast.Spanned`-обёртка снимается — печатается вложенный узел.
    """
    if file is None:
        file = sys.stdout
    color_on = _use_color(file)
    print(_label(node, color_on), file=file)
    _print_children(node, "", file, color_on)


def _print_children(node: Any, prefix: str, file: IO[str], color_on: bool) -> None:
    children = list(_iter_children(node))
    for i, child in enumerate(children):
        is_last = i == len(children) - 1
        _print_node(child, prefix, is_last, file, color_on)


def _print_node(node: Any, prefix: str, is_last: bool, file: IO[str], color_on: bool) -> None:
    connector = _LAST if is_last else _BRANCH
    line = (
        _paint(prefix, color_on, _TREE_COLOR)
        + _paint(connector, color_on, _TREE_COLOR)
        + _label(node, color_on)
    )
    print(line, file=file)
    new_prefix = prefix + (_BLANK if is_last else _VERT)
    _print_children(node, new_prefix, file, color_on)


def _label(node: Any, color_on: bool) -> str:
    inner = _unwrap(node)
    cls_name = type(inner).__name__
    parts = [_paint(cls_name, color_on, _NODE_COLORS.get(cls_name, ""))]
    for field in dataclasses.fields(inner):
        value = getattr(inner, field.name)
        if _is_ast_child(value) or isinstance(value, (tuple, list)):
            continue
        field_name = _paint(field.name, color_on, _FIELD_NAME_COLOR)
        value_str = _format_scalar(value, color_on)
        parts.append(f"{field_name}={value_str}")
    return " ".join(parts)


def _format_scalar(v: Any, color_on: bool) -> str:
    if isinstance(v, Enum):
        return _paint(v.name, color_on, _OP_NAME_COLOR)
    if isinstance(v, str):
        return _paint(repr(v), color_on, _IDENT_COLOR)
    if isinstance(v, bool):
        return _paint(str(v), color_on, _NUM_COLOR)
    if isinstance(v, (int, float)):
        return _paint(str(v), color_on, _NUM_COLOR)
    return str(v)


def _iter_children(node: Any):
    """AST-дети узла; для tuple/list-полей — каждый элемент по отдельности."""
    inner = _unwrap(node)
    for field in dataclasses.fields(inner):
        value = getattr(inner, field.name)
        if _is_ast_child(value):
            yield value
        elif isinstance(value, (tuple, list)):
            for elem in value:
                if _is_ast_child(elem):
                    yield elem


def _is_ast_child(v: Any) -> bool:
    """True для AST-узлов (Spanned-обёртки и bare-узлов — Param/Type/...).

    В новом дизайне span живёт на `Spanned`, а не на самом узле, поэтому
    dataclass-с-полем-`.span` уже недостаточно. Достаточно "это dataclass":
    любой AST-узел (Expr/Stmt/Lvalue/Iterable/Type/Param/FunctionDef/Module/
    Block) — это dataclass, как и сам `Spanned` и `Span` (Span мы
    отфильтровываем по имени поля, см. _label/_iter_children).
    """
    if v is None:
        return False
    if isinstance(v, ast.Spanned):
        return True
    if dataclasses.is_dataclass(v):
        return True
    return False
