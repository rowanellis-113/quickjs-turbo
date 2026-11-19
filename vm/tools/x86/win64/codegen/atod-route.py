"""Route typed direct js_atod calls; retain every other core COFF byte."""

# Shared source/tool/artifact addressing for the x86 backend package.
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[3])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from x86.common.paths_x86 import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

_frame_activate_tools()
import argparse, hashlib, importlib.util, json, struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("atod_coff", _frame_tool_path("object-adapter"))
M = importlib.util.module_from_spec(sp)
sp.loader.exec_module(M)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
ap = argparse.ArgumentParser()
ap.add_argument("--object", type=Path, required=True)
a = ap.parse_args()
p = a.object
backup = p.with_name(p.name + ".before-atod")
receipt = p.with_name(p.name + ".atod-route.json")
assert not backup.exists() and not receipt.exists()
raw = p.read_bytes()
c = M.Coff(raw)
target = c.external("JS_FrameAtod")
routes = []
for section, r in enumerate(c.section_records, 1):
    if not r["flags"] & 0x20:
        continue
    assert r["count"] < 65535
    for i in range(r["count"]):
        at = r["reloc"] + 10 * i
        offset, index, kind = struct.unpack_from("<IIH", raw, at)
        sym = c.all_symbols[index]
        if sym["name"] != "js_atod":
            continue
        assert kind == 4 and sym["section"] == 0 and sym["storage"] == 2
        assert (
            1 <= offset and offset + 4 <= r["size"] and raw[r["raw"] + offset - 1] in (0xE8, 0xE9)
        )
        struct.pack_into("<I", c.data, at + 4, target)
        routes.append(
            dict(
                section=section,
                offset=offset,
                kind=kind,
                old_symbol=index,
                new_symbol=target,
                old_target="js_atod",
                new_target="JS_FrameAtod",
                opcode=raw[r["raw"] + offset - 1],
            )
        )
assert routes
result = bytearray(c.finish())
# The first adapter can append decoded MinGW relocations after the symbol and
# string tables. Appending another alias shifts that tail, so repair only file
# pointers into it. Section payloads, symbol indices and relocation offsets
# inside the sections retain exactly their old values.
old_tail = c.string_offset + struct.unpack_from("<I", raw, c.string_offset)[0]
tail_shift = len(result) - len(raw)
tail_pointer_repairs = []
for r in c.section_records:
    for field in (20, 24, 28):
        value = struct.unpack_from("<I", raw, r["pos"] + field)[0]
        if value and value >= old_tail:
            struct.pack_into("<I", result, r["pos"] + field, value + tail_shift)
            tail_pointer_repairs.append(
                dict(header_offset=r["pos"] + field, before=value, after=value + tail_shift)
            )
d = M.Coff(result)
restored = bytearray(result)
for x in routes:
    r = d.section_records[x["section"] - 1]
    hit = [
        r["reloc"] + 10 * i
        for i in range(r["count"])
        if struct.unpack_from("<I", restored, r["reloc"] + 10 * i)[0] == x["offset"]
    ]
    assert len(hit) == 1
    assert struct.unpack_from("<I", restored, hit[0] + 4)[0] == target
    struct.pack_into("<I", restored, hit[0] + 4, x["old_symbol"])
assert M.Coff(restored).sections == M.Coff(raw).sections
assert all(d.all_symbols[i] == x for i, x in M.Coff(raw).all_symbols.items())
backup.write_bytes(raw)
p.write_bytes(result)
receipt.write_text(
    json.dumps(
        dict(
            status="passed",
            object=str(p),
            before_sha256=sha(backup),
            after_sha256=sha(p),
            runner_sha256=sha(Path(__file__)),
            routes=routes,
            tail_pointer_repairs=tail_pointer_repairs,
            tail_shift=tail_shift,
            original_symbols_unchanged=True,
            core_identical_except_audited_relocation_targets=True,
            limits=[
                "Only typed REL32 CALL/JMP operands are routed; linked layout and decoded destinations require separate checks.",
                "The original js_atod symbol and function remain available for fallback.",
            ],
        ),
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print("ATOD CORE ROUTES", len(routes), flush=True)
