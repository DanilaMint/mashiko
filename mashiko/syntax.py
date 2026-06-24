"""AST node dataclasses for mashiko.

The transformer (`transformer.TreeToAST`) converts a Lark parse tree into
instances of these frozen dataclasses. Every node is immutable and
hashable; equality and repr are value-based. Types are written using
``from __future__ import annotations`` so forward references resolve at
runtime via the module-level ``_collect_types`` helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union

# ---- Module & declarations ---------------------------------------------------


@dataclass(frozen=True)
class Module:
    declarations: tuple[Declaration, ...]


@dataclass(frozen=True)
class FunctionDecl:
    template: Optional[TemplateDecl]
    name: str
    params: tuple[Param, ...]
    return_type: Optional[Type]
    body: Block


@dataclass(frozen=True)
class ClassDecl:
    template: Optional[TemplateDecl]
    name: str
    interfaces: tuple[InterfaceRef, ...]
    body: ClassBody


@dataclass(frozen=True)
class InterfaceDecl:
    template: Optional[TemplateDecl]
    name: str
    interfaces: tuple[InterfaceRef, ...]
    body: InterfaceBody


@dataclass(frozen=True)
class TypeParam:
    name: str
    interfaces: tuple[InterfaceRef, ...]


@dataclass(frozen=True)
class ConstParam:
    name: str
    type: Type
    default: Optional[Expression]


@dataclass(frozen=True)
class TemplateDecl:
    members: tuple[TemplateMember, ...]


TemplateMember = Union[TypeParam, ConstParam]





Declaration = Union[FunctionDecl, ClassDecl, InterfaceDecl]


# ---- Class body --------------------------------------------------------------


@dataclass(frozen=True)
class ClassBody:
    members: tuple[ClassMember, ...]


@dataclass(frozen=True)
class Field:
    name: str
    type: Type


@dataclass(frozen=True)
class Constructor:
    params: tuple[Param, ...]
    body: Block


@dataclass(frozen=True)
class Destructor:
    body: Block


@dataclass(frozen=True)
class Cloner:
    body: Block


@dataclass(frozen=True)
class Method:
    name: str
    params: tuple[Param, ...]
    return_type: Optional[Type]
    body: Block


ClassMember = Union[Field, Constructor, Destructor, Cloner, Method]


# ---- Interface body ----------------------------------------------------------


@dataclass(frozen=True)
class InterfaceBody:
    methods: tuple[InterfaceMethod, ...]


@dataclass(frozen=True)
class InterfaceMethod:
    name: str
    params: tuple[Param, ...]
    return_type: Optional[Type]
    body: Optional[Block]  # None for abstract methods (terminated by `;`)


# ---- Common ------------------------------------------------------------------


@dataclass(frozen=True)
class Param:
    name: str
    type: Type


# ---- Types -------------------------------------------------------------------


@dataclass(frozen=True)
class SimpleType:
    name: str


@dataclass(frozen=True)
class TupleType:
    types: tuple[Type, ...]


@dataclass(frozen=True)
class GenericType:
    name: str
    args: tuple[Union[Type, Expression], ...]


@dataclass(frozen=True)
class MaybeType:
    inner: Type


# An interface reference is structurally a type but the grammar restricts
# it to a simple name or generic instantiation (no tuple / maybe forms).
InterfaceRef = Union[SimpleType, GenericType]

Type = Union[SimpleType, TupleType, GenericType, MaybeType]


# ---- Statements --------------------------------------------------------------


@dataclass(frozen=True)
class Block:
    statements: tuple[Statement, ...]


@dataclass(frozen=True)
class AssignStatement:
    target: AssignTarget
    op: str
    value: Expression


@dataclass(frozen=True)
class ExpressionStatement:
    expression: Expression


@dataclass(frozen=True)
class IfStatement:
    condition: Expression
    then_branch: Statement
    else_branch: Optional[Statement]


@dataclass(frozen=True)
class WhileStatement:
    condition: Expression
    body: Statement


@dataclass(frozen=True)
class ForStatement:
    variable: IterationVariable
    iterable: Expression
    body: Statement


@dataclass(frozen=True)
class BreakStatement:
    pass


@dataclass(frozen=True)
class ContinueStatement:
    pass


@dataclass(frozen=True)
class ReturnStatement:
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
class Name:
    name: str


@dataclass(frozen=True)
class IndexLValue:
    obj: Name
    index: Expression


@dataclass(frozen=True)
class TupleLValue:
    names: tuple[str, ...]


@dataclass(frozen=True)
class MemberLValue:
    obj: Name
    name: str


AssignTarget = Union[Name, IndexLValue, TupleLValue, MemberLValue]
IterationVariable = Union[Name, TupleLValue]


# ---- Expressions -------------------------------------------------------------


@dataclass(frozen=True)
class IntLiteral:
    value: int


@dataclass(frozen=True)
class FloatLiteral:
    value: float


@dataclass(frozen=True)
class StringLiteral:
    value: str


@dataclass(frozen=True)
class CharLiteral:
    value: str


@dataclass(frozen=True)
class BoolLiteral:
    value: bool


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: tuple[Expression, ...]


@dataclass(frozen=True)
class MethodCall:
    obj: Expression
    name: str
    args: tuple[Expression, ...]


@dataclass(frozen=True)
class Indexing:
    obj: Expression
    index: Expression


@dataclass(frozen=True)
class MaybeUnwrap:
    expr: Expression


@dataclass(frozen=True)
class MemberAccess:
    obj: Expression
    name: str


@dataclass(frozen=True)
class BinaryOp:
    op: str
    left: Expression
    right: Expression


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: Expression


@dataclass(frozen=True)
class Conditional:
    condition: Expression
    then_expr: Expression
    else_expr: Expression


@dataclass(frozen=True)
class ParenExpr:
    expr: Expression


@dataclass(frozen=True)
class ArrayLiteral:
    elements: tuple[Expression, ...]


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
]
