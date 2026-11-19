"""Readonly embedding-test constants from this target's actual compiler ABI."""

import argparse
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--header", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
lines = [s for s in a.header.read_text().splitlines() if s.startswith("#define ")]
for name in (
    "QJS_ABI_BIT_JSObject_fast_array_BYTE",
    "QJS_ABI_BIT_JSObject_fast_array_MASK",
    "QJS_ABI_OFF_JSObject_u_array_u_values",
    "QJS_ABI_OFF_JSObject_u_array_u1",
):
    if sum(s.split()[1] == name for s in lines) != 1:
        raise ValueError("Missing actual compiler array observer constant: " + name)
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text(
    "/* Readonly test constants from the actual compiler contract. */\n" + "\n".join(lines) + "\n"
)
