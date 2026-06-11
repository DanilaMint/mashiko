#ifndef PUNCTUATION_NODE_H
#define PUNCTUATION_NODE_H

#include "node.h"

#include <tuple>

/// Punctuation symbol `,`
typedef struct Comma {} Comma;
/// Punctuation symbol `.`
typedef struct Dot {} Dot;
/// Punctuation symbol `;`
typedef struct Semicolon {} Semicolon;
/// Punctuation symbol `:`
typedef struct Colon {} Colon;
/// Punctuation symbol `(`
typedef struct LeftParen {} LeftParen;
/// Punctuation symbol `)`
typedef struct RightParen {} RightParen;
/// Punctuation symbol `(`
typedef struct LeftBracket {} LeftBracket;
/// Punctuation symbol `)`
typedef struct RightBracket {} RightBracket;
/// Punctuation symbol `(`
typedef struct LeftBrace {} LeftBrace;
/// Punctuation symbol `)`
typedef struct RightBrace {} RightBrace;
/// Punctuation symbol `<`
typedef struct LeftChevrone {} LeftChevrone;
/// Punctuation symbol `>`
typedef struct RightChevrone {} RightChevrone;

///
template<typename T>
using Sequence = std::tuple<T, Comma>;

using Parens = flatten_variant_t<LeftParen, RightParen>;
using Brackets = flatten_variant_t<LeftBracket, RightBracket>;
using Braces = flatten_variant_t<LeftBrace, RightBrace>;
using Chevrones = flatten_variant_t<LeftChevrone, RightChevrone>;

using PunctuationSymbols = flatten_variant<Comma, Dot, Semicolon, Colon, Parens, Brackets, Braces, Chevrones>;

#endif
