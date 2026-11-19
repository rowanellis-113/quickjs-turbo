"""Append an external COFF alias without changing old section/symbol records."""

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
    routed = path.with_name(path.name + ".null-route.json")
    if routed.exists():
        report = json.loads(routed.read_text())
        restored = bytearray(raw)
        ext = path.with_name(path.name + ".extension.json")
        if ext.exists():
            for section in json.loads(ext.read_text())["sections"]:
                struct.pack_into(
                    "<I", restored, section["header_offset"] + 36, int(section["before"], 16)
                )
        assert report["after_sha256"] == hashlib.sha256(restored).hexdigest()
        before = path.with_name(path.name + ".before-null-route")
        assert report["before_sha256"] == hashlib.sha256(before.read_bytes()).hexdigest()
        alias = json.loads(path.with_name(path.name + ".shared-alias.json").read_text())
        assert alias["after_sha256"] == report["before_sha256"]
        return
    assert struct.unpack_from("<H", raw)[0] == 0x8664
    assert struct.unpack_from("<H", raw, 16)[0] == 0
    table, count = struct.unpack_from("<II", raw, 8)
    strings = table + count * 18
    length = struct.unpack_from("<I", raw, strings)[0]
    assert strings + length == len(raw)
    found = None
    i = 0
    while i < count:
        at = table + i * 18
        name = raw[at : at + 8]
        if name[:4] == b"\0" * 4:
            start = strings + struct.unpack_from("<I", name, 4)[0]
            name = raw[start : raw.index(0, start)]
        else:
            name = name.split(b"\0")[0]
        if name == b"JS_FrameCallEntryLegacy":
            report = json.loads(path.with_name(path.name + ".shared-alias.json").read_text())
            backup = path.with_name(path.name + ".before-shared-alias")
            assert report["before_sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
            # Extension classification may already have adapted section flags.
            restored = bytearray(raw)
            ext = path.with_name(path.name + ".extension.json")
            if ext.exists():
                for section in json.loads(ext.read_text())["sections"]:
                    struct.pack_into(
                        "<I", restored, section["header_offset"] + 36, int(section["before"], 16)
                    )
            assert report["after_sha256"] == hashlib.sha256(restored).hexdigest()
            return
        if name == b"js_frame_call_entry":
            value, section, typ, storage, aux = struct.unpack_from("<IhHBB", raw, at + 8)
            assert section > 0 and storage == 3 and typ == 0x20
            found = (value, section, typ)
        i += 1 + raw[at + 17]
    assert found, "Compiler must preserve the original static entry symbol"
    alias = struct.pack("<II", 0, length) + struct.pack("<IhHBB", *found, 2, 0)
    name = b"JS_FrameCallEntryLegacy\0"
    output = bytearray(raw[:strings] + alias + raw[strings:] + name)
    struct.pack_into("<I", output, 12, count + 1)
    struct.pack_into("<I", output, strings + 18, length + len(name))
    backup = path.with_name(path.name + ".before-shared-alias")
    backup.write_bytes(raw)
    path.write_bytes(output)
    report = {
        "before_sha256": hashlib.sha256(raw).hexdigest(),
        "after_sha256": hashlib.sha256(output).hexdigest(),
        "alias": "JS_FrameCallEntryLegacy",
        "target": "js_frame_call_entry",
        "value": found[0],
        "section": found[1],
        "old_symbol_count": count,
        "contract": "Only SymbolCount and StringTableLength change; append one external alias and name. Old section data, relocations and symbol indices are intact.",
    }
    path.with_name(path.name + ".shared-alias.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Shared entry alias:", path.name, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("object", type=Path)
    adapt(parser.parse_args().object)
