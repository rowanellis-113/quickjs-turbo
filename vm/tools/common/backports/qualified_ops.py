"""Verify the already-qualified R9 C opcode backports on pinned NG bodies.
All six R9 C opcode backports are upstream in 0.17.0 (7b5f588e0f); keep
their pinned SHA256s in PATCHES as fail-closed checks with empty edit lists.
"""

import hashlib

PATCHES = {
    "get_array_el": (
        "5f8e2918708f5a3316e44c442d905853c334b19e472fd73d3b154d909df2e308",
        [],
    ),
    "get_array_el2": (
        "910d0e6752f57bf5989b759174157feedfcfdab8c33c1f6ae73a59596b2b50d4",
        [],
    ),
    "add": (
        "96b652ca9b7d3b82be02635f0f42d905c0cfadf7bd411832bdf6e6a4e1ba0fdc",
        [],
    ),
    "sub": (
        "7ff3c6ae06f20d6623c9fdf04ccc278ef9913f46b1d77ebcea182d3e8a6d5a76",
        [],
    ),
    "mul": (
        "9b160da5f4e038e5128c65222c60fa2bb2b2bd0b5a59d7ef5323c70489a9e1b0",
        [],
    ),
    "div": (
        "89f0906489dd07af438a265012c7c57dbef241a9dad61068a4eab18c204ffe34",
        [],
    ),
}


def apply(text):
    for name, (digest, edits) in PATCHES.items():
        start = text.index("        CASE(OP_" + name + "):")
        end = text.index("        CASE(", start + 1)
        block = text[start:end]
        if hashlib.sha256(block.encode()).hexdigest() != digest:
            raise ValueError("Review qualified R9 opcode backport after upstream change: " + name)
        lines = block.splitlines(True)
        for first, last, before, after in reversed(edits):
            assert "".join(lines[first:last]) == before
            lines[first:last] = [after]
        text = text[:start] + "".join(lines) + text[end:]
    return text
