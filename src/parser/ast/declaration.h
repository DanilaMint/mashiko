#ifndef DECLARATION_NODE_H
#define DECLARATION_NODE_H

#include "node.h"
#include "statement.h"
#include "word.h"
#include "punctuation.h"
#include "typing.h"

#include <tuple>

struct TypedIdentDeclaration;
struct GenericDeclaration;

typedef struct FuncDeclaration {
    Node<FuncKeyword> funckw;
    Node<Ident> name;
    Node<LeftParen> lp;
    NodeList<Sequence<TypedIdentDeclaration>> args;
    OptionalBoxedNode<TypedIdentDeclaration> last_arg;
    Node<RightParen> rp;
    OptionalNode<std::tuple<Colon, Type>> return_type;
    Node<Block> body;
} FuncDeclaration;

typedef struct GenericDeclaration {
    Node<Ident> ident;
    Node<LeftChevrone> lp;
    NodeList<Sequence<Ident>> types;
    OptionalNode<Ident> last_type;
    Node<RightChevrone> rp;
} GenericDeclaration;

typedef struct TypedIdentDeclaration {
    Node<Ident> ident;
    Node<Colon> colon;
    Node<Type> type;
} TypedIdentDeclaration;

typedef struct ClassDeclaration {
    Node<ClassKeyword> classkw;
    Node<Ident> name;
} ClassDeclaration;

#endif
