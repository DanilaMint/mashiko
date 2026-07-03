"""Render a mashiko AST as an ASCII tree (à la ``tree(1)``), optionally colored.

Public API
----------
- :func:`print_ast` — write the rendered tree to ``file`` (default stdout).

Standalone use
--------------
``python -m mashiko.print_ast FILE.msk [--color|--no-color]``

The walker recurses through the frozen-dataclass nodes defined in
``mashiko.syntax``. Each node is drawn with its class name (and a short
summary such as the identifier for ``FunctionDecl`` or the operator for
``BinaryOp``) and then one branch per non-``span`` dataclass field.

Field rendering rules
~~~~~~~~~~~~~~~~~~~~~
- ``Node`` value              → branch ``field: NodeKind`` with the node's
                                own children nested underneath.
- ``tuple``/``list`` of Nodes → branch ``field: (N items)`` with each item
                                as a nested node.
- ``tuple``/``list`` of primitives → leaf ``field = (a, b, c)`` (inline).
- ``None``                    → leaf ``field: None``.
- primitive (``int``, ``float``, ``bool``, ``str``) → leaf ``field = repr(v)``.

Color
~~~~~
ANSI colors are applied by default when ``file.isatty()`` is true. Pass
``color=True`` to force them on, or ``color=False`` to force them off
(useful for piping into ``less -R`` or a file).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields as dc_fields
from typing import IO, Any, Iterable, Optional

from .errors import ParseError
from .parser import parse_ast_file
from .parser.syntax import Module, Node

# ---- ANSI palette ------------------------------------------------------------


class _Style:
    RESET = "\x1b[0m"
    BOLD = "\x1b[1m"
    DIM = "\x1b[2m"

    CYAN = "\x1b[36m"
    YELLOW = "\x1b[33m"
    GREEN = "\x1b[32m"
    BLUE = "\x1b[34m"
    MAGENTA = "\x1b[35m"
    GREY = "\x1b[90m"


def _paint(code: str, text: str, enabled: bool) -> str:
    if not enabled or not text:
        return text
    return f"{code}{text}{_Style.RESET}"


# Tree-drawing characters. ASCII-only on purpose — they survive any
# locale and survive piping through most terminals.
_BRANCH = "├── "
_LAST = "└── "
_VERT = "│   "
_BLANK = "    "


# ---- Field iteration ---------------------------------------------------------


def _iter_fields(node: Any) -> Iterable[tuple[str, Any]]:
    for f in dc_fields(node):
        if f.name == "span":
            continue
        yield f.name, getattr(node, f.name)


def _is_node(value: Any) -> bool:
    return isinstance(value, Node)


def _all_nodes(values: Iterable[Any]) -> bool:
    items = list(values)
    return bool(items) and all(_is_node(v) for v in items)


# ---- Header / value formatting ----------------------------------------------


def _short_summary(node: Any) -> tuple[str, frozenset[str]]:
    """A short trailing annotation for the node header line.

    Returns ``(text, fields_already_shown)`` so the walker can skip
    fields that the summary already rendered. Without this,
    ``AssignStatement op='='`` would draw ``op='='`` in the header and
    then again as ``op = '='`` underneath.

    The rule is: pick the single most identifying bit of the node —
    ``FunctionDecl`` shows its name, ``BinaryOp`` shows its operator,
    literal nodes show their value — and report which dataclass field
    supplied it.
    """
    cls = type(node).__name__
    name_attr = getattr(node, "name", None)
    if isinstance(name_attr, str):
        return f"{cls} {name_attr}", frozenset({"name"})
    op_attr = getattr(node, "op", None)
    if isinstance(op_attr, str):
        return f"{cls} op={op_attr!r}", frozenset({"op"})
    if cls.endswith("Literal"):
        v = getattr(node, "value", None)
        if isinstance(v, (int, float, bool, str)):
            return f"{cls} {v!r}", frozenset({"value"})
    return cls, frozenset()


def _paint_value(value: Any, color: bool) -> str:
    if value is None:
        return _paint(_Style.DIM + _Style.GREY, "None", color)
    if isinstance(value, bool):
        return _paint(_Style.MAGENTA, repr(value), color)
    if isinstance(value, (int, float)):
        return _paint(_Style.BLUE, repr(value), color)
    if isinstance(value, str):
        return _paint(_Style.GREEN, repr(value), color)
    return str(value)


def _paint_node_header(node: Any, color: bool) -> str:
    """Bold cyan for the class name; plain for the trailing summary."""
    cls = type(node).__name__
    summary, _skip = _short_summary(node)
    head = _paint(_Style.BOLD + _Style.CYAN, cls, color)
    if summary == cls:
        return head
    tail = summary[len(cls) :]
    return f"{head}{tail}"


def _paint_field_label(field_name: str, color: bool) -> str:
    return _paint(_Style.YELLOW, field_name, color)


def _paint_collection_label(count: int, color: bool) -> str:
    label = f"({count} item{'s' if count != 1 else ''})"
    return _paint(_Style.DIM + _Style.GREY, label, color)


# ---- Tree walker -------------------------------------------------------------


def _walk(
    node: Node,
    prefix: str,
    is_last: bool,
    out: list[str],
    color: bool,
) -> None:
    connector = _LAST if is_last else _BRANCH
    _summary, skip = _short_summary(node)
    out.append(prefix + connector + _paint_node_header(node, color))

    if isinstance(node, Module):
        decls = node.declarations
        child_prefix = prefix + (_BLANK if is_last else _VERT)
        for i, decl in enumerate(decls):
            _walk(decl, child_prefix, i == len(decls) - 1, out, color)
        return

    children = [(n, v) for n, v in _iter_fields(node) if n not in skip]
    child_prefix = prefix + (_BLANK if is_last else _VERT)
    for i, (fname, fvalue) in enumerate(children):
        _walk_field(
            fname,
            fvalue,
            child_prefix,
            i == len(children) - 1,
            out,
            color,
        )


def _walk_field(
    name: str,
    value: Any,
    prefix: str,
    is_last: bool,
    out: list[str],
    color: bool,
) -> None:
    connector = _LAST if is_last else _BRANCH
    label = _paint_field_label(name, color)

    if value is None:
        out.append(f"{prefix}{connector}{label}: {_paint_value(None, color)}")
        return

    if _is_node(value):
        header = f"{label}: {_paint_node_header(value, color)}"
        out.append(f"{prefix}{connector}{header}")
        _gsummary, gskip = _short_summary(value)
        grand_children = [(n, v) for n, v in _iter_fields(value) if n not in gskip]
        grand_prefix = prefix + (_BLANK if is_last else _VERT)
        for i, (gfname, gfvalue) in enumerate(grand_children):
            _walk_field(
                gfname,
                gfvalue,
                grand_prefix,
                i == len(grand_children) - 1,
                out,
                color,
            )
        return

    if isinstance(value, (tuple, list)):
        if _all_nodes(value):
            items = list(value)
            header = f"{label}: {_paint_collection_label(len(items), color)}"
            out.append(f"{prefix}{connector}{header}")
            item_prefix = prefix + (_BLANK if is_last else _VERT)
            for i, item in enumerate(items):
                _walk(item, item_prefix, i == len(items) - 1, out, color)
            return
        # tuple of primitives — keep it on one line
        joined = "(" + ", ".join(_paint_value(v, color) for v in value) + ")"
        out.append(f"{prefix}{connector}{label} = {joined}")
        return

    # primitive
    out.append(f"{prefix}{connector}{label} = {_paint_value(value, color)}")


# ---- Public API --------------------------------------------------------------


def _resolve_color(color: Optional[bool], file: IO[str]) -> bool:
    if color is None:
        return bool(getattr(file, "isatty", lambda: False)())
    return color


def _render_lines(node: Node, enabled: bool) -> list[str]:
    lines: list[str] = []
    lines.append(_paint_node_header(node, enabled))
    if isinstance(node, Module):
        decls = node.declarations
        for i, decl in enumerate(decls):
            _walk(decl, "", i == len(decls) - 1, lines, enabled)
        return lines
    _summary, skip = _short_summary(node)
    children = [(n, v) for n, v in _iter_fields(node) if n not in skip]
    for i, (fname, fvalue) in enumerate(children):
        _walk_field(fname, fvalue, "", i == len(children) - 1, lines, enabled)
    return lines


def render(node: Node, *, color: Optional[bool] = None) -> str:
    """Return the rendered tree as a single newline-joined string.

    ``color`` defaults to ``True`` when stdout is a TTY and ``False`` otherwise;
    pass ``True``/``False`` explicitly to override.
    """
    enabled = _resolve_color(color, sys.stdout)
    return "\n".join(_render_lines(node, enabled))


def print_ast(
    node: Node,
    *,
    color: Optional[bool] = None,
    file: Optional[IO[str]] = None,
) -> None:
    """Print a mashiko AST as an ASCII tree.

    ``color`` follows :func:`render`'s auto-detection rules but is
    resolved against ``file`` (default ``sys.stdout``).
    """
    out = file or sys.stdout
    enabled = _resolve_color(color, out)
    out.write("\n".join(_render_lines(node, enabled)))
    out.write("\n")


# ---- CLI ---------------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m mashiko.print_ast",
        description="Parse a mashiko source file and print its AST as a tree.",
    )
    p.add_argument("file", help="path to a .msk source file")
    color_group = p.add_mutually_exclusive_group()
    color_group.add_argument(
        "--color",
        dest="color",
        action="store_true",
        default=None,
        help="force colored output (default when stdout is a TTY)",
    )
    color_group.add_argument(
        "--no-color",
        dest="color",
        action="store_false",
        help="disable colored output",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    try:
        module = parse_ast_file(args.file)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except ParseError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 1
    print_ast(module, color=args.color)
    return 0


if __name__ == "__main__":
    sys.exit(main())
