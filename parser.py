"""Парсер mashiko: lark + наш лексер → AST."""

from __future__ import annotations

from typing import Any, Iterator

import lark
from lark import Lark, Token as LarkToken, Transformer
from lark.lexer import Lexer as LarkLexer

import syntax as ast
from lexer import Lexer as MashikoLexer


# =============================================================
# Лексер-обёртка
# =============================================================

class _MashikoLarkLexer(LarkLexer):
    """Подкласс lark-лексера, который выдаёт токены от нашего lexer.Lexer.

    Терминалы грамматики матчатся по имени: `Token.type.name` (например
    `IDENT`, `INT`, `LPAREN`, `LANGLE`) сравнивается с именем терминала
    из `mashiko.lark`. Regex-паттерны терминалов lark'ом не используются.

    `__future_interface__ = 1` переключает lark на новый API:
    `lex(self, lexer_state, parser_state)`. Иначе (default=0) lark
    зовёт `lex(self, text)`, и старый интерфейс ломает позиции.
    """

    __future_interface__ = 1

    def __init__(self, lexer_conf: Any) -> None:
        pass

    def lex(self, lexer_state: Any, parser_state: Any) -> Iterator[LarkToken]:
        src = lexer_state.text
        if hasattr(src, "text"):
            src = src.text
        for tok in MashikoLexer(src).tokenize():
            if tok.type.name == "EOF":
                continue
            yield LarkToken(
                tok.type.name,
                tok.value,
                line=tok.line,
                column=tok.col,
            )


# =============================================================
# Парсер (singleton)
# =============================================================

_PARSER = Lark.open(
    "mashiko.lark",
    parser="earley",
    lexer=_MashikoLarkLexer,
)


# =============================================================
# Transformer: Lark Tree → ast.*
# =============================================================

