"""Convert a Lark parse tree to the typed AST defined in `syntax.py`.

The transformer is a subclass of ``lark.visitors.Transformer``. Each
public method corresponds to a rule (or rule alias) that actually appears
in the parse tree; many pass-through rules are collapsed by the
``__default__`` fallback, which simply returns the single child of a
wrapper rule.
"""

from __future__ import annotations

from lark import Token, Tree
from lark.visitors import Transformer

from .syntax import (
    ArrayLiteral,
    AssignStatement,
    BinaryOp,
    Block,
    BoolLiteral,
    BreakStatement,
    CharLiteral,
    ClassBody,
    ClassDecl,
    Cloner,
    Conditional,
    ConstParam,
    Constructor,
    ContinueStatement,
    Destructor,
    ExpressionStatement,
    Field,
    FloatLiteral,
    ForStatement,
    FunctionCall,
    FunctionDecl,
    GenericType,
    IfStatement,
    Indexing,
    IndexLValue,
    IntLiteral,
    InterfaceBody,
    InterfaceDecl,
    InterfaceMethod,
    MaybeType,
    MaybeUnwrap,
    MemberAccess,
    MemberLValue,
    Method,
    MethodCall,
    Module,
    Name,
    Param,
    ParenExpr,
    ReturnStatement,
    SimpleType,
    Statement,
    StringLiteral,
    TemplateDecl,
    TupleLValue,
    TupleType,
    Type,
    TypeParam,
    UnaryOp,
    WhileStatement,
)


def _is_token(x: object) -> bool:
    return isinstance(x, Token)


def _strip_quotes(s: str) -> str:
    return s[1:-1]


