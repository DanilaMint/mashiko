"""Парсер mashiko: lark + наш лексер → AST."""

from __future__ import annotations

import os
from typing import Any, Iterator

from lark import Lark, Transformer
from lark import Token as LarkToken
from lark.lexer import Lexer as LarkLexer

from . import syntax as ast
from .lexer import Lexer as MashikoLexer

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
    lark сам проставляет LarkToken.start_pos и LarkToken.end_pos на
    основе счётчика в lexer_state.pos и длины токена.
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
            lt = LarkToken(
                tok.type.name,
                tok.value,
                line=tok.line,
                column=tok.col,
            )
            # lark не заполняет start_pos для external-токенов;
            # прокидываем byte-offset из нашего lexer.Token.
            lt.start_pos = tok.index
            yield lt


# =============================================================
# Парсер (singleton)
# =============================================================

_LARK_PATH = os.path.join(os.path.dirname(__file__), "mashiko.lark")

_PARSER = Lark.open(
    _LARK_PATH,
    parser="earley",
    lexer=_MashikoLarkLexer,
)


# =============================================================
# Lark-токен (по имени) → AST-enum
# =============================================================
# В Transformer'е операторный токен приходит как LarkToken с .type == str
# (имя терминала, ровно TokenType.name из lexer.py). Маппим в BinOp /
# UnaryOp / AssignOp, чтобы AST хранил enum'ы, а не сырые строки.

_BIN_OP_FROM_TOKEN: dict[str, ast.BinOp] = {
    "PIPE_PIPE": ast.BinOp.PIPE_PIPE,
    "AMP_AMP": ast.BinOp.AMP_AMP,
    "PIPE": ast.BinOp.PIPE,
    "CARET": ast.BinOp.CARET,
    "AMP": ast.BinOp.AMP,
    "EQEQ": ast.BinOp.EQEQ,
    "BANG_EQ": ast.BinOp.BANG_EQ,
    "LANGLE": ast.BinOp.LANGLE,
    "RANGLE": ast.BinOp.RANGLE,
    "LE": ast.BinOp.LE,
    "GE": ast.BinOp.GE,
    "PLUS": ast.BinOp.PLUS,
    "MINUS": ast.BinOp.MINUS,
    "STAR": ast.BinOp.STAR,
    "SLASH": ast.BinOp.SLASH,
    "PERCENT": ast.BinOp.PERCENT,
}

_UNARY_OP_FROM_TOKEN: dict[str, ast.UnaryOp] = {
    "MINUS": ast.UnaryOp.MINUS,
    "BANG": ast.UnaryOp.BANG,
}

_ASSIGN_OP_FROM_TOKEN: dict[str, ast.AssignOp] = {
    "EQ": ast.AssignOp.EQ,
    "PLUS_EQ": ast.AssignOp.PLUS_EQ,
    "MINUS_EQ": ast.AssignOp.MINUS_EQ,
    "STAR_EQ": ast.AssignOp.STAR_EQ,
    "SLASH_EQ": ast.AssignOp.SLASH_EQ,
    "PERCENT_EQ": ast.AssignOp.PERCENT_EQ,
}


# =============================================================
# Span-helpers
# =============================================================


def _pos_to_linecol(src: str, pos: int) -> tuple[int, int]:
    """Возвращает (line, col) для символьного offset `pos` в `src` (1-based)."""
    line = 1
    col = 1
    limit = min(pos, len(src))
    for i in range(limit):
        if src[i] == "\n":
            line += 1
            col = 1
        else:
            col += 1
    return line, col


def _token_end_linecol(tok: LarkToken, src: str) -> tuple[int, int]:
    """end_line/end_col для LarkToken.

    lark не заполняет `end_pos` автоматически для external-токенов, поэтому
    считаем конец как start_pos + len(value).
    """
    end_pos = tok.start_pos + len(tok.value)
    return _pos_to_linecol(src, end_pos)


def _start_of(item: Any) -> tuple[int, int, int]:
    """(index, line, col) начала `item` — LarkToken, Span, Spanned или список."""
    if isinstance(item, LarkToken):
        return (item.start_pos, item.line, item.column)
    if isinstance(item, ast.Span):
        return (item.start_index, item.start_line, item.start_col)
    if isinstance(item, ast.Spanned):
        sp = item.span
        return (sp.start_index, sp.start_line, sp.start_col)
    if isinstance(item, (list, tuple)):
        for sub in item:
            if sub is not None:
                return _start_of(sub)
    raise TypeError(f"cannot get start of {item!r}")


