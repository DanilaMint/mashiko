#ifndef CHAR_ITER_H
#define CHAR_ITER_H

#include <string_view>
#include <stddef.h>
#include <optional>

typedef unsigned long ulong;

class CharIterator {
    private:
    std::string_view _source;
    size_t _idx;
    ulong _line;
    ulong _column;

    public:
    CharIterator(std::string_view str)
        : _source(str), _idx(0), _line(1), _column(1) {}

    std::string_view getSubStr();

    std::string_view slice(size_t start, size_t end);

    std::optional<char32_t> current();

    std::optional<char32_t> next();

    void advance();

    size_t id();

    ulong line();

    ulong column();
};

#endif
