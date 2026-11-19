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


def append(
    destination,
    source,
    root,
    tag,
    keep_all=False,
    *,
    code_input=".qjscold$zznullfast",
    code_output=".qjscold",
    pdata_output=".pdata$zzzzqjsnull",
    metadata_inputs=(),
    allocated_metadata_inputs=(),
    writable_metadata_inputs=(),
    base_owner="JS_FrameJSOwnedMissingGuard",
    baseline_sections=(".qjscold", ".pdata$zzzzqjsnull"),
    section_order=None,
    section_outputs=None,
):
    oldraw = destination.read_bytes()
    newraw = source.read_bytes()
    old = M.Coff(oldraw)
    new = M.Coff(newraw)
    assert old.header == new.header == 20 and old.stride == new.stride == 18
    assert any(x["name"] == base_owner and x["section"] > 0 for x in old.all_symbols.values()), (
        "Destination owner missing",
        base_owner,
    )
    # Earlier private contributions may already reference this owned entry.
    # Preserve those undefined symbol indexes and let the ordinary COFF linker
    # resolve them to the appended definition. Never append a second definition.
    forward_roots = [x for x in old.all_symbols.values() if x["name"] == root]
    assert all(
        x["section"] == 0 and x["storage"] == 2 and x["value"] == 0 for x in forward_roots
    ), "Owned entry already defined"
    assert all(
        any(section_name(old, i) == n for i in range(1, old.count + 1)) for n in baseline_sections
    )
    selected = []
    for index, r in enumerate(new.section_records, 1):
        name = section_name(new, index)
        if name in (code_input, ".pdata$zzzzzznullfast"):
            assert r["size"] and r["count"] < 65535 and not r["flags"] & 0x01000000
            selected.append((index, code_output if name == code_input else pdata_output, r))
        elif name in writable_metadata_inputs:
            assert r["flags"] & 0xE0000000 == 0xC0000000 and r["size"] and r["count"] < 65535, (
                "Explicit owned RW metadata only"
            )
            selected.append((index, name, r))
        elif name in allocated_metadata_inputs:
            assert r["flags"] & 0xE0000000 == 0x60000000 and r["size"], (
                "Only owned readonly metadata"
            )
            selected.append((index, name, r))
        elif name in metadata_inputs:
            assert not r["flags"] & 0xE0000000 and r["flags"] & 0x800, (
                "Only linker-removed metadata is admitted"
            )
            assert not r["flags"] & 0x01000000 and r["count"] < 65535
            selected.append((index, name, r))
        else:
            assert name.startswith(".debug") or name in (".drectve", ".chks64") or not r["size"], (
                "Unexpected allocated ASM data",
                name,
            )
    section_outputs = section_outputs or {}
    assert set(section_outputs) <= {n for n, _, _ in selected}
    selected = [(n, section_outputs.get(n, name), rec) for n, name, rec in selected]
    if section_order is not None:
        assert len(section_order) == len(set(section_order)) and set(section_order) == {
            n for n, _, _ in selected
        }
        ranks = {n: i for i, n in enumerate(section_order)}
        selected.sort(key=lambda item: ranks[item[0]])
    assert selected and all(
        x[1]
        in (
            code_output,
            pdata_output,
            *metadata_inputs,
            *allocated_metadata_inputs,
            *writable_metadata_inputs,
        )
        for x in selected
    )
    # A compiler TU can emit unused header data and out-of-line inline copies.
    # Root the public entry and its own runtime-function metadata, then retain
    # every actual relocation dependency and COMDAT association transitively.
    available = {number: (number, name, record) for number, name, record in selected}
    entry = next(x for x in new.all_symbols.values() if x["name"] == root)
    root_code = entry["section"]
    assert root_code in available
    root_pdata = []
    for number, name, record in selected:
        if section_name(new, number) != ".pdata$zzzzzznullfast":
            continue
        assert (
            record["size"] and record["size"] % 12 == 0 and record["count"] == record["size"] // 4
        ), "Complete native runtime-function records only"
        assert keep_all or record["size"] == 12, (
            "Multiple entries require whole-contribution ownership"
        )
        relocations = [
            struct.unpack_from("<IIH", newraw, record["reloc"] + 10 * i)
            for i in range(record["count"])
        ]
        assert sorted(r[0] for r in relocations) == list(range(0, record["size"], 4)) and all(
            r[2] == 3 for r in relocations
        ), "One ADDR32NB per native unwind field"
        fields = {offset: new.all_symbols[symbol] for offset, symbol, kind in relocations}
        if any(
            fields[at]["section"] == fields[at + 4]["section"] == root_code
            for at in range(0, record["size"], 12)
        ):
            root_pdata.append(number)
    assert len(root_pdata) >= 1 if keep_all else len(root_pdata) == 1
    associations = {}
    for index, symbol in new.all_symbols.items():
        if symbol["storage"] != 3 or symbol["type"] != 0 or symbol["section"] not in available:
            continue
        at = new.table + index * 18
        if not newraw[at + 17]:
            continue
        assert newraw[at + 17] == 1
        aux = newraw[at + 18 : at + 36]
        if aux[14] == 5:
            associations.setdefault(struct.unpack_from("<h", aux, 12)[0], set()).add(
                symbol["section"]
            )
    closure = set(available) if keep_all else {root_code, *root_pdata}
    pending = list(closure)
    edges = []
    while pending:
        number = pending.pop()
        record = available[number][2]
        dependencies = set(associations.get(number, ()))
        for i in range(record["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", newraw, record["reloc"] + 10 * i)
            target = new.all_symbols[symbol]
            assert target["section"] >= 0, ("Unsupported absolute/debug dependency", target)
            edges.append(
                dict(
                    from_section=number,
                    offset=offset,
                    target_symbol=target["name"],
                    target_section=target["section"],
                    kind=kind,
                )
            )
            if target["section"] > 0:
                dependencies.add(target["section"])
        for index, symbol in new.all_symbols.items():
            if symbol["section"] != number or symbol["storage"] != 3 or symbol["type"] != 0:
                continue
            at = new.table + index * 18
            if newraw[at + 17]:
                assert newraw[at + 17] == 1
                auxiliary = newraw[at + 18 : at + 36]
                if auxiliary[14] == 5:
                    dependencies.add(struct.unpack_from("<h", auxiliary, 12)[0])
        for dependency in dependencies:
            assert dependency in available, ("Dependency outside allocated new groups", dependency)
            if dependency not in closure:
                closure.add(dependency)
                pending.append(dependency)
    omitted = [
        dict(
            section=section_name(new, n),
            number=n,
            size=r["size"],
            defined_symbols=[x["name"] for x in new.all_symbols.values() if x["section"] == n],
        )
        for n, _, r in selected
        if n not in closure
    ]
    selected = [x for x in selected if x[0] in closure]

    required = set()
    for _, _, r in selected:
        for i in range(r["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", newraw, r["reloc"] + 10 * i)
            assert kind in (3, 4, 5, 11), (
                "Only AMD64 ADDR32NB / REL32 / REL32_1 / SECREL supported",
                kind,
            )
            assert offset + 4 + int(kind == 5) <= r["size"]
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
            if name == ".pdata$zzzzzznullfast":
                name = pdata_output
            if name == code_input:
                name = code_output
            if x["storage"] == 3 and x["type"] == 0 and name == section_name(new, x["section"]):
                name = dict((n, v) for n, v, _ in selected)[x["section"]]
        named(records, name)
        if aux and x["type"] & 32:
            # GNU emits a null function auxiliary for an out-of-line static
            # inline helper. It has no symbol/line indexes to remap. Retain it.
            assert aux == 1 and x["storage"] in (2, 3) and x["section"] in section_map
            assert records[18:36] == bytes(18), "Unsupported function auxiliary indexes"
        elif aux:
            assert aux == 1 and x["storage"] == 3 and x["type"] == 0 and x["section"] in section_map
            selection = records[18 + 14]
            assert selection in (0, 1, 2, 5), ("Unsupported C COMDAT selection", selection, name)
            association = struct.unpack_from("<h", records, 18 + 12)[0]
            if association:
                assert selection == 5 and association in section_map
                struct.pack_into("<h", records, 18 + 12, section_map[association])
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
            name = pdata_output
        pos = header_end + 40 * i
        encoded = name.encode("ascii")
        if len(encoded) > 8:
            at = len(strings)
            strings.extend(encoded + b"\0")
            encoded = ("/" + str(at)).encode("ascii")
        assert len(encoded) <= 8
        result[pos : pos + 8] = encoded.ljust(8, b"\0")
        alignment = 16 if name == code_output else 4
        result.extend(bytes((-len(result)) % alignment))
        raw_at = len(result)
        result.extend(newraw[r["raw"] : r["raw"] + r["size"]])
        reloc_at = len(result)
        for j in range(r["count"]):
            offset, symbol, kind = struct.unpack_from("<IIH", newraw, r["reloc"] + 10 * j)
            result.extend(struct.pack("<IIH", offset, symbol_map[symbol], kind))
        flags = r["flags"]
        if name == pdata_output and pdata_output in (".qjs$zzzzzzjsonU1", ".qjszzzz$r"):
            assert flags & 0xE0000000 == 0x40000000
            flags |= 0x20000000
        struct.pack_into(
            "<IIIIHHI", result, pos + 16, r["size"], raw_at, reloc_at, 0, r["count"], 0, flags
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
    assert sum(x["name"] == root and x["section"] > 0 for x in after.all_symbols.values()) == 1
    assert sum(x["name"] == root for x in after.all_symbols.values()) == 1 + len(forward_roots)
    backup = destination.with_name(destination.name + ".before-" + tag)
    report = destination.with_name(destination.name + "." + tag + "-merge.json")
    assert not backup.exists() and not report.exists()
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
                entry=root,
                tag=tag,
                code_input=code_input,
                code_output=code_output,
                pdata_output=pdata_output,
                metadata_inputs=list(metadata_inputs),
                allocated_metadata_inputs=list(allocated_metadata_inputs),
                writable_metadata_inputs=list(writable_metadata_inputs),
                old_sections=old.count,
                old_symbols=old.symbol_count,
                old_payloads_relocations_symbols_unchanged=True,
                added_sections=added_records,
                added_symbols=next_index - old.symbol_count,
                relocation_closure=sorted(closure),
                closure_edges=edges,
                omitted_unreferenced_sections=omitted,
                limits=[
                    "COFF preservation; linked RVAs, operands, prefixes and unwind must be checked separately."
                ],
            ),
            indent=2,
        )
        + "\n"
    )
    print("Atod C contribution appended:", destination.name, added_records, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--destination", type=Path, required=True)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--keep-all", action="store_true")
    a = ap.parse_args()
    append(a.destination, a.source, a.entry, a.tag, keep_all=a.keep_all)
