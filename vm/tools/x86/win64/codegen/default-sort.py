"""Route the pinned default-sort C call without changing its function layout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from x86.common.paths_x86 import (
    activate_tools,
    tool_path,
    source_text,
    generated_file,
    build_file,
    normalized_source_digest,
    source_file,
)

activate_tools()
import hashlib
import importlib.util
import json
import re
import struct
import subprocess

CONTRACT = json.loads(
    source_text(Path(__file__).resolve().parents[4], "default-string-sort-abi.json")
)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def module(name):
    spec = importlib.util.spec_from_file_location(
        "default_sort_" + name.replace("-", "_"), tool_path(name)
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def fingerprint(co, name, expected):
    return module("function-fingerprint").fingerprint(
        co, name, expected["local_transfers"], expected["local_addresses"], tuple(range(4, 10))
    )


def reviewed_profile(core):
    profiles = [
        (tc, item)
        for tc, item in CONTRACT["functions"].items()
        if item["callee"] in core.symbols
        and "js_array_sort" in core.symbols
        and fingerprint(core, "js_array_sort", item["caller"]) == item["caller"]
        and fingerprint(core, item["callee"], item["sorter"]) == item["sorter"]
    ]
    return profiles[0] if len(profiles) == 1 else None


def generate(source, build, target):
    assert CONTRACT is not None
    adapter = module("object-adapter")
    text = source_file(source, "quickjs.c").read_text(encoding="utf-8")
    assert normalized_source_digest(source, "quickjs.c") == CONTRACT["source_sha256"]
    assert normalized_source_digest(source, "cutils.h") == CONTRACT["cutils_sha256"]
    for name, digest in CONTRACT["bodies"].items():
        body = next(m[0] for m in adapter.FUNCTION.finditer(text) if m[2] == name)
        assert hashlib.sha256(body.encode()).hexdigest() == digest, name
    core = adapter.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    reviewed = reviewed_profile(core)
    if reviewed is None:
        target.write_text(
            "/* Optional fast sorter unavailable; pinned input retained. */\n"
            "typedef int qjs_default_sort_disabled_translation_unit;\n",
            encoding="utf-8",
            newline="\n",
        )
        return dict(
            enabled=False,
            exports=[],
            copies=[],
            private_sha256=None,
            reason="unreviewed private compiler ABI",
        )
    types = []
    for pattern in (
        r"typedef struct ValueSlot\s*\{.*?\}\s*ValueSlot;",
        r"struct array_sort_context\s*\{.*?\};",
    ):
        match = re.search(pattern, text, re.S)
        assert match
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
    body = source_text(source, "default-string-sort.inc")
    header, exports, copies = adapter.generate(expanded, core, body)
    private = generated_file(build, "quickjs-default-sort-private.h")
    private.write_text(header, encoding="utf-8", newline="\n")
    contract = """
_Static_assert(sizeof(ValueSlot) == 32 && offsetof(ValueSlot, val) == 0 &&
    offsetof(ValueSlot, str) == 16 && offsetof(ValueSlot, pos) == 24,
    "Pinned owned sort slots");
_Static_assert(sizeof(struct array_sort_context) == 32 &&
    offsetof(struct array_sort_context, ctx) == 0 &&
    offsetof(struct array_sort_context, exception) == 8 &&
    offsetof(struct array_sort_context, has_method) == 12 &&
    offsetof(struct array_sort_context, method) == 16,
    "Pinned sort context");
