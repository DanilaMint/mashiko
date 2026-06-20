import sys

from lark.exceptions import LarkError

from mashiko import cli
from mashiko import parser
from mashiko.optional import Optional
from mashiko.print_ast import print_ast


def main() -> None:
    args = cli.arguments.parse_args()

    log_level = args.log

    source = Optional(read_file(args.file_path))
    if source.is_none():
        print(f"error: cannot read file {args.file_path!r}", file=sys.stderr)
        sys.exit(1)

    try:
        module = parser.parse(source.unwrap())
    except LarkError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    funcs = module.node.functions

    if log_level != "quiet":
        print(f"parsed {len(funcs)} function(s)")

    if args.tree:
        print_ast(module)

    if args.output:
        write_placeholder(args.output)

    if log_level == "detail":
        names = ", ".join(f.node.name for f in funcs) if funcs else "(none)"
        print(f"functions: {names}")
        mangle_state = "off" if args.mangle else "on"
        print(f"mangle={mangle_state} (no codegen yet)")
        if args.output:
            print(f"output: {args.output} (placeholder written)")
        elif args.tree:
            print("output: not set (AST printed to stdout only)")
        else:
            print("output: not set")


def read_file(path: str) -> str | None:
    try:
        with open(path, "rt", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return None


def write_placeholder(path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("mashiko: codegen pending\n")


if __name__ == "__main__":
    main()
