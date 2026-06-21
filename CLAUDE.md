# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`mashiko` — a frontend for the `mashiko` programming language (`.msk` files). The pipeline is currently lexer → parser → AST; type-checking, desugaring, and C codegen are stubs (see "Roadmap" below). Single runtime dependency: `lark>=1.1,<2`. Python ≥ 3.10.

## Build / Run

No build step. No tests. No linter. Just run:

```
python main.py <file.msk>                  # parse, print summary
python main.py <file.msk> -t               # also print AST tree (bash-tree style, ANSI-colored)
python main.py <file.msk> -o result.c      # write placeholder output to result.c
python main.py <file.msk> --log detail     # verbose: list functions, mangle/output status
python main.py --help                      # CLI flags
```

`result.c` content is the literal string `"mashiko: codegen pending\n"` until `cgen.py` is wired up — do not expect real C output. `--mangle` is accepted but currently has no effect (logged only).

## Architecture

Source `.msk` → `mashiko.lexer.Lexer.tokenize()` → `mashiko.parser._MashikoLarkLexer` (lark external-lexer adapter) → lark Earley parse against `mashiko.lark` (loaded from `mashiko/mashiko.lark` via `__file__`) → `mashiko.parser._MashikoTransformer` builds `Spanned[Module]` → `mashiko.print_ast.print_ast` for `--tree`.

Layout: flat Python package `mashiko/` at the repo root; `main.py` is the entry-point script and stays at the root alongside `examples/`, `pyproject.toml`, `.gitignore`, `CLAUDE.md`. `result.c` is a build artifact (untracked; output of `-o`).

Modules, in pipeline order:

- **`mashiko/lexer.py`** — hand-written tokenizer. `TokenType` enum, `Token` dataclass (`type, value, line, col, index`), `Lexer` class with `tokenize()`. Throws `LexerError`. Supports int literals (`0x`, `0b`, decimal), floats with exponents, strings, chars, all operators in `mashiko.lark`. Single-line (`//`) and block (`/* */`) comments.
- **`mashiko/mashiko.lark`** — Earley grammar (lives inside the package so `parser.py` can locate it via `__file__`, independent of cwd). Terminal names must equal `TokenType.name` from `lexer.py` (lark matches external tokens by name; regex patterns on terminals are placeholders only). Binary operators form a left-associative precedence ladder via `?expression` aliases that collapse single-child rules.
- **`mashiko/parser.py`** — wires our `Lexer` into lark via `_MashikoLarkLexer` (subclass of `lark.lexer.Lexer` with `__future_interface__ = 1`, which switches lark to call `lex(self, lexer_state, parser_state)` instead of the legacy `lex(self, text)`). Sets `lt.start_pos = tok.index` on each LarkToken because lark doesn't auto-fill positions for external tokens. `_MashikoTransformer` then maps `LarkToken.type` (a string == `TokenType.name`) to `BinOp`/`UnaryOp`/`AssignOp` enums via three lookup dicts at the top of the file, and constructs `Spanned[T]` nodes with spans computed from the first/last child.
- **`mashiko/syntax.py`** — AST. All nodes are frozen dataclasses with `slots=True`. Spans live on `Spanned[T]` wrappers, not on the nodes themselves. Marker classes (`Type`, `Expr`, `Stmt`, `Lvalue`, `Iterable`) subclassed by nodes enable `isinstance(node.node, Expr)` checks. Operator enums (`BinOp`, `UnaryOp`, `AssignOp`) use **shape names** (PLUS, LANGLE, AMP_AMP), not semantic ones — keep this consistent when adding operators.
- **`mashiko/print_ast.py`** — `print_ast(node, file=sys.stdout)`. Uses ANSI colors (disabled when `NO_COLOR` env var is set or `file.isatty()` is false). Walks dataclass fields, treats `Spanned`/dataclass/tuple-of-dataclass as children, renders scalars inline. `└── ` / `├── ` connectors.
- **`main.py`** — entry point. Imports use the package form: `from mashiko import cli, parser`, `from mashiko.optional import Optional`, `from mashiko.print_ast import print_ast`.
- **`mashiko/cgen.py`** — `CGenerator` class skeleton (empty `code` buffer). Currently unused; `main.py` writes the placeholder `result.c` directly.
- **`mashiko/desugar.py`** — empty placeholder.
- **`mashiko/cli.py`** — argparse setup. Note typo: `--log` choice `"standart"` (not `"standard"`).
- **`mashiko/optional.py`** — local `Optional[T]` dataclass; `unwrap()` raises generic `Exception` on `None`. Don't add to it — use stdlib `T | None` for new code.

Imports inside the package are relative (`from .lexer import ...`, `from . import syntax as ast`); `main.py` is the only thing that uses absolute `from mashiko.X import ...`.

## Conventions

- **Spans**: every parsed AST node is wrapped in `Spanned(node, span)`. `Span` has `start_index, start_line, start_col, end_index, end_line, end_col` (1-based line/col; `end_*` is exclusive — `src[span.start_index:span.end_index]` reproduces the construct). Types that don't carry source positions (`Param`, `FunctionDef`, `Module`, `Block`) are bare dataclasses, not `Spanned`. `Spanned` itself is generic in `T` for type hints.
- **Marker-class check**: `isinstance(spanned.node, Expr)`, not `isinstance(spanned, Expr)`.
- **Operator names**: keep shape tokens (`PLUS`, `LANGLE`, `AMP_AMP`, `MAYBE`) — both the lexer, the lark grammar, the parser's token-name dicts, and `syntax.py`'s `BinOp`/`UnaryOp`/`AssignOp` enums must stay in lockstep. Adding an operator means editing four files.
- **External lexer contract**: lark matches tokens to terminals by `TokenType.name`. The `_MashikoLarkLexer.lex()` generator must skip the `EOF` sentinel and set `lt.start_pos` manually.
- **Transformer span computation**: `_span(items, src)` walks `items` skipping `None` and empty lists, takes start from first non-empty child, end from last. Empty inputs yield a zeroed `Span` — only valid for the empty `module` case.
- **Comments and CLI strings are in Russian** — preserve this when adding user-facing text.

## Examples

`examples/find_super_prime.msk` is the canonical working example and exercises most language features (functions, params with types, if/while, assignment ops, function calls, method calls, generic types). `examples/box.msk` and `examples/hash.msk` contain syntax (`class`, `template<...>`, `const`, `Slice<Byte>`, `Ptr<T>`, `ByteView` refinement) that the parser does **not** currently understand — keep these in mind: they are aspirational, not parseable.

## Roadmap (where to plug in)

- `mashiko/desugar.py` — drop AST-rewriting passes here (e.g. expand `for` over tuple destructuring, lower `?` unwrap to match).
- `mashiko/cgen.py` — replace `write_placeholder` in `main.py` with a real `CGenerator().emit(module)` → C string. `main.py` already accepts `--mangle`; honor it by skipping identifier renaming when set.
- No type checker exists yet. `RefinementType.predicate` is parsed but unvalidated.
