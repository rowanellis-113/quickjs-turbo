"""Native JSON island, parser-extracted private declarations and typed routes."""

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
import argparse, hashlib, importlib.util, json, re, struct, os
from pathlib import Path

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name, file):
    sp = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def backend_parts(backend):
    # Materialize only the selected backend before private-helper extraction.
    # A preprocessor guard alone would expose/copy helpers from the other TU.
    markers = (
        "typedef struct FrameJSONText {",
        "JSON_INLINE unsigned frame_json_first_lane(",
        "JSON_INLINE unsigned frame_json_hash(",
        "typedef struct FrameJSONWriter {",
    )
    assert all(backend.count(x) == 1 for x in markers)
    text, scan, hashed, writer = (backend.index(x) for x in markers)
    assert text < scan < hashed < writer
    common = backend[:text]
    scanners = backend[scan:hashed]
    parser = backend[:writer]
    owned = '_Atomic unsigned char JS_FrameJSONControl __attribute__((section(".qjscbmt$zzjson")));'
    assert common.count(owned) == 1
    common = common.replace(owned, "extern _Atomic unsigned char JS_FrameJSONControl;")
    writer = common + scanners + backend[writer:]

    def sections(body, suffix):
        assert body.count(".qjs$zzjson") == body.count(".qjsjson") == 1
        return body.replace(".qjs$zzjson", ".qjs$zzjson" + suffix).replace(
            ".qjsjson", ".qjsjson$" + suffix
        )

    return {"parser": sections(parser, "A"), "writer": sections(writer, "B")}


