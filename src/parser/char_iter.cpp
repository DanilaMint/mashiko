#include "char_iter.h"

#include <cstdint>
#include <stdint.h>
#include <optional>
#include <string_view>

uint8_t sizeOfFirstUtf8Char(std::string_view str) {
    if (str.empty()) { return 0; }

    uint8_t first = static_cast<uint8_t>(str[0]);

    if ( (first & 0x80) == 0 ) { return 1; }
    else if ( (first & 0xE0) == 0xC0 ) { return 2; }
    else if ( (first & 0xF0) == 0xE0 ) { return 3; }
    else if ( (first & 0xF8) == 0xF0 ) { return 4; }

    return 0;
}

std::optional<char32_t> readFirstUtf8Char(std::string_view str) {
    if (str.empty()) {
        return std::nullopt;
    }

    uint8_t first = static_cast<uint8_t>(str[0]);

    if ((first & 0x80) == 0) {
        return first;
    }

    if ((first & 0xE0) == 0xC0) {
        if (str.length() < 2) return std::nullopt;
        uint8_t second = static_cast<uint8_t>(str[1]);
        if ((second & 0xC0) != 0x80) return std::nullopt;

        return ((first & 0x1F) << 6) | (second & 0x3F);
    }

    if ((first & 0xF0) == 0xE0) {
        if (str.length() < 3) return std::nullopt;
        uint8_t second = static_cast<uint8_t>(str[1]);
        uint8_t third = static_cast<uint8_t>(str[2]);
        if ((second & 0xC0) != 0x80 || (third & 0xC0) != 0x80) return std::nullopt;

        return ((first & 0x0F) << 12) | ((second & 0x3F) << 6) | (third & 0x3F);
    }

    if ((first & 0xF8) == 0xF0) {
        if (str.length() < 4) return std::nullopt;
        uint8_t second = static_cast<uint8_t>(str[1]);
        uint8_t third = static_cast<uint8_t>(str[2]);
        uint8_t fourth = static_cast<uint8_t>(str[3]);
        if ((second & 0xC0) != 0x80 || (third & 0xC0) != 0x80 || (fourth & 0xC0) != 0x80) {
            return std::nullopt;
        }

        return ((first & 0x07) << 18) | ((second & 0x3F) << 12) | ((third & 0x3F) << 6) | (fourth & 0x3F);
    }

    return std::nullopt;
}

std::string_view CharIterator::getSubStr() {
    return this->_source.substr(this->_idx);
}

std::string_view CharIterator::slice(size_t start, size_t end) {
    return this->_source.substr(start, end - start);
}

void CharIterator::advance() {
    std::optional<char32_t> ch = this->next();
    if (ch.has_value()) {
        if (ch.value() == '\n') {
            this->_line += 1;
            this->_column = 1;
        } else {
            this->_column += 1;
        }
    }
}

std::optional<char32_t> CharIterator::current() {
    return readFirstUtf8Char(this->getSubStr());
}

std::optional<char32_t> CharIterator::next() {
    uint8_t size = sizeOfFirstUtf8Char(this->getSubStr());
    std::optional<char32_t> ch = this->current();
    this->_idx += size;
    return ch;
}

size_t CharIterator::id() { return this->_idx; }

ulong CharIterator::line() { return this->_line; }

ulong CharIterator::column() { return this->_column; }