def _end_of(item: Any, src: str) -> tuple[int, int, int]:
    """(index, line, col) конца `item` — LarkToken, Span, Spanned или список."""
    if isinstance(item, LarkToken):
        end_index = item.start_pos + len(item.value)
        end_line, end_col = _token_end_linecol(item, src)
        return (end_index, end_line, end_col)
    if isinstance(item, ast.Span):
        return (item.end_index, item.end_line, item.end_col)
    if isinstance(item, ast.Spanned):
        sp = item.span
        return (sp.end_index, sp.end_line, sp.end_col)
    if isinstance(item, (list, tuple)):
        for sub in reversed(item):
            if sub is not None:
                return _end_of(sub, src)
    raise TypeError(f"cannot get end of {item!r}")


def _span(items: list[Any], src: str) -> ast.Span:
    """Span для конструкции, заданной списком children из lark Transformer.

    Start берётся из первого непустого ребёнка, end — из последнего.
    Дети могут быть LarkToken'ы, Spanned-обёртки или вложенные списки.
    Пустые списки/None игнорируются, чтобы function_call без аргументов
    давал end == start (а не падал на пустом list).
    """
    flat: list[Any] = []
    for it in items:
        if it is None:
            continue
        if isinstance(it, (list, tuple)) and len(it) == 0:
            continue
        flat.append(it)
    if not flat:
        return ast.Span(0, 0, 0, 0, 0, 0)
    s = _start_of(flat[0])
    e = _end_of(flat[-1], src)
    return ast.Span(s[0], s[1], s[2], e[0], e[1], e[2])


# =============================================================
# Transformer: Lark Tree → ast.*
# =============================================================


