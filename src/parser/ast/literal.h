#ifndef LITERAL_NODE_H
#define LITERAL_NODE_H

#include "node.h"

#include <stdint.h>

typedef struct IntLiteral {
    unsigned long long value;
} IntLiteral;

typedef struct FloatLiteral {
    double value;
} FloatLiteral;

typedef struct BoolLiteral {
    bool value;
} BoolLiteral;

typedef struct CharLiteral {
    char32_t value;
} CharLiteral;

typedef struct StringLiteral {
    std::string value;
} StringLiteral;

using Literal = flatten_variant_t<IntLiteral, FloatLiteral, BoolLiteral, CharLiteral, StringLiteral>;

#endif
