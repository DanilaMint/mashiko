from typing import Dict, List, Optional

from mashiko.errors import TranslationError
from mashiko.sema.op_method import binary_op_method, unary_op_method

# from tests.test_errors import ast
from ..parser.syntax import (
    ArrayLiteral,
    AssignStatement,
    BinaryOp,
    Block,
    BoolLiteral,
    CharLiteral,
    ClassDecl,
    Conditional,
    Declaration,
    Expression,
    Field,
    FloatLiteral,
    FunctionCall,
    FunctionDecl,
    GenericType,
    Indexing,
    InterfaceDecl,
    IntLiteral,
    MaybeType,
    MaybeUnwrap,
    MemberAccess,
    Method,
    MethodCall,
    Module,
    Name,
    ParenExpr,
    SimpleType,
    StringLiteral,
    TupleType,
    Type,
    UnaryOp,
)
from .symbol import (
    ClassSymbol,
    FunctionSymbol,
    InterfaceSymbol,
    MaybeTypeSymbol,
    MethodSymbol,
    PrimitiveTypeSymbol,
    Symbol,
    TupleTypeSymbol,
    TypeSymbol,
    UserDefinedTypeSymbol,
)

GENERIC_EXCEPTION = Exception("GENERICS ARE NOT READY NOW!!!")


def type_to_symbol(t: Type) -> TypeSymbol:
    match t:
        case SimpleType(name=name):
            primitive = PrimitiveTypeSymbol.from_str(name)
            return primitive if primitive is not None else UserDefinedTypeSymbol(name)

        case TupleType(types=types):
            return TupleTypeSymbol(tuple(type_to_symbol(i) for i in types))

        case GenericType():
            raise GENERIC_EXCEPTION

        case MaybeType(inner=inner):
            return MaybeTypeSymbol(type_to_symbol(inner))

        case _:
            return None


class Scope:
    symbols: Dict[str, Symbol]
    parent_scope: Optional["Scope"]

    def __init__(self, parent_scope: Optional["Scope"]):
        self.parent_scope = parent_scope
        self.symbols = {}

    def push_symbol(self, ident: str, sym: Symbol) -> Optional[Symbol]:
        """Push symbol to current scope and returns old symbol"""
        prev = self.symbols.get(ident)
        self.symbols[ident] = sym
        return prev

    def get_symbol(self, ident: str) -> Optional[Symbol]:
        curr = self._get_symbol_current(ident)
        if curr is not None:
            return curr

        else:
            return self._get_symbol_parent(ident)

    def _get_symbol_current(self, ident: str) -> Optional[Symbol]:
        return self.symbols.get(ident)

    def _get_symbol_parent(self, ident: str) -> Optional[Symbol]:
        if self.parent_scope is not None:
            return self.parent_scope.get_symbol(ident)
        return None

    def get_parent_scope(self) -> Optional["Scope"]:
        return self.parent_scope


