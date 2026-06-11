#ifndef POS_H
#define POS_H

#include <stddef.h>

class Position {
    private:
    size_t idx;
    unsigned long line;
    unsigned long column;

    public:
    Position(size_t idx, unsigned long line, unsigned long column);

    unsigned long get_index();

    unsigned long get_line();

    unsigned long get_column();
};

class Span {
    private:
    Position start;
    Position end;

    public:
    Span(Position start, Position end);

    Position get_start();

    size_t get_start_index();

    Position get_end();

    size_t get_end_index();
};

#endif