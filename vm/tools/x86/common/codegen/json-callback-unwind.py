"""Complete MS JSON callback exception records in a late readonly PE table.
Static-library consumers run the same deterministic post-link metadata step.
No native code, inherited mapped bytes, image base or ASLR flags are moved.
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
from pathlib import Path
import argparse, hashlib, json, struct

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
align = lambda n, a: (n + a - 1) & ~(a - 1)


def finalize_inherited(image, record=None):
    raw = bytearray(image.read_bytes())
    before = sha(image)
    pe = struct.unpack_from("<I", raw, 60)[0]
    assert raw[:2] == b"MZ" and raw[pe : pe + 4] == b"PE\0\0"
    count = struct.unpack_from("<H", raw, pe + 6)[0]
    optional = pe + 24
    assert struct.unpack_from("<H", raw, optional)[0] == 0x20B
    sections_at = optional + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(count):
        at = sections_at + 40 * i
        name = raw[at : at + 8].split(b"\0")[0].decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, at + 8)
        sections.append(
            dict(
                name=name, size=size, rva=rva, physical_size=physical_size, physical=physical, at=at
            )
        )

    def file_at(rva, size):
        sec = next(
            s for s in sections if s["rva"] <= rva and rva + size <= s["rva"] + s["physical_size"]
        )
        return sec["physical"] + rva - sec["rva"]

    directory = optional + 112 + 3 * 8
    old_rva, old_size = struct.unpack_from("<II", raw, directory)
    carrier = next((s for s in sections if s["name"] == ".qjscold"), None)
    data = (
        bytes(raw[carrier["physical"] : carrier["physical"] + carrier["size"]]) if carrier else b""
    )
    magic = b"QJSJCB_UNWIND_v1"
    footer = b"QJSJCB_END_v1!!!"
    positions = [i for i in range(len(data)) if data.startswith(magic, i)]
    carrier = carrier if positions else None
    if carrier is None:
        result = dict(
            status="not-applicable",
            image=str(image),
            image_sha256=before,
            reason="No prepared JSON callback runtime-function carrier",
        )
    elif any(s["name"] == ".qjscfi" for s in sections):
        sec = next(s for s in sections if s["name"] == ".qjscfi")
        assert old_rva == sec["rva"] and old_size == sec["size"]
        result = dict(status="already-finalized", image=str(image), image_sha256=before)
    elif any(
        s["name"] == ".reloc" and s["rva"] <= old_rva and old_rva + old_size <= s["rva"] + s["size"]
        for s in sections
    ):
        result = dict(
            status="already-finalized",
            image=str(image),
            image_sha256=before,
            metadata_carrier=".reloc",
        )
    else:
        assert old_size > 0 and old_size % 12 == 0 and len(positions) == 1
        compiled_max, version = struct.unpack_from("<II", data, positions[0] + 16)
        assert version == 1 and compiled_max > 0
        tails = [i for i in range(len(data)) if data.startswith(footer, i)]
        assert len(tails) == 1
        native_start = positions[0] + 32
        gap = tails[0] - native_start
        assert gap >= 0
        native_count = min(compiled_max, gap // 12)
        while native_count and data[
            native_start + (native_count - 1) * 12 : native_start + native_count * 12
        ] == bytes(12):
            native_count -= 1
        native_size = 12 * native_count
        padding = gap - native_size
        assert 0 <= padding < 16 and data[native_start + native_size : tails[0]] == bytes(
            padding
        ), "Unexpected native record/footer alignment"
        if native_size == 0:
            result = dict(
                status="not-applicable",
                image=str(image),
                image_sha256=before,
                reason="Linker discarded all unused prepared JSON callback code and associated runtime records",
            )
            if record:
                record.write_text(json.dumps(result, indent=2) + chr(10))
            return result
        old_at = file_at(old_rva, old_size)
        inherited = bytes(raw[old_at : old_at + old_size])
        addition = data[native_start : native_start + native_size]
        rows = sorted(
            set(inherited[i : i + 12] for i in range(0, len(inherited), 12))
            | set(addition[i : i + 12] for i in range(0, len(addition), 12)),
            key=lambda p: struct.unpack_from("<I", p)[0],
        )
        previous = 0
        for row in rows:
            lo, hi, uw = struct.unpack("<III", row)
            assert previous <= lo < hi and uw > 0
            previous = hi
            file_at(lo, hi - lo)
            file_at(uw, 4)
        table = b"".join(rows)
        section_alignment, file_alignment = struct.unpack_from("<II", raw, optional + 32)
        header_size = struct.unpack_from("<I", raw, optional + 60)[0]
        header = sections_at + 40 * count
        spare = header + 40 <= header_size and raw[header : header + 40] == bytes(40)
        if spare:
            table_rva = align(max(s["rva"] + s["size"] for s in sections), section_alignment)
            physical = align(len(raw), file_alignment)
            physical_size = align(len(table), file_alignment)
            raw.extend(bytes(physical - len(raw)))
            raw.extend(table)
            raw.extend(bytes(physical_size - len(table)))
            struct.pack_into(
                "<8sIIIIIIHHI",
                raw,
                header,
                b".qjscfi\0",
                len(table),
                table_rva,
                physical_size,
                physical,
                0,
                0,
                0,
                0,
                0x40000040,
            )
            struct.pack_into("<H", raw, pe + 6, count + 1)
            initialized = struct.unpack_from("<I", raw, optional + 8)[0]
            struct.pack_into("<I", raw, optional + 8, initialized + physical_size)
            struct.pack_into(
                "<I", raw, optional + 56, align(table_rva + len(table), section_alignment)
            )
            metadata_carrier = ".qjscfi"
        else:
            # MS executable headers can have no spare section slot. Extend the
            # existing last readonly relocation carrier, outside the retained
            # relocation-directory size. Keep it resident for OS unwind lookup.
            last = max(sections, key=lambda s: s["rva"])
            assert last["name"] == ".reloc" and len(raw) == last["physical"] + last["physical_size"]
            assert struct.unpack_from("<II", raw, pe + 12) == (0, 0) and struct.unpack_from(
                "<II", raw, optional + 112 + 4 * 8
            ) == (0, 0), "Unsupported symbol/security overlay"
            delta = align(max(last["size"], last["physical_size"]), 4)
            physical = last["physical"] + delta
            table_rva = last["rva"] + delta
            new_size = delta + len(table)
            new_physical = align(new_size, file_alignment)
            raw.extend(bytes(physical - len(raw)))
            raw.extend(table)
            raw.extend(bytes(last["physical"] + new_physical - len(raw)))
            flags = struct.unpack_from("<I", raw, last["at"] + 36)[0]
            assert flags & 0xE0000000 == 0x40000000
            struct.pack_into("<I", raw, last["at"] + 36, flags & ~0x02000000)
            struct.pack_into("<I", raw, last["at"] + 8, new_size)
            struct.pack_into("<I", raw, last["at"] + 16, new_physical)
            initialized = struct.unpack_from("<I", raw, optional + 8)[0]
            struct.pack_into(
                "<I", raw, optional + 8, initialized + new_physical - last["physical_size"]
            )
            struct.pack_into(
                "<I", raw, optional + 56, align(last["rva"] + new_size, section_alignment)
            )
            metadata_carrier = ".reloc"
        struct.pack_into("<II", raw, directory, table_rva, len(table))
        original = image.read_bytes()
        for sec in sections:
            at = sec["physical"]
            size = sec["physical_size"]
            assert raw[at : at + size] == original[at : at + size]
        image.write_bytes(raw)
        result = dict(
            status="passed",
            image=str(image),
            before_sha256=before,
            image_sha256=sha(image),
            inherited_table_rva=old_rva,
            inherited_entries=old_size // 12,
            new_native_entries=native_count,
            native_records_rva=carrier["rva"] + native_start,
            directory_entries=len(rows),
            directory_rva=table_rva,
            metadata_carrier=metadata_carrier,
            inherited_table_sha256=hashlib.sha256(inherited).hexdigest(),
            native_records_sha256=hashlib.sha256(addition).hexdigest(),
            all_inherited_mapped_section_bytes_retained=True,
            runner_sha256=sha(Path(__file__)),
            policy="Exact compiler records, deduplicate only identical records, sorted nonoverlapping complete readonly late exception table; old code/data/RVA/fixup/base/ASLR preserved.",
        )
    if record:
        record.write_text(json.dumps(result, indent=2) + "\n")
    return result


def writable_finalized(image):
    raw = image.read_bytes()
    pe = struct.unpack_from("<I", raw, 60)[0]
    op = pe + 24
    count = struct.unpack_from("<H", raw, pe + 6)[0]
    headers = op + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(count):
        at = headers + 40 * i
        name = raw[at : at + 8].split(b"\0")[0].decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, at + 8)
        sections.append((name, size, rva, physical_size, physical))
    directory, span = struct.unpack_from("<II", raw, op + 112 + 3 * 8)
    if not span:
        return False
    table = next(s for s in sections if s[2] <= directory and directory + span <= s[2] + s[3])
    off = table[4] + directory - table[2]
    rows = set(raw[i : i + 12] for i in range(off, off + span, 12))
    for name, size, rva, physical_size, physical in sections:
        if name not in (".qjszzzz", ".qjscwfn"):
            continue
        data = raw[physical : physical + size]
        at = data.find(b"QJSCW_UNWIND_v1!")
        if at >= 0:
            return data[at + 32 : at + 44] in rows
    return False


def finalize_writable(
    image,
    record=None,
    carrier_name=None,
    *,
    magic=b"QJSCW_UNWIND_v1!",
    footer=b"QJSCW_END_v1!!!!",
    directory_in_carrier_is_final=True,
):
    raw = bytearray(image.read_bytes())
    before = sha(image)
    pe = struct.unpack_from("<I", raw, 60)[0]
    assert raw[:2] == b"MZ" and raw[pe : pe + 4] == b"PE\0\0"
    count = struct.unpack_from("<H", raw, pe + 6)[0]
    optional = pe + 24
    assert struct.unpack_from("<H", raw, optional)[0] == 0x20B
    sections_at = optional + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(count):
        at = sections_at + 40 * i
        name = raw[at : at + 8].split(b"\0")[0].decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, at + 8)
        sections.append(
            dict(
                name=name, size=size, rva=rva, physical_size=physical_size, physical=physical, at=at
            )
        )

    def file_at(rva, size):
        sec = next(
            s for s in sections if s["rva"] <= rva and rva + size <= s["rva"] + s["physical_size"]
        )
        return sec["physical"] + rva - sec["rva"]

    directory = optional + 112 + 3 * 8
    old_rva, old_size = struct.unpack_from("<II", raw, directory)
    candidates = [
        s
        for s in sections
        if s["name"] in ((carrier_name,) if carrier_name else (".qjszzzz", ".qjscwfn"))
    ]
    assert len(candidates) <= 1, "Independent carrier split by incompatible section flags"
    carrier = candidates[0] if candidates else None
    data = (
        bytes(raw[carrier["physical"] : carrier["physical"] + carrier["size"]]) if carrier else b""
    )
    positions = [i for i in range(len(data)) if data.startswith(magic, i)]
    carrier = carrier if positions else None
    if carrier is None:
        result = dict(
            status="not-applicable",
            image=str(image),
            image_sha256=before,
            reason="No prepared JSON callback runtime-function carrier",
        )
    elif any(s["name"] == ".qjswfi" for s in sections):
        sec = next(s for s in sections if s["name"] == ".qjswfi")
        assert old_rva == sec["rva"] and old_size == sec["size"]
        result = dict(status="already-finalized", image=str(image), image_sha256=before)
    elif directory_in_carrier_is_final and any(
        s["name"] == carrier["name"]
        and s["rva"] <= old_rva
        and old_rva + old_size <= s["rva"] + s["size"]
        for s in sections
    ):
        result = dict(
            status="already-finalized",
            image=str(image),
            image_sha256=before,
            metadata_carrier=carrier["name"],
        )
    else:
        assert old_size > 0 and old_size % 12 == 0 and len(positions) == 1
        compiled_max, version = struct.unpack_from("<II", data, positions[0] + 16)
        assert version == 1 and compiled_max == 0
        tails = [i for i in range(len(data)) if data.startswith(footer, i)]
        assert len(tails) == 1
        native_start = positions[0] + 32
        gap = tails[0] - native_start
        assert gap >= 0
        native_count = gap // 12
        while native_count and data[
            native_start + (native_count - 1) * 12 : native_start + native_count * 12
        ] == bytes(12):
            native_count -= 1
        native_size = 12 * native_count
        padding = gap - native_size
        assert 0 <= padding < 16 and data[native_start + native_size : tails[0]] == bytes(
            padding
        ), "Unexpected native record/footer alignment"
        if native_size == 0:
            result = dict(
                status="not-applicable",
                image=str(image),
                image_sha256=before,
                reason="Linker discarded all unused prepared JSON callback code and associated runtime records",
            )
            if record:
                record.write_text(json.dumps(result, indent=2) + chr(10))
            return result
        old_at = file_at(old_rva, old_size)
        inherited = bytes(raw[old_at : old_at + old_size])
        addition = data[native_start : native_start + native_size]
        rows = sorted(
            set(inherited[i : i + 12] for i in range(0, len(inherited), 12))
            | set(addition[i : i + 12] for i in range(0, len(addition), 12)),
            key=lambda p: struct.unpack_from("<I", p)[0],
        )
        previous = 0
        for row in rows:
            lo, hi, uw = struct.unpack("<III", row)
            assert previous <= lo < hi and uw > 0
            previous = hi
            file_at(lo, hi - lo)
            file_at(uw, 4)
        table = b"".join(rows)
        section_alignment, file_alignment = struct.unpack_from("<II", raw, optional + 32)
        header_size = struct.unpack_from("<I", raw, optional + 60)[0]
        header = sections_at + 40 * count
        spare = header + 40 <= header_size and raw[header : header + 40] == bytes(40)
        capacity, capacity_version = struct.unpack_from("<II", data, tails[0] + 16)
        assert capacity_version == 1
        if capacity:
            assert capacity >= len(table) and capacity % 12 == 0
            delta = tails[0] + 24
            physical = carrier["physical"] + delta
            table_rva = carrier["rva"] + delta
            assert delta + capacity <= carrier["size"]
            assert raw[physical : physical + capacity] in (
                bytes(capacity),
                table + bytes(capacity - len(table)),
            ), "Previously populated directory must exactly match compiler/inherited records"
            raw[physical : physical + len(table)] = table
            metadata_carrier = carrier["name"]
        elif spare:
            table_rva = align(max(s["rva"] + s["size"] for s in sections), section_alignment)
            physical = align(len(raw), file_alignment)
            physical_size = align(len(table), file_alignment)
            raw.extend(bytes(physical - len(raw)))
            raw.extend(table)
            raw.extend(bytes(physical_size - len(table)))
            struct.pack_into(
                "<8sIIIIIIHHI",
                raw,
                header,
                b".qjswfi\0",
                len(table),
                table_rva,
                physical_size,
                physical,
                0,
                0,
                0,
                0,
                0x40000040,
            )
            struct.pack_into("<H", raw, pe + 6, count + 1)
            initialized = struct.unpack_from("<I", raw, optional + 8)[0]
            struct.pack_into("<I", raw, optional + 8, initialized + physical_size)
            struct.pack_into(
                "<I", raw, optional + 56, align(table_rva + len(table), section_alignment)
            )
            metadata_carrier = ".qjswfi"
        else:
            # MS executable headers can have no spare section slot. Extend the
            # existing last readonly relocation carrier, outside the retained
            # relocation-directory size. Keep it resident for OS unwind lookup.
            last = max(sections, key=lambda s: s["rva"])
            assert last["name"] == ".reloc" and len(raw) == last["physical"] + last["physical_size"]
            assert struct.unpack_from("<II", raw, pe + 12) == (0, 0) and struct.unpack_from(
                "<II", raw, optional + 112 + 4 * 8
            ) == (0, 0), "Unsupported symbol/security overlay"
            delta = align(max(last["size"], last["physical_size"]), 4)
            physical = last["physical"] + delta
            table_rva = last["rva"] + delta
            new_size = delta + len(table)
            new_physical = align(new_size, file_alignment)
            raw.extend(bytes(physical - len(raw)))
            raw.extend(table)
            raw.extend(bytes(last["physical"] + new_physical - len(raw)))
            flags = struct.unpack_from("<I", raw, last["at"] + 36)[0]
            assert flags & 0xE0000000 == 0x40000000
            struct.pack_into("<I", raw, last["at"] + 36, flags & ~0x02000000)
            struct.pack_into("<I", raw, last["at"] + 8, new_size)
            struct.pack_into("<I", raw, last["at"] + 16, new_physical)
            initialized = struct.unpack_from("<I", raw, optional + 8)[0]
            struct.pack_into(
                "<I", raw, optional + 8, initialized + new_physical - last["physical_size"]
            )
            struct.pack_into(
                "<I", raw, optional + 56, align(last["rva"] + new_size, section_alignment)
            )
            metadata_carrier = ".reloc"
        struct.pack_into("<II", raw, directory, table_rva, len(table))
        original = image.read_bytes()
        for sec in sections:
            at = sec["physical"]
            size = sec["physical_size"]
            if sec["name"] == carrier["name"] and capacity:
                assert (
                    raw[at:physical] == original[at:physical]
                    and raw[physical + capacity : at + size]
                    == original[physical + capacity : at + size]
                )
            else:
                assert raw[at : at + size] == original[at : at + size]
        image.write_bytes(raw)
        result = dict(
            status="passed",
            image=str(image),
            before_sha256=before,
            image_sha256=sha(image),
            inherited_table_rva=old_rva,
            inherited_entries=old_size // 12,
            new_native_entries=native_count,
            native_records_rva=carrier["rva"] + native_start,
            directory_entries=len(rows),
            directory_rva=table_rva,
            metadata_carrier=metadata_carrier,
            inherited_table_sha256=hashlib.sha256(inherited).hexdigest(),
            native_records_sha256=hashlib.sha256(addition).hexdigest(),
            all_inherited_mapped_section_bytes_retained=True,
            runner_sha256=sha(Path(__file__)),
            policy="Exact compiler records, deduplicate only identical records, sorted nonoverlapping complete readonly late exception table; old code/data/RVA/fixup/base/ASLR preserved.",
        )
    if record:
        record.write_text(json.dumps(result, indent=2) + "\n")
    return result


def finalize_previous(image, record=None):
    if writable_finalized(image):
        result = dict(status="already-finalized", image=str(image), image_sha256=sha(image))
        source = finalize_writable(image, None, carrier_name=".qjssrf")
        if source["status"] == "not-applicable":
            source = finalize_writable(image, None, carrier_name=".qjscold")
        if source["status"] != "not-applicable":
            result = source
        if record:
            record.write_text(json.dumps(result, indent=2) + chr(10))
        return result
    inherited = finalize_inherited(image, None)
    result = finalize_writable(image, None)
    result["inherited_json_finalization"] = inherited
    source = finalize_writable(image, None, carrier_name=".qjssrf")
    if source["status"] == "not-applicable":
        source = finalize_writable(image, None, carrier_name=".qjscold")
    if source["status"] != "not-applicable":
        source["inherited_json_finalization"] = result
        result = source
    if record:
        record.write_text(json.dumps(result, indent=2) + chr(10))
    return result


def finalize(image, record=None):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "call_metadata_finalizer", _frame_tool_path("call-metadata")
    )
    metadata = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metadata)
    result = metadata.finalize_image(image, finalize_previous, finalize_writable)
    spec = importlib.util.spec_from_file_location("varargs_finalizer", _frame_tool_path("varargs"))
    varargs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(varargs)
    result = varargs.finalize_image(image, result)
    if record:
        record.write_text(json.dumps(result, indent=2) + chr(10))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--record", type=Path)
    a = ap.parse_args()
    result = finalize(a.image, a.record)
    print("JSON callback unwind metadata:", result["status"], a.image)
