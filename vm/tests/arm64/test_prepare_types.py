"""Expose the exact shared DATA_TYPE to the independent ARM test translation unit."""

import argparse
import ast
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--source", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
tree = ast.parse((a.source / "tools/common/c_extract/call_prepare_c.py").read_text())
definitions = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "DATA_TYPE" for t in n.targets)
]
if len(definitions) != 1:
    raise ValueError("Review the actual shared prepared DATA_TYPE")
body = ast.literal_eval(definitions[0].value)
if not isinstance(body, str) or body.count("typedef struct JSFramePrepareData {") != 1:
    raise ValueError("Review the shared prepared data declaration")
a.output.parent.mkdir(parents=True, exist_ok=True)
a.output.write_text("#include <stdint.h>\n#include <stddef.h>\n" + body)
