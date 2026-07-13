"""AST node dataclasses for mashiko.

The transformer (`transformer.TreeToAST`) converts a Lark parse tree into
instances of these frozen dataclasses. Every node is immutable and
hashable; equality and repr are value-based. Types are written using
``from __future__ import annotations`` so forward references resolve at
runtime via the module-level ``_collect_types`` helper.

Every AST node inherits from :class:`Node` and carries a :class:`Span`
recording the source range it covers: character offsets
(``start_pos``/``end_pos``, end-exclusive) plus 1-based line/column at
both ends. Spans are produced by the transformer from Lark's per-rule
metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union

from ..span import Span

# ---- Common -----------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    """Base class for every AST node.

    Subclasses inherit ``span`` as the first field, so every constructor
    takes ``span=...`` before its own keyword arguments.
    """

    span: Span


# ---- Module & declarations ---------------------------------------------------


@dataclass(frozen=True)
class Module(Node):
    declarations: tuple[Declaration, ...]


@dataclass(frozen=True)
class FunctionDecl(Node):
    visibility: bool
    template: Optional[TemplateDecl]
    inline: bool
    name: str
    params: tuple[Param, ...]
    return_type: Optional[Type]
    body: Block


@dataclass(frozen=True)
class ClassDecl(Node):
    visibility: bool
    template: Optional[TemplateDecl]
    name: str
    interfaces: tuple[InterfaceRef, ...]
    body: ClassBody


@dataclass(frozen=True)
class InterfaceDecl(Node):
    template: Optional[TemplateDecl]
    name: str
    interfaces: tuple[InterfaceRef, ...]
    body: InterfaceBody


@dataclass(frozen=True)
class TypeParam(Node):
    name: str
    interfaces: tuple[InterfaceRef, ...]


@dataclass(frozen=True)
class ConstParam(Node):
    name: str
    type: Type
    default: Optional[Expression]


@dataclass(frozen=True)
class TemplateDecl(Node):
    members: tuple[TemplateMember, ...]


TemplateMember = Union[TypeParam, ConstParam]


Declaration = Union[FunctionDecl, ClassDecl, InterfaceDecl]


# ---- Class body --------------------------------------------------------------


@dataclass(frozen=True)
class ClassBody(Node):
    members: tuple[ClassMember, ...]


@dataclass(frozen=True)
class Field(Node):
    visibility: bool
    name: str
    type: Type


@dataclass(frozen=True)
class Constructor(Node):
    visibility: bool
    params: tuple[Param, ...]
    body: Block


@dataclass(frozen=True)
class Destructor(Node):
    visibility: bool
    body: Block


@dataclass(frozen=True)
class Cloner(Node):
    visibility: bool
    body: Block


@dataclass(frozen=True)
class Method(Node):
    visibility: bool
    static: bool
    inline: bool
    name: str
    params: tuple[Param, ...]
    return_type: Optional[Type]
    body: Block


ClassMember = Union[Field, Constructor, Destructor, Cloner, Method]


# ---- Interface body ----------------------------------------------------------


@dataclass(frozen=True)
class InterfaceBody(Node):
    methods: tuple[InterfaceMethod, ...]


@dataclass(frozen=True)
class InterfaceMethod(Node):
    static: bool
    name: str
    params: tuple[Param, ...]
    return_type: Optional[Type]
    body: Optional[Block]  # None for abstract methods (terminated by `;`)


# ---- Common ------------------------------------------------------------------


@dataclass(frozen=True)
class Param(Node):
    name: str
    type: Type


# ---- Types -------------------------------------------------------------------


@dataclass(frozen=True)
class SimpleType(Node):
    name: str


@dataclass(frozen=True)
class TupleType(Node):
    types: tuple[Type, ...]


@dataclass(frozen=True)
class GenericType(Node):
    name: str
    args: tuple[Union[Type, Expression], ...]


@dataclass(frozen=True)
class MaybeType(Node):
    inner: Type


# An interface reference is structurally a type but the grammar restricts
# it to a simple name or generic instantiation (no tuple / maybe forms).
InterfaceRef = Union[SimpleType, GenericType]

Type = Union[SimpleType, TupleType, GenericType, MaybeType]


# ---- Statements --------------------------------------------------------------


@dataclass(frozen=True)
class Block(Node):
    statements: tuple[Statement, ...]


@dataclass(frozen=True)
class AssignStatement(Node):
    target: AssignTarget
    op: str
    value: Expression


@dataclass(frozen=True)
class ExpressionStatement(Node):
    expression: Expression


@dataclass(frozen=True)
class IfStatement(Node):
    condition: Expression
    then_branch: Statement
    else_branch: Optional[Statement]


@dataclass(frozen=True)
class WhileStatement(Node):
    condition: Expression
    body: Statement


@dataclass(frozen=True)
class ForStatement(Node):
    variable: IterationVariable
    iterable: Expression
    body: Statement


@dataclass(frozen=True)
class BreakStatement(Node):
    pass


@dataclass(frozen=True)
class ContinueStatement(Node):
    pass


@dataclass(frozen=True)
class ReturnStatement(Node):
    value: Optional[Expression]


Statement = Union[
    AssignStatement,
    ExpressionStatement,
    IfStatement,
    WhileStatement,
    ForStatement,
    BreakStatement,
    ContinueStatement,
    ReturnStatement,
    Block,
]


# ---- L-values for assignment / for-loop variables ----------------------------


@dataclass(frozen=True)
class Name(Node):
    name: str


@dataclass(frozen=True)
class IndexLValue(Node):
    obj: Name
    index: Expression


@dataclass(frozen=True)
class TupleLValue(Node):
    names: tuple[str, ...]


@dataclass(frozen=True)
class MemberLValue(Node):
    obj: Name
    name: str


AssignTarget = Union[Name, IndexLValue, TupleLValue, MemberLValue]
IterationVariable = Union[Name, TupleLValue]


# ---- Expressions -------------------------------------------------------------


@dataclass(frozen=True)
class IntLiteral(Node):
    value: int


@dataclass(frozen=True)
class FloatLiteral(Node):
    value: float


@dataclass(frozen=True)
class StringLiteral(Node):
    value: str


@dataclass(frozen=True)
class CharLiteral(Node):
    value: str


@dataclass(frozen=True)
class BoolLiteral(Node):
    value: bool


@dataclass(frozen=True)
class FunctionCall(Node):
    name: str
    args: tuple[Expression, ...]


@dataclass(frozen=True)
class MethodCall(Node):
    obj: Expression
    name: str
    args: tuple[Expression, ...]


@dataclass(frozen=True)
class Indexing(Node):
    obj: Expression
    index: Expression


@dataclass(frozen=True)
class MaybeUnwrap(Node):
    expr: Expression


@dataclass(frozen=True)
class MemberAccess(Node):
    obj: Expression
    name: str


class BinaryOpKind(Enum):
    LOGICAL_OR = "||"
    LOGICAL_AND = "&&"
    BITWISE_OR = "|"
    BITWISE_XOR = "^"
    BITWISE_AND = "&"
    EQUAL = "=="
    NOT_EQUAL = "!="
    LESS = "<"
    GREATER = ">"
    LESS_EQUAL = "<="
    GREATER_EQUAL = ">="
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    MODULO = "%"

    @staticmethod
    def from_token(token: str) -> "BinaryOpKind":
        match token:
            case "||": return BinaryOpKind.LOGICAL_OR
            case "&&": return BinaryOpKind.LOGICAL_AND
            case "|": return BinaryOpKind.BITWISE_OR
            case "^": return BinaryOpKind.BITWISE_XOR
            case "&": return BinaryOpKind.BITWISE_AND
            case "==": return BinaryOpKind.EQUAL
            case "!=": return BinaryOpKind.NOT_EQUAL
            case "<": return BinaryOpKind.LESS
            case ">": return BinaryOpKind.GREATER
            case "<=": return BinaryOpKind.LESS_EQUAL
            case ">=": return BinaryOpKind.GREATER_EQUAL
            case "+": return BinaryOpKind.ADD
            case "-": return BinaryOpKind.SUBTRACT
            case "*": return BinaryOpKind.MULTIPLY
            case "/": return BinaryOpKind.DIVIDE
            case "%": return BinaryOpKind.MODULO
            case _: raise ValueError(f"Unknown binary operator: {token!r}")


class UnaryOpKind(Enum):
    NEGATE = "-"
    NOT = "!"

    @staticmethod
    def from_token(token: str) -> "UnaryOpKind":
        match token:
            case "-": return UnaryOpKind.NEGATE
            case "!": return UnaryOpKind.NOT
            case _: raise ValueError(f"Unknown unary operator: {token!r}")


@dataclass(frozen=True)
class BinaryOp(Node):
    op: BinaryOpKind
    left: Expression
    right: Expression


@dataclass(frozen=True)
class UnaryOp(Node):
    op: UnaryOpKind
    operand: Expression


@dataclass(frozen=True)
class Conditional(Node):
    condition: Expression
    then_expr: Expression
    else_expr: Expression


@dataclass(frozen=True)
class ParenExpr(Node):
    expr: Expression


@dataclass(frozen=True)
class ArrayLiteral(Node):
    elements: tuple[Expression, ...]


@dataclass(frozen=True)
class InlinedCall(Node):
    """A call to an ``inline`` function/method that has been expanded
    in place at the call site by the semantic analyzer.

    ``callee`` is the function/method name (``"foo"`` for ``foo()`` or
    ``"C::bar"`` for ``C.bar()``). ``args`` preserves the original
    call's argument list — kept on the node so error spans and future
    diagnostic passes can still point at the call site.

    ``block`` is the callee's body with type-param placeholders
    substituted and params rebound to the call's argument expressions
    in a fresh :class:`Scope`. The block's value is determined by
    walking it for the first :class:`ReturnStatement` (or implicitly
    :class:`~mashiko.sema.symbols.PrimitiveTypeSymbol.Void` for a
    void-returning callee). ``return_type`` is stored alongside so
    downstream passes don't have to re-derive it.

    The :class:`mashiko.sema.desugaring` pass later walks the
    inlined block to add ``.destruct()`` calls for any locals bound
    in the inlined body.
    """

    callee: str
    args: tuple[Expression, ...]
    block: Block
    return_type: Type


Expression = Union[
    IntLiteral,
    FloatLiteral,
    StringLiteral,
    CharLiteral,
    BoolLiteral,
    Name,
    FunctionCall,
    MethodCall,
    Indexing,
    MaybeUnwrap,
    MemberAccess,
    BinaryOp,
    UnaryOp,
    Conditional,
    ParenExpr,
    ArrayLiteral,
    InlinedCall,
]
