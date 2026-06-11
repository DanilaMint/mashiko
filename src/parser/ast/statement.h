#ifndef STATEMENT_NODE_H
#define STATEMENT_NODE_H

#include "node.h"
#include "punctuation.h"
#include "word.h"
#include "expression.h"
#include "operator.h"

struct ExprStatement;
struct VarStatement;
struct IfStatement;
struct Block;

using Statement = flatten_variant_t<ExprStatement, VarStatement, IfStatement, Block>;

typedef struct ExprStatement {
    Node<Expression> expr;
    Node<Semicolon> semicolon;
} ExprStatement;

typedef struct VarStatement {
    Node<Ident> var;
    Node<AssignOperator> op;
    Node<Expression> value;
    Node<Semicolon> semicolon;
} VarStatement;

typedef struct IfStatement {
    Node<IfKeyword> ifkw;
    Node<Expression> condition;
    BoxedNode<Statement> action;
    OptionalBoxedNode<Statement> else_action;
} IfStatement;

typedef struct Block {
    Node<LeftBrace> lp;
    NodeList<Statement> statements;
    Node<RightBrace> rp;
} Block;

#endif