"""
    target.write_text(
        '#include "quickjs-default-sort-private.h"\n' + contract + body,
        encoding="utf-8",
        newline="\n",
    )
    return dict(
        enabled=True,
        toolchain=reviewed[0],
        exports=exports,
        copies=copies,
        private_sha256=sha(private),
    )


def place_control(out, toolchain):
    """Append the sole new mode byte without growing ordinary core BSS."""
    C = module("object-adapter")
    raw = out.read_bytes()
    co = C.Coff(raw)
    modes = [
        (i, s)
        for i, s in co.all_symbols.items()
        if s["name"] == "js_default_string_sort_mode" and s["section"] > 0
    ]
    assert len(modes) == 1
    _, mode = modes[0]
    sn = mode["section"]
    rec = co.section_records[sn - 1]
    old_name = co.sections[sn - 1]["name"]
    assert old_name == ".bss" and mode["value"] == 0 and mode["storage"] == 3
    assert rec["flags"] & 0x80 and not rec["flags"] & 0x20000000
    assert rec["count"] == 0 and 0 < rec["size"] <= 16
    assert not rec["raw"] or not any(co.data[rec["raw"] : rec["raw"] + rec["size"]])
    assert all(
        s["name"] in (old_name, mode["name"]) for s in co.all_symbols.values() if s["section"] == sn
    )
    # Both toolchains already own this writable-control input family. MSVC
    # also has an inherited uninitialized .qjsem output, so retain BSS flags.
    new_name = ".qjsem$zzzzzzdefaultsort"
    offset = len(co.strings)
    co.strings += new_name.encode() + b"\0"
    encoded = ("/" + str(offset)).encode()
    assert len(encoded) <= 8
    old_header = bytes(co.data[rec["pos"] : rec["pos"] + 8])
    co.data[rec["pos"] : rec["pos"] + 8] = encoded.ljust(8, b"\0")
    symbols = []
    for index, sym in co.all_symbols.items():
        if (
            sym["section"] == sn
            and sym["name"] == old_name
            and sym["storage"] == 3
            and sym["type"] == 0
        ):
            at = co.table + index * co.stride
            symbols.append((at, bytes(co.data[at : at + 8])))
            struct.pack_into("<II", co.data, at, 0, offset)
    result = co.finish()
    restored = bytearray(result)
    restored[rec["pos"] : rec["pos"] + 8] = old_header
    for at, name in symbols:
        restored[at : at + 8] = name
    assert C.Coff(restored).sections == C.Coff(raw).sections
    backup = out.with_suffix(".before-control.obj")
    assert not backup.exists()
    backup.write_bytes(raw)
    out.write_bytes(result)
    return dict(
        status="passed-name-only-control-placement",
        from_section=old_name,
        to_section=new_name,
        size=rec["size"],
        before_sha256=sha(backup),
        after_sha256=sha(out),
        exact_restoration=True,
        flags_data_relocations_and_symbol_values_held=True,
    )


def compile_extra(source, build, out):
    generated = {}

    def generator(src, target):
        generated.update(generate(src, build, target))

    # Reuse existing ordinary C output families and standard compiler unwind.
    core = module("object-adapter").Coff(
        generated_file(build, "quickjs-core-original.obj").read_bytes()
    )
    reviewed = reviewed_profile(core)
    # GNU's final existing C group keeps all earlier core/VM code and data in
    # place. MSVC retains its existing array C group. This creates no output group.
    late = ".qjsex$zzzzzzdefaultsort" if reviewed and reviewed[0] == "mingw" else ".qjsacp$D"
    module("atod").compile_extra(
        source, build, out, generator=generator, filename="quickjs-default-sort.c", late_name=late
    )
    placement = place_control(out, generated["toolchain"]) if generated["enabled"] else None
    receipt = json.loads(out.with_suffix(".compile.json").read_text())
    receipt.update(
        object_sha256=sha(out),
        generated=generated,
        control_placement=placement,
        contract="Ordinary C archive member, standard compiler unwind; unchanged original collection and commit.",
    )
    out.with_suffix(".compile.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    return generated


def route_core(source, build):
    C = module("object-adapter")
    path = build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")
    original = path.read_bytes()
    raw, packing = module("call-metadata").packed(original, C)
    before, co = C.Coff(raw), C.Coff(raw)
    cache = build_file(build, "CMakeCache.txt").read_text()
    original_core = C.Coff(generated_file(build, "quickjs-core-original.obj").read_bytes())
    reviewed = reviewed_profile(original_core)
    if reviewed is None:
        proof = dict(
            status="disabled-unreviewed-private-ABI-input-retained",
            before_sha256=sha(path),
            after_sha256=sha(path),
            original_sorter_retained=True,
        )
        generated_file(build, "quickjs-default-sort-route.json").write_text(
            json.dumps(proof, indent=2) + "\n", encoding="utf-8"
        )
        return proof
    tc, expected = reviewed
    assert fingerprint(before, "js_array_sort", expected["caller"]) == expected["caller"], (
        "Unreviewed current caller ABI/code"
    )
    assert all(
        before.symbols[expected["callee"]][key] == original_core.symbols[expected["callee"]][key]
        for key in ("section", "value", "storage")
    ), "Original sorter entry changed"
    adapted_sorter = fingerprint(before, expected["callee"], expected["sorter"])
    caller, callee = before.symbols["js_array_sort"], before.symbols[expected["callee"]]
    section = caller["section"]
    rec = co.section_records[section - 1]
    end = caller["value"] + expected["caller"]["size"]
    hits = []
    for at in before.relocation_positions(section):
        off, index, kind = struct.unpack_from("<IIH", co.data, at)
        if not caller["value"] <= off < end or kind != 4:
            continue
        sym = before.all_symbols[index]
        addend = struct.unpack_from("<i", co.data, rec["raw"] + off)[0]
        if sym["section"] == callee["section"] and sym["value"] + addend == callee["value"]:
            assert co.data[rec["raw"] + off - 1] == 0xE8
            hits.append(dict(offset=off, relocation_at=at, old_symbol=index))
    if tc == "mingw":
        assert (
            not hits
            and section == callee["section"]
            and before.sections[section - 1]["name"] == ".text"
        )
        match = re.search(r"^QJS_FRAME_OBJDUMP:FILEPATH=(.+)$", cache, re.M) or re.search(
            r"^CMAKE_OBJDUMP:FILEPATH=(.+)$", cache, re.M
        )
        assert match
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
                str(path),
            ],
            text=True,
        )
        generated_file(build, "quickjs-default-sort-caller.asm").write_text(
            listing, encoding="utf-8"
        )
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
            if not m:
                continue
            address, code = int(m[1], 16), bytes.fromhex(m[2])
            if (
                len(code) == 5
                and code[0] == 0xE8
                and address + 5 + struct.unpack_from("<i", code, 1)[0] == callee["value"]
            ):
                assert bytes(co.data[rec["raw"] + address : rec["raw"] + address + 5]) == code
                hits.append(dict(offset=address + 1, relocation_at=None, old_symbol=None))
    assert len(hits) == (1 if tc.startswith("msvc") else 2), (
        "Unexpected sort call sites",
        tc,
        hits,
    )
    target = co.external("JS_ArrayDefaultStringSortDispatch")
    for site in hits:
        off = site["offset"]
        site["old_operand"] = bytes(co.data[rec["raw"] + off : rec["raw"] + off + 4]).hex()
        if site["relocation_at"] is not None:
            struct.pack_into("<I", co.data, site["relocation_at"] + 4, target)
        else:
            co.extra_relocations.setdefault(section, []).append(struct.pack("<IIH", off, target, 4))
        co.data[rec["raw"] + off : rec["raw"] + off + 4] = bytes(4)
    # Give the exact, reviewed original ABI a valid independent external alias.
    offset = len(co.strings)
    co.strings += b"qjs_default_string_sort_original\0"
    alias = bytearray(co.stride)
    struct.pack_into("<III", alias, 0, 0, offset, callee["value"])
    struct.pack_into("<i" if co.stride == 20 else "<h", alias, 12, callee["section"])
    struct.pack_into("<H", alias, 16 if co.stride == 20 else 14, 32)
    alias[co.class_offset] = 2
    co.aliases.append(alias)
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    new_rec = after.section_records[section - 1]
    for site in hits:
        off = site["offset"]
        restored[new_rec["raw"] + off : new_rec["raw"] + off + 4] = bytes.fromhex(
            site["old_operand"]
        )
        if site["relocation_at"] is not None:
            at = next(
                at
                for at in after.relocation_positions(section)
                if struct.unpack_from("<I", after.data, at)[0] == off
            )
            struct.pack_into("<I", restored, at + 4, site["old_symbol"])
    if tc == "mingw":
        struct.pack_into("<I", restored, new_rec["pos"] + 24, rec["reloc"])
        struct.pack_into("<H", restored, new_rec["pos"] + 32, rec["count"])
    assert C.Coff(restored).sections == before.sections, "Mutation beyond admitted calls"
    assert all(after.all_symbols[i] == s for i, s in before.all_symbols.items()), (
        "Old symbol changed"
    )
    backup = path.with_name(path.name + ".before-default-sort")
    assert not backup.exists()
    backup.write_bytes(original)
    path.write_bytes(result)
    proof = dict(
        status="passed-exact-call-restoration-and-original-ABI-binding",
        toolchain=tc,
        original_callee=expected["callee"],
        original_arguments=5 if tc.startswith("msvc") else 3,
        caller_fingerprint=expected["caller"],
        original_sorter_fingerprint=expected["sorter"],
        adapted_sorter_fingerprint=adapted_sorter,
        original_abi_profile_unique=True,
        hits=hits,
        packing=packing,
        all_original_symbols_held=True,
        sections_equal_after_exact_restoration=True,
        before_sha256=sha(backup),
        after_sha256=sha(path),
    )
    generated_file(build, "quickjs-default-sort-route.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
    return proof
