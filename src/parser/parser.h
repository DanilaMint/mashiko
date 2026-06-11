#ifndef PARSER_H
#define PARSER_H

#include "./char_iter.h"
#include "./ast/punctuation.h"
#include "./ast/word.h"
#include "../misc/pos.h"
#include <string_view>

class Parser {
    private:
    CharIterator _it;

    public:
    Parser(std::string_view str): _it(CharIterator(str)) {}

    Position getPos();

    Span getSpan(Position start);

    OptionalNode<Comma> parseComma();
    OptionalNode<Dot> parseDot();
    OptionalNode<Semicolon> parseSemicolon();
    OptionalNode<Colon> parseColon();
    OptionalNode<LeftParen> parseLeftParen();
    OptionalNode<RightParen> parseRightParen();
    OptionalNode<LeftBracket> parseLeftBracket();
    OptionalNode<RightBracket> parseRightBracket();
    OptionalNode<LeftBrace> parseLeftBrace();
    OptionalNode<RightBrace> parseRightBrace();
    OptionalNode<LeftChevrone> parseLeftChevrone();
    OptionalNode<RightChevrone> parseRightChevrone();

    OptionalNode<Word> parseWord();
};

#endif
