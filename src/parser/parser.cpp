#include "parser.h"

#define PUNCT_PARSER_BODY(T, ch)                                       \
    std::optional<char32_t> curr = this->_it.current();                \
    if (!curr.has_value() || curr.value() != ch) { return std::nullopt; } \
    Position start = this->getPos();                                   \
    this->_it.advance();                                               \
    return Node<T>(T(), this->getSpan(start));

Position Parser::getPos() {
    return Position(this->_it.id(), this->_it.line(), this->_it.column());
}

Span Parser::getSpan(Position start) {
    Position end = this->getPos();
    return Span(start, end);
}

OptionalNode<Comma> Parser::parseComma() { PUNCT_PARSER_BODY(Comma, ','); }
OptionalNode<Dot> Parser::parseDot() { PUNCT_PARSER_BODY(Dot, '.'); }
OptionalNode<Semicolon> Parser::parseSemicolon() { PUNCT_PARSER_BODY(Semicolon, ';'); }
OptionalNode<Colon> Parser::parseColon() { PUNCT_PARSER_BODY(Colon, ':'); }
OptionalNode<LeftParen> Parser::parseLeftParen() { PUNCT_PARSER_BODY(LeftParen, '('); }
OptionalNode<RightParen> Parser::parseRightParen() { PUNCT_PARSER_BODY(RightParen, ')'); }
OptionalNode<LeftBracket> Parser::parseLeftBracket() { PUNCT_PARSER_BODY(LeftBracket, '['); }
OptionalNode<RightBracket> Parser::parseRightBracket() { PUNCT_PARSER_BODY(RightBracket, ']'); }
OptionalNode<LeftBrace> Parser::parseLeftBrace() { PUNCT_PARSER_BODY(LeftBrace, '{'); }
OptionalNode<RightBrace> Parser::parseRightBrace() { PUNCT_PARSER_BODY(RightBrace, '}'); }
OptionalNode<LeftChevrone> Parser::parseLeftChevrone() { PUNCT_PARSER_BODY(LeftChevrone, '<'); }
OptionalNode<RightChevrone> Parser::parseRightChevrone() { PUNCT_PARSER_BODY(RightChevrone, '>'); }

static bool isIdentStart(char32_t ch) {
    return (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z') || ch == '_';
}

static bool isIdentContinue(char32_t ch) {
    return isIdentStart(ch) || (ch >= '0' && ch <= '9');
}

#define MATCH_KEYWORD(literal, Type) \
    if (word == literal) return Node<Word>(Word(Type()), span);

OptionalNode<Word> Parser::parseWord() {
    std::optional<char32_t> first = this->_it.current();
    if (!first.has_value() || !isIdentStart(first.value())) { return std::nullopt; }

    Position startPos = this->getPos();
    this->_it.advance();

    while (true) {
        std::optional<char32_t> curr = this->_it.current();
        if (!curr.has_value() || !isIdentContinue(curr.value())) { break; }
        this->_it.advance();
    }

    Span span = this->getSpan(startPos);
    size_t endIdx = this->getPos().get_index();
    std::string_view word = this->_it.slice(static_cast<size_t>(startPos.get_index()), endIdx);

    MATCH_KEYWORD("if", IfKeyword)
    MATCH_KEYWORD("else", ElseKeyword)
    MATCH_KEYWORD("while", WhileKeyword)
    MATCH_KEYWORD("for", ForKeyword)
    MATCH_KEYWORD("break", BreakKeyword)
    MATCH_KEYWORD("continue", ContinueKeyword)
    MATCH_KEYWORD("return", ReturnKeyword)
    MATCH_KEYWORD("func", FuncKeyword)
    MATCH_KEYWORD("class", ClassKeyword)
    MATCH_KEYWORD("abstract", AbstractKeyword)
    MATCH_KEYWORD("public", PublicKeyword)
    MATCH_KEYWORD("type", TypeKeyword)

    return Node<Word>(Word(Ident{std::string(word)}), span);
}
