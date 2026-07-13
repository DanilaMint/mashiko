"""Scope-exit RAII destruct desugaring.

The sema pass already handles explicit ``.destruct()`` calls and the
use-after-destruct mark; this module is the **second** pass that
synthesises implicit ``.destruct()`` calls at the end of every lexical
block that has locals reaching its end.

The pass is bottom-up: we rewrite the deepest blocks first, then walk
outwards. Each :class:`~mashiko.parser.syntax.Block` is rewritten by
appending a synthetic
``ExpressionStatement(MethodCall(Name(x), "destruct", ()))`` for every
local ``x`` declared in the block that hasn't already been explicitly
destructed at scope exit. If the block ends with a terminator
(:class:`ReturnStatement`, :class:`BreakStatement`,
:class:`ContinueStatement`), the destructs are prepended before the
terminator.

``params`` are intentionally **not** emitted as destructs: they don't
appear in the body as :class:`~mashiko.parser.syntax.AssignStatement`
nodes, so they're naturally invisible to the "names bound inside this
block" computation. A user who wants to destruct a param writes
``p.destruct();`` explicitly — the same path the sema pass uses for
locals.

If the terminator of a block is :class:`Terminator.UNREACHABLE`
(e.g. an ``if`` whose both branches return), no synthetic destructs
are added to that join point — the locals' lifetime has already
ended along every reachable path.

The pass operates on the AST only; the original tree is never
mutated. Each modified node is rebuilt with
:func:`dataclasses.replace`. Function/method bodies are rewritten
in place inside the :class:`~mashiko.parser.syntax.Module`.

A *names bound in this block* set is computed by walking the block
looking for :class:`~mashiko.parser.syntax.AssignStatement` nodes
with ``op == "="`` and a :class:`~mashiko.parser.syntax.Name` target.
Nested blocks are *not* descended into: their own destructs are
emitted by the inner pass, and a name declared inside an inner block
that escapes (e.g. via hoisting) is a separate concern we don't model
in v1.

A *names destructed in this block* set is computed by walking the
block looking for
:func:`ExpressionStatement(MethodCall(obj=Name(n), name="destruct", args=()))`
shapes. Again, inner blocks are not descended into — if you wrote a
``.destruct()`` on a local of the outer block from inside an inner
block, the inner block's terminator-and-destructs pass doesn't fire
on the outer block's locals, so the mark is recorded only at the
outer block level when the call site is reached in the outer
traversal. (In v1, both the inner and outer block see the call
because the inner-block walk doesn't filter on `if`-branch
containment; the set is shared. This is acceptable for v1 because
the destruct pass's only consumer of the *destructed* set is "skip
re-emitting a synthetic destruct for a name the user already
destructed" — the worst case is a false positive of "I already
destructed it" leading to no extra emission, which is safe.)
"""

from __future__ import annotations

import dataclasses
from typing import Optional, Tuple

from ..parser.syntax import (
    AssignStatement,
    Block,
    BreakStatement,
    ClassDecl,
    Cloner,
    Constructor,
    ContinueStatement,
    Destructor,
    ExpressionStatement,
    ForStatement,
    FunctionDecl,
    IfStatement,
    Method,
    MethodCall,
    Module,
    Name,
    ReturnStatement,
    Statement,
    WhileStatement,
)
from .cfg import Terminator, terminator_of


def desugar(module: Module) -> Module:
    """Rewrite ``module`` with synthetic ``.destruct()`` calls at scope exit.

    Returns a new :class:`Module` with the same declarations except
    that every function/method/constructor/destructor/cloner body
    has had its blocks rewritten. The input ``module`` is not
    mutated; nested rewrites reuse :func:`dataclasses.replace`.
    """
    new_decls = tuple(_rewrite_decl(d) for d in module.declarations)
    return dataclasses.replace(module, declarations=new_decls)


# ---- Declaration dispatch ---------------------------------------------------


def _rewrite_decl(decl) -> object:
    if isinstance(decl, ClassDecl):
        return _rewrite_class(decl)
    if isinstance(decl, FunctionDecl):
        new_body = _rewrite_block(decl.body)
        if new_body is decl.body:
            return decl
        return dataclasses.replace(decl, body=new_body)
    return decl


def _rewrite_class(c: ClassDecl) -> ClassDecl:
    new_members = tuple(_rewrite_member(m) for m in c.body.members)
    if all(m is orig for m, orig in zip(new_members, c.body.members)):
        return c
    new_body = dataclasses.replace(c.body, members=new_members)
    return dataclasses.replace(c, body=new_body)


