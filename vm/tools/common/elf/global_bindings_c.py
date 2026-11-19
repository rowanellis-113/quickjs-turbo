"""Pure-C global-binding source invariant proof for common/ARM callers."""

from global_binding_c import inspect_global_invariants


def source_rows(source, layout):
    info = inspect_global_invariants(source)
    return (
        ["/* source-owned global invariant proof */"],
        dict(
            constructor_invariants=info["object_invariants"],
            dispatch_slots=info["dispatch_slots"],
            undefined_atom=info["undefined_atom"],
            undefined_hash=info["undefined_hash"],
        ),
    )