class SemaAnalyzer:
    current_scope: Scope
    ast: Module
    errors: List[TranslationError]

    def __init__(self, ast: Module):
        self.ast = ast
        self.current_scope = Scope(None)

    def register_declarations(self):
        # Preregister
        prereg: Dict[str, Declaration] = {}
        for decl in self.ast.declarations:
            prereg[decl.name] = decl

        for i in prereg.values():
            match i:
                case FunctionDecl():
                    self.register_function(i)

                case ClassDecl():
                    self.register_class(i)

                case InterfaceDecl():
                    self.register_interface(i)

                case _:
                    raise TranslationError(i.span)

    def register_function(self, f: FunctionDecl):
        if f.template is None:
            types = [type_to_symbol(p.type) for p in f.params]
            return_type = (
                type_to_symbol(f.return_type)
                if f.return_type is not None
                else PrimitiveTypeSymbol.Void
            )
            sym = FunctionSymbol(types, return_type)

            self.current_scope.push_symbol(f.name, sym)
        else:
            raise GENERIC_EXCEPTION

    def register_class(self, c: ClassDecl):
        if c.template is None:
            public_fields: Dict[str, TypeSymbol] = {}
            private_fields: Dict[str, TypeSymbol] = {}
            public_methods: Dict[str, MethodSymbol] = {}
            private_methods: Dict[str, MethodSymbol] = {}
            for member in c.body.members:
                match member:
                    case Field():
                        field_type = type_to_symbol(member.type)
                        if member.visibility:
                            public_fields[member.name] = field_type
                        else:
                            private_fields[member.name] = field_type

                    case Method():
                        params = [type_to_symbol(p.type) for p in member.params]
                        return_type = (
                            type_to_symbol(member.return_type)
                            if member.return_type is not None
                            else PrimitiveTypeSymbol.Void
                        )
                        method_sym = MethodSymbol(params, return_type, member.static)
                        if member.visibility:
                            public_methods[member.name] = method_sym
                        else:
                            private_methods[member.name] = method_sym

            parent_interfaces = [iface.name for iface in c.interfaces]
            sym = ClassSymbol(
                parent_interfaces,
                public_methods,
                private_methods,
                public_fields,
                private_fields,
            )
            self.current_scope.push_symbol(c.name, sym)
        else:
            raise GENERIC_EXCEPTION

    def register_interface(self, i: InterfaceDecl):
        if i.template is None:
            public_methods: Dict[str, MethodSymbol] = {}
            for method in i.body.methods:
                params = [type_to_symbol(p.type) for p in method.params]
                return_type = (
                    type_to_symbol(method.return_type)
                    if method.return_type is not None
                    else PrimitiveTypeSymbol.Void
                )
                public_methods[method.name] = MethodSymbol(
                    params, return_type, method.static
                )

            parent_interfaces = [iface.name for iface in i.interfaces]
            sym = InterfaceSymbol(parent_interfaces, public_methods)
            self.current_scope.push_symbol(i.name, sym)
        else:
            raise GENERIC_EXCEPTION

    def check_block(self, ast: Block):
        # Создание нового скопа
        self.current_scope = Scope(self.current_scope)

        for stmt in ast.statements:
            match stmt:
                case AssignStatement():
                    ...

    def get_expression_type(self, expr: Expression) -> Optional[TypeSymbol]:
        match expr:
            case IntLiteral():
                return PrimitiveTypeSymbol.Int

            case FloatLiteral():
                return PrimitiveTypeSymbol.Float64

            case StringLiteral():
                return UserDefinedTypeSymbol("String")

            case CharLiteral():
                return PrimitiveTypeSymbol.Char32

            case BoolLiteral():
                return PrimitiveTypeSymbol.Bool

            case Name(name=name):
                return UserDefinedTypeSymbol(name)

            case FunctionCall(name=call_name):
                function_symbol = self.current_scope.get_symbol(call_name)
                if isinstance(function_symbol, FunctionSymbol):
                    return function_symbol.return_type
                else:
                    return None

            case MethodCall(name=method_name):
                obj_type = self.get_expression_type(expr.obj)
                if obj_type is None:
                    return None
                obj_methods = self.get_type_public_methods(obj_type)
                if obj_methods is None:
                    return None
                method = obj_methods.get(method_name)
                if method is None:
                    return None
                return method.return_type

            case Indexing():
                # Cant be realized now
                return None

            case MaybeUnwrap(expr=inner):
                return self.get_expression_type(inner)

            case MemberAccess(name=field_name):
                obj_type = self.get_expression_type(expr.obj)
                if obj_type is None:
                    return None
                obj_fields = self.get_type_public_fields(obj_type)
                if obj_fields is None:
                    return None
                return obj_fields.get(field_name)

            case BinaryOp():
                obj_type = self.get_expression_type(expr.left)
                if obj_type is None:
                    return None
                obj_methods = self.get_type_public_methods(obj_type)
                if obj_methods is None:
                    return None
                method = obj_methods.get(binary_op_method(expr.op))
                if method is None:
                    return None
                return method.return_type

            case UnaryOp():
                obj_type = self.get_expression_type(expr.operand)
                if obj_type is None:
                    return None
                obj_methods = self.get_type_public_methods(obj_type)
                if obj_methods is None:
                    return None
                method = obj_methods.get(unary_op_method(expr.op))
                if method is None:
                    return None
                return method.return_type

            case Conditional():
                if self.get_expression_type(expr.condition) != PrimitiveTypeSymbol.Bool:
                    # Докидывается TypeError, что условия должны быть Bool
                    return None

                then_type = self.get_expression_type(expr.then_expr)
                else_type = self.get_expression_type(expr.else_expr)

                if then_type != else_type or then_type is None or else_type is None:
                    # Докидывается TypeError, что результат должен быть одного и того же типа
                    return None

                return then_type

            case ParenExpr():
                ### WTF??? зачем нужен этот вариант
                ...

            case ArrayLiteral():
                ## Пока нельзя реализовать
                return None
                ...

    def get_type_public_methods(
        self, type: TypeSymbol
    ) -> Optional[Dict[str, MethodSymbol]]: ...

    def get_type_public_fields(
        self, type: TypeSymbol
    ) -> Optional[Dict[str, TypeSymbol]]: ...
