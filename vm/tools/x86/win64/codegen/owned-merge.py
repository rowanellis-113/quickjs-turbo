"""Append an owned ASM contribution to the existing last MSVC extension member.

Keep every old section number, symbol index, section payload and relocation.
Add two sections in existing output groups, plus only the symbols they need.
This makes archive extraction independent of a new member's unresolved symbol.
The linked code/data/unwind checks remain separate acceptance requirements.
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
import argparse, hashlib, importlib.util, json, struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
sp = importlib.util.spec_from_file_location("owned_merge_coff", _frame_tool_path("object-adapter"))
M = importlib.util.module_from_spec(sp)
sp.loader.exec_module(M)
sha = lambda b: hashlib.sha256(b).hexdigest()


def section_name(obj, index):
    name = obj.sections[index - 1]["name"]
    if name.startswith("/"):
        at = int(name[1:])
        name = obj.strings[at : obj.strings.index(0, at)].decode("ascii")
    return name


def append(destination, source):
    oldraw = destination.read_bytes()
    newraw = source.read_bytes()
    old = M.Coff(oldraw)
    new = M.Coff(newraw)
    assert old.header == new.header == 20 and old.stride == new.stride == 18
    assert not any(x["name"] == "JS_FrameJSOwnedMissingGuard" for x in old.all_symbols.values()), (
        "Fresh compile required"
    )
    assert any(section_name(old, i) == ".qjscold" for i in range(1, old.count + 1))
    assert any(section_name(old, i) == ".pdata$zzzzqjsnull" for i in range(1, old.count + 1))
    selected = []
    for index, r in enumerate(new.section_records, 1):
        name = section_name(new, index)
        if name in (".qjscold", ".pdata$zzqjscold"):
            assert r["size"] and r["count"] < 65535 and not r["flags"] & 0x01000000
            assert not r["flags"] & 0x1000, "New contribution must not be COMDAT"
            selected.append((index, name, r))
        else:
            assert name.startswith(".debug") or not r["size"], (
                "Unexpected allocated ASM data",
                name,
            )
    assert [x[1] for x in selected] == [".qjscold", ".pdata$zzqjscold"]
    required = set()
    for _, _, r in selected:
        for i in range(r["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", newraw, r["reloc"] + 10 * i)
            assert kind in (3, 4, 11), ("Only AMD64 ADDR32NB / REL32 / SECREL supported", kind)
            assert offset + 4 <= r["size"]
            required.add(symbol)
    selected_numbers = {x[0] for x in selected}
    section_map = {n: old.count + i + 1 for i, (n, _, _) in enumerate(selected)}
    kept = {i for i, x in new.all_symbols.items() if x["section"] in selected_numbers} | required
    assert all(i in new.all_symbols for i in kept), "No auxiliary symbol relocation targets"
    strings = bytearray(old.strings)

    def named(record, name):
        encoded = name.encode("ascii")
        if len(encoded) <= 8:
            record[:8] = encoded.ljust(8, b"\0")
        else:
            at = len(strings)
            strings.extend(encoded + b"\0")
            struct.pack_into("<II", record, 0, 0, at)

    added = []
    symbol_map = {}
    next_index = old.symbol_count
    old_externals = {x["name"]: i for i, x in old.all_symbols.items() if x["storage"] == 2}
    for i, x in new.all_symbols.items():
        if i not in kept:
            continue
        if x["section"] == 0:
            assert x["storage"] == 2 and x["value"] == 0
            if x["name"] in old_externals:
                symbol_map[i] = old_externals[x["name"]]
                continue
        else:
            assert x["section"] in section_map
        at = new.table + i * 18
        aux = newraw[at + 17]
        records = bytearray(newraw[at : at + 18 * (1 + aux)])
        name = x["name"]
        if x["section"] in section_map:
            struct.pack_into("<h", records, 12, section_map[x["section"]])
            if name == ".pdata$zzqjscold":
                name = ".pdata$zzzzqjsnull"
        named(records, name)
        if aux:
            assert aux == 1 and x["storage"] == 3 and x["type"] == 0 and x["section"] in section_map
            assert records[18 + 14] == 0, "Only plain section-definition auxiliary supported"
            # Plain section definitions have no associated COMDAT section.
            assert struct.unpack_from("<h", records, 18 + 12)[0] == 0
        symbol_map[i] = next_index
        next_index += 1 + aux
        added.append(records)
    assert required <= symbol_map.keys()
    header_end = 20 + old.count * 40
    shift = len(selected) * 40
    result = (
        bytearray(oldraw[:header_end])
        + bytearray(shift)
        + bytearray(oldraw[header_end : old.table])
    )
    for r in old.section_records:
        for field in (20, 24, 28):
            value = struct.unpack_from("<I", result, r["pos"] + field)[0]
            if value:
                struct.pack_into("<I", result, r["pos"] + field, value + shift)
    added_records = []
    for i, (number, name, r) in enumerate(selected):
        if name == ".pdata$zzqjscold":
            name = ".pdata$zzzzqjsnull"
        pos = header_end + 40 * i
        encoded = name.encode("ascii")
        if len(encoded) > 8:
            at = len(strings)
            strings.extend(encoded + b"\0")
            encoded = ("/" + str(at)).encode("ascii")
        assert len(encoded) <= 8
        result[pos : pos + 8] = encoded.ljust(8, b"\0")
        alignment = 16 if name == ".qjscold" else 4
        result.extend(bytes((-len(result)) % alignment))
        raw_at = len(result)
        result.extend(newraw[r["raw"] : r["raw"] + r["size"]])
        reloc_at = len(result)
        for j in range(r["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", newraw, r["reloc"] + 10 * j)
            result.extend(struct.pack("<IIH", offset, symbol_map[symbol], kind))
        struct.pack_into(
            "<IIIIHHI", result, pos + 16, r["size"], raw_at, reloc_at, 0, r["count"], 0, r["flags"]
        )
        added_records.append(
            dict(section=name, number=section_map[number], size=r["size"], relocations=r["count"])
        )
    table = len(result)
    oldsymbols = oldraw[old.table : old.string_offset]
    result.extend(oldsymbols)
    for records in added:
        result.extend(records)
    struct.pack_into("<I", strings, 0, len(strings))
    result.extend(strings)
    struct.pack_into("<H", result, 2, old.count + len(selected))
    struct.pack_into("<II", result, 8, table, next_index)
    after = M.Coff(result)
    assert after.sections[: old.count] == old.sections, (
        "Old payload / relocation / line hashes changed"
    )
    assert all(after.all_symbols[i] == x for i, x in old.all_symbols.items())
    assert result[after.table : after.table + len(oldsymbols)] == oldsymbols, (
        "Old symbol bytes changed"
    )
    assert [x["name"] for x in after.all_symbols.values()].count("JS_FrameJSOwnedMissingGuard") == 1
    backup = destination.with_name(destination.name + ".before-owned")
    report = destination.with_name(destination.name + ".owned-merge.json")
    backup.write_bytes(oldraw)
    destination.write_bytes(result)
    report.write_text(
        json.dumps(
            dict(
                status="passed",
                destination=str(destination),
                source=str(source),
                before_sha256=sha(oldraw),
                source_sha256=sha(newraw),
                after_sha256=sha(result),
                runner_sha256=sha(Path(__file__).read_bytes()),
                old_sections=old.count,
                old_symbols=old.symbol_count,
                old_payloads_relocations_symbols_unchanged=True,
                added_sections=added_records,
                added_symbols=next_index - old.symbol_count,
                limits=[
                    "COFF preservation; linked RVAs, operands, prefixes and unwind must be checked separately."
                ],
            ),
            indent=2,
        )
        + "\n"
    )
    print("Owned contribution appended:", destination.name, added_records, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--destination", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    a = ap.parse_args()
    append(a.destination, a.source)
