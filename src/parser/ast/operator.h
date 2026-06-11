#ifndef OPERATOR_NODE_H
#define OPERATOR_NODE_H

#include "node.h"

/// Operator `+`
typedef struct Plus {} Plus;
/// Operator `-`
typedef struct Minus {} Minus;
/// Operator `*`
typedef struct Asterisk {} Asterisk;
/// Operator `/`
typedef struct Slash {} Slash;
/// Operator `%`
typedef struct Percent {} Percent;

/// Operator `&&`
typedef struct And {} And;
/// Operator `||`
typedef struct Or {} Or;
/// Operator `!`
typedef struct Not {} Not;

/// Operator `&`
typedef struct Ampersand {} Ampersand;
/// Operator `|`
typedef struct BitOr {} BitOr;
/// Operator `^`
typedef struct BitXor {} BitXor;

/// Operator `=`
typedef struct Assign {} Assign;
/// Operator `+=`
typedef struct AddAssign {} AddAssign;
/// Operator `-=`
typedef struct SubAssign {} SubAssign;
/// Operator `*=`
typedef struct MulAssign {} MulAssign;
/// Operator `/=`
typedef struct DivAssign {} DivAssign;
/// Operator `%=`
typedef struct RemAssign {} RemAssign;

/// Operator `==`
typedef struct Equal {} Equal;
/// Operator `!=`
typedef struct NotEqual {} NotEqual;
/// Operator `<`
typedef struct Less {} Less;
/// Operator `>`
typedef struct Greater {} Greater;
/// Operator `<=`
typedef struct LessEqual {} LessEqual;
/// Operator `>=`
typedef struct GreaterEqual {} GreaterEqual;

/// Operator `?`
typedef struct Question {} Question;

using ArithmeticOperator = flatten_variant_t<Plus, Minus, Asterisk, Slash, Percent>;
using BooleanOperator = flatten_variant_t<And, Or, Not>;
using BitOperator = flatten_variant_t<Ampersand, BitOr, BitXor>;
using EquationOperator = flatten_variant_t<Equal, NotEqual>;
using OrderingOperator = flatten_variant_t<EquationOperator, Less, Greater, LessEqual, GreaterEqual>;
using BinaryOperator = flatten_variant_t<ArithmeticOperator, BitOperator, And, Or, OrderingOperator>;
using UnaryOperator = flatten_variant_t<Asterisk, Ampersand, Not, Minus>;
using UnaryPostOperator = flatten_variant_t<Question>;

using AssignOperator = flatten_variant_t<Assign, AddAssign, SubAssign, MulAssign, DivAssign, RemAssign>;

#endif
