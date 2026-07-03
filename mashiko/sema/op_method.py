"""Mapping from operator kind to its method name.

Used by the semantic analyzer to resolve a ``BinaryOp``/``UnaryOp`` AST
node to the trait method that implements it on the operand's type.
"""

from ..parser.syntax import BinaryOpKind, UnaryOpKind


def binary_op_method(op: BinaryOpKind) -> str:
    match op:
        case BinaryOpKind.ADD: return "add"
        case BinaryOpKind.SUBTRACT: return "sub"
        case BinaryOpKind.MULTIPLY: return "mul"
        case BinaryOpKind.DIVIDE: return "div"
        case BinaryOpKind.MODULO: return "mod"
        case BinaryOpKind.EQUAL: return "eq"
        case BinaryOpKind.NOT_EQUAL: return "neq"
        case BinaryOpKind.LESS: return "lt"
        case BinaryOpKind.GREATER: return "gt"
        case BinaryOpKind.LESS_EQUAL: return "leq"
        case BinaryOpKind.GREATER_EQUAL: return "geq"
        case BinaryOpKind.LOGICAL_OR: return "or"
        case BinaryOpKind.LOGICAL_AND: return "and"
        case BinaryOpKind.BITWISE_OR: return "bitor"
        case BinaryOpKind.BITWISE_XOR: return "bitxor"
        case BinaryOpKind.BITWISE_AND: return "bitand"
        case _: raise ValueError(f"No method for binary operator: {op!r}")


def unary_op_method(op: UnaryOpKind) -> str:
    match op:
        case UnaryOpKind.NEGATE: return "neg"
        case UnaryOpKind.NOT: return "not"
        case _: raise ValueError(f"No method for unary operator: {op!r}")
