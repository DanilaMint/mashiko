"""Лексер языка mashiko (.msk)."""

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    # ключевые слова
    CLASS = auto()
    CONSTRUCTOR = auto()
    DESTRUCTOR = auto()
    INTERFACE = auto()
    FUNC = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    RETURN = auto()
    BREAK = auto()
    CONTINUE = auto()
    TRUE = auto()
    FALSE = auto()

    # литералы и идентификаторы
    IDENT = auto()
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    CHAR = auto()

    # пунктуация
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    LANGLE = auto()
    RANGLE = auto()
    COLON = auto()
    SEMICOLON = auto()
    COMMA = auto()
    DOT = auto()

    # операторы
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    EQ = auto()
    PLUS_EQ = auto()
    MINUS_EQ = auto()
    STAR_EQ = auto()
    SLASH_EQ = auto()
    PERCENT_EQ = auto()
    EQEQ = auto()
    BANG_EQ = auto()
    LE = auto()
    GE = auto()

    # логические и побитовые
    BANG = auto()
    AMP_AMP = auto()
    PIPE_PIPE = auto()
    AMP = auto()
    PIPE = auto()
    CARET = auto()
    TILDE = auto()
    MAYBE = auto()

    EOF = auto()


KEYWORDS: dict[str, TokenType] = {
    "class": TokenType.CLASS,
    "constructor": TokenType.CONSTRUCTOR,
    "destructor": TokenType.DESTRUCTOR,
    "interface": TokenType.INTERFACE,
    "func": TokenType.FUNC,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "return": TokenType.RETURN,
    "break": TokenType.BREAK,
    "continue": TokenType.CONTINUE,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}


@dataclass
class Token:
    type: TokenType
    value: str
    line: int
    col: int
    index: int

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.col}@{self.index})"


class LexerError(Exception):
    pass


