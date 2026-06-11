#ifndef EXPRESSION_NODE_H
#define EXPRESSION_NODE_H

#include "node.h"
#include "literal.h"
#include "operator.h"
#include "punctuation.h"
#include "word.h"

struct BinOpExpression;
struct UnOpExpression;
struct UnOpPostExpression;
struct FunctionCallExpression;
struct MethodCallExpression;
struct TupleExpression;
struct ArrayExpression;
struct ConditionalExpression;

using Expression = flatten_variant_t<Literal, BinOpExpression, UnOpExpression,
    UnOpPostExpression, FunctionCallExpression, MethodCallExpression,
    TupleExpression, ArrayExpression, ConditionalExpression>;

typedef struct BinOpExpression {
    BoxedNode<Expression> lhs;
    Node<BinaryOperator> op;
    BoxedNode<Expression> rhs;
} BinOpExpression;

typedef struct UnOpExpression {
    Node<UnaryOperator> op;
    BoxedNode<Expression> val;
} UnOpExpression;

typedef struct UnOpPostExpression {
    BoxedNode<Expression> val;
    Node<UnaryPostOperator> op;
} UnOpPostExpression;

typedef struct TupleExpression {
    Node<LeftParen> lp;
    NodeList<Sequence<Node<Expression>>> args;
    OptionalBoxedNode<Expression> last_arg;
    Node<RightParen> rp;
} TupleExpression;

typedef struct ArrayExpression {
    Node<LeftBracket> lp;
    NodeList<Sequence<Node<Expression>>> args;
    OptionalBoxedNode<Expression> last_arg;
    Node<RightBracket> rp;
} ArrayExpression;

typedef struct FunctionCallExpression {
    Node<Ident> name;
    Node<LeftParen> lp;
    NodeList<Sequence<Node<Expression>>> args;
    OptionalBoxedNode<Expression> last_arg;
    Node<RightParen> rp;
} FunctionCallExpression;

typedef struct MethodCallExpression {
    BoxedNode<Expression> expr;
    Node<Dot> dot;
    Node<FunctionCallExpression> call;
} MethodCallExpression;

typedef struct ConditionalExpression {
    BoxedNode<Expression> value;
    Node<IfKeyword> ifkw;
    BoxedNode<Expression> condition;
    Node<ElseKeyword> elsekw;
    BoxedNode<Expression> else_value;
} ConditionalExpression;

#endif
