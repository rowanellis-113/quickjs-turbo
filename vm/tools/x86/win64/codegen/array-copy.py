"""One audited internal CopySubArray call, independent ordinary C worker."""

import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_sys.path.insert(0, str(_FramePath(__file__).resolve().parents[3]))
from x86.common.paths_x86 import (
    activate_tools,
    tool_path,
    source_file,
    source_text,
    generated_file,
    build_file,
)

activate_tools()
import hashlib
import importlib.util
import json
import re
import struct
import subprocess

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location(
        "array_copy_" + name.replace("-", "_"), tool_path(name)
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def generate(source, build, target):
    adapter = module("object-adapter")
    text = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    for name, digest in {
        "js_array_slice": "c515f0bbb694eb4aebf3f297ac1326a4f539ec2f7c95f792f5fbe3ccbd6bc123",
        "JS_CopySubArray": "64b14ef3db3a4d2cedc09fc62f38943c3df0ca3d955517107df2c534d569ba91",
    }.items():
        body = next(m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == name)
        assert hashlib.sha256(body.encode()).hexdigest() == digest, (
            "Review array-copy semantics after upstream change: " + name
        )
    body = source_text(source, "array-copy-grow.inc")
    length_start = text.index("static int set_array_length(")
    length_end = text.index("\n/* return -1 if exception */", length_start)
    assert (
        hashlib.sha256(text[length_start:length_end].encode()).hexdigest()
        == "abc7c79ef2cc727c1f5f4c54974fbe35eac78ddbb0a8485c565d96569f4e4b6c"
    ), "Review sparse length semantics after upstream change"
    body += "\n" + source_text(source, "array-length.inc")
    types = []
    for name in ["StringBuffer", "ValueBuffer"]:
        match = re.search(r"typedef struct " + name + r"\s*\{.*?\}\s*" + name + r";", text, re.S)
        assert match, name
        types.append(match[0])
    expanded = text.replace(
        "static inline bool double_is_int32",
        "\n".join(types) + "\n\nstatic inline bool double_is_int32",
        1,
    )
    expanded = re.sub(r"^static const \w+ \w+(?:\[[^]\n]*\])?;\n", "", expanded, flags=re.M)
    formatted = "static int JS_PRINTF_FORMAT_ATTR(3, 4) JS_ThrowTypeErrorOrFalse("
    assert expanded.count(formatted) == 1
    expanded = expanded.replace(formatted, "static int JS_ThrowTypeErrorOrFalse(", 1)
    core = adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    assert "JS_CopySubArray" in core.symbols and "js_array_slice" in core.symbols, (
        "Unrecognized private compiler clones"
    )
    header, exports, copies = adapter.generate(expanded, core, body)
    private = generated_file(build, "quickjs-array-copy-private.h")
    private.write_text(header, encoding="utf-8", newline="\n")
    contract = """
_Static_assert(sizeof(JSValue)==16 && offsetof(JSStackFrame,cur_func)==8 &&
    offsetof(JSStackFrame,arg_buf)==24 && offsetof(JSStackFrame,arg_count)==58,
    "Reviewed normal/native-synthetic C frame ABI");
_Static_assert(JS_CLASS_C_FUNCTION==12 && JS_CFUNC_generic_magic==1,
    "Reviewed original splice C-function identity");
"""
    target.write_text(
        '#include "quickjs-array-copy-private.h"\n' + contract + "\n" + body,
        encoding="utf-8",
        newline="\n",
    )
    return dict(
        exports=exports, copies=copies, private_sha256=sha(private), builtin_tables_unchanged=True
    )


def compile_extra(source, build, out):
    compiler = module("atod")
    generated = {}

    def generator(src, target):
        generated.update(generate(src, build, target))

    compiler.compile_extra(
        source,
        build,
        out,
        generator=generator,
        filename="quickjs-array-copy.c",
        late_name=".qjsacp$C",
    )
    receipt = json.loads(out.with_suffix(".compile.json").read_text())
    receipt.update(
        generated=generated,
        contract="Ordinary separate C TU/member; original builtin identity and code size held; standard compiler unwind.",
    )
    out.with_suffix(".compile.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return generated


def route_core(source, build):
    C = module("object-adapter")
    path = build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    original_raw = path.read_bytes()
    raw, packing = module("call-metadata").packed(original_raw, C)
    before = C.Coff(raw)
    co = C.Coff(raw)
    caller = before.symbols["js_array_slice"]
    callee = before.symbols["JS_CopySubArray"]
    section = caller["section"]
    rec = co.section_records[section - 1]
    ends = sorted(
        {
            s["value"]
            for s in before.all_symbols.values()
            if s["section"] == section and s["type"] & 32 and s["value"] > caller["value"]
        }
    )
    end = ends[0] if ends else rec["size"]
    assert caller["value"] < end <= rec["size"]
    hits = []
    for at in before.relocation_positions(section):
        off, index, kind = struct.unpack_from("<IIH", co.data, at)
        if not caller["value"] <= off < end or kind != 4:
            continue
        symbol = before.all_symbols[index]
        addend = struct.unpack_from("<i", co.data, rec["raw"] + off)[0]
        if symbol["section"] == callee["section"] and symbol["value"] + addend == callee["value"]:
            assert co.data[rec["raw"] + off - 1] == 0xE8
            hits.append(dict(offset=off, kind=kind, relocation_at=at, old_symbol=index))
    if not hits:
        # GCC resolves local .text calls before COFF linking. Admit only an
        # instruction decoded by this build's configured disassembler.
        assert section == callee["section"] and before.sections[section - 1]["name"] == ".text"
        commands = json.loads(build_file(build, "compile_commands.json").read_text())
        cache = build_file(build, "CMakeCache.txt").read_text()
        match = re.search(r"^QJS_FRAME_OBJDUMP:FILEPATH=(.+)$", cache, re.M)
        if not match:
            match = re.search(r"^CMAKE_OBJDUMP:FILEPATH=(.+)$", cache, re.M)
        assert match, "Configured objdump required for a local call"
        listing = subprocess.check_output(
            [
                match[1],
                "-d",
                "-w",
                "-Mintel",
                "-j",
                ".text",
                "--start-address=" + hex(caller["value"]),
                "--stop-address=" + hex(end),
                str(generated_file(build, "quickjs-core-original.obj")),
            ],
            text=True,
        )
        generated_file(build, "quickjs-array-copy-caller.asm").write_text(listing, encoding="utf-8")
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
            if not m:
                continue
            address = int(m[1], 16)
            code = bytes.fromhex(m[2])
            if (
                len(code) != 5
                or code[0] != 0xE8
                or address + 5 + struct.unpack_from("<i", code, 1)[0] != callee["value"]
            ):
                continue
            assert bytes(co.data[rec["raw"] + address : rec["raw"] + address + 5]) == code
            hits.append(dict(offset=address + 1, kind=4, relocation_at=None, old_symbol=None))
    assert len(hits) == 1, ("Expected precisely one original splice copy call", hits)
    site = hits[0]
    off = site["offset"]
    old_operand = bytes(co.data[rec["raw"] + off : rec["raw"] + off + 4])
    target = co.external("JS_FrameArrayCopySubArray")
    if site["relocation_at"] is not None:
        struct.pack_into("<I", co.data, site["relocation_at"] + 4, target)
    else:
        co.extra_relocations.setdefault(section, []).append(struct.pack("<IIH", off, target, 4))
    co.data[rec["raw"] + off : rec["raw"] + off + 4] = bytes(4)
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    after_rec = after.section_records[section - 1]
    restored[after_rec["raw"] + off : after_rec["raw"] + off + 4] = old_operand
    if site["relocation_at"] is not None:
        at = next(
            at
            for at in after.relocation_positions(section)
            if struct.unpack_from("<I", after.data, at)[0] == off
        )
        struct.pack_into("<I", restored, at + 4, site["old_symbol"])
    else:
        struct.pack_into("<I", restored, after_rec["pos"] + 24, rec["reloc"])
        struct.pack_into("<H", restored, after_rec["pos"] + 32, rec["count"])
    assert C.Coff(restored).sections == before.sections, (
        "Change outside the single allowed call operand/relocation"
    )
    assert all(after.all_symbols[i] == s for i, s in before.all_symbols.items()), (
        "Old symbol changed"
    )
    backup = path.with_name(path.name + ".before-array-copy")
    assert not backup.exists()
    backup.write_bytes(original_raw)
    path.write_bytes(result)
    proof = dict(
        status="passed",
        caller="js_array_slice",
        original_callee="JS_CopySubArray",
        destination="JS_FrameArrayCopySubArray",
        allowed_changes=[
            dict(
                section=section,
                offset=off,
                width=4,
                relocation_kind=4,
                decoded_local=site["relocation_at"] is None,
                old_operand=old_operand.hex(),
            )
        ],
        packing=packing,
        all_original_symbols_held=True,
        all_sections_and_relocations_equal_after_exact_restoration=True,
        before_sha256=sha(backup),
        after_sha256=sha(path),
        builtin_table_pointers_unchanged=True,
        semantics="Same C ABI, original builtin entry and item loop; worker fallbacks call unchanged original CopySubArray.",
    )
    generated_file(build, "quickjs-array-copy-route.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
    route_length_core(source, build)
    return proof


def route_length_core(source, build):
    """Keep the pinned function/prologue; route all real calls to fixed C."""
    C = module("object-adapter")
    path = build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    original = path.read_bytes()
    raw, packing = module("call-metadata").packed(original, C)
    before = C.Coff(raw)
    co = C.Coff(raw)
    assert before.sections == C.Coff(original).sections, "COFF packing changed section semantics"

    def section_name(number):
        name = before.sections[number - 1]["name"]
        if name.startswith("/") and name[1:].isdigit():
            offset = int(name[1:])
            assert 4 <= offset < len(before.strings)
            name = bytes(before.strings[offset:]).split(b"\0", 1)[0].decode("utf-8")
        return name

    callee = before.symbols["set_array_length"]
    section = callee["section"]
    related = []
    length_metadata = []
    for s in before.all_symbols.values():
        if "set_array_length" not in s["name"]:
            continue
        assert s["section"] > 0, ("Unreviewed length reference", s)
        if before.section_records[s["section"] - 1]["flags"] & 0x20000000:
            related.append(s)
        else:
            # MSVC emits named unwind/pdata/chained-unwind records. They are
            # not executable function clones and must remain byte-for-byte.
            assert (
                re.fullmatch(r"\$(?:unwind|pdata|chain)(?:\$\d+)?\$set_array_length", s["name"])
                and section_name(s["section"]).startswith((".pdata", ".xdata"))
                and s["type"] == 0
                and s["storage"] == 3
                and s["value"] == 0
            ), ("Unreviewed length metadata", s)
            length_metadata.append(dict(s, section_name=section_name(s["section"])))
    assert all(
        s["name"] in ("set_array_length", "qjs_frame_core_set_array_length")
        and s["section"] == section
        and s["value"] == callee["value"]
        for s in related
    ), "Unreviewed length clone/private ABI"
    hits = []
    relocation_fields = {}
    metadata_refs = []
    for number, sec in enumerate(co.section_records, 1):
        fields = {}
        for at in before.relocation_positions(number):
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            fields[off] = (at, index, kind)
            symbol = before.all_symbols[index]
            if symbol["section"] != section:
                continue
            addend = struct.unpack_from("<i", co.data, sec["raw"] + off)[0]
            if symbol["value"] + addend != callee["value"]:
                continue
            if not sec["flags"] & 0x20000000:
                name = section_name(number)
                assert name.startswith((".debug", ".pdata", ".xdata", ".eh_frame")), (
                    "Unreviewed allocated length pointer",
                    name,
                    off,
                )
                metadata_refs.append(dict(section=number, name=name, offset=off, kind=kind))
                continue
            assert (
                kind == 4
                and sec["flags"] & 0x20000000
                and co.data[sec["raw"] + off - 1] in (0xE8, 0xE9)
            ), (number, off, kind, symbol)
            hits.append(
                dict(section=number, offset=off, kind=kind, relocation_at=at, old_symbol=index)
            )
        relocation_fields[number] = fields
    # Only a call in the same input section can be assembler-resolved without
    # a relocation. Decode that complete section; never scan arbitrary E8 bytes.
    sec = co.section_records[section - 1]
    name = section_name(section)
    same_names = sum(section_name(n) == name for n in range(1, len(before.sections) + 1))
    funcs = [
        s
        for s in before.all_symbols.values()
        if s["section"] == section and s["type"] & 32 and not s["name"].startswith(".")
    ]
    if same_names == 1:
        cache = build_file(build, "CMakeCache.txt").read_text()
        match = re.search(r"^QJS_FRAME_OBJDUMP:FILEPATH=(.+)$", cache, re.M) or re.search(
            r"^CMAKE_OBJDUMP:FILEPATH=(.+)$", cache, re.M
        )
        assert match
        listing = subprocess.check_output(
            [match[1], "-d", "-w", "-z", "-Mintel", "--insn-width=16", "-j", name, str(path)],
            text=True,
            timeout=90,
        )
        generated_file(build, "quickjs-array-length-core.asm").write_text(listing, encoding="utf-8")
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
            if not m:
                continue
            address = int(m[1], 16)
            blob = bytes.fromhex(m[2])
            off = address + 1
            if len(blob) != 5 or blob[0] not in (0xE8, 0xE9) or off in relocation_fields[section]:
                continue
            if address + 5 + struct.unpack_from("<i", blob, 1)[0] != callee["value"]:
                continue
            assert bytes(co.data[sec["raw"] + address : sec["raw"] + address + 5]) == blob
            hits.append(
                dict(section=section, offset=off, kind=4, relocation_at=None, old_symbol=None)
            )
    else:
        assert {s["value"] for s in funcs} == {callee["value"]}, (
            "Ambiguous duplicate section names with additional local callers"
        )
    assert len(hits) == 2, ("Expected both original set/define length calls", hits)
    target = co.external("JS_FrameSetArrayLength")
    allowed = []
    for site in hits:
        sec = co.section_records[site["section"] - 1]
        off = site["offset"]
        old = bytes(co.data[sec["raw"] + off : sec["raw"] + off + 4])
        if site["relocation_at"] is not None:
            struct.pack_into("<I", co.data, site["relocation_at"] + 4, target)
        else:
            co.extra_relocations.setdefault(site["section"], []).append(
                struct.pack("<IIH", off, target, 4)
            )
        co.data[sec["raw"] + off : sec["raw"] + off + 4] = bytes(4)
        allowed.append(dict(**site, old_operand=old.hex(), width=4))
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    for site in allowed:
        number = site["section"]
        sec = after.section_records[number - 1]
        off = site["offset"]
        restored[sec["raw"] + off : sec["raw"] + off + 4] = bytes.fromhex(site["old_operand"])
        if site["relocation_at"] is not None:
            at = next(
                at
                for at in after.relocation_positions(number)
                if struct.unpack_from("<I", after.data, at)[0] == off
            )
            struct.pack_into("<I", restored, at + 4, site["old_symbol"])
    for number in {s["section"] for s in allowed if s["relocation_at"] is None}:
        old = before.section_records[number - 1]
        new = after.section_records[number - 1]
        first = old["reloc"]
        last = first + 10 * old["count"]
        permitted = {
            position
            for s in allowed
            if s["section"] == number and s["relocation_at"] is not None
            for position in range(s["relocation_at"] + 4, s["relocation_at"] + 8)
        }
        assert all(
            raw[position] == restored[position] or position in permitted
            for position in range(first, last)
        ), "Unexpected old relocation-table mutation"
        restored[first:last] = raw[first:last]
        struct.pack_into("<I", restored, new["pos"] + 24, old["reloc"])
        struct.pack_into("<H", restored, new["pos"] + 32, old["count"])
    assert C.Coff(restored).sections == before.sections, (
        "Change outside the two allowed length-call operands/relocations"
    )
    assert all(after.all_symbols[i] == s for i, s in before.all_symbols.items()), (
        "Old core symbol changed"
    )
    backup = path.with_name(path.name + ".before-array-length")
    assert not backup.exists()
    backup.write_bytes(original)
    path.write_bytes(result)
    proof = dict(
        status="passed-two-pinned-standard-ABI-length-calls-routed",
        callee="set_array_length",
        destination="JS_FrameSetArrayLength",
        allowed_changes=allowed,
        before_sha256=sha(backup),
        after_sha256=sha(path),
        packing=packing,
        old_callee_symbol=callee,
        old_symbols_held=True,
        preserved_metadata_references=metadata_refs,
        preserved_length_metadata_symbols=length_metadata,
        all_sections_and_relocations_equal_after_exact_restoration=True,
        scope="Pinned C signature;all source calls2 and actual typed/decoded call/tail-jump targets2. No entry/prologue/pdata/root-source modification;ordinary C worker owns compiler unwind. No unrecognized clone admitted.",
    )
    generated_file(build, "quickjs-array-length-route.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
    return proof
