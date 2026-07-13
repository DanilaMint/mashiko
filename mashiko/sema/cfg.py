"""Lightweight control-flow model for the destruct desugaring pass.

We don't need a full basic-block / dominator CFG for the current
features — just enough to answer the question "does this ``if``/``else``
or block exit normally, or does control leave it (return/break/
continue/unreachable)?" The destruct desugaring pass in
:mod:`mashiko.sema.desugaring` uses the :class:`Terminator` of a region
to decide whether synthesized ``.destruct()`` calls need to fire at
the join point.

The model is intentionally coarse:

* :class:`Terminator.FALLTHROUGH` — control reaches the end of the
  region normally and continues with whatever follows.
* :class:`Terminator.RETURNS` / :class:`Terminator.BREAKS` /
  :class:`Terminator.CONTINUES` — the region terminates with the
  named jump.
* :class:`Terminator.UNREACHABLE` — the join of two regions where
  one branch returns/breaks/continues and the other falls through;
  or a region whose end can never be reached.

A :func:`join` is associative, commutative, and idempotent for the
five cases the destruct pass needs to distinguish.
"""

from __future__ import annotations

from enum import Enum

from ..parser.syntax import (
    Block,
    BreakStatement,
    ContinueStatement,
    ExpressionStatement,
    IfStatement,
    ReturnStatement,
    Statement,
    WhileStatement,
)


class Terminator(Enum):
    FALLTHROUGH = "fallthrough"
    RETURNS = "returns"
    BREAKS = "breaks"
    CONTINUES = "continues"
    UNREACHABLE = "unreachable"


def join(a: Terminator, b: Terminator) -> Terminator:
    """Combine the terminators of two sibling regions.

    Rules (read top-to-bottom; first match wins):

    * ``UNREACHABLE`` is the identity: ``(UNREACHABLE, x) == x``.
    * Same-kind collapses: ``(RETURNS, RETURNS) == RETURNS``, etc.
    * ``FALLTHROUGH`` is absorbing on the right: any branch that
      falls through keeps the join reachable.
    * A mismatch (e.g. ``RETURNS`` vs ``BREAKS``) collapses to
      ``UNREACHABLE`` — the join point cannot predict what will
      actually happen, but the surrounding destruct pass must
      still emit destructors for any locals that might reach it.
    """
    if a is Terminator.UNREACHABLE:
        return b
    if b is Terminator.UNREACHABLE:
        return a
    if a is b:
        return a
    if a is Terminator.FALLTHROUGH or b is Terminator.FALLTHROUGH:
        return Terminator.FALLTHROUGH
    return Terminator.UNREACHABLE


def terminator_of(stmt: Statement) -> Terminator:
    """Compute the :class:`Terminator` of an arbitrary statement region.

    Used for:

    * A :class:`Block` — terminator of its last non-empty statement,
      or :class:`Terminator.FALLTHROUGH` if empty.
    * An :class:`IfStatement` — ``join(then, else or FALLTHROUGH)``.
    * A :class:`WhileStatement` — the *body* is treated as
      :class:`Terminator.UNREACHABLE` for the outer scope: a loop body
      may execute any number of times, and the outer block's RAII must
      fire whether the loop runs zero times or many.
    * A :class:`ReturnStatement` / :class:`BreakStatement` /
      :class:`ContinueStatement` — the matching terminator.
    * An :class:`ExpressionStatement` / :class:`AssignStatement` —
      :class:`Terminator.FALLTHROUGH`.
    * Anything else (e.g. nested :class:`Block`) — recurses.
    """
    if isinstance(stmt, ReturnStatement):
        return Terminator.RETURNS
    if isinstance(stmt, BreakStatement):
        return Terminator.BREAKS
    if isinstance(stmt, ContinueStatement):
        return Terminator.CONTINUES
    if isinstance(stmt, WhileStatement):
        return Terminator.UNREACHABLE
    if isinstance(stmt, IfStatement):
        then_term = terminator_of(stmt.then_branch)
        else_term = (
            terminator_of(stmt.else_branch)
            if stmt.else_branch is not None
            else Terminator.FALLTHROUGH
        )
        return join(then_term, else_term)
    if isinstance(stmt, Block):
        if not stmt.statements:
            return Terminator.FALLTHROUGH
        return terminator_of(stmt.statements[-1])
    return Terminator.FALLTHROUGH
