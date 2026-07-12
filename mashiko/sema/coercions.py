"""Implicit numeric widening rules.

A widening is a value-preserving coercion from a narrower to a wider
numeric type. We allow only **same-hierarchy** widenings:

* signed integers: ``Int8 → Int16 → Int32 → Int64``
* unsigned integers: ``Uint8 → Uint16 → Uint32 → Uint64``
* floats: ``Float32 → Float64``

No signed ↔ unsigned, no integer ↔ float, no narrowing. The lattice
is therefore three independent linear chains; the helper
:func:`common_numeric_type` finds the join of two operand types (if
any) along their shared chain.
"""

from .symbols import PrimitiveTypeSymbol

# Each entry lists every type a value of this type can silently widen to.
WIDENING: dict[PrimitiveTypeSymbol, frozenset[PrimitiveTypeSymbol]] = {
    PrimitiveTypeSymbol.Int8: frozenset({
        PrimitiveTypeSymbol.Int16, PrimitiveTypeSymbol.Int32,
        PrimitiveTypeSymbol.Int64,
    }),
    PrimitiveTypeSymbol.Int16: frozenset({
        PrimitiveTypeSymbol.Int32, PrimitiveTypeSymbol.Int64,
    }),
    PrimitiveTypeSymbol.Int32: frozenset({PrimitiveTypeSymbol.Int64}),
    PrimitiveTypeSymbol.Uint8: frozenset({
        PrimitiveTypeSymbol.Uint16, PrimitiveTypeSymbol.Uint32,
        PrimitiveTypeSymbol.Uint64,
    }),
    PrimitiveTypeSymbol.Uint16: frozenset({
        PrimitiveTypeSymbol.Uint32, PrimitiveTypeSymbol.Uint64,
    }),
    PrimitiveTypeSymbol.Uint32: frozenset({PrimitiveTypeSymbol.Uint64}),
    PrimitiveTypeSymbol.Float32: frozenset({PrimitiveTypeSymbol.Float64}),
}


def can_widen(src: PrimitiveTypeSymbol, dst: PrimitiveTypeSymbol) -> bool:
    """True if ``src`` can be silently promoted to ``dst``.

    Identity (``src == dst``) is always allowed. Cross-kind
    (Int ↔ Float, signed ↔ unsigned) and narrowing are rejected.
    """
    if src == dst:
        return True
    return dst in WIDENING.get(src, frozenset())


def common_numeric_type(
    a: PrimitiveTypeSymbol, b: PrimitiveTypeSymbol
) -> PrimitiveTypeSymbol | None:
    """Return the widest of ``a`` and ``b`` if both can unify to it.

    Used by binary operators to coerce both operands to a single
    common type before the operator is applied. Returns ``None`` when
    the two types live on different chains (e.g. ``Int32`` vs
    ``Float64``) or when one is a narrowing of the other.
    """
    if a == b:
        return a
    if can_widen(a, b):
        return b
    if can_widen(b, a):
        return a
    return None


def types_compatible(src: object, dst: object) -> bool:
    """True if a value of type ``src`` may flow into a ``dst`` position.

    Accepts exact equality (always) and primitive widening (same
    hierarchy, value-preserving). Returns ``False`` for non-primitive
    pairs unless they are structurally identical — class / user-defined
    / generic / tuple / maybe types must match exactly.
    """
    if src == dst:
        return True
    if isinstance(src, PrimitiveTypeSymbol) and isinstance(dst, PrimitiveTypeSymbol):
        return can_widen(src, dst)
    return False