def _rewrite_member(member) -> object:
    """Rewrite the body of a class member, or return it unchanged.

    Methods, constructors, destructors, and cloners all have a
    ``body: Block`` (or, for methods, ``body: Block`` as well).
    """
    if isinstance(member, (Method, Constructor, Destructor, Cloner)):
        new_body = _rewrite_block(member.body)
        if new_body is member.body:
            return member
        return dataclasses.replace(member, body=new_body)
    return member


# ---- Block rewriting --------------------------------------------------------


def _rewrite_block(block: Block) -> Block:
    """Bottom-up: rewrite children, then append/prepend destructs to this block.

    A :class:`Block`'s terminator decides *whether* to emit destructs
    and *where* (before the terminator, or appended to the end of
    the statements tuple).
    """
    new_stmts = tuple(_rewrite_stmt(s) for s in block.statements)
    if all(s is orig for s, orig in zip(new_stmts, block.statements)):
        rewritten = block
    else:
        rewritten = dataclasses.replace(block, statements=new_stmts)

    term = terminator_of(rewritten)
    if term is Terminator.UNREACHABLE:
        return rewritten

    bound = _names_bound_in(rewritten)
    if not bound:
        return rewritten

    destructed = _names_destructed_in(rewritten)
    pending = sorted(set(bound) - set(destructed))
    if not pending:
        return rewritten

    # Span for synthesized nodes: the block's span covers the whole
    # scope, which is the most useful location for diagnostics.
    synth_span = block.span
    destruct_calls = tuple(
        ExpressionStatement(
            span=synth_span,
            expression=MethodCall(
                span=synth_span,
                obj=Name(span=synth_span, name=n),
                name="destruct",
                args=(),
            ),
        )
        for n in pending
    )

    if not rewritten.statements:
        return dataclasses.replace(rewritten, statements=destruct_calls)

    last = rewritten.statements[-1]
    if isinstance(last, (ReturnStatement, BreakStatement, ContinueStatement)):
        head = rewritten.statements[:-1]
        new_stmts = head + destruct_calls + (last,)
    else:
        new_stmts = rewritten.statements + destruct_calls

    if new_stmts == rewritten.statements:
        return rewritten
    return dataclasses.replace(rewritten, statements=new_stmts)


# ---- Statement dispatch -----------------------------------------------------


def _rewrite_stmt(stmt: Statement) -> Statement:
    if isinstance(stmt, Block):
        return _rewrite_block(stmt)
    if isinstance(stmt, IfStatement):
        return _rewrite_if(stmt)
    if isinstance(stmt, WhileStatement):
        new_body = _rewrite_stmt(stmt.body)
        if new_body is stmt.body:
            return stmt
        return dataclasses.replace(stmt, body=new_body)
    if isinstance(stmt, ForStatement):
        new_body = _rewrite_stmt(stmt.body)
        if new_body is stmt.body:
            return stmt
        return dataclasses.replace(stmt, body=new_body)
    return stmt


def _rewrite_if(stmt: IfStatement) -> IfStatement:
    new_then = _rewrite_stmt(stmt.then_branch)
    new_else = (
        _rewrite_stmt(stmt.else_branch) if stmt.else_branch is not None else None
    )
    if new_then is stmt.then_branch and new_else is stmt.else_branch:
        return stmt
    return dataclasses.replace(stmt, then_branch=new_then, else_branch=new_else)


# ---- Name collection --------------------------------------------------------


def _names_bound_in(block: Block) -> Tuple[str, ...]:
    """Collect names introduced by ``x = ...;`` statements in ``block``.

    Only top-level statements of the block are considered; nested
    blocks declare their own locals and are responsible for their own
    destructs. Compound assignments (``+=`` etc.) are not
    declarations and are excluded.
    """
    names = []
    for s in block.statements:
        if (
            isinstance(s, AssignStatement)
            and s.op == "="
            and isinstance(s.target, Name)
        ):
            names.append(s.target.name)
    # De-duplicate while preserving order.
    seen = set()
    out = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return tuple(out)


def _names_destructed_in(block: Block) -> Tuple[str, ...]:
    """Collect names that received an explicit ``.destruct()`` in ``block``.

    Only ``ExpressionStatement(MethodCall(obj=Name(n), name="destruct",
    args=()))`` shapes count. :class:`MemberLValue` etc. destruct
    calls (e.g. on fields) are well-known no-ops per the sema pass
    and don't track a local's lifetime.
    """
    names = []
    for s in block.statements:
        if not isinstance(s, ExpressionStatement):
            continue
        mc = s.expression
        if (
            isinstance(mc, MethodCall)
            and mc.name == "destruct"
            and not mc.args
            and isinstance(mc.obj, Name)
        ):
            names.append(mc.obj.name)
    return tuple(names)