class Lexer:
    def __init__(self, source: str) -> None:
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def _peek(self, offset: int = 0) -> str:
        idx = self.pos + offset
        return self.src[idx] if idx < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.src) and self.src[self.pos] in " \t\r\n":
            self._advance()

    def _skip_line_comment(self) -> None:
        while self.pos < len(self.src) and self.src[self.pos] != "\n":
            self._advance()

    def _skip_block_comment(self) -> None:
        start_line, start_col = self.line, self.col
        self._advance()
        self._advance()
        while self.pos < len(self.src):
            if self._peek(0) == "*" and self._peek(1) == "/":
                self._advance()
                self._advance()
                return
            self._advance()
        raise LexerError(f"unterminated block comment at {start_line}:{start_col}")

    def _number(self) -> Token:
        start_line, start_col = self.line, self.col
        start = self.pos
        if self._peek() == "0":
            nxt = self._peek(1)
            if nxt == "x" or nxt == "X":
                self._advance()
                self._advance()
                hex_start = self.pos
                while self.pos < len(self.src) and self.src[self.pos] in "0123456789abcdefABCDEF":
                    self._advance()
                if self.pos == hex_start:
                    raise LexerError(f"empty hex literal at {start_line}:{start_col}")
                return Token(
                    TokenType.INT,
                    self.src[start : self.pos],
                    start_line,
                    start_col,
                    start,
                )
            if nxt == "b" or nxt == "B":
                self._advance()
                self._advance()
                bin_start = self.pos
                while self.pos < len(self.src) and self.src[self.pos] in "01":
                    self._advance()
                if self.pos == bin_start:
                    raise LexerError(f"empty binary literal at {start_line}:{start_col}")
                return Token(
                    TokenType.INT,
                    self.src[start : self.pos],
                    start_line,
                    start_col,
                    start,
                )
        is_float = False
        while self.pos < len(self.src) and self.src[self.pos].isdigit():
            self._advance()
        if self.pos < len(self.src) and self.src[self.pos] == "." and (
            self._peek(1).isdigit() or self._peek(1) == ""
        ):
            is_float = True
            self._advance()
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                self._advance()
        if self.pos < len(self.src) and self.src[self.pos] in "eE":
            is_float = True
            self._advance()
            if self.pos < len(self.src) and self.src[self.pos] in "+-":
                self._advance()
            exp_start = self.pos
            while self.pos < len(self.src) and self.src[self.pos].isdigit():
                self._advance()
            if self.pos == exp_start:
                raise LexerError(f"empty exponent at {start_line}:{start_col}")
        value = self.src[start : self.pos]
        return Token(
            TokenType.FLOAT if is_float else TokenType.INT,
            value,
            start_line,
            start_col,
            start,
        )

    def _identifier(self) -> Token:
        start_line, start_col = self.line, self.col
        start = self.pos
        while self.pos < len(self.src) and (
            self.src[self.pos].isalnum() or self.src[self.pos] == "_"
        ):
            self._advance()
        text = self.src[start : self.pos]
        return Token(
            KEYWORDS.get(text, TokenType.IDENT), text, start_line, start_col, start
        )

    def _string(self) -> Token:
        start_line, start_col = self.line, self.col
        start = self.pos
        self._advance()
        chars: list[str] = []
        while self.pos < len(self.src):
            ch = self._peek()
            if ch == '"':
                self._advance()
                return Token(
                    TokenType.STRING, "".join(chars), start_line, start_col, start
                )
            if ch == "\n":
                raise LexerError(
                    f"unterminated string literal at {start_line}:{start_col}"
                )
            if ch == "\\":
                self._advance()
                if self.pos >= len(self.src):
                    raise LexerError(
                        f"unterminated string literal at {start_line}:{start_col}"
                    )
                esc = self._advance()
                match esc:
                    case "n":
                        chars.append("\n")
                    case "t":
                        chars.append("\t")
                    case "r":
                        chars.append("\r")
                    case "\\":
                        chars.append("\\")
                    case '"':
                        chars.append('"')
                    case "0":
                        chars.append("\0")
                    case _:
                        chars.append(esc)
            else:
                chars.append(self._advance())
        raise LexerError(
            f"unterminated string literal at {start_line}:{start_col}"
        )

    def _char(self) -> Token:
        start_line, start_col = self.line, self.col
        start = self.pos
        self._advance()
        if self.pos >= len(self.src) or self._peek() == "\n":
            raise LexerError(
                f"unterminated char literal at {start_line}:{start_col}"
            )
        ch = self._peek()
        if ch == "'":
            self._advance()
            raise LexerError(f"empty char literal at {start_line}:{start_col}")
        if ch == "\\":
            self._advance()
            if self.pos >= len(self.src) or self._peek() == "\n":
                raise LexerError(
                    f"unterminated char literal at {start_line}:{start_col}"
                )
            esc = self._advance()
            match esc:
                case "n":
                    value = "\n"
                case "t":
                    value = "\t"
                case "r":
                    value = "\r"
                case "\\":
                    value = "\\"
                case "'":
                    value = "'"
                case "0":
                    value = "\0"
                case _:
                    value = esc
        else:
            value = self._advance()
        if self.pos >= len(self.src) or self._peek() != "'":
            raise LexerError(
                f"unterminated char literal at {start_line}:{start_col}"
            )
        self._advance()
        return Token(TokenType.CHAR, value, start_line, start_col, start)

    def _emit(self, tt: TokenType, length: int = 1) -> Token:
        start = self.pos
        value = self.src[self.pos : self.pos + length]
        tok = Token(tt, value, self.line, self.col, start)
        for _ in range(length):
            self._advance()
        return tok

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.pos < len(self.src):
            self._skip_whitespace()
            if self.pos >= len(self.src):
                break

            ch = self._peek()

            if ch.isdigit():
                tokens.append(self._number())
                continue

            if ch == '"':
                tokens.append(self._string())
                continue

            if ch == "'":
                tokens.append(self._char())
                continue

            if ch.isalpha() or ch == "_":
                tokens.append(self._identifier())
                continue

            two = self._peek(0) + self._peek(1)
            match two:
                case "==":
                    tokens.append(self._emit(TokenType.EQEQ, 2))
                case "!=":
                    tokens.append(self._emit(TokenType.BANG_EQ, 2))
                case "<=":
                    tokens.append(self._emit(TokenType.LE, 2))
                case ">=":
                    tokens.append(self._emit(TokenType.GE, 2))
                case "+=":
                    tokens.append(self._emit(TokenType.PLUS_EQ, 2))
                case "-=":
                    tokens.append(self._emit(TokenType.MINUS_EQ, 2))
                case "*=":
                    tokens.append(self._emit(TokenType.STAR_EQ, 2))
                case "/=":
                    tokens.append(self._emit(TokenType.SLASH_EQ, 2))
                case "%=":
                    tokens.append(self._emit(TokenType.PERCENT_EQ, 2))
                case "&&":
                    tokens.append(self._emit(TokenType.AMP_AMP, 2))
                case "||":
                    tokens.append(self._emit(TokenType.PIPE_PIPE, 2))
                case "//":
                    self._skip_line_comment()
                case "/*":
                    self._skip_block_comment()
                case _:
                    match ch:
                        case "(":
                            tokens.append(self._emit(TokenType.LPAREN))
                        case ")":
                            tokens.append(self._emit(TokenType.RPAREN))
                        case "{":
                            tokens.append(self._emit(TokenType.LBRACE))
                        case "}":
                            tokens.append(self._emit(TokenType.RBRACE))
                        case "[":
                            tokens.append(self._emit(TokenType.LBRACKET))
                        case "]":
                            tokens.append(self._emit(TokenType.RBRACKET))
                        case "<":
                            tokens.append(self._emit(TokenType.LANGLE))
                        case ">":
                            tokens.append(self._emit(TokenType.RANGLE))
                        case ":":
                            tokens.append(self._emit(TokenType.COLON))
                        case ";":
                            tokens.append(self._emit(TokenType.SEMICOLON))
                        case ",":
                            tokens.append(self._emit(TokenType.COMMA))
                        case ".":
                            tokens.append(self._emit(TokenType.DOT))
                        case "+":
                            tokens.append(self._emit(TokenType.PLUS))
                        case "-":
                            tokens.append(self._emit(TokenType.MINUS))
                        case "*":
                            tokens.append(self._emit(TokenType.STAR))
                        case "/":
                            tokens.append(self._emit(TokenType.SLASH))
                        case "%":
                            tokens.append(self._emit(TokenType.PERCENT))
                        case "=":
                            tokens.append(self._emit(TokenType.EQ))
                        case "!":
                            tokens.append(self._emit(TokenType.BANG))
                        case "&":
                            tokens.append(self._emit(TokenType.AMP))
                        case "|":
                            tokens.append(self._emit(TokenType.PIPE))
                        case "^":
                            tokens.append(self._emit(TokenType.CARET))
                        case "~":
                            tokens.append(self._emit(TokenType.TILDE))
                        case "?":
                            tokens.append(self._emit(TokenType.MAYBE))
                        case _:
                            raise LexerError(
                                f"unexpected character {ch!r} at {self.line}:{self.col}"
                            )

        tokens.append(Token(TokenType.EOF, "", self.line, self.col, self.pos))
        return tokens
