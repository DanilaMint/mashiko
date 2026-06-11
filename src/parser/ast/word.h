#ifndef WORD_NODE_H
#define WORD_NODE_H

#include "node.h"

#include <string>

typedef struct Ident {
    std::string value;
} Ident;

/// keyword `if`
typedef struct IfKeyword {} IfKeyword;
/// keyword `else`
typedef struct ElseKeyword {} ElseKeyword;
/// Keyword `while`
typedef struct WhileKeyword {} WhileKeyword;
/// Keyword `for`
typedef struct ForKeyword {} ForKeyword;
/// Keyword `break`
typedef struct BreakKeyword {} BreakKeyword;
/// Keyword `continue`
typedef struct ContinueKeyword {} ContinueKeyword;
/// Keyword `return`
typedef struct ReturnKeyword {} ReturnKeyword;

/// Keyword `func`
typedef struct FuncKeyword {} FuncKeyword;
/// Keyword `class`
typedef struct ClassKeyword {} ClassKeyword;
/// Keyword `abstract`
typedef struct AbstractKeyword {} AbstractKeyword;
/// Keyword `public`
typedef struct PublicKeyword {} PublicKeyword;
/// Keyword `type`
typedef struct TypeKeyword {} TypeKeyword;

using ImperativeKeyword = flatten_variant_t<IfKeyword, ElseKeyword, WhileKeyword, ForKeyword, BreakKeyword, ContinueKeyword, ReturnKeyword>;
using DeclarativeKeyword = flatten_variant_t<FuncKeyword, ClassKeyword, AbstractKeyword, PublicKeyword, TypeKeyword>;

using Keyword = flatten_variant_t<ImperativeKeyword, DeclarativeKeyword>;

using Word = flatten_variant_t<Keyword, Ident>;

#endif
