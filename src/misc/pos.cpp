#include "pos.h"

Position::Position(size_t idx, unsigned long line, unsigned long column) {
    this->idx = idx;
    this->line = line;
    this->column = column;
}

unsigned long Position::get_index() {
    return this->idx;
}

unsigned long Position::get_line() {
    return this->line;
}

unsigned long Position::get_column() {
    return this->column;
}

Span::Span(Position start, Position end)
    : start(start), end(end) {}

Position Span::get_start() {
    return this->start;
}

size_t Span::get_start_index() {
    return this->start.get_index();
}

Position Span::get_end() {
    return this->end;
}

size_t Span::get_end_index() {
    return this->end.get_index();
}
