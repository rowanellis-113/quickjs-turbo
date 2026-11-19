"""Expose core helpers without recompiling them in a changed call graph.

Experimental Windows x64 COFF adapter. By default only symbol names/visibility
change. Optional internal entry routing changes audited direct call targets,
without changing function boundaries, instruction sizes or unwind records.
The generated private header takes its types and inline helpers from exactly
the source used to build the input object. Optimizer clones are never called
through the original function ABI.
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
import argparse
import bisect
import collections
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path


def relocation_layout(data, pointer, count, flags):
    """Return logical records and complete storage for COFF's overflow form.

    The first extended record stores the physical count, including itself;
    it is metadata, not a relocation at that section offset. Keep the section
    header representation intact and still reject unsupported code rewrites.
    """
    first, records, storage = pointer, count, count * 10
    if flags & 0x01000000:
        if count != 0xFFFF or not pointer or pointer + 10 > len(data):
            raise RuntimeError("Invalid extended COFF relocation header")
        physical, symbol, kind = struct.unpack_from("<IIH", data, pointer)
        if physical < 0x10000 or symbol or kind:
            raise RuntimeError("Invalid extended COFF relocation count")
        first, records, storage = pointer + 10, physical - 1, physical * 10
    if storage and (not pointer or pointer + storage > len(data)):
        raise RuntimeError("Truncated COFF relocation table")
    return first, records, storage


class Coff:
    def __init__(self, data):
        self.data = bytearray(data)
        big = data[:4] == b"\0\0\xff\xff"
        if big:
            if struct.unpack_from("<H", data, 6)[0] != 0x8664:
                raise RuntimeError("Expected an x64 bigobj COFF object")
            self.header, self.stride, self.class_offset = 56, 20, 18
            self.count = struct.unpack_from("<I", data, 44)[0]
            self.table, self.symbol_count = struct.unpack_from("<II", data, 48)
            self.table_offset = 48
        else:
            machine, self.count = struct.unpack_from("<HH", data)
            if machine != 0x8664:
                raise RuntimeError("Expected an x64 COFF object")
            self.header, self.stride, self.class_offset = 20, 18, 16
            self.table, self.symbol_count = struct.unpack_from("<II", data, 8)
            self.table_offset = 8
            self.header += struct.unpack_from("<H", data, 16)[0]
        self.string_offset = self.table + self.stride * self.symbol_count
        length = struct.unpack_from("<I", data, self.string_offset)[0]
        self.strings = bytearray(data[self.string_offset : self.string_offset + length])
        self.symbols = {}
        self.all_symbols = {}
        self.aliases = []
        self.sections = []
        self.section_records = []
        self.extra_relocations = {}
        for i in range(self.count):
            pos = self.header + i * 40
            size, raw, reloc, line, nr, nl = struct.unpack_from("<IIIIHH", data, pos + 16)
            name = data[pos : pos + 8].split(b"\0")[0].decode("ascii", errors="replace")
            flags = struct.unpack_from("<I", data, pos + 36)[0]
            _, _, relocation_bytes = relocation_layout(data, reloc, nr, flags)
            self.sections.append(
                dict(
                    name=name,
                    size=size,
                    flags=flags,
                    sha256=hashlib.sha256(
                        data[raw : raw + size] if raw else b"\0" * size
                    ).hexdigest(),
                    relocations_sha256=hashlib.sha256(
                        data[reloc : reloc + relocation_bytes]
                    ).hexdigest(),
                    lines_sha256=hashlib.sha256(data[line : line + nl * 6]).hexdigest(),
                )
            )
            self.section_records.append(
                dict(
                    pos=pos,
                    size=size,
                    raw=raw,
                    reloc=reloc,
                    count=nr,
                    flags=flags,
                    relocation_bytes=relocation_bytes,
                )
            )
        index = 0
        while index < self.symbol_count:
            pos = self.table + index * self.stride
            if data[pos : pos + 4] == b"\0" * 4:
                off = struct.unpack_from("<I", data, pos + 4)[0]
                end = self.strings.find(0, off)
                name = self.strings[off:end].decode("utf-8", errors="replace")
            else:
                name = data[pos : pos + 8].split(b"\0")[0].decode("ascii", errors="replace")
            section = struct.unpack_from("<i" if big else "<h", data, pos + 12)[0]
            typ = struct.unpack_from("<H", data, pos + (16 if big else 14))[0]
            storage, aux = data[pos + self.class_offset : pos + self.class_offset + 2]
            self.all_symbols[index] = dict(
                name=name,
                section=section,
                type=typ,
                storage=storage,
                value=struct.unpack_from("<I", data, pos + 8)[0],
            )
            if section > 0 and typ & 0x20 and storage in (2, 3):
                self.symbols[name] = dict(
                    pos=pos,
                    section=section,
                    storage=storage,
                    value=struct.unpack_from("<I", data, pos + 8)[0],
                )
            index += 1 + aux

    def relocation_positions(self, index):
        section = self.section_records[index - 1]
        first, count, _ = relocation_layout(
            self.data, section["reloc"], section["count"], section["flags"]
        )
        return range(first, first + count * 10, 10)

    def external(self, name):
        index = self.symbol_count + len(self.aliases)
        offset = len(self.strings)
        self.strings += name.encode("ascii") + b"\0"
        symbol = bytearray(self.stride)
        struct.pack_into("<II", symbol, 0, 0, offset)
        struct.pack_into("<H", symbol, 16 if self.stride == 20 else 14, 0x20)
        symbol[self.class_offset] = 2
        self.aliases.append(symbol)
        return index

    def route_internal_calls(self, object_path, objdump):
        """Change only decoded direct calls to the exact unspecialized ABI.

        MSVC retains REL32 call relocations. GCC resolves same-section calls
        before writing COFF, so decode instructions and add REL32 relocations.
        Keep the original public wrapper's call unchanged for legacy fallback.
        """
        original = self.symbols["JS_CallInternal"]
        target = self.external("JS_FrameDispatchInternal")
        functions = collections.defaultdict(list)
        for name, info in self.symbols.items():
            functions[info["section"]].append((info["value"], name))
        for values in functions.values():
            values.sort()

        def owner(section, offset):
            values = functions[section]
            at = bisect.bisect_right([v[0] for v in values], offset) - 1
            assert at >= 0, (section, offset)
            return values[at][1]

        routes = []
        self.internal_entry_skipped = []
        relocated = set()
        for section, info in enumerate(self.section_records, 1):
            if not info["flags"] & 0x20:
                continue
            assert info["count"] != 65535, "Relocation overflow requires explicit support"
            for i in range(info["count"]):
                pos = info["reloc"] + i * 10
                at, symbol, kind = struct.unpack_from("<IIH", self.data, pos)
                if self.all_symbols[symbol]["name"] != "JS_CallInternal" or kind != 4:
                    continue
                caller = owner(section, at)
                if caller == "JS_Call":
                    continue
                if self.data[info["raw"] + at - 1] not in (0xE8, 0xE9):
                    self.internal_entry_skipped.append(
                        dict(
                            section=section,
                            offset=at,
                            caller=caller,
                            reason="function address reference, not a direct CALL/JMP",
                        )
                    )
                    continue
                struct.pack_into("<I", self.data, pos + 4, target)
                relocated.add((section, at))
                routes.append(
                    dict(
                        section=section,
                        offset=at,
                        caller=caller,
                        kind="existing-rel32",
                        old_symbol=symbol,
                        new_symbol=target,
                    )
                )

        # A direct call to a local function in the same section may have no
        # relocation at all. Only decoded five-byte CALL/JMP instructions are
        # candidates; an E8 byte inside data/immediates is never sufficient.
        section = original["section"]
        info = self.section_records[section - 1]
        name = self.sections[section - 1]["name"]
        if name == ".text" and not any(r["section"] == section for r in routes):
            assert objdump is not None, "GCC internal entry requires objdump"
            listing = subprocess.check_output(
                [str(objdump), "-d", "-w", "-Mintel", "-j", name, str(object_path)], text=True
            )
            for line in listing.splitlines():
                match = re.match(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+)+)\s*(.*?)\s*$", line)
                if not match:
                    continue
                address = int(match[1], 16)
                code = bytes.fromhex(match[2])
                if len(code) != 5 or code[0] not in (0xE8, 0xE9):
                    continue
                if address + 5 + struct.unpack_from("<i", code, 1)[0] != original["value"]:
                    continue
                at = address + 1
                caller = owner(section, address)
                if caller == "JS_Call" or (section, at) in relocated:
                    continue
                assert bytes(self.data[info["raw"] + address : info["raw"] + address + 5]) == code
                self.data[info["raw"] + at : info["raw"] + at + 4] = bytes(4)
                self.extra_relocations.setdefault(section, []).append(
                    struct.pack("<IIH", at, target, 4)
                )
                routes.append(
                    dict(
                        section=section,
                        offset=at,
                        caller=caller,
                        kind="decoded-rel32",
                        old_bytes=code[1:].hex(),
                        new_symbol=target,
                    )
                )
        assert routes and any(r["caller"] == "JS_CallInternal" for r in routes)
        return routes

    def expose(self, name):
        # Preserve the original static symbol and COMDAT identity. Append a
        # separate external alias for the backend instead of changing class 3
        # to class 2, which can change the linker's folding decisions.
        info = self.symbols[name]
        alias = "qjs_frame_core_" + name
        offset = len(self.strings)
        self.strings += alias.encode("ascii") + b"\0"
        symbol = bytearray(self.stride)
        struct.pack_into("<III", symbol, 0, 0, offset, info["value"])
        big = self.stride == 20
        struct.pack_into("<i" if big else "<h", symbol, 12, info["section"])
        struct.pack_into("<H", symbol, 16 if big else 14, 0x20)
        symbol[self.class_offset] = 2
        self.aliases.append(symbol)

    def rename(self, old, new):
        pos = self.symbols[old]["pos"]
        offset = len(self.strings)
        self.strings += new.encode("ascii") + b"\0"
        struct.pack_into("<II", self.data, pos, 0, offset)

    def finish(self):
        struct.pack_into("<I", self.strings, 0, len(self.strings))
        struct.pack_into(
            "<I", self.data, self.table_offset + 4, self.symbol_count + len(self.aliases)
        )
        # Leave section addresses and relocation/symbol indices untouched.
        result = bytearray(
            self.data[: self.string_offset]
            + b"".join(self.aliases)
            + self.strings
            + self.data[
                self.string_offset + struct.unpack_from("<I", self.data, self.string_offset)[0] :
            ]
        )
        for section, additions in self.extra_relocations.items():
            info = self.section_records[section - 1]
            count = info["count"] + len(additions)
            assert count < 65535
            result += bytes((-len(result)) & 3)
            offset = len(result)
            result += self.data[info["reloc"] : info["reloc"] + info["count"] * 10]
            result += b"".join(additions)
            struct.pack_into("<I", result, info["pos"] + 24, offset)
            struct.pack_into("<H", result, info["pos"] + 32, count)
        return bytes(result)


FUNCTION = re.compile(
    r"^((?:(?:static|inline|no_inline|__maybe_unused)\s+)*"
    r"(?:[\w]+\s+|\*\s*)+?)(\w+)\s*\(([^;{}]*)\)\s*\{(.*?)^\}",
    re.M | re.S,
)
MACRO = re.compile(r"^#define\s+(\w+)(?:[^\n]*\\\n)*[^\n]*", re.M)

# These helpers were inlined into the original interpreter's hot paths.
# Keeping them local avoids adding an ABI boundary per value or global load.
# Cold semantic helpers stay shared with the unchanged core.
HOT_LOCAL_HELPERS = {
    "js_dup",
    "js_bool",
    "js_int32",
    "js_uint32",
    "js_float64",
    "js_number",
    "__JS_NewShortBigInt",
    "hash_atom",
    "JS_GetGlobalVar",
    "JS_SetPropertyInternal",
    "needs_backtrace",
    # These retained argument builders were already local/inlined. Copy this
    # upstream's implementation, including its VarRef ownership protocol.
    "js_dup_shape",
    "add_gc_object",
    "js_create_var_ref",
    "js_build_arguments",
    "js_build_mapped_arguments",
}

# These small helpers are newly needed by the primitive BigInt boundary. Any
# compiler-emitted out-of-line copy belongs beside that boundary, so introducing
# it cannot shift existing .text helpers. The core's definitions are untouched.
BIGINT_ISLAND_HELPERS = {"JS_CompactBigInt", "js_bigint_set_si", "js_bigint_set_short"}


def identifiers(text):
    text = re.sub(
        r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', " ", text, flags=re.S
    )
    return set(re.findall(r"\b\w+\b", text))


def dependency_source(text, disabled_macros):
    """Resolve only explicitly known feature guards for dependency discovery.

    Other preprocessor branches remain visible. The compiler still receives
    the original bodies and enforces the measured private-layout contract.
    """
    if not disabled_macros:
        return text
    output, stack, active = [], [], True
    for line in text.splitlines(keepends=True):
        directive = re.match(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", line)
        if not directive:
            if active:
                output.append(line)
            continue
        kind, condition = directive[1], re.sub(r"/\*.*?\*/|//.*", "", directive[2]).strip()
        if kind in ("if", "ifdef", "ifndef"):
            known = kind in ("ifdef", "ifndef") and condition in disabled_macros
            if kind == "if" and any(
                re.search(r"\b" + re.escape(name) + r"\b", condition) for name in disabled_macros
            ):
                raise ValueError("Review compound disabled-feature condition: " + condition)
            stack.append((active, known, kind == "ifndef"))
            if known:
                active = active and kind == "ifndef"
            elif active:
                output.append(line)
        elif kind == "endif":
            parent, known, _ = stack.pop()
            if not known and parent:
                output.append(line)
            active = parent
        else:
            parent, known, branch = stack[-1]
            if known:
                if kind == "elif":
                    raise ValueError("Review elif in a disabled-feature dependency block")
                stack[-1] = (parent, known, not branch)
                active = parent and not branch
            elif parent:
                output.append(line)
    if stack:
        raise ValueError("Unbalanced source feature guards")
    return "".join(output)


def generate(source, coff, backend, owned_functions=(), disabled_macros=()):
    prelude_end = source.index("static inline bool double_is_int32")
    prelude = source[:prelude_end]
    from property_ic import private_types

    prelude = private_types(prelude, conditional=True)
    # The core public API remains in its original object, including this one.
    prelude = re.sub(
        r"^const char\* JS_GetVersion\(void\) \{.*?^\}", "", prelude, flags=re.M | re.S
    )
    prelude = re.sub(r"^static\s+[^;{}]+\([^;{}]*\);\s*", "", prelude, flags=re.M)
    functions = {m[2]: m for m in FUNCTION.finditer(source)}
    in_prelude = {name for name, m in functions.items() if m.start() < prelude_end}
    needed, copied, exported = set(), set(), set()
    analysis = dependency_source(backend, disabled_macros)
    names = identifiers(analysis)
    # Retained modules spell their explicit aliases directly. Resolve those
    # requests against this core rather than carrying frozen private headers.
    alias_requests = {
        name[len("qjs_frame_core_") :] for name in names if name.startswith("qjs_frame_core_")
    }
    names |= alias_requests
    owned_functions = set(owned_functions)
    pending = names & functions.keys() - owned_functions
    while pending:
        name = pending.pop()
        if name in needed or name in in_prelude:
            continue
        needed.add(name)
        # Debug COFF can retain inline helper symbols. Calling those externally
        # would turn each value/stack/poll operation into a native ABI call.
        # Copy their bodies into this TU; the frozen core is unaffected.
        copy_inline = (
            bool(re.search(r"\binline\b", functions[name][1]))
            or name in HOT_LOCAL_HELPERS | BIGINT_ISLAND_HELPERS
        )
        if name in coff.symbols and not copy_inline:
            if coff.symbols[name]["storage"] == 3:
                exported.add(name)
        else:
            copied.add(name)
            pending |= (
                identifiers(dependency_source(functions[name][0], disabled_macros))
                & functions.keys() - needed - owned_functions
            )
    # Add only referenced out-of-prelude macros, preserving complete bodies.
    local_macros = {m[1] for m in MACRO.finditer(backend)}
    macros = {
        m[1]: m
        for m in MACRO.finditer(source)
        if m.start() >= prelude_end
        and m[1] not in local_macros | {"DEF", "def", "FMT", "CASE", "BREAK"}
    }
    macro_names, work = (
        set(),
        identifiers(
            analysis
            + "\n".join(dependency_source(functions[n][0], disabled_macros) for n in copied)
        ),
    )
    while True:
        new = work & macros.keys() - macro_names
        if not new:
            break
        macro_names |= new
        work |= identifiers("\n".join(macros[n][0] for n in new))
    pieces = [
        "/* Generated from this build's quickjs.c; do not edit. */",
        prelude,
        '#include "src/common/property/property-ic.h"',
        '#include "interpreter-private-abi.h"\n#include "src/x86/win64/internal/interpreter-private-compat.inc"',
    ]
    if "opcode_info" in work:
        start = source.index("typedef struct JSOpCode {")
        array = source.index("static const JSOpCode opcode_info[", start)
        end = source.index("\n};", array) + 3
        pieces.append(source[start:end])
    if "JSDOMExceptionData" in work:
        match = re.search(
            r"^typedef struct JSDOMExceptionData \{.*?^\} JSDOMExceptionData;", source, re.M | re.S
        )
        if not match:
            raise ValueError("Missing current DOMException private data type")
        pieces.append(match[0])
    pieces += ["#define %s qjs_frame_core_%s" % (n, n) for n in sorted(exported)]
    pieces += [
        "#define qjs_frame_core_%s %s" % (n, n) for n in sorted(alias_requests & needed - exported)
    ]
    pieces += [macros[n][0] for n in sorted(macro_names)]
    pieces += [
        '#ifdef _MSC_VER\n#define FRAME_BIGINT_LOCAL __declspec(code_seg(".qjsprop"))\n'
        '#else\n#define FRAME_BIGINT_LOCAL __attribute__((section(".qjsprop")))\n#endif'
    ]
    # Forward declarations precede all copied bodies, including mutually
    # recursive helpers. Existing external functions retain their exact ABI.
    for name in sorted(needed):
        m = functions[name]
        prefix = m[1]
        if name in copied & BIGINT_ISLAND_HELPERS:
            prefix = "FRAME_BIGINT_LOCAL " + prefix
        if name not in copied:
            prefix = re.sub(r"\b(?:static|inline|no_inline|__maybe_unused)\s*", "", prefix)
            prefix = "extern " + prefix
        pieces.append(prefix + name + "(" + m[3] + ");")
    for n in sorted(copied, key=lambda n: functions[n].start()):
        body = functions[n][0]
        if n == "js_free_shape":
            opening = body.index("{")
            assert body[opening:].count("js_free_shape0(rt, sh)") == 1
            body = (
                body[: opening + 1]
                + "\n#ifdef QJS_PROPERTY_IC\n"
                + "    js_property_ic_release_shape_ref(rt, sh);\n#else\n"
                + body[opening + 1 : body.rindex("}")]
                + "\n#endif\n}"
            )
        elif n == "js_dup_shape":
            opening = body.index("{")
            assert body[opening:].count("sh->header.ref_count++") == 1
            body = (
                body[: opening + 1]
                + "\n#ifdef QJS_PROPERTY_IC\n"
                + "    return js_property_ic_acquire_shape_ref(sh);\n#else\n"
                + body[opening + 1 : body.rindex("}")]
                + "\n#endif\n}"
            )
        pieces.append(("FRAME_BIGINT_LOCAL " if n in BIGINT_ISLAND_HELPERS else "") + body)
    return "\n\n".join(pieces) + "\n", sorted(exported), sorted(copied)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--object", type=Path, required=True)
    ap.add_argument("--header", type=Path, required=True)
    ap.add_argument("--retained-header", type=Path)
    ap.add_argument("--wire-header", type=Path)
    ap.add_argument("--internal-entry", action="store_true")
    ap.add_argument("--native-instanceof", action="store_true")
    ap.add_argument("--objdump", type=Path)
    args = ap.parse_args()
    raw = args.object.read_bytes()
    backup = args.header.with_name("quickjs-core-original.obj")
    coff = Coff(raw)
    if "JS_Call" not in coff.symbols:
        if "JS_LegacyCall" not in coff.symbols or not backup.exists():
            raise RuntimeError("Cannot recover the unadapted core object")
        raw = backup.read_bytes()
        coff = Coff(raw)
    source = args.source.read_text(encoding="utf-8")
    vm_root = (
        args.source.parent
        if (args.source.parent / "src/sources.json").is_file()
        else _frame_project_root()
    )
    from abi_layout import write_contracts

    write_contracts(vm_root, args.header.parent)
    backend_sources = (
        "quickjs-interpreter.c",
        "quickjs-interpreter-loop.h",
        "quickjs-interpreter-ops.h",
        "quickjs-interpreter-bigint.h",
    )
    if args.native_instanceof:
        HOT_LOCAL_HELPERS.add("js_operator_instanceof")
        backend_sources += ("interpreter-instanceof.c",)
    backend = "\n".join(_frame_source_text(vm_root, n) for n in backend_sources)
    header, exports, copies = generate(source, coff, backend)
    retained_exports = []
    if args.retained_header:
        manifest = json.loads((vm_root / "src/x86/win64/backend.json").read_text(encoding="utf-8"))
        retained_sources = sorted(
            {
                module["source"]
                for profile in manifest["toolchains"].values()
                for module in profile["modules"]
                if module["language"] == ".c" and module["id"] != "wire"
            }
        )
        retained_body = "\n".join(_frame_source_text(vm_root, name) for name in retained_sources)
        retained_header, retained_exports, retained_copies = generate(source, coff, retained_body)
        args.retained_header.write_text(retained_header, encoding="utf-8", newline="\n")
        args.retained_header.with_suffix(".json").write_text(
            json.dumps(
                dict(
                    source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                    header_sha256=hashlib.sha256(retained_header.encode("utf-8")).hexdigest(),
                    sources=retained_sources,
                    exported_helpers=retained_exports,
                    copied_inline_helpers=retained_copies,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    wire_exports = []
    if args.wire_header:
        wire_body = _frame_source_text(vm_root, "wire.c")
        wire_owned = {match[2] for match in FUNCTION.finditer(wire_body)}
        wire_header, wire_exports, wire_copies = generate(
            source, coff, wire_body, wire_owned, ("ENABLE_DUMPS",)
        )
        args.wire_header.write_text(wire_header, encoding="utf-8", newline="\n")
        args.wire_header.with_suffix(".json").write_text(
            json.dumps(
                dict(
                    source_sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
                    wire_sha256=hashlib.sha256(wire_body.encode("utf-8")).hexdigest(),
                    header_sha256=hashlib.sha256(wire_header.encode("utf-8")).hexdigest(),
                    owned_functions=sorted(wire_owned),
                    exported_helpers=wire_exports,
                    copied_inline_helpers=wire_copies,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    for name in sorted(set(exports) | set(retained_exports) | set(wire_exports)):
        coff.expose(name)
    routes = []
    if args.internal_entry:
        backup.write_bytes(raw)
        routes = coff.route_internal_calls(backup, args.objdump)
    coff.rename("JS_Call", "JS_LegacyCall")
    result = coff.finish()
    verified = Coff(result)
    if routes:
        restored = bytearray(result)
        for route in routes:
            section = route["section"]
            info = coff.section_records[section - 1]
            if route["kind"] == "decoded-rel32":
                at = info["raw"] + route["offset"]
                restored[at : at + 4] = bytes.fromhex(route["old_bytes"])
                struct.pack_into("<I", restored, info["pos"] + 24, info["reloc"])
                struct.pack_into("<H", restored, info["pos"] + 32, info["count"])
            else:
                for i in range(info["count"]):
                    pos = info["reloc"] + i * 10
                    if struct.unpack_from("<I", restored, pos)[0] == route["offset"]:
                        assert struct.unpack_from("<I", restored, pos + 4)[0] == route["new_symbol"]
                        struct.pack_into("<I", restored, pos + 4, route["old_symbol"])
                        break
                else:
                    raise RuntimeError("Routed call relocation missing")
        assert Coff(restored).sections == Coff(raw).sections, "Changes outside audited calls"
    elif coff.sections != verified.sections:
        raise RuntimeError("Core sections or relocations changed")
    for name, info in coff.symbols.items():
        if name != "JS_Call":
            assert verified.symbols[name]["storage"] == info["storage"], name
            assert verified.symbols[name]["section"] == info["section"], name
            assert verified.symbols[name]["value"] == info["value"], name
    backup.write_bytes(raw)
    args.object.write_bytes(result)
    args.header.write_text(header, encoding="utf-8")
    evidence = dict(
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        original_object_sha256=hashlib.sha256(raw).hexdigest(),
        adapted_object_sha256=hashlib.sha256(result).hexdigest(),
        core_sections_identical=not routes,
        original_static_symbols_unchanged=True,
        core_identical_except_audited_call_targets=True,
        internal_entry_routes=routes,
        internal_entry_skipped=getattr(coff, "internal_entry_skipped", []),
        sections=coff.sections,
        exported_helpers=exports,
        copied_inline_helpers=copies,
        header_sha256=hashlib.sha256(header.encode("utf-8")).hexdigest(),
    )
    args.header.with_suffix(".json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        "Frame adapter: %d audited internal call targets; %d helpers exposed, %d copied"
        % (len(routes), len(exports), len(copies))
    )


if __name__ == "__main__":
    main()