class _MashikoTransformer(Transformer):
    """Преобразует Lark-дерево в `ast.Spanned[ast.Module]` и вложенные узлы.

    Каждый constructed-узел оборачивается в `ast.Spanned` со span'ом от
    первого до последнего ребёнка. Типы в текущем дизайне НЕ оборачиваются
    (только `RefinementType.predicate` — `Spanned[Expr]`, потому что это
    выражение внутри типа).
    """

    def __init__(self, src: str) -> None:
        super().__init__()
        self.src = src

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

    # ----- Types (оборачиваются в Spanned — span нужен для диагностик) -----

    def simple_type(self, items: list[Any]) -> ast.Spanned[ast.SimpleType]:
        tok = items[0]
        return ast.Spanned(
            ast.SimpleType(name=tok.value),
            _span(items, self.src),
        )

    def tuple_type(self, items: list[Any]) -> ast.Spanned[ast.TupleType]:
        types = tuple(i for i in items if isinstance(i, ast.Spanned))
        return ast.Spanned(
            ast.TupleType(items=types),
            _span(items, self.src),
        )

    def generic_type(self, items: list[Any]) -> ast.Spanned[ast.GenericType]:
        name = items[0].value
        args = tuple(i for i in items if isinstance(i, ast.Spanned))
        return ast.Spanned(
            ast.GenericType(name=name, args=args),
            _span(items, self.src),
        )

    def maybe_type(self, items: list[Any]) -> ast.Spanned[ast.MaybeType]:
        return ast.Spanned(
            ast.MaybeType(inner=items[0]),
            _span(items, self.src),
        )

    def refinement_type(self, items: list[Any]) -> ast.Spanned[ast.RefinementType]:
        return ast.Spanned(
            ast.RefinementType(inner=items[1], predicate=items[3]),
            _span(items, self.src),
        )

    # ----- Param -----

    def typed_field(self, items: list[Any]) -> ast.Spanned[ast.Param]:
        return ast.Spanned(
            ast.Param(name=items[0].value, type=items[2]),
            _span(items, self.src),
        )

    # ----- Lvalues / Iterables -----

    def lvalue_ident(self, items: list[Any]) -> ast.Spanned[ast.LvalueIdent]:
        return ast.Spanned(
            ast.LvalueIdent(name=items[0].value),
            _span(items, self.src),
        )

    def lvalue_tuple(self, items: list[Any]) -> ast.Spanned[ast.LvalueTuple]:
        lv = tuple(i for i in items if isinstance(i, ast.Spanned))
        return ast.Spanned(
            ast.LvalueTuple(items=lv),
            _span(items, self.src),
        )

    def lvalue_index(self, items: list[Any]) -> ast.Spanned[ast.LvalueIndex]:
        return ast.Spanned(
            ast.LvalueIndex(obj=items[0], index=items[2]),
            _span(items, self.src),
        )

    def iterable_ident(self, items: list[Any]) -> ast.Spanned[ast.IterableIdent]:
        return ast.Spanned(
            ast.IterableIdent(name=items[0].value),
            _span(items, self.src),
        )

    def iterable_tuple(self, items: list[Any]) -> ast.Spanned[ast.IterableTuple]:
        lv = tuple(i for i in items if isinstance(i, ast.Spanned))
        return ast.Spanned(
            ast.IterableTuple(items=lv),
            _span(items, self.src),
        )

    # ----- Statements -----

    def block(self, items: list[Any]) -> ast.Spanned[ast.Block]:
        stmts = tuple(items[1:-1])
        return ast.Spanned(
            ast.Block(stmts=stmts),
            _span(items, self.src),
        )

    def expression_stmt(self, items: list[Any]) -> ast.Spanned[ast.ExpressionStmt]:
        return ast.Spanned(
            ast.ExpressionStmt(expr=items[0]),
            _span(items, self.src),
        )

    def assign_stmt(self, items: list[Any]) -> ast.Spanned[ast.AssignStmt]:
        return ast.Spanned(
            ast.AssignStmt(
                target=items[0],
                op=_ASSIGN_OP_FROM_TOKEN[items[1].type],
                value=items[2],
            ),
            _span(items, self.src),
        )

    def if_stmt(self, items: list[Any]) -> ast.Spanned[ast.IfStmt]:
        cond = items[1]
        then_branch = items[2]
        else_branch = items[4] if len(items) == 5 else None
        return ast.Spanned(
            ast.IfStmt(
                cond=cond,
                then_branch=then_branch,
                else_branch=else_branch,
            ),
            _span(items, self.src),
        )

    def while_stmt(self, items: list[Any]) -> ast.Spanned[ast.WhileStmt]:
        return ast.Spanned(
            ast.WhileStmt(cond=items[1], body=items[2]),
            _span(items, self.src),
        )

    def for_stmt(self, items: list[Any]) -> ast.Spanned[ast.ForStmt]:
        return ast.Spanned(
            ast.ForStmt(
                targets=items[1],
                iterable=items[3],
                body=items[4],
            ),
            _span(items, self.src),
        )

    def break_stmt(self, items: list[Any]) -> ast.Spanned[ast.BreakStmt]:
        return ast.Spanned(
            ast.BreakStmt(),
            _span(items, self.src),
        )

    def continue_stmt(self, items: list[Any]) -> ast.Spanned[ast.ContinueStmt]:
        return ast.Spanned(
            ast.ContinueStmt(),
            _span(items, self.src),
        )

    def return_stmt(self, items: list[Any]) -> ast.Spanned[ast.ReturnStmt]:
        value = items[1] if len(items) == 3 else None
        return ast.Spanned(
            ast.ReturnStmt(value=value),
            _span(items, self.src),
        )

    # ----- Expressions: literals -----

    def int_literal(self, items: list[Any]) -> ast.Spanned[ast.IntLiteral]:
        tok = items[0]
        return ast.Spanned(
            ast.IntLiteral(value=tok.value),
            _span(items, self.src),
        )

    def float_literal(self, items: list[Any]) -> ast.Spanned[ast.FloatLiteral]:
        tok = items[0]
        return ast.Spanned(
            ast.FloatLiteral(value=tok.value),
            _span(items, self.src),
        )

    def string_literal(self, items: list[Any]) -> ast.Spanned[ast.StringLiteral]:
        tok = items[0]
        return ast.Spanned(
            ast.StringLiteral(value=tok.value),
            _span(items, self.src),
        )

    def char_literal(self, items: list[Any]) -> ast.Spanned[ast.CharLiteral]:
        tok = items[0]
        return ast.Spanned(
            ast.CharLiteral(value=tok.value),
            _span(items, self.src),
        )

    def true_literal(self, items: list[Any]) -> ast.Spanned[ast.BoolLiteral]:
        tok = items[0]
        return ast.Spanned(
            ast.BoolLiteral(value=True),
            _span(items, self.src),
        )

    def false_literal(self, items: list[Any]) -> ast.Spanned[ast.BoolLiteral]:
        tok = items[0]
        return ast.Spanned(
            ast.BoolLiteral(value=False),
            _span(items, self.src),
        )

    # ----- Expressions: refs/calls -----

    def name(self, items: list[Any]) -> ast.Spanned[ast.Name]:
        tok = items[0]
        return ast.Spanned(
            ast.Name(identifier=tok.value),
            _span(items, self.src),
        )

    def function_call(self, items: list[Any]) -> ast.Spanned[ast.FunctionCall]:
        callee = items[0].value
        args = items[1] if isinstance(items[1], list) else []
        return ast.Spanned(
            ast.FunctionCall(callee=callee, args=tuple(args)),
            _span(items, self.src),
        )

    def method_call(self, items: list[Any]) -> ast.Spanned[ast.MethodCall]:
        obj = items[0]
        method = items[2].value
        args = items[3] if isinstance(items[3], list) else []
        return ast.Spanned(
            ast.MethodCall(obj=obj, method=method, args=tuple(args)),
            _span(items, self.src),
        )

    def indexing(self, items: list[Any]) -> ast.Spanned[ast.Index]:
        return ast.Spanned(
            ast.Index(obj=items[0], index=items[2]),
            _span(items, self.src),
        )

    def maybe_unwrap(self, items: list[Any]) -> ast.Spanned[ast.MaybeUnwrap]:
        return ast.Spanned(
            ast.MaybeUnwrap(operand=items[0]),
            _span(items, self.src),
        )

    # ----- Expressions: grouping/sequences -----

    def paren_expr(self, items: list[Any]) -> ast.Spanned[ast.ParenExpr]:
        return ast.Spanned(
            ast.ParenExpr(inner=items[1]),
            _span(items, self.src),
        )

    def tuple_expr(self, items: list[Any]) -> ast.Spanned[ast.TupleExpr]:
        ex = tuple(i for i in items if isinstance(i, ast.Spanned))
        return ast.Spanned(
            ast.TupleExpr(items=ex),
            _span(items, self.src),
        )

    def array_literal(self, items: list[Any]) -> ast.Spanned[ast.ArrayLiteral]:
        ex = tuple(i for i in items if isinstance(i, ast.Spanned))
        return ast.Spanned(
            ast.ArrayLiteral(items=ex),
            _span(items, self.src),
        )

    # ----- Expressions: operators -----

    def binary_op(self, items: list[Any]) -> ast.Spanned[ast.BinaryOp]:
        op_tok = items[1]
        return ast.Spanned(
            ast.BinaryOp(
                op=_BIN_OP_FROM_TOKEN[op_tok.type],
                left=items[0],
                right=items[2],
            ),
            _span(items, self.src),
        )

    def unary_pre_op(self, items: list[Any]) -> ast.Spanned[ast.UnaryPreOp]:
        op_tok = items[0]
        return ast.Spanned(
            ast.UnaryPreOp(
                op=_UNARY_OP_FROM_TOKEN[op_tok.type],
                operand=items[1],
            ),
            _span(items, self.src),
        )

    def conditional(self, items: list[Any]) -> ast.Spanned[ast.Conditional]:
        return ast.Spanned(
            ast.Conditional(
                cond=items[0],
                then_branch=items[2],
                else_branch=items[4],
            ),
            _span(items, self.src),
        )

    # ----- Function / Module -----

    def function(self, items: list[Any]) -> ast.Spanned[ast.FunctionDef]:
        name = items[1].value
        block = items[-1]
        params = next(
            (
                list(t)
                for t in items
                if isinstance(t, list) and all(isinstance(p, ast.Spanned) for p in t)
            ),
            [],
        )
        return_type = next(
            (
                t
                for t in items
                if isinstance(t, ast.Spanned) and isinstance(t.node, ast.Type)
            ),
            None,
        )
        return ast.Spanned(
            ast.FunctionDef(
                name=name,
                params=tuple(params),
                return_type=return_type,
                body=block,
            ),
            _span(items, self.src),
        )

    def module(self, items: list[Any]) -> ast.Spanned[ast.Module]:
        if items:
            first = items[0]
            last = items[-1]
            sp_first = first.span
            sp_last = last.span
            span = ast.Span(
                sp_first.start_index,
                sp_first.start_line,
                sp_first.start_col,
                sp_last.end_index,
                sp_last.end_line,
                sp_last.end_col,
            )
        else:
            span = ast.Span(0, 0, 0, 0, 0, 0)
        return ast.Spanned(
            ast.Module(functions=tuple(items)),
            span,
        )


# =============================================================
# Entry point
# =============================================================


def parse(source: str) -> ast.Spanned[ast.Module]:
    """Парсит исходник mashiko и возвращает `ast.Spanned[ast.Module]`."""
    tree = _PARSER.parse(source)
    return _MashikoTransformer(source).transform(tree)
