"""Convert a Lark parse tree to the typed AST defined in `syntax.py`.

The transformer is a subclass of ``lark.visitors.Transformer``. Each
public method corresponds to a rule (or rule alias) that actually appears
in the parse tree; many pass-through rules are collapsed by the
``__default__`` fallback, which simply returns the single child of a
wrapper rule.

The parser is constructed with ``propagate_positions=True``, so every
rule's ``meta`` carries the source range (character offsets plus 1-based
line/column). ``@v_args(meta=True)`` reshapes the callback signature to
``(meta, children)`` so we can convert that range — or, for a sub-range,
the position of a child ``Token`` — into a
:class:`~mashiko.syntax.Span` and pass it as the first constructor
argument.
"""

from __future__ import annotations

from lark import Token, Tree
from lark.visitors import Transformer, v_args

from .syntax import (
    ArrayLiteral,
    AssignStatement,
    BinaryOp,
    BinaryOpKind,
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
    Span,
    Statement,
    StringLiteral,
    TemplateDecl,
    TupleLValue,
    TupleType,
    Type,
    TypeParam,
    UnaryOp,
    UnaryOpKind,
    WhileStatement,
)


def _is_token(x: object) -> bool:
    return isinstance(x, Token)


def _strip_quotes(s: str) -> str:
    return s[1:-1]


def _span_from_meta(meta) -> Span:
    if meta.empty:
        # The rule matched zero tokens (e.g. an empty class_body in
        # `class C { }`). Lark doesn't know a source range for it; we
        # fall back to a zero-width span at the start of the file so
        # downstream code can still rely on the field existing.
        return Span(0, 0, 1, 1, 1, 1)
    return Span(
        start_pos=meta.start_pos,
        end_pos=meta.end_pos,
        start_line=meta.line,
        start_column=meta.column,
        end_line=meta.end_line,
        end_column=meta.end_column,
    )


def _span_from_token(token: Token) -> Span:
    return Span(
        start_pos=token.start_pos,
        end_pos=token.end_pos,
        start_line=token.line,
        start_column=token.column,
        end_line=token.end_line,
        end_column=token.end_column,
    )


