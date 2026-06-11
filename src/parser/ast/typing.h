#ifndef TYPING_NODE_H
#define TYPING_NODE_H

#include "node.h"
#include "word.h"
#include "literal.h"
#include "punctuation.h"
#include "operator.h"

struct TupleType;
struct PointerType;
struct MaybeType;

using Type = flatten_variant_t<Ident>;

typedef struct TupleType {
    Node<LeftParen> lp;
    NodeList<Sequence<Type>> types;
    OptionalBoxedNode<Type> last_type;
    Node<RightParen> rp;
} TupleType;

typedef struct PointerType {
    Node<Ampersand> ptr;
    BoxedNode<Type> type;
} PointerType;

typedef struct MaybeType {
    BoxedNode<Type> type;
    Node<Question> qst;
} MaybeType;

typedef struct GenericType {
    Node<Ident> ident;
    Node<LeftChevrone> lp;
    NodeList<Sequence<Type>> types;
    OptionalBoxedNode<Type> last_type;
    Node<RightChevrone> rp;
} GenericType;

#endif
