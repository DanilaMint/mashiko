# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Mashiko is a compiling, statically-typed programming language. The toolchain is written in C++20 and built with CMake using `clang`/`clang++`. Source files for the language itself use the `.msk` extension and live in `examples/`.

The project is in early scaffolding: a stub `main.cpp` prints "Hello, world", and the parser/AST layer is being built out. The `src/compiler/` directory is currently empty and reserved for future compiler stages.

## Build

```bash
# Configure (from repo root)
cmake -S . -B build

# Build (Debug by default)
cmake --build build
# or: make -C build

# Release build
cmake -S . -B build-release -DCMAKE_BUILD_TYPE=Release
cmake --build build-release

# Run
./build/bin/mashiko
```

Build output layout (set in `CMakeLists.txt`):
- `build/bin/` — executables
- `build/lib/` — libraries

`CMakeLists.txt` uses `file(GLOB_RECURSE SOURCES src/*.cpp src/*.c)`, so new `.cpp`/`.c` files under `src/` are picked up automatically on the next build. Headers are not globbed, so adding a new `.h` requires no CMake change.

There is no test suite yet.

## Source Layout

```
src/
  main.cpp                    # Entry point (currently a stub)
  misc/
    pos.h / pos.cpp           # Position + Span (byte idx, line, column)
    flatten_variant.h         # AI-generated template metaprogramming utility
  parser/
    char_iter.h / .cpp        # UTF-8 char iterator; tracks line/column
    parser.h / .cpp           # Hand-written recursive-descent lexer
    ast/                      # AST node definitions (all headers)
      node.h                  # Node<T> wrapper + BoxedNode/OptionalNode/NodeList aliases
      punctuation.h           # , . ; : ( ) [ ] { } < >
      word.h                  # Ident + keyword tags (if, func, class, ...)
      literal.h               # Int / Float / Bool / Char / String literals
      operator.h              # +, -, ==, =, +=, ?, &, *, ...
      expression.h            # BinOp, UnOp, calls, tuples, arrays, conditionals
      statement.h             # Expr/Var/If statements, Block
      declaration.h           # FuncDeclaration, GenericDeclaration
      typing.h                # TupleType, PointerType, MaybeType, GenericType
  compiler/                   # (empty) reserved for future compiler stages
```

## Architecture & Conventions

### AST representation

Every AST node is a `Node<T>` (`src/parser/ast/node.h`) wrapping a typed payload plus a `Span`. Each "thing" in the language (a punctuation symbol, an operator, a keyword, a literal kind) is a tag type — an empty `struct`. For example:

```cpp
typedef struct Plus {} Plus;
typedef struct IfKeyword {} IfKeyword;
typedef struct Ident { std::string value; } Ident;
```

Tags are composed into `std::variant`s via the `flatten_variant` template metaprogramming helper in `src/misc/flatten_variant.h` (AI-generated, comment header says so). This flattens nested variants like `flatten_variant_t<A, B, C>` into a single `std::variant<A, B, C>`. The `using` aliases in the AST headers (e.g. `Word`, `Expression`, `Statement`, `BinaryOperator`) are all built this way.

Standard aliases:
- `BoxedNode<T>` = `unique_ptr<Node<T>>`
- `OptionalNode<T>` = `optional<Node<T>>`
- `NodeList<T>` = `vector<Node<T>>`

### Sequence / list convention

A comma-separated list is represented as `NodeList<Sequence<T>>` plus an `OptionalNode<T>` for a trailing item without a comma. `Sequence<T>` (`src/parser/ast/punctuation.h`) holds the value and a required `Node<Comma>`. This means a trailing comma in a list is *not* optional in the AST shape, even though most languages treat it as optional at parse time. When adding parsers, mirror this convention.

### Parser style

`Parser` (`src/parser/parser.h`) is a hand-written recursive-descent parser driven by a `CharIterator`. Each punctuator and operator has its own `parseX()` method returning `OptionalNode<X>`. Punctuation parsers share the `PUNCT_PARSER_BODY(T, ch)` macro (`src/parser/parser.cpp:3-8`), which: peeks the current char, returns `nullopt` on mismatch, otherwise records the start position, advances, and returns `Node<T>` with a `Span`. When adding a new punctuator, declare the tag in `punctuation.h` and add one line using the macro.

`parseWord()` (the only non-punctuator parser so far) reads an identifier (`[A-Za-z_][A-Za-z0-9_]*`) and matches it against the keyword list via the `MATCH_KEYWORD(literal, Type)` macro. The order of `MATCH_KEYWORD` calls is the de-facto keyword table — add new keywords there.

`CharIterator` is UTF-8 aware: `current()`/`next()` return `optional<char32_t>`, and `advance()` updates line/column (note: `\n` resets column to 1, all other chars increment it).

### Adding to the AST

The dependency order is: `node.h` → `punctuation.h`/`word.h`/`literal.h`/`operator.h` → `expression.h` → `statement.h` → `declaration.h`/`typing.h`. Higher-level headers include lower-level ones. When adding a new node type, follow the same pattern: tag struct (or payload struct for things carrying data) + a `flatten_variant` alias into the appropriate parent variant.

## Language Surface (from existing AST and examples)

- Imperative keywords: `if`, `else`, `while`, `for`, `break`, `continue`, `return`
- Declarative keywords: `func`, `class`, `abstract`, `public`, `type`
- Literals: integer, float, bool, char, string
- Operators: arithmetic (`+ - * / %`), boolean (`&& || !`), bitwise (`& | ^`), comparison (`== != < > <= >=`), assignment (`= += -= *= /= %=`), ternary `?`
- Types: identifier refs, generic types `<T, U>`, tuple types, `&T` pointer, `T?` maybe
- Generic declarations use chevrons: `func name<T, U>(...)`
- Examples in `examples/`: `hello_world.msk`, `add.msk` (abstract class with associated type `Self.Output`), `refcount.msk`, `find_frac.msk`