@v_args(meta=True)
class TreeToAST(Transformer):
    """Walk a Lark ``Tree`` and emit ``syntax`` dataclass instances."""

    # ---- Earley ambiguity wrapper -----------------------------------------
    # When ``ambiguity='explicit'``, Lark wraps ambiguous parses in a
    # ``_ambig`` node. Take the first alternative.
    # This method is not wrapped by ``@v_args(meta=True)`` (the decorator
    # skips names starting with ``_``), so it keeps the plain
    # ``(self, children)`` signature.
    def _ambig(self, children):
        return children[0]

    # ---- Module & declarations --------------------------------------------
    def module(self, meta, children):
        return Module(span=_span_from_meta(meta), declarations=tuple(children))

    def visibility(self, meta, children):
        # `visibility` matches the literal `public` keyword and always
        # represents True. Absence of the slot on the parent rule is
        # represented by `None`, which the call sites translate to False.
        return True

    def static(self, meta, children):
        # `static` matches the literal `static` keyword and always
        # represents True. Absence of the slot on the parent rule is
        # represented by `None`, which the call sites translate to False.
        return True

    def function_decl(self, meta, children):
        # children: [visibility_or_None, template_or_None, FUNC, IDENT,
        #             arguments_tree, return_type_or_None, block]
        return FunctionDecl(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            template=children[1],
            name=str(children[3]),
            params=tuple(children[4]),
            return_type=children[5],
            body=children[6],
        )

    def class_decl(self, meta, children):
        # children: [visibility_or_None, template_or_None, CLASS, IDENT,
        #             depent_interfaces_or_None, LBRACE, class_body, RBRACE]
        return ClassDecl(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            template=children[1],
            name=str(children[3]),
            interfaces=tuple(children[4]) if children[4] is not None else (),
            body=children[6],
        )

    def interface_decl(self, meta, children):
        # children: [template_or_None, INTERFACE, IDENT, depent_interfaces_or_None,
        #             LBRACE, method..., RBRACE]
        # `?interface_body` is inlined, so the methods are direct children
        # between LBRACE (idx 5) and RBRACE (last).
        methods = tuple(c for c in children[5:-1] if not _is_token(c))
        return InterfaceDecl(
            span=_span_from_meta(meta),
            template=children[0],
            name=str(children[2]),
            interfaces=tuple(children[3]) if children[3] is not None else (),
            body=InterfaceBody(span=_span_from_meta(meta), methods=methods),
        )

    # ---- Templates --------------------------------------------------------
    def template_decl(self, meta, children):
        # children: [TEMPLATE, LANGLE, template_member (COMMA template_member)*, RANGLE]
        members = tuple(c for c in children[2:-1] if not _is_token(c))
        return TemplateDecl(span=_span_from_meta(meta), members=members)

    def template_param(self, meta, children):
        # children: [TYPE, IDENT, depent_interfaces_or_None]
        return TypeParam(
            span=_span_from_meta(meta),
            name=str(children[1]),
            interfaces=tuple(children[2]) if children[2] else (),
        )

    def template_const(self, meta, children):
        # children: [CONST, IDENT, COLON, type, EQ_expression_or_None]
        return ConstParam(
            span=_span_from_meta(meta),
            name=str(children[1]),
            type=children[3],
            default=children[4] if len(children) > 4 else None,
        )

    # ---- Helper rules -----------------------------------------------------
    def arguments(self, meta, children):
        # children: [LPAREN, (Param (COMMA Param)*)?, RPAREN]
        # The optional inner slot is `None` when there are no params.
        params = [c for c in children[1:-1] if not _is_token(c) and c is not None]
        return params

    def return_type(self, meta, children):
        # children: [COLON, type]
        return children[1]

    def depent_interfaces(self, meta, children):
        # children: [COLON, interface (COMMA interface)*]
        return tuple(c for c in children[1:] if not _is_token(c))

    def typed_ident(self, meta, children):
        # children: [IDENT, COLON, type]
        return Param(
            span=_span_from_meta(meta),
            name=str(children[0]),
            type=children[2],
        )

    # ---- Class / interface body ------------------------------------------
    def class_body(self, meta, children):
        return ClassBody(span=_span_from_meta(meta), members=tuple(children))

    def field(self, meta, children):
        # children: [visibility_or_None, Param, SEMICOLON]
        param = children[1]
        return Field(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            name=param.name,
            type=param.type,
        )

    def constructor(self, meta, children):
        # children: [visibility_or_None, CONSTRUCTOR, arguments_tree, block]
        return Constructor(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            params=tuple(children[2]),
            body=children[3],
        )

    def destructor(self, meta, children):
        # children: [visibility_or_None, DESTRUCTOR, LPAREN, RPAREN, block]
        return Destructor(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            body=children[4],
        )

    def cloner(self, meta, children):
        # children: [visibility_or_None, CLONER, LPAREN, RPAREN, block]
        return Cloner(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            body=children[4],
        )

    def method(self, meta, children):
        # children: [visibility_or_None, static_or_None, IDENT, arguments_tree,
        #             return_type_or_None, block]
        return Method(
            span=_span_from_meta(meta),
            visibility=children[0] is not None,
            static=children[1] is not None,
            name=str(children[2]),
            params=tuple(children[3]),
            return_type=children[4],
            body=children[5],
        )

    def interface_body(self, meta, children):
        return InterfaceBody(span=_span_from_meta(meta), methods=tuple(children))

    def interface_method(self, meta, children):
        # children: [static_or_None, IDENT, arguments_tree, return_type_or_None,
        #             block | SEMICOLON_token]
        if _is_token(children[4]):
            body = None
        else:
            body = children[4]
        return InterfaceMethod(
            span=_span_from_meta(meta),
            static=children[0] is not None,
            name=str(children[1]),
            params=tuple(children[2]),
            return_type=children[3],
            body=body,
        )

    # ---- Statements -------------------------------------------------------
    def statement(self, meta, children):
        # statement has exactly one alternative that matches
        return children[0]

    def block(self, meta, children):
        # children: [LBRACE, statement*, RBRACE]
        statements = tuple(c for c in children[1:-1] if not _is_token(c))
        return Block(span=_span_from_meta(meta), statements=statements)

    def expression_statement(self, meta, children):
        # children: [expression, SEMICOLON]
        return ExpressionStatement(span=_span_from_meta(meta), expression=children[0])

    def assign_statement(self, meta, children):
        # children: [left_side_assign_tree, assign_operator_token, expression, SEMICOLON]
        return AssignStatement(
            span=_span_from_meta(meta),
            target=children[0],
            op=str(children[1]),
            value=children[2],
        )

    def assign_operator(self, meta, children):
        return children[0]  # pass the EQ / PLUS_EQ / ... token through

    def if_statement(self, meta, children):
        # children: [IF, condition, statement, (ELSE, statement)?]
        condition = children[1]
        then_branch = children[2]
        else_branch = None
        if len(children) > 3 and children[3] is not None:
            # The optional is (ELSE_token, else_stmt)
            else_branch = children[4]
        return IfStatement(
            span=_span_from_meta(meta),
            condition=condition,
            then_branch=then_branch,
            else_branch=else_branch,
        )

    def while_statement(self, meta, children):
        # children: [WHILE, condition, statement]
        return WhileStatement(
            span=_span_from_meta(meta),
            condition=children[1],
            body=children[2],
        )

    def for_statement(self, meta, children):
        # children: [FOR, iteration_variable, COLON, expression, statement]
        return ForStatement(
            span=_span_from_meta(meta),
            variable=children[1],
            iterable=children[3],
            body=children[4],
        )

    def break_statement(self, meta, children):
        return BreakStatement(span=_span_from_meta(meta))

    def continue_statement(self, meta, children):
        return ContinueStatement(span=_span_from_meta(meta))

    def return_statement(self, meta, children):
        # children: [RETURN, expression_or_None, SEMICOLON]
        value = children[1] if len(children) > 1 and children[1] is not None else None
        return ReturnStatement(span=_span_from_meta(meta), value=value)

    def left_side_assign(self, meta, children):
        # children: [IDENT] (single name)
        #   or   [IDENT, LBRACKET, expression, RBRACKET] (indexed)
        #   or   [LPAREN, IDENT (COMMA IDENT)*, RPAREN] (tuple lvalue)
        #   or   [MemberLValue] (this.field — already transformed)
        if len(children) == 1:
            if isinstance(children[0], MemberLValue):
                return children[0]
            return Name(span=_span_from_meta(meta), name=str(children[0]))
        if _is_token(children[0]) and str(children[0]) == "(":
            names = tuple(str(c) for c in children if not _is_token(c))
            return TupleLValue(span=_span_from_meta(meta), names=names)
        # IDENT LBRACKET expr RBRACKET
        return IndexLValue(
            span=_span_from_meta(meta),
            obj=Name(span=_span_from_token(children[0]), name=str(children[0])),
            index=children[2],
        )

    def member_lvalue(self, meta, children):
        # children: [IDENT, DOT, IDENT]
        return MemberLValue(
            span=_span_from_meta(meta),
            obj=Name(span=_span_from_token(children[0]), name=str(children[0])),
            name=str(children[2]),
        )

    def iteration_variable(self, meta, children):
        # children: [IDENT] (single)
        #   or   [LPAREN, IDENT (COMMA IDENT)*, RPAREN] (tuple)
        if len(children) == 1:
            return Name(span=_span_from_meta(meta), name=str(children[0]))
        names = tuple(str(c) for c in children if not _is_token(c))
        return TupleLValue(span=_span_from_meta(meta), names=names)

    # ---- Types ------------------------------------------------------------
    def simple_type(self, meta, children):
        return SimpleType(span=_span_from_meta(meta), name=str(children[0]))

    def tuple_type(self, meta, children):
        # children: [LPAREN, (type (COMMA type)*)?, RPAREN]
        types = tuple(c for c in children[1:-1] if not _is_token(c))
        return TupleType(span=_span_from_meta(meta), types=types)

    def generic_type(self, meta, children):
        # children: [TYPE_IDENT, LANGLE, type (COMMA (type|expression))*, RANGLE]
        name = str(children[0])
        args = tuple(c for c in children[2:-1] if not _is_token(c))
        return GenericType(span=_span_from_meta(meta), name=name, args=args)

    def maybe_type(self, meta, children):
        # children: [type, MAYBE]
        return MaybeType(span=_span_from_meta(meta), inner=children[0])

    def interface(self, meta, children):
        # children: [TYPE_IDENT]  (single name)
        #   or   [TYPE_IDENT, LANGLE, type (COMMA (type|expression))*, RANGLE]
        name = str(children[0])
        if len(children) == 1:
            return SimpleType(span=_span_from_meta(meta), name=name)
        args = tuple(c for c in children[2:-1] if not _is_token(c))
        return GenericType(span=_span_from_meta(meta), name=name, args=args)

    # ---- Expressions ------------------------------------------------------
    def binary_op(self, meta, children):
        # children: [left, op_token, right]
        return BinaryOp(
            span=_span_from_meta(meta),
            op=BinaryOpKind.from_token(str(children[1])),
            left=children[0],
            right=children[2],
        )

    def unary_pre_op(self, meta, children):
        # children: [op_token, operand]
        return UnaryOp(
            span=_span_from_meta(meta),
            op=UnaryOpKind.from_token(str(children[0])),
            operand=children[1],
        )

    def conditional(self, meta, children):
        # Two shapes from `?conditional`:
        #   * pass-through (no IF/ELSE): children == [or_expr_passthrough]
        #   * IF/ELSE form: children == [cond, IF, then, ELSE, else_cond]
        if len(children) == 1:
            return children[0]
        return Conditional(
            span=_span_from_meta(meta),
            condition=children[0],
            then_expr=children[2],
            else_expr=children[4],
        )

    def indexing(self, meta, children):
        # children: [obj, LBRACKET, index, RBRACKET]
        return Indexing(
            span=_span_from_meta(meta),
            obj=children[0],
            index=children[2],
        )

    def method_call(self, meta, children):
        # children: [obj, DOT, IDENT, LPAREN, args_or_None, RPAREN]
        args = tuple(children[4]) if children[4] is not None else ()
        return MethodCall(
            span=_span_from_meta(meta),
            obj=children[0],
            name=str(children[2]),
            args=args,
        )

    def maybe_unwrap(self, meta, children):
        # children: [expr, MAYBE]
        return MaybeUnwrap(span=_span_from_meta(meta), expr=children[0])

    def member_access(self, meta, children):
        # children: [obj, DOT, IDENT]
        return MemberAccess(
            span=_span_from_meta(meta),
            obj=children[0],
            name=str(children[2]),
        )

    def int_literal(self, meta, children):
        return IntLiteral(span=_span_from_meta(meta), value=int(str(children[0])))

    def float_literal(self, meta, children):
        return FloatLiteral(span=_span_from_meta(meta), value=float(str(children[0])))

    def string_literal(self, meta, children):
        return StringLiteral(span=_span_from_meta(meta), value=_strip_quotes(str(children[0])))

    def char_literal(self, meta, children):
        return CharLiteral(span=_span_from_meta(meta), value=_strip_quotes(str(children[0])))

    def bool_literal(self, meta, children):
        return BoolLiteral(span=_span_from_meta(meta), value=str(children[0]) == "true")

    def function_call(self, meta, children):
        # children: [IDENT, LPAREN, args_or_None, RPAREN]
        args = tuple(children[2]) if children[2] is not None else ()
        return FunctionCall(
            span=_span_from_meta(meta),
            name=str(children[0]),
            args=args,
        )

    def name(self, meta, children):
        return Name(span=_span_from_meta(meta), name=str(children[0]))

    def paren_expr(self, meta, children):
        # children: [LPAREN, expression, RPAREN]
        return ParenExpr(span=_span_from_meta(meta), expr=children[1])

    def array_literal(self, meta, children):
        # children: [LBRACKET, (expression (COMMA expression)*)?, RBRACKET]
        elements = tuple(c for c in children[1:-1] if not _is_token(c))
        return ArrayLiteral(span=_span_from_meta(meta), elements=elements)

    def args(self, meta, children):
        # children: [expr, COMMA, expr, COMMA, ...] — filter COMMA tokens
        return tuple(c for c in children if not _is_token(c))

    # ---- Default: pass-through for wrapper rules --------------------------
    # Many grammar rules are simple one-child wrappers (the alternatives
    # of `?or_expr`, `?and_expr`, `?unary_expr`'s "passthrough" branch,
    # etc.). When the child has already been transformed, just return it.
    # This is reached via ``_call_userfunc``'s ``AttributeError`` branch
    # (the wrapper only fires for methods that exist on the class), so
    # the ``(data, children, meta)`` signature is preserved here.
    def __default__(self, data, children, meta):
        if len(children) == 1:
            return children[0]
        # Unknown multi-child rule — keep the raw tree for inspection.
        return Tree(data, children)
