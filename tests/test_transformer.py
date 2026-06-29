"""Tests for mashiko.transformer.

Verifies that ``parse_ast`` (which runs ``TreeToAST`` over the Lark tree)
produces well-formed dataclass instances for examples that already parse.
"""

import unittest
from pathlib import Path

from mashiko import parse_ast, parse_ast_file
from mashiko.parser.syntax import (
    BinaryOp,
    Block,
    ClassBody,
    ClassDecl,
    FloatLiteral,
    FunctionDecl,
    GenericType,
    IfStatement,
    IntLiteral,
    InterfaceBody,
    InterfaceDecl,
    InterfaceMethod,
    MethodCall,
    Module,
    Name,
    Param,
    ReturnStatement,
    SimpleType,
    WhileStatement,
)

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


class InterfacesASTTests(unittest.TestCase):
    """Typed AST for examples/interfaces.msk."""

    @classmethod
    def setUpClass(cls):
        cls.module, cls.errors = parse_ast_file(EXAMPLES_DIR / "interfaces.msk")

    def setUp(self):
        self.assertEqual(self.errors, [])
        self.assertIsNotNone(self.module)

    def test_module_shape(self):
        self.assertIsInstance(self.module, Module)
        self.assertEqual(len(self.module.declarations), 2)

    def test_interface_decl(self):
        iface = self.module.declarations[0]
        self.assertIsInstance(iface, InterfaceDecl)
        self.assertEqual(iface.name, "ByteView")
        self.assertEqual(iface.interfaces, ())
        self.assertIsInstance(iface.body, InterfaceBody)
        self.assertEqual(len(iface.body.methods), 1)

    def test_interface_method_is_abstract(self):
        meth = self.module.declarations[0].body.methods[0]
        self.assertIsInstance(meth, InterfaceMethod)
        self.assertEqual(meth.name, "bytes")
        self.assertEqual(meth.params, ())
        self.assertIsInstance(meth.return_type, GenericType)
        self.assertEqual(meth.return_type.name, "Array")
        self.assertEqual(len(meth.return_type.args), 1)
        self.assertEqual(meth.return_type.args[0].name, "Byte")
        # No block body — terminated by `;` → abstract.
        self.assertIsNone(meth.body)

    def test_class_implements_interface(self):
        cls = self.module.declarations[1]
        self.assertIsInstance(cls, ClassDecl)
        self.assertEqual(cls.name, "Int")
        self.assertEqual(len(cls.interfaces), 1)
        self.assertEqual(cls.interfaces[0].name, "ByteView")
        self.assertIsInstance(cls.body, ClassBody)


class FindSuperPrimeASTTests(unittest.TestCase):
    """Typed AST for examples/find_super_prime.msk."""

    @classmethod
    def setUpClass(cls):
        cls.module, cls.errors = parse_ast_file(EXAMPLES_DIR / "find_super_prime.msk")

    def setUp(self):
        self.assertEqual(self.errors, [])
        self.assertIsNotNone(self.module)

    def test_two_functions(self):
        self.assertEqual(len(self.module.declarations), 2)
        names = [d.name for d in self.module.declarations]
        self.assertEqual(names, ["is_prime", "get_super_primes"])

    def test_is_prime_signature(self):
        f = self.module.declarations[0]
        self.assertIsInstance(f, FunctionDecl)
        self.assertEqual(len(f.params), 1)
        self.assertIsInstance(f.params[0], Param)
        self.assertEqual(f.params[0].name, "n")
        self.assertIsInstance(f.params[0].type, SimpleType)
        self.assertEqual(f.params[0].type.name, "Int")
        self.assertIsInstance(f.return_type, SimpleType)
        self.assertEqual(f.return_type.name, "Bool")
        self.assertIsInstance(f.body, Block)

    def test_is_prime_body_statements(self):
        stmts = self.module.declarations[0].body.statements
        kinds = [type(s).__name__ for s in stmts]
        self.assertEqual(kinds, ["IfStatement", "AssignStatement", "WhileStatement", "ReturnStatement"])

    def test_is_prime_if_condition_is_binary_op(self):
        stmt = self.module.declarations[0].body.statements[0]
        self.assertIsInstance(stmt, IfStatement)
        self.assertIsInstance(stmt.condition, BinaryOp)
        self.assertEqual(stmt.condition.op, "<")
        self.assertEqual(type(stmt.condition.left).__name__, "Name")
        self.assertEqual(stmt.condition.left.name, "n")
        self.assertIsInstance(stmt.condition.right, IntLiteral)
        self.assertEqual(stmt.condition.right.value, 2)

    def test_is_prime_while_condition_has_method_call(self):
        stmt = self.module.declarations[0].body.statements[2]
        self.assertIsInstance(stmt, WhileStatement)
        # acc * acc <= n  →  BinaryOp(<=, BinaryOp(*, acc, acc), n)
        self.assertIsInstance(stmt.condition, BinaryOp)
        self.assertEqual(stmt.condition.op, "<=")

    def test_get_super_primes_uses_generic_return_type(self):
        f = self.module.declarations[1]
        self.assertIsInstance(f.return_type, GenericType)
        self.assertEqual(f.return_type.name, "DynArray")
        self.assertEqual(f.return_type.args[0].name, "Int")

    def test_get_super_primes_has_method_call_expr_statement(self):
        # Somewhere inside get_super_primes is `primes.push(acc);` — an
        # expression statement whose expression is a MethodCall.
        f = self.module.declarations[1]

        def find_push(node):
            # Walk every dataclass instance recursively, yielding each
            # node so callers can filter the type they care about.
            if hasattr(node, "__dataclass_fields__"):
                yield node
                for field in node.__dataclass_fields__:
                    yield from find_push(getattr(node, field))
            elif isinstance(node, tuple):
                for child in node:
                    yield from find_push(child)

        method_calls = [
            mc for mc in find_push(f)
            if isinstance(mc, MethodCall) and mc.name == "push"
        ]
        self.assertGreaterEqual(len(method_calls), 1)
        push = method_calls[0]
        self.assertIsInstance(push.obj, Name)
        self.assertEqual(push.obj.name, "primes")
        self.assertEqual(len(push.args), 1)


class APITests(unittest.TestCase):
    def test_parse_ast_returns_module(self):
        m, errors = parse_ast("func f() { x = 1; }")
        self.assertEqual(errors, [])
        self.assertIsInstance(m, Module)
        self.assertEqual(len(m.declarations), 1)

    def test_parse_ast_empty_source(self):
        m, errors = parse_ast("")
        self.assertEqual(errors, [])
        self.assertIsInstance(m, Module)
        self.assertEqual(m.declarations, ())

    def test_parse_ast_literals_and_names(self):
        # `1 + 2.5` → BinaryOp(+, IntLiteral, FloatLiteral)
        m, errors = parse_ast("func f() { return 1 + 2.5; }")
        self.assertEqual(errors, [])
        f = m.declarations[0]
        ret = f.body.statements[0]
        self.assertIsInstance(ret, ReturnStatement)
        binop = ret.value
        self.assertIsInstance(binop, BinaryOp)
        self.assertEqual(binop.op, "+")
        self.assertIsInstance(binop.left, IntLiteral)
        self.assertIsInstance(binop.right, FloatLiteral)
        self.assertEqual(binop.right.value, 2.5)


if __name__ == "__main__":
    unittest.main()