class _MashikoTransformer(Transformer):
    """Преобразует Lark-дерево в `ast.Module` и вложенные `ast.*`-узлы.

    Все позиции (`line`, `col`) берутся из items[0] — первый элемент
    в каждом правиле всегда либо именованный токен, либо уже
    трансформированный AST-узел с собственными line/col.
    """

    # ----- args / params (вернуть список детей) -----

    def args(self, items: list[Any]) -> list[Any]:
        return list(items)

    def params(self, items: list[Any]) -> list[Any]:
        return list(items)

    # ----- inline-обёртки (single-child правила без алиаса) -----

    def lvalue(self, items: list[Any]) -> Any:
        return items[0]

    def iterable(self, items: list[Any]) -> Any:
        return items[0]

    def statement(self, items: list[Any]) -> Any:
        return items[0]

    # ----- Types -----

    def simple_type(self, items: list[Any]) -> ast.Type:
        tok = items[0]
        return ast.SimpleType(name=tok.value, line=tok.line, col=tok.column)

    def tuple_type(self, items: list[Any]) -> ast.Type:
        types = tuple(i for i in items if isinstance(i, ast.Type))
        return ast.TupleType(items=types, line=items[0].line, col=items[0].column)

    def generic_type(self, items: list[Any]) -> ast.Type:
        name = items[0].value
        args = tuple(i for i in items if isinstance(i, ast.Type))
        return ast.GenericType(name=name, args=args, line=items[0].line, col=items[0].column)

    def maybe_type(self, items: list[Any]) -> ast.Type:
        return ast.MaybeType(inner=items[0], line=items[0].line, col=items[0].col)

    def refinement_type(self, items: list[Any]) -> ast.Type:
        return ast.RefinementType(
            inner=items[1],
            predicate=items[3],
            line=items[0].line,
            col=items[0].column,
        )

    # ----- Param -----

    def typed_field(self, items: list[Any]) -> ast.Param:
        return ast.Param(
            name=items[0].value,
            type=items[2],
            line=items[0].line,
            col=items[0].column,
        )

    # ----- Lvalues / Iterables -----

    def lvalue_ident(self, items: list[Any]) -> ast.Lvalue:
        return ast.LvalueIdent(name=items[0].value, line=items[0].line, col=items[0].column)

    def lvalue_tuple(self, items: list[Any]) -> ast.Lvalue:
        lv = tuple(i for i in items if isinstance(i, ast.Lvalue))
        return ast.LvalueTuple(items=lv, line=items[0].line, col=items[0].column)

    def lvalue_index(self, items: list[Any]) -> ast.Lvalue:
        return ast.LvalueIndex(
            obj=items[0],
            index=items[2],
            line=items[0].line,
            col=items[0].col,
        )

    def iterable_ident(self, items: list[Any]) -> ast.Iterable:
        return ast.IterableIdent(name=items[0].value, line=items[0].line, col=items[0].column)

    def iterable_tuple(self, items: list[Any]) -> ast.Iterable:
        lv = tuple(i for i in items if isinstance(i, ast.Lvalue))
        return ast.IterableTuple(items=lv, line=items[0].line, col=items[0].column)

    # ----- Statements -----

    def block(self, items: list[Any]) -> ast.Stmt:
        stmts = tuple(items[1:-1])
        return ast.Block(stmts=stmts, line=items[0].line, col=items[0].column)

    def expression_stmt(self, items: list[Any]) -> ast.Stmt:
        return ast.ExpressionStmt(expr=items[0], line=items[0].line, col=items[0].col)

    def assign_stmt(self, items: list[Any]) -> ast.Stmt:
        return ast.AssignStmt(
            target=items[0],
            op=items[1].value,
            value=items[2],
            line=items[0].line,
            col=items[0].col,
        )

    def if_stmt(self, items: list[Any]) -> ast.Stmt:
        cond = items[1]
        then_branch = items[2]
        else_branch = items[4] if len(items) == 5 else None
        return ast.IfStmt(
            cond=cond,
            then_branch=then_branch,
            else_branch=else_branch,
            line=items[0].line,
            col=items[0].column,
        )

    def while_stmt(self, items: list[Any]) -> ast.Stmt:
        return ast.WhileStmt(
            cond=items[1],
            body=items[2],
            line=items[0].line,
            col=items[0].column,
        )

    def for_stmt(self, items: list[Any]) -> ast.Stmt:
        return ast.ForStmt(
            targets=items[1],
            iterable=items[3],
            body=items[4],
            line=items[0].line,
            col=items[0].column,
        )

    def break_stmt(self, items: list[Any]) -> ast.Stmt:
        return ast.BreakStmt(line=items[0].line, col=items[0].column)

    def continue_stmt(self, items: list[Any]) -> ast.Stmt:
        return ast.ContinueStmt(line=items[0].line, col=items[0].column)

    def return_stmt(self, items: list[Any]) -> ast.Stmt:
        value = items[1] if len(items) == 3 else None
        return ast.ReturnStmt(value=value, line=items[0].line, col=items[0].column)

    # ----- Expressions: literals -----

    def int_literal(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.IntLiteral(value=tok.value, line=tok.line, col=tok.column)

    def float_literal(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.FloatLiteral(value=tok.value, line=tok.line, col=tok.column)

    def string_literal(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.StringLiteral(value=tok.value, line=tok.line, col=tok.column)

    def char_literal(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.CharLiteral(value=tok.value, line=tok.line, col=tok.column)

    def true_literal(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.BoolLiteral(value=True, line=tok.line, col=tok.column)

    def false_literal(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.BoolLiteral(value=False, line=tok.line, col=tok.column)

    # ----- Expressions: refs/calls -----

    def name(self, items: list[Any]) -> ast.Expr:
        tok = items[0]
        return ast.Name(identifier=tok.value, line=tok.line, col=tok.column)

    def function_call(self, items: list[Any]) -> ast.Expr:
        callee = items[0].value
        args = items[1] if isinstance(items[1], list) else []
        return ast.FunctionCall(
            callee=callee,
            args=tuple(args),
            line=items[0].line,
            col=items[0].column,
        )

    def method_call(self, items: list[Any]) -> ast.Expr:
        obj = items[0]
        method = items[2].value
        args = items[3] if isinstance(items[3], list) else []
        return ast.MethodCall(
            obj=obj,
            method=method,
            args=tuple(args),
            line=items[0].line,
            col=items[0].col,
        )

    def indexing(self, items: list[Any]) -> ast.Expr:
        return ast.Index(
            obj=items[0],
            index=items[2],
            line=items[0].line,
            col=items[0].col,
        )

    def maybe_unwrap(self, items: list[Any]) -> ast.Expr:
        return ast.MaybeUnwrap(operand=items[0], line=items[0].line, col=items[0].col)

    # ----- Expressions: grouping/sequences -----

    def paren_expr(self, items: list[Any]) -> ast.Expr:
        return ast.ParenExpr(inner=items[1], line=items[0].line, col=items[0].column)

    def tuple_expr(self, items: list[Any]) -> ast.Expr:
        ex = tuple(i for i in items if isinstance(i, ast.Expr))
        return ast.TupleExpr(items=ex, line=items[0].line, col=items[0].column)

    def array_literal(self, items: list[Any]) -> ast.Expr:
        ex = tuple(i for i in items if isinstance(i, ast.Expr))
        return ast.ArrayLiteral(items=ex, line=items[0].line, col=items[0].column)

    # ----- Expressions: operators -----

    def binary_op(self, items: list[Any]) -> ast.Expr:
        op_tok = items[1]
        return ast.BinaryOp(
            op=op_tok.value,
            left=items[0],
            right=items[2],
            line=op_tok.line,
            col=op_tok.column,
        )

    def unary_pre_op(self, items: list[Any]) -> ast.Expr:
        op_tok = items[0]
        return ast.UnaryPreOp(
            op=op_tok.value,
            operand=items[1],
            line=op_tok.line,
            col=op_tok.column,
        )

    def conditional(self, items: list[Any]) -> ast.Expr:
        return ast.Conditional(
            cond=items[0],
            then_branch=items[2],
            else_branch=items[4],
            line=items[0].line,
            col=items[0].col,
        )

    # ----- Function / Module -----

    def function(self, items: list[Any]) -> ast.FunctionDef:
        name = items[1].value
        block = items[-1]
        params = next(
            (
                list(t)
                for t in items
                if isinstance(t, list) and all(isinstance(p, ast.Param) for p in t)
            ),
            [],
        )
        return_type = next(
            (t for t in items if isinstance(t, ast.Type)),
            None,
        )
        return ast.FunctionDef(
            name=name,
            params=tuple(params),
            return_type=return_type,
            body=block,
            line=items[0].line,
            col=items[0].column,
        )

    def module(self, items: list[Any]) -> ast.Module:
        if items:
            first = items[0]
            line, col = first.line, first.col
        else:
            line, col = 0, 0
        return ast.Module(functions=tuple(items), line=line, col=col)


# =============================================================
# Entry point
# =============================================================

def parse(source: str) -> ast.Module:
    """Парсит исходник mashiko и возвращает `ast.Module`."""
    tree = _PARSER.parse(source)
    return _MashikoTransformer().transform(tree)
