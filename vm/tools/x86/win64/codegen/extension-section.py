"""Keep executable extension storage after the core's standard PE sections.

For .qjsprop/.qjscold/.qjsvm$* only, change COFF CNT_CODE to CNT_INITIALIZED_DATA.
READ and EXECUTE remain set, WRITE remains clear. Both Windows linkers group
this storage after the standard core sections. Code bytes, symbols, relocations
and compiler-generated unwind remain byte-for-byte unchanged.
"""

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
import argparse, hashlib, json, struct
from pathlib import Path


def adapt(path):
    raw = path.read_bytes()
    result = bytearray(raw)
    assert struct.unpack_from("<H", raw)[0] == 0x8664, "Expected standard AMD64 COFF"
    assert struct.unpack_from("<H", raw, 16)[0] == 0
    table, count = struct.unpack_from("<II", raw, 8)
    strings = table + count * 18
    records = []
    allowed = set()
    for i in range(struct.unpack_from("<H", raw, 2)[0]):
        at = 20 + 40 * i
        name = raw[at : at + 8].split(b"\0")[0].decode()
        if name.startswith("/"):
            start = strings + int(name[1:])
            name = raw[start : raw.index(0, start)].decode()
        if name not in (".qjsprop", ".qjscold", ".qjsleaf") and not name.startswith(
            (".qjsvm$", ".qjscold$", ".qjsleaf$", ".qjs$")
        ):
            continue
        before = struct.unpack_from("<I", raw, at + 36)[0]
        if name in (".qjs$zzzzzzjsonU0", ".qjs$zzzzzzjsonU1", ".qjs$zzzzzzjsonU2"):
            assert before & 0xE0000000 == 0x60000000, (name, hex(before))
            continue
        assert before & 0xE0000000 == 0x60000000, (name, hex(before))
        assert before & 0xE0 in (0x20, 0x40), (name, hex(before))
        after = (before & ~0x20) | 0x40
        struct.pack_into("<I", result, at + 36, after)
        allowed.update(range(at + 36, at + 40))
        records.append(
            {"section": name, "header_offset": at, "before": hex(before), "after": hex(after)}
        )
    assert records, f"No extension storage in {path}"
    changed = [i for i, (x, y) in enumerate(zip(raw, result)) if x != y]
    assert set(changed) <= allowed
    backup = path.with_name(path.name + ".before-extension")
    report_path = path.with_name(path.name + ".extension.json")
    if not changed and (backup.exists() or report_path.exists()):
        assert backup.exists() and report_path.exists(), "Adapted input lacks its original evidence"
        report = json.loads(report_path.read_text())
        assert report["after_sha256"] == hashlib.sha256(raw).hexdigest()
        assert report["before_sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
        return
    backup.write_bytes(raw)
    if changed:
        path.write_bytes(result)
    report = {
        "path": str(path),
        "backup": str(backup),
        "before_sha256": hashlib.sha256(raw).hexdigest(),
        "after_sha256": hashlib.sha256(result).hexdigest(),
        "changed_offsets": changed,
        "sections": records,
        "producer_input_already_compliant": not changed,
        "contract": "Only extension storage classification changes; read+execute, no write. No instructions, relocations, symbols or unwind change.",
    }
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print("Frame extension storage:", path.name, records, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("objects", nargs="+", type=Path)
    a = ap.parse_args()
    for p in a.objects:
        adapt(p)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "bigint_release_routes", _frame_tool_path("free-boundary")
    )
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    for p in a.objects:
        if p.name in ("quickjs-interpreter.c.obj", "quickjs-interpreter-null-proto.obj"):
            release.route_big_release(p)