class TreeToAST(Transformer):
    """Walk a Lark ``Tree`` and emit ``syntax`` dataclass instances."""

    # ---- Earley ambiguity wrapper -----------------------------------------
    # When ``ambiguity='explicit'``, Lark wraps ambiguous parses in a
    # ``_ambig`` node. Take the first alternative.
    def _ambig(self, children):
        return children[0]

    # ---- Module & declarations --------------------------------------------
    def module(self, children):
        return Module(declarations=tuple(children))

    def function_decl(self, children):
        # children: [template_or_None, FUNC, IDENT, arguments_tree, return_type_or_None, block]
        return FunctionDecl(
            template=children[0],
            name=str(children[2]),
            params=tuple(children[3]),
            return_type=children[4],
            body=children[5],
        )

    def class_decl(self, children):
        # children: [template_or_None, CLASS, IDENT, depent_interfaces_or_None, LBRACE, class_body, RBRACE]
        return ClassDecl(
            template=children[0],
            name=str(children[2]),
            interfaces=tuple(children[3]) if children[3] is not None else (),
            body=children[5],
        )

    def interface_decl(self, children):
        # children: [template_or_None, INTERFACE, IDENT, depent_interfaces_or_None,
        #             LBRACE, method..., RBRACE]
        # `?interface_body` is inlined, so the methods are direct children
        # between LBRACE (idx 5) and RBRACE (last).
        methods = tuple(c for c in children[5:-1] if not _is_token(c))
        return InterfaceDecl(
            template=children[0],
            name=str(children[2]),
            interfaces=tuple(children[3]) if children[3] is not None else (),
            body=InterfaceBody(methods=methods),
        )

    # ---- Templates --------------------------------------------------------
    def template_decl(self, children):
        # children: [TEMPLATE, LANGLE, template_member (COMMA template_member)*, RANGLE]
        members = tuple(c for c in children[2:-1] if not _is_token(c))
        return TemplateDecl(members=members)

    def template_param(self, children):
        # children: [TYPE, IDENT, depent_interfaces_or_None]
        return TypeParam(
            name=str(children[1]),
            interfaces=tuple(children[2]) if children[2] else (),
        )

    def template_const(self, children):
        # children: [CONST, IDENT, COLON, type, EQ_expression_or_None]
        return ConstParam(
            name=str(children[1]),
            type=children[3],
            default=children[4] if len(children) > 4 else None,
        )

    # ---- Helper rules -----------------------------------------------------
    def arguments(self, children):
        # children: [LPAREN, (Param (COMMA Param)*)?, RPAREN]
        # The optional inner slot is `None` when there are no params.
        params = [c for c in children[1:-1] if not _is_token(c) and c is not None]
        return params

    def return_type(self, children):
        # children: [COLON, type]
        return children[1]

    def depent_interfaces(self, children):
        # children: [COLON, interface (COMMA interface)*]
        return tuple(c for c in children[1:] if not _is_token(c))

    def typed_ident(self, children):
        # children: [IDENT, COLON, type]
        return Param(name=str(children[0]), type=children[2])

    # ---- Class / interface body ------------------------------------------
    def class_body(self, children):
        return ClassBody(members=tuple(children))

    def field(self, children):
        # children: [Param, SEMICOLON]
        param = children[0]
        return Field(name=param.name, type=param.type)

    def constructor(self, children):
        # children: [CONSTRUCTOR, arguments_tree, block]
        return Constructor(params=tuple(children[1]), body=children[2])

    def destructor(self, children):
        # children: [DESTRUCTOR, LPAREN, RPAREN, block]
        return Destructor(body=children[3])

    def cloner(self, children):
        # children: [CLONER, LPAREN, RPAREN, block]
        return Cloner(body=children[3])

    def method(self, children):
        # children: [IDENT, arguments_tree, return_type_or_None, block]
        return Method(
            name=str(children[0]),
            params=tuple(children[1]),
            return_type=children[2],
            body=children[3],
        )

    def interface_body(self, children):
        return InterfaceBody(methods=tuple(children))

    def interface_method(self, children):
        # children: [IDENT, arguments_tree, return_type_or_None, block | SEMICOLON_token]
        if _is_token(children[3]):
            body = None
        else:
            body = children[3]
        return InterfaceMethod(
            name=str(children[0]),
            params=tuple(children[1]),
            return_type=children[2],
            body=body,
        )

    # ---- Statements -------------------------------------------------------
    def statement(self, children):
        # statement has exactly one alternative that matches
        return children[0]

    def block(self, children):
        # children: [LBRACE, statement*, RBRACE]
        statements = tuple(c for c in children[1:-1] if not _is_token(c))
        return Block(statements=statements)

    def expression_statement(self, children):
        # children: [expression, SEMICOLON]
        return ExpressionStatement(expression=children[0])

    def assign_statement(self, children):
        # children: [left_side_assign_tree, assign_operator_token, expression, SEMICOLON]
        return AssignStatement(
            target=children[0],
            op=str(children[1]),
            value=children[2],
        )

    def assign_operator(self, children):
        return children[0]  # pass the EQ / PLUS_EQ / ... token through

    def if_statement(self, children):
        # children: [IF, condition, statement, (ELSE, statement)?]
        condition = children[1]
        then_branch = children[2]
        else_branch = None
        if len(children) > 3 and children[3] is not None:
            # The optional is (ELSE_token, else_stmt)
            else_branch = children[4]
        return IfStatement(
            condition=condition, then_branch=then_branch, else_branch=else_branch
        )

    def while_statement(self, children):
        # children: [WHILE, condition, statement]
        return WhileStatement(condition=children[1], body=children[2])

    def for_statement(self, children):
        # children: [FOR, iteration_variable, COLON, expression, statement]
        return ForStatement(
            variable=children[1], iterable=children[3], body=children[4]
        )

    def break_statement(self, children):
        return BreakStatement()

    def continue_statement(self, children):
        return ContinueStatement()

    def return_statement(self, children):
        # children: [RETURN, expression_or_None, SEMICOLON]
        value = children[1] if len(children) > 1 and children[1] is not None else None
        return ReturnStatement(value=value)

    def left_side_assign(self, children):
        # children: [IDENT] (single name)
        #   or   [IDENT, LBRACKET, expression, RBRACKET] (indexed)
        #   or   [LPAREN, IDENT (COMMA IDENT)*, RPAREN] (tuple lvalue)
        #   or   [MemberLValue] (this.field — already transformed)
        if len(children) == 1:
            if isinstance(children[0], MemberLValue):
                return children[0]
            return Name(name=str(children[0]))
        if _is_token(children[0]) and str(children[0]) == "(":
            names = tuple(str(c) for c in children if not _is_token(c))
            return TupleLValue(names=names)
        # IDENT LBRACKET expr RBRACKET
        return IndexLValue(obj=Name(name=str(children[0])), index=children[2])

    def member_lvalue(self, children):
        # children: [IDENT, DOT, IDENT]
        return MemberLValue(obj=Name(name=str(children[0])), name=str(children[2]))

    def iteration_variable(self, children):
        # children: [IDENT] (single)
        #   or   [LPAREN, IDENT (COMMA IDENT)*, RPAREN] (tuple)
        if len(children) == 1:
            return Name(name=str(children[0]))
        names = tuple(str(c) for c in children if not _is_token(c))
        return TupleLValue(names=names)

    # ---- Types ------------------------------------------------------------
    def simple_type(self, children):
        return SimpleType(name=str(children[0]))

    def tuple_type(self, children):
        # children: [LPAREN, (type (COMMA type)*)?, RPAREN]
        types = tuple(c for c in children[1:-1] if not _is_token(c))
        return TupleType(types=types)

    def generic_type(self, children):
        # children: [TYPE_IDENT, LANGLE, type (COMMA (type|expression))*, RANGLE]
        name = str(children[0])
        args = tuple(c for c in children[2:-1] if not _is_token(c))
        return GenericType(name=name, args=args)

    def maybe_type(self, children):
        # children: [type, MAYBE]
        return MaybeType(inner=children[0])

    def interface(self, children):
        # children: [TYPE_IDENT]  (single name)
        #   or   [TYPE_IDENT, LANGLE, type (COMMA (type|expression))*, RANGLE]
        name = str(children[0])
        if len(children) == 1:
            return SimpleType(name=name)
        args = tuple(c for c in children[2:-1] if not _is_token(c))
        return GenericType(name=name, args=args)

    # ---- Expressions ------------------------------------------------------
    def binary_op(self, children):
        # children: [left, op_token, right]
        return BinaryOp(op=str(children[1]), left=children[0], right=children[2])

    def unary_pre_op(self, children):
        # children: [op_token, operand]
        return UnaryOp(op=str(children[0]), operand=children[1])

    def conditional(self, children):
        # Two shapes from `?conditional`:
        #   * pass-through (no IF/ELSE): children == [or_expr_passthrough]
        #   * IF/ELSE form: children == [cond, IF, then, ELSE, else_cond]
        if len(children) == 1:
            return children[0]
        return Conditional(
            condition=children[0],
            then_expr=children[2],
            else_expr=children[4],
        )

    def indexing(self, children):
        # children: [obj, LBRACKET, index, RBRACKET]
        return Indexing(obj=children[0], index=children[2])

    def method_call(self, children):
        # children: [obj, DOT, IDENT, LPAREN, args_or_None, RPAREN]
        args = tuple(children[4]) if children[4] is not None else ()
        return MethodCall(obj=children[0], name=str(children[2]), args=args)

    def maybe_unwrap(self, children):
        # children: [expr, MAYBE]
        return MaybeUnwrap(expr=children[0])

    def member_access(self, children):
        # children: [obj, DOT, IDENT]
        return MemberAccess(obj=children[0], name=str(children[2]))

    def int_literal(self, children):
        return IntLiteral(value=int(str(children[0])))

    def float_literal(self, children):
        return FloatLiteral(value=float(str(children[0])))

    def string_literal(self, children):
        return StringLiteral(value=_strip_quotes(str(children[0])))

    def char_literal(self, children):
        return CharLiteral(value=_strip_quotes(str(children[0])))

    def bool_literal(self, children):
        return BoolLiteral(value=str(children[0]) == "true")

    def function_call(self, children):
        # children: [IDENT, LPAREN, args_or_None, RPAREN]
        args = tuple(children[2]) if children[2] is not None else ()
        return FunctionCall(name=str(children[0]), args=args)

    def name(self, children):
        return Name(name=str(children[0]))

    def paren_expr(self, children):
        # children: [LPAREN, expression, RPAREN]
        return ParenExpr(expr=children[1])

    def array_literal(self, children):
        # children: [LBRACKET, (expression (COMMA expression)*)?, RBRACKET]
        elements = tuple(c for c in children[1:-1] if not _is_token(c))
        return ArrayLiteral(elements=elements)

    def args(self, children):
        # children: [expr, COMMA, expr, COMMA, ...] — filter COMMA tokens
        return tuple(c for c in children if not _is_token(c))

    # ---- Default: pass-through for wrapper rules --------------------------
    # Many grammar rules are simple one-child wrappers (the alternatives
    # of `?or_expr`, `?and_expr`, `?unary_expr`'s "passthrough" branch,
    # etc.). When the child has already been transformed, just return it.
    def __default__(self, data, children, meta):
        if len(children) == 1:
            return children[0]
        # Unknown multi-child rule — keep the raw tree for inspection.
        return Tree(data, children)
