"""Append the exception directory without growing/moving inherited .pdata.

New unwind entries are linked at the end of .qjsitcp. Copy the final old and
new runtime-function records into one late read-only PE table. Only section
and exception-directory metadata change. Old RX/data/RVAs/fixups stay pinned.
This is a deterministic post-link metadata step, with no code placement knob.
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

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
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

    symbol_table, symbol_count = struct.unpack_from("<II", raw, pe + 12)
    string_table = symbol_table + 18 * symbol_count
    symbols = {}
    i = 0
    while i < symbol_count:
        at = symbol_table + 18 * i
        if raw[at : at + 4] == bytes(4):
            n = string_table + struct.unpack_from("<I", raw, at + 4)[0]
            name = raw[n : raw.index(0, n)].decode("utf-8")
        else:
            name = raw[at : at + 8].split(b"\0")[0].decode("utf-8")
        value = struct.unpack_from("<I", raw, at + 8)[0]
        sn = struct.unpack_from("<h", raw, at + 12)[0]
        if 0 < sn <= count:
            symbols[name] = sections[sn - 1]["rva"] + value
        i += 1 + raw[at + 17]
    names = ("__qjsit_checkpoint_unwind_begin", "__qjsit_checkpoint_unwind_end")
    if not any(n in symbols for n in names):
        result = dict(
            status="not-applicable",
            image=str(image),
            image_sha256=before,
            reason="No iterator checkpoint island in this image.",
        )
        if record:
            record.write_text(json.dumps(result, indent=2) + "\n")
        return result
    assert all(n in symbols for n in names)
    begin, end = (symbols[n] for n in names)
    assert end >= begin and (end - begin) % 12 == 0
    if begin == end:
        result = dict(
            status="not-applicable",
            image=str(image),
            image_sha256=before,
            reason="Empty iterator checkpoint unwind contribution.",
        )
        if record:
            record.write_text(json.dumps(result, indent=2) + "\n")
        return result
    directory = optional + 112 + 3 * 8
    old_rva, old_size = struct.unpack_from("<II", raw, directory)
    if any(s["name"] == ".qjscfi" for s in sections):
        sec = next(s for s in sections if s["name"] == ".qjscfi")
        assert old_rva == sec["rva"] and old_size == sec["size"]
        result = dict(status="already-finalized", image=str(image), image_sha256=before)
        if record:
            record.write_text(json.dumps(result, indent=2) + "\n")
        return result
    json_directory = ("__qjsjson_directory_begin", "__qjsjson_directory_end")
    if (
        all(n in symbols for n in json_directory)
        and old_rva == symbols[json_directory[0]]
        and old_size
    ):
        result = dict(status="already-finalized", image=str(image), image_sha256=before)
        if record:
            record.write_text(json.dumps(result, indent=2) + "\n")
        return result
    regexp_directory = ("__qjsregexp_directory_begin", "__qjsregexp_directory_end")
    regexp_active = "JS_RegExpOwnedReplace" in symbols
    global_directory = ("__qjsgl_directory_begin", "__qjsgl_directory_end")
    active_global_directory = "JS_FrameGlobalBindingGet" in symbols
    if regexp_active:
        global_directory = regexp_directory
        active_global_directory = True
    if (
        active_global_directory
        and all(n in symbols for n in global_directory)
        and old_rva == symbols[global_directory[0]]
    ):
        result = dict(status="already-finalized", image=str(image), image_sha256=before)
        if record:
            record.write_text(json.dumps(result, indent=2) + "\n")
        return result
    assert old_size > 0 and old_size % 12 == 0
    old_at = file_at(old_rva, old_size)
    new_at = file_at(begin, end - begin)
    inherited = bytes(raw[old_at : old_at + old_size])
    addition = bytes(raw[new_at : new_at + end - begin])
    literal = ("__qjsit_literal_unwind_begin", "__qjsit_literal_unwind_end")
    if any(n in symbols for n in literal):
        assert all(n in symbols for n in literal)
        lb, le = (symbols[n] for n in literal)
        assert le >= lb and (le - lb) % 12 == 0
        if le > lb:
            la = file_at(lb, le - lb)
            addition += bytes(raw[la : la + le - lb])
    global_binding = ("__qjsgl_unwind_begin", "__qjsgl_unwind_end")
    if any(n in symbols for n in global_binding):
        assert all(n in symbols for n in global_binding)
        gb, ge = (symbols[n] for n in global_binding)
        assert ge >= gb and (ge - gb) % 12 == 0
        if ge > gb:
            ga = file_at(gb, ge - gb)
            addition += bytes(raw[ga : ga + ge - gb])
    leaf = ("__qjsleaf_unwind_begin", "__qjsleaf_unwind_end")
    if any(n in symbols for n in leaf):
        assert all(n in symbols for n in leaf)
        fb, fe = (symbols[n] for n in leaf)
        assert fe >= fb and (fe - fb) % 12 == 0
        if fe > fb:
            fa = file_at(fb, fe - fb)
            addition += bytes(raw[fa : fa + fe - fb])
    regexp = ("__qjsregexp_unwind_begin", "__qjsregexp_unwind_end")
    if regexp_active:
        assert all(n in symbols for n in regexp)
        rb, re = (symbols[n] for n in regexp)
        assert re > rb and (re - rb) % 12 == 0
        ra = file_at(rb, re - rb)
        addition += bytes(raw[ra : ra + re - rb])
    # Preserve the inherited directory carrier as well as the inherited code.
    # Only the active PE directory moves to the new, larger late carrier.
    if regexp_active:
        inherited_addition = addition[: len(addition) - (re - rb)]
        old_rows = [inherited[i : i + 12] for i in range(0, len(inherited), 12)] + [
            inherited_addition[i : i + 12] for i in range(0, len(inherited_addition), 12)
        ]
        old_rows.sort(key=lambda p: struct.unpack_from("<I", p)[0])
        old_table = b"".join(old_rows)
        ob, oe = (symbols[n] for n in ("__qjsgl_directory_begin", "__qjsgl_directory_end"))
        assert oe - ob == len(old_table)
        oa = file_at(ob, oe - ob)
        assert raw[oa : oa + len(old_table)] == bytes(len(old_table))
        raw[oa : oa + len(old_table)] = old_table
    json_native = ("__qjsjson_unwind_begin", "__qjsjson_unwind_end")
    json_active = False
    if any(n in symbols for n in json_native):
        assert all(n in symbols for n in json_native)
        jb, je = (symbols[n] for n in json_native)
        assert je >= jb and (je - jb) % 12 == 0
        if je > jb:
            # Fill the retained active carrier with its original subset before
            # selecting a JSON-local directory. JSON records are added only to
            # the final new directory; no earlier carrier depends on them.
            if active_global_directory:
                prior = [inherited[i : i + 12] for i in range(0, len(inherited), 12)] + [
                    addition[i : i + 12] for i in range(0, len(addition), 12)
                ]
                prior.sort(key=lambda p: struct.unpack_from("<I", p)[0])
                prior_table = b"".join(prior)
                pb, pe_end = (symbols[n] for n in global_directory)
                assert pe_end - pb == len(prior_table)
                pa = file_at(pb, pe_end - pb)
                assert raw[pa : pa + len(prior_table)] == bytes(len(prior_table))
                raw[pa : pa + len(prior_table)] = prior_table
            ja = file_at(jb, je - jb)
            addition += bytes(raw[ja : ja + je - jb])
            global_directory = ("__qjsjson_directory_begin", "__qjsjson_directory_end")
            active_global_directory = True
            json_active = True
    rows = [inherited[i : i + 12] for i in range(0, len(inherited), 12)] + [
        addition[i : i + 12] for i in range(0, len(addition), 12)
    ]
    rows.sort(key=lambda p: struct.unpack_from("<I", p)[0])
    previous = 0
    for row in rows:
        lo, hi, uw = struct.unpack("<III", row)
        assert previous <= lo < hi and uw > 0
        previous = hi
    table = b"".join(rows)
    section_alignment, file_alignment = struct.unpack_from("<II", raw, optional + 32)
    if active_global_directory:
        assert all(n in symbols for n in global_directory)
        db, de = (symbols[n] for n in global_directory)
        assert de - db >= len(table)
        at = file_at(db, de - db)
        assert raw[at : at + de - db] == bytes(de - db)
        carrier = next(s for s in sections if s["rva"] <= db < de <= s["rva"] + s["size"])
        assert carrier["name"] == (
            ".qjsjfn" if json_active else ".qjszre" if regexp_active else ".qjsglob"
        )
        raw[at : at + len(table)] = table
        struct.pack_into("<II", raw, directory, db, len(table))
        image.write_bytes(raw)
        result = dict(
            status="passed",
            image=str(image),
            before_sha256=before,
            image_sha256=sha(image),
            inherited_table_rva=old_rva,
            inherited_entries=old_size // 12,
            new_entries=len(addition) // 12,
            directory_rva=db,
            directory_bytes=len(table),
            directory_capacity=de - db,
            new_section=None,
            metadata_carrier=carrier["name"],
            raw_offset=at,
            inherited_table_sha256=hashlib.sha256(inherited).hexdigest(),
            new_records_sha256=hashlib.sha256(addition).hexdigest(),
            runner_sha256=sha(__file__),
            policy="Fill derived-capacity new read-only island directory; no old code/data/RVA/fixup or section-header movement.",
        )
        if record:
            record.write_text(json.dumps(result, indent=2) + "\n")
        return result
    header_size = struct.unpack_from("<I", raw, optional + 60)[0]
    header = sections_at + 40 * count
    assert header + 40 <= header_size and raw[header : header + 40] == bytes(40), (
        "No spare PE section header; fail rather than move old bytes."
    )
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
    struct.pack_into("<I", raw, optional + 56, align(table_rva + len(table), section_alignment))
    struct.pack_into("<II", raw, directory, table_rva, len(table))
    # Every pre-existing mapped section is byte-for-byte retained, including
    # original .pdata and each new native/compiler unwind/code contribution.
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
        new_entries=len(addition) // 12,
        directory_rva=table_rva,
        directory_bytes=len(table),
        new_section=".qjscfi",
        raw_offset=physical,
        inherited_table_sha256=hashlib.sha256(inherited).hexdigest(),
        new_records_sha256=hashlib.sha256(addition).hexdigest(),
        all_inherited_mapped_section_bytes_retained=True,
        runner_sha256=sha(__file__),
        policy="Append exact sorted exception directory; retain all old code/data/RVAs/fixups. ASLR flags and image base unchanged.",
    )
    if record:
        record.write_text(json.dumps(result, indent=2) + "\n")
    return result


def finalize(image, record=None):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "writable_callback_unwind", _frame_tool_path("json-callback-unwind")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.writable_finalized(image):
        return module.finalize(image, record)
    inherited = finalize_inherited(image, None)
    result = module.finalize(image, None)
    result["inherited_iterator_finalization"] = inherited
    if record:
        record.write_text(json.dumps(result, indent=2) + chr(10))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, required=True)
    ap.add_argument("--record", type=Path)
    a = ap.parse_args()
    result = finalize(a.image, a.record)
    print("Iterator checkpoint unwind metadata:", result["status"], a.image)