def adapt(source, object_path, header):
    M = module("json_coff", "object-adapter.py")
    raw = object_path.read_bytes()
    old = M.Coff(raw)
    c = M.Coff(raw)
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    backend = _frame_source_text(source, "quickjs-interpreter-json.h")
    types = re.search(r"typedef struct StringBuffer \{.*?\} StringBuffer;", original, re.S)[0]
    marker = "static inline bool double_is_int32"
    assert original.count(marker) == 1
    virtual = original.replace(marker, types + "\n" + marker)
    # The shared parser expects the opening brace on the next line. Normalize
    # this one inline helper's signature whitespace, preserving its body.
    pattern = r"^(static inline int string_get\([^\n]*\)) \{"
    assert len(re.findall(pattern, virtual, re.M)) == 1
    virtual = re.sub(pattern, lambda m: m[1] + "\n{", virtual, count=1, flags=re.M)
    functions = {m[2]: m for m in M.FUNCTION.finditer(original)}
    atom_body = functions["JS_DupAtom"][0]
    private_atom_body = atom_body.replace(
        "JSAtom JS_DupAtom(", "static inline JSAtom frame_json_dup_atom("
    )
    assert private_atom_body != atom_body
    virtual += "\n" + private_atom_body + "\n"
    # Keep tiny buffer operations local; allocation/growth and semantic slow
    # operations retain their current-source bodies/ABI through the generator.
    M.HOT_LOCAL_HELPERS |= {
        "string_buffer_putc8",
        "string_buffer_putc16",
        "string_buffer_write8",
        "string_buffer_write16",
        "string_buffer_puts8",
        "string_buffer_free",
        "string_buffer_init2",
        "js_new_string8_len",
        "js_new_string16_len",
        "add_fast_array_element",
        "JS_AtomGetKind",
        "js_dup_shape",
        "js_free_shape",
        "JS_AtomIsArrayIndex",
        "is_num_string",
    }
    callback_generator = module("json_callback_generator", "json-callback.py")
    virtual, callback_backend, callback_proto, callback_proof = callback_generator.prepare(
        source, virtual
    )
    parts = backend_parts(backend)
    parts["callback"] = callback_backend
    generated = {
        part: M.generate(virtual, c, body) for part, body in parts.items() if part != "callback"
    }
    shared = set(generated["parser"][1]) | set(generated["writer"][1])
    parts["callback"], generated["callback"], owned_helpers = callback_generator.generate_owned(
        M, virtual, c, parts["callback"], shared
    )
    callback_proof["owned_core_helpers"] = owned_helpers
    callback_text, callback_exports, callback_copies = generated["callback"]
    callback_text = callback_proto + callback_text
    text, exports, copies = generated["parser"]
    writer_text, writer_exports, writer_copies = generated["writer"]
    assert types in text and types in writer_text
    source_text, source_backend, source_exports, source_proof = (
        callback_generator.prepare_source_records(
            source, virtual, c, set(exports) | set(writer_exports) | set(callback_exports)
        )
    )
    source_unit = source_proof.pop("codeunit_generated")
    exports = sorted(
        set(exports) | set(writer_exports) | set(callback_exports) | set(source_exports)
    )
    copies = sorted(set(copies) | set(writer_copies) | set(callback_copies))
    names = {s["name"] for s in c.all_symbols.values()}
    added = []
    for n in exports:
        if "qjs_frame_core_" + n not in names:
            c.expose(n)
            added.append(n)
    # Public API exports move to an admitted wrapper. All references already
    # inside the frozen core keep targeting its original function bodies.
    renames = []
    for n in ("JS_ParseJSON", "JS_JSONStringify"):
        before = c.symbols[n]
        c.rename(n, "JS_Legacy" + n[3:])
        renames.append(
            dict(
                original=n,
                target="JS_Legacy" + n[3:],
                section=before["section"],
                value=before["value"],
            )
        )
    routes = []
    for original_name, target in (
        ("js_json_parse", "JS_FrameJSONParse"),
        ("js_json_stringify", "JS_FrameJSONStringify"),
    ):
        fn = c.symbols[original_name]
        external = c.external(target)
        for si, rec in enumerate(c.section_records):
            sec = c.sections[si]
            if rec["flags"] & 0x20000000 or not sec["name"].startswith(".rdata"):
                continue
            for i in range(rec["count"]):
                q = rec["reloc"] + i * 10
                off, sym, kind = struct.unpack_from("<IIH", c.data, q)
                if sym not in c.all_symbols:
                    continue
                s = c.all_symbols[sym]
                if kind != 1 or s["section"] != fn["section"]:
                    continue
                addend = struct.unpack_from("<Q", c.data, rec["raw"] + off)[0]
                if addend + s["value"] != fn["value"]:
                    continue
                struct.pack_into("<Q", c.data, rec["raw"] + off, 0)
                struct.pack_into("<I", c.data, q + 4, external)
                routes.append(
                    dict(
                        section=si + 1,
                        offset=off,
                        original=original_name,
                        target=target,
                        original_symbol=sym,
                        original_addend=addend,
                    )
                )
        assert any(r["original"] == original_name for r in routes), original_name
    old_end = old.string_offset + struct.unpack_from("<I", raw, old.string_offset)[0]
    result = bytearray(c.finish())
    shift = len(result) - len(raw)
    for rec in old.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            value = struct.unpack_from("<I", raw, at)[0]
            if value and value >= old_end:
                struct.pack_into("<I", result, at, value + shift)
    check = M.Coff(result)
    for si, (a, b) in enumerate(zip(old.section_records, check.section_records), 1):
        before = bytearray(raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"]))
        after = bytearray(result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"]))
        for r in routes:
            if r["section"] == si:
                after[r["offset"] : r["offset"] + 8] = before[r["offset"] : r["offset"] + 8]
        assert before == after, (si, "unaltered original payload")
        before = bytearray(raw[a["reloc"] : a["reloc"] + a["count"] * 10])
        after = bytearray(result[b["reloc"] : b["reloc"] + b["count"] * 10])
        for r in routes:
            if r["section"] != si:
                continue
            hits = [
                i
                for i in range(a["count"])
                if struct.unpack_from("<I", before, i * 10)[0] == r["offset"]
            ]
            assert len(hits) == 1
            i = hits[0]
            before[i * 10 + 4 : i * 10 + 8] = after[i * 10 + 4 : i * 10 + 8] = bytes(4)
        assert before == after, (si, "unaltered original relocations")
    object_path.write_bytes(result)
    header.write_text(text, encoding="utf-8")
    (header.parent / "quickjs-json-source-private.h").write_text(source_text, encoding="utf-8")
    (header.parent / "quickjs-json-source-backend.h").write_text(source_backend, encoding="utf-8")
    (header.parent / "quickjs-json-source-codeunits-private.h").write_text(
        source_unit["header"], encoding="utf-8"
    )
    (header.parent / "quickjs-json-source-codeunits-backend.h").write_text(
        source_unit["backend"], encoding="utf-8"
    )
    (header.parent / "quickjs-json-source-generation.json").write_text(
        json.dumps(source_proof, indent=2) + "\n", encoding="utf-8"
    )
    writer_header = header.with_name("quickjs-json-writer-private.h")
    writer_header.write_text(writer_text, encoding="utf-8")
    callback_header = header.with_name("quickjs-json-callback-private.h")
    callback_header.write_text(callback_text, encoding="utf-8")
    backend_headers = {}
    for part, body in parts.items():
        path = header.with_name("quickjs-json-" + part + "-backend.h")
        path.write_text(body, encoding="utf-8")
        backend_headers[part] = {
            "file": path.name,
            "sha256": sha(path),
            "private_header_sha256": sha(
                header
                if part == "parser"
                else writer_header
                if part == "writer"
                else callback_header
            ),
            "copied_helpers": generated[part][2],
            "exports": generated[part][1],
        }
    header.with_name("quickjs-json-split.json").write_text(
        json.dumps(
            dict(
                status="passed",
                source_backend_sha256=sha(_frame_source_file(source, "quickjs-interpreter-json.h")),
                parts=backend_headers,
                callback_generation=callback_proof,
                callback_source_sha256=sha(
                    _frame_source_file(source, "quickjs-interpreter-json-callback.h")
                ),
                callback_generator_sha256=sha(_frame_tool_path("json-callback")),
                control_owner="parser TU on GCC; retained MASM control section on MSVC",
                policy="Disjoint parser/writer definitions, independently extracted helpers, parser-before-writer late sections.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    header.with_suffix(".json").write_text(
        json.dumps(
            dict(
                status="passed",
                original_object_sha256=hashlib.sha256(raw).hexdigest(),
                adapted_object_sha256=sha(object_path),
                core_sha256=sha(_frame_source_file(source, "quickjs.c")),
                backend_sha256=sha(_frame_source_file(source, "quickjs-interpreter-json.h")),
                generator_sha256=sha(__file__),
                header_sha256=sha(header),
                added_exports=added,
                copied_helpers=copies,
                routes=routes,
                renames=renames,
                atom_copy=dict(
                    original_sha256=hashlib.sha256(atom_body.encode()).hexdigest(),
                    private_sha256=hashlib.sha256(private_atom_body.encode()).hexdigest(),
                    policy="Exact JS_DupAtom body with private inline signature only.",
                ),
                policy="Two typed builtin-table pointers and two public export aliases only; original code bodies, function offsets and internal references retained.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    callback_generator.adapt_tojson_slot(source, object_path)
    callback_generator.adapt_slice_simple(source, object_path)
    print("JSON ADAPTER", len(routes), "pointers;", len(renames), "API aliases", flush=True)


def compile_extra(source, build, out):
    M = module("json_compile", "atod.py")
    original_argv = M.win_argv
    M.win_argv = lambda command: [x for x in original_argv(command) if not x.startswith("-g")] + (
        ["-g0"] if any("mingw" in x.lower() for x in original_argv(command)[:1]) else []
    )
    command = next(
        x["command"]
        for x in json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
        if Path(x["file"]).name == "quickjs-interpreter.c"
    )
    msvc = "/nologo" in command.lower()
    writer_out = out.with_name(out.stem + "-writer.obj")
    callback_out = out.with_name(out.stem + "-callback.obj")

    def compile_part(part, target, suffix):
        # All compiler-generated constants/helpers/unwind remain in this
        # part's ordered late contribution, with no earlier RX/RW group.
        late = (".qjs$zzjson" if msvc else ".qjsjson$") + suffix
        private = (
            "quickjs-json-private.h"
            if part == "parser"
            else "quickjs-json-writer-private.h"
            if part == "writer"
            else "quickjs-json-callback-private.h"
        )

        def generate(source, path):
            path.write_text(
                '#include "' + private + '"\n#include "quickjs-json-' + part + '-backend.h"\n',
                encoding="utf-8",
            )

        if msvc and part == "callback":
            original_generate = generate

            def generate(source, path):
                original_generate(source, path)
                with path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        '\n#pragma section(".qjs$zzzzzzjsonU0",read)\n#pragma section(".qjs$zzzzzzjsonU2",read)\n__declspec(allocate(".qjs$zzzzzzjsonU0")) const unsigned char qjs_json_callback_unwind_header[32]={'
                        + ",".join(
                            str(x)
                            for x in b"QJSJCB_UNWIND_v1" + bytes(4) + bytes([1, 0, 0, 0]) + bytes(8)
                        )
                        + '};\n__declspec(allocate(".qjs$zzzzzzjsonU2")) const unsigned char qjs_json_callback_unwind_footer[16]={'
                        + ",".join(str(x) for x in b"QJSJCB_END_v1!!!")
                        + "};\n"
                    )

        if msvc:
            from types import SimpleNamespace

            Base = module("json_part_coff_" + part, "object-adapter.py").Coff

            class JSONCoff(Base):
                def finish(self):
                    # Parser/writer objects share the last archive member on
                    # MSVC. Two same-name COMDAT definitions in one object are
                    # illegal, even if their bytes match. Namespace only the
                    # writer's compiler-generated string/vector constants;
                    # retain COMDAT flags, complete payloads and relocations.
                    if part != "parser":
                        for index, symbol in self.all_symbols.items():
                            name = symbol["name"]
                            if (
                                symbol["storage"] != 2
                                or symbol["section"] <= 0
                                or not (
                                    name.startswith(("??_C@", "__xmm@"))
                                    or (part == "callback" and name.startswith("__real@"))
                                )
                            ):
                                continue
                            assert self.section_records[symbol["section"] - 1]["flags"] & 0x1000
                            private = (
                                "qjs_json_"
                                + part
                                + "_const_"
                                + hashlib.sha256(name.encode()).hexdigest()[:32]
                            )
                            at = len(self.strings)
                            self.strings += private.encode() + b"\0"
                            struct.pack_into(
                                "<II", self.data, self.table + index * self.stride, 0, at
                            )
                    if part == "callback":
                        native_sections = {
                            s["section"]
                            for s in self.all_symbols.values()
                            if s["storage"] == 3
                            and s["type"] == 0
                            and s["name"].startswith(".pdata")
                        }
                        native_count = sum(
                            self.section_records[n - 1]["size"] // 12 for n in native_sections
                        )
                        assert native_count > 0
                        header = next(
                            s
                            for s in self.all_symbols.values()
                            if s["name"] == "qjs_json_callback_unwind_header"
                        )
                        for symbol in self.all_symbols.values():
                            if symbol["name"] in (
                                "qjs_json_callback_unwind_header",
                                "qjs_json_callback_unwind_footer",
                            ):
                                owned = self.section_records[symbol["section"] - 1]
                                flags = struct.unpack_from("<I", self.data, owned["pos"] + 36)[0]
                                assert flags & 0xE0000000 == 0x40000000
                                struct.pack_into(
                                    "<I", self.data, owned["pos"] + 36, flags | 0x20000000
                                )
                        rec = self.section_records[header["section"] - 1]
                        at = rec["raw"] + header["value"]
                        assert self.data[at : at + 16] == b"QJSJCB_UNWIND_v1"
                        struct.pack_into("<I", self.data, at + 16, native_count)
                    for rec in self.section_records:
                        name = (
                            self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode("ascii")
                        )
                        if name.startswith("/"):
                            at = int(name[1:])
                            name = self.strings[at : self.strings.find(0, at)].decode("ascii")
                        if name == late:
                            flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                            struct.pack_into(
                                "<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040
                            )
                    return super().finish()

            M.coff_module = lambda: SimpleNamespace(Coff=JSONCoff)
        else:
            from types import SimpleNamespace

            Base = module("json_native_unwind_coff_" + part, "object-adapter.py").Coff

            class JSONCoff(Base):
                def finish(self):
                    # Native JSON runtime-function records must not grow the
                    # earlier global/regexp directory carriers. Retain each
                    # compiler payload/relocation/association, only changing
                    # its owned input-section and section-symbol names.
                    for number, rec in enumerate(self.section_records, 1):
                        current = (
                            self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode("ascii")
                        )
                        if current.startswith("/"):
                            at = int(current[1:])
                            current = self.strings[at : self.strings.find(0, at)].decode("ascii")
                        if not current.startswith(".pdata") or not rec["size"]:
                            continue
                        assert rec["size"] % 12 == 0 and rec["count"] == rec["size"] // 4
                        renamed = ".qjsjfn$" + suffix
                        at = len(self.strings)
                        self.strings += renamed.encode() + b"\0"
                        encoded = ("/" + str(at)).encode()
                        assert len(encoded) <= 8
                        self.data[rec["pos"] : rec["pos"] + 8] = encoded.ljust(8, b"\0")
                        for index, symbol in self.all_symbols.items():
                            if (
                                symbol["section"] == number
                                and symbol["storage"] == 3
                                and symbol["type"] == 0
                                and symbol["name"].startswith(".pdata")
                            ):
                                struct.pack_into(
                                    "<II", self.data, self.table + index * self.stride, 0, at
                                )
                    return super().finish()

            M.coff_module = lambda: SimpleNamespace(Coff=JSONCoff)
        M.compile_extra(
            source,
            build,
            target,
            generator=generate,
            filename="quickjs-interpreter-json" + ("" if part == "parser" else "-" + part) + ".c",
            late_name=late,
        )

    compile_part("parser", out, "A")
    compile_part("writer", writer_out, "B")
    compile_part("callback", callback_out, "C")
    if not msvc:
        module("json_write_entry", "json-callback.py").compile_writable(
            source, build, callback_out, out, writer_out
        )
        module("json_reviver_value_entry", "json-callback.py").compile_reviver_value(
            source, build, callback_out, out
        )
        module("json_source_record_entry", "json-callback.py").compile_source_records(
            source, build, callback_out
        )
    late = ".qjs$zzjson0"  # Atomics precede both independently compiled parts.
    if msvc:
        # The original MASM control section establishes the output-group order.
        # Append one owned data symbol/byte there, preserving every old byte,
        # relocation, symbol, section classification and control offset.
        register = _frame_generated_file(build, "quickjs-interpreter-register.obj")
        stamp_register = register.stat()
        raw = register.read_bytes()
        C = module("json_register_control", "object-adapter.py").Coff
        rc = C(raw)
        matches = [
            (i, s) for i, s in rc.all_symbols.items() if s["name"] == "JS_FrameCallbackControl"
        ]
        assert len(matches) == 1
        _, symbol = matches[0]
        sn = symbol["section"]
        rec = rc.section_records[sn - 1]
        assert rec["flags"] & 0xE0000000 == 0xC0000000 and not rec["count"] and rec["raw"]
        before = raw[rec["raw"] : rec["raw"] + rec["size"]]
        assert before and before[0] == 0
        name = "JS_FrameJSONControl"
        at = len(rc.strings)
        rc.strings += name.encode() + b"\0"
        alias = bytearray(rc.stride)
        struct.pack_into("<III", alias, 0, 0, at, len(before))
        struct.pack_into("<h", alias, 12, sn)
        alias[rc.class_offset] = 2
        rc.aliases.append(alias)
        rv_name = "JS_FrameJSONReviverValueControl"
        rv_at = len(rc.strings)
        rc.strings += rv_name.encode() + b"\0"
        rv_alias = bytearray(rc.stride)
        struct.pack_into("<III", rv_alias, 0, 0, rv_at, len(before) + 1)
        struct.pack_into("<h", rv_alias, 12, sn)
        rv_alias[rc.class_offset] = 2
        rc.aliases.append(rv_alias)
        source_name = "JS_FrameJSONReviverSourceControl"
        source_at = len(rc.strings)
        rc.strings += source_name.encode() + b"\0"
        source_alias = bytearray(rc.stride)
        struct.pack_into("<III", source_alias, 0, 0, source_at, len(before) + 2)
        struct.pack_into("<h", source_alias, 12, sn)
        source_alias[rc.class_offset] = 2
        rc.aliases.append(source_alias)
        for index, s in rc.all_symbols.items():
            pos = rc.table + index * rc.stride
            if (
                s["section"] == sn
                and s["storage"] == 3
                and s["type"] == 0
                and raw[pos + rc.class_offset + 1]
            ):
                assert raw[pos + rc.class_offset + 1] == 1
                struct.pack_into("<I", rc.data, pos + rc.stride, len(before) + 3)
        # Keep the payload before the symbol/string tables. Later typed COFF
        # passes extend the string table while preserving preceding payload
        # pointers; an EOF payload would require every such pass to relocate it.
        result = bytearray(rc.finish())
        old_end = rc.string_offset + struct.unpack_from("<I", raw, rc.string_offset)[0]
        tail_shift = len(result) - len(raw)
        payload_at = rc.table
        payload = before + b"\0\0\0"
        for oldrec in rc.section_records:
            for field in (20, 24, 28):
                at = oldrec["pos"] + field
                value = struct.unpack_from("<I", raw, at)[0]
                if not value:
                    continue
                if value >= old_end:
                    value += tail_shift
                if value >= payload_at:
                    value += len(payload)
                struct.pack_into("<I", result, at, value)
        result[payload_at:payload_at] = payload
        struct.pack_into("<I", result, rc.table_offset, rc.table + len(payload))
        struct.pack_into("<II", result, rec["pos"] + 16, len(before) + 3, payload_at)
        check = C(result)
        assert check.data[payload_at : payload_at + len(before)] == before
        assert check.all_symbols[rc.symbol_count]["name"] == name
        assert check.all_symbols[rc.symbol_count + 1]["name"] == rv_name
        assert check.all_symbols[rc.symbol_count + 2]["name"] == source_name
        assert all(check.all_symbols[i] == s for i, s in rc.all_symbols.items())
        for i, (old, new) in enumerate(zip(rc.sections, check.sections), 1):
            if i != sn:
                assert old == new, ("Old register contribution changed", i)
        backup = register.with_name(register.name + ".before-json-control")
        proof = register.with_name(register.name + ".json-control.json")
        assert not backup.exists() and not proof.exists()
        backup.write_bytes(raw)
        register.write_bytes(result)
        os.utime(register, ns=(stamp_register.st_atime_ns, stamp_register.st_mtime_ns))
        proof.write_text(
            json.dumps(
                dict(
                    status="passed",
                    before_sha256=sha(backup),
                    after_sha256=sha(register),
                    section=sn,
                    old_size=len(before),
                    new_size=len(before) + 3,
                    control_offset=len(before),
                    reviver_control_offset=len(before) + 1,
                    contract="Two appended zero-initialized bytes for JSON mode and reviver control; all parent offsets/prefix and complete old register sections/symbols/relocations and old RW prefix preserved.",
                ),
                indent=2,
            )
            + "\n"
        )
        merger = module("json_merge", "extension-merge.py")
        destination = _frame_generated_file(build, "quickjs-interpreter-null-proto.obj")
        stamp = destination.stat()
        # Explicit Win64 leaf byte atomics. Preserve native unwind entries and
        # every original section; no CFG/volatile metadata suppression flags.
        asm = _frame_generated_file(build, "quickjs-interpreter-json-atomic.asm")
        asm_obj = _frame_generated_file(build, "quickjs-interpreter-json-atomic.obj")
        asm.write_text(
            """PUBLIC JS_FrameJSONLoad8, JS_FrameJSONCAS8
.code
JS_FrameJSONLoad8 PROC FRAME
    .endprolog
    movzx eax, BYTE PTR [rcx]
    ret
JS_FrameJSONLoad8 ENDP
JS_FrameJSONCAS8 PROC FRAME
    .endprolog
    movzx eax, BYTE PTR [rdx]
    lock cmpxchg BYTE PTR [rcx], r8b
    jne json_cas_failed
    mov al, 1
    ret
json_cas_failed:
    mov BYTE PTR [rdx], al
    xor eax, eax
    ret
JS_FrameJSONCAS8 ENDP
END
""",
            encoding="ascii",
        )
        import subprocess

        compiler = Path(M.win_argv(command)[0]).with_name("ml64.exe")
        assert compiler.is_file()
        argv = [str(compiler), "/nologo", "/c", "/Fo" + str(asm_obj), str(asm)]
        p = subprocess.run(argv, capture_output=True)
        asm.with_suffix(".log").write_bytes(p.stdout + p.stderr)
        assert p.returncode == 0, (p.stdout + p.stderr).decode(errors="replace")
        # The common compiler pass already maps xdata into the same late island.
        # Do that explicitly for the MASM leaf entries before the checked merge.
        ac = C(asm_obj.read_bytes())
        for number, rec in enumerate(ac.section_records, 1):
            name = ac.sections[number - 1]["name"]
            if name.startswith("/"):
                offset = int(name[1:])
                name = ac.strings[offset : ac.strings.index(0, offset)].decode()
            renamed = (
                late
                if name.startswith((".text", ".xdata"))
                else ".pdata$zzzzzznullfast"
                if name.startswith(".pdata")
                else None
            )
            if not renamed:
                continue
            at = len(ac.strings)
            ac.strings += renamed.encode() + b"\0"
            ac.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
            if renamed == late:
                struct.pack_into(
                    "<I", ac.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040
                )
            for index, symbol in ac.all_symbols.items():
                if (
                    symbol["section"] == number
                    and symbol["storage"] == 3
                    and symbol["type"] == 0
                    and symbol["name"] == name
                ):
                    struct.pack_into("<II", ac.data, ac.table + index * ac.stride, 0, at)
        asm_obj.write_bytes(ac.finish())
        asm.with_suffix(".json").write_text(
            json.dumps(
                dict(
                    status="passed",
                    command=argv,
                    compiler_sha256=sha(compiler),
                    source_sha256=sha(asm),
                    object_sha256=sha(asm_obj),
                    contract="Win64 leaf byte read / locked CAS, volatile registers only, zero-size prologs with explicit native unwind entries.",
                ),
                indent=2,
            )
            + "\n"
        )
        merger.append(
            destination,
            asm_obj,
            "JS_FrameJSONLoad8",
            "json_atomic",
            keep_all=True,
            code_input=late,
            code_output=late,
            pdata_output=".pdata$zzzzzzjsonAtomic",
        )
        # Qualified MS parser/writer keep the parent source view; callback TU is not merged.
        merger.append(
            destination,
            out,
            "JS_FrameJSONParse",
            "json_parser",
            keep_all=True,
            code_input=".qjs$zzjsonA",
            code_output=".qjs$zzjsonA",
            pdata_output=".pdata$zzzzzzjsonA",
            metadata_inputs=(".voltbl",),
        )
        merger.append(
            destination,
            writer_out,
            "JS_FrameJSONStringify",
            "json_writer",
            keep_all=True,
            code_input=".qjs$zzjsonB",
            code_output=".qjs$zzjsonB",
            pdata_output=".pdata$zzzzzzjsonB",
            metadata_inputs=(".voltbl",),
        )
        # Separate value-reviver RX/RW contributions; no callback traversal or core rewrite.
        module("json_reviver_value_msvc", "json-callback.py").compile_reviver_value(
            source, build, callback_out, out, msvc=True, destination=destination
        )
        module("json_source_record_msvc", "json-callback.py").compile_source_records(
            source, build, destination, msvc=True
        )
        os.utime(destination, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapt", action="store_true")
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--object", type=Path)
    ap.add_argument("--header", type=Path)
    ap.add_argument("--build", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    if a.adapt:
        adapt(a.source, a.object, a.header)
    elif a.compile:
        compile_extra(a.source, a.build, a.out)
    else:
        ap.error("operation required")
