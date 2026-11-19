"""Inspect real compiler-only COFF contributions and the generated core interface."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--build", type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.source / "tools"))
from x86.common.paths_x86 import activate_tools, tool_path

activate_tools()
spec = importlib.util.spec_from_file_location("compiler_plan_coff", tool_path("object-adapter"))
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
proof = json.loads((args.build / "generated/quickjs-compiler-plan-native.json").read_text())
assert proof["status"] == "passed-native-compiler-code-data-isolation"
assert {r["kind"] for r in proof["records"]} == {"analysis", "projection"}
for record in proof["records"]:
    path = Path(record["path"])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    co = C.Coff(path.read_bytes())
    for sn, section in enumerate(co.section_records, 1):
        name = co.sections[sn - 1]["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = co.strings[at : co.strings.find(0, at)].decode()
        if not section["size"] or name.startswith(".debug") or section["flags"] & 0x02000000:
            continue
        if section["flags"] & 0x80:
            raise AssertionError(("Unexpected compiler retained BSS", name))
        if section["flags"] & 0x60:
            assert name.startswith((".qjscmp$", ".qjzzec$", ".pdata$", ".rdata$.refptr.")), (
                record["kind"],
                name,
            )
core = (args.build / "generated/backports/quickjs.c").read_text(encoding="utf-8")
assert core.count("extern void JS_CompilerFunctionPlan(JSContext *, void *);") == 1
assert "src/common/bytecode/compiler-plan-shim.inc" not in core
assert "JS_CompilerFunctionPlan(ctx, fd);" in core
print("COMPILER_PLAN_ISOLATION_OK components=2 core=opaque-call-only")
