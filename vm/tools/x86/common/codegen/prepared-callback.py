"""Scoped callback wrapper routing and private Win64 prepared entry. MIT."""

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
from native_abi import current as current_abi, source_abi
from abi_layout import constants as abi_constants
import argparse, hashlib, importlib.util, json, re, struct
from pathlib import Path

HERE = Path(__file__).resolve().parent


def module(name, file):
    sp = importlib.util.spec_from_file_location(name, _frame_tool_path(file))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def prepare_source(source):
    """Extract complete array loops before any platform object routing."""
    M = module("callback_coff", "object-adapter.py")
    source_text = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    functions = {m[2]: m for m in M.FUNCTION.finditer(source_text)}
    virtual = source_text
    loop_proofs = []
    loops = [
        ("js_array_every", "frame_callback_array_every"),
        ("js_array_reduce", "frame_callback_array_reduce"),
    ]
    loops += [
        ("js_array_every", "frame_callback_write_array_every"),
        ("js_array_reduce", "frame_callback_write_array_reduce"),
    ]
    for original, local in loops:
        body = functions[original][0]
        assert len(re.findall(r"\bJS_Call\s*\(", body)) == 1, original
        prepared = re.sub(
            r"\b(" + original + r"|JS_Call)\b",
            lambda m: local if m[0] == original else "frame_callback_prepared_call",
            body,
        )
        signature = next(m for m in M.FUNCTION.finditer(prepared) if m[2] == local)
        prepared = prepared[: signature.end(3)] + ",void *scope" + prepared[signature.end(3) :]
        if "_write_" in local:
            prepared = prepared.replace(
                "frame_callback_prepared_call", "frame_callback_write_prepared_call"
            )
        call_name = (
            "frame_callback_write_prepared_call"
            if "_write_" in local
            else "frame_callback_prepared_call"
        )
        prepared, count = re.subn(
            r"\b" + call_name + r"\s*\(([^;]*?)\)",
            lambda m: call_name + "(" + m[1] + ",scope)",
            prepared,
        )
        assert count == 1, original
        virtual += "\n" + prepared + "\n"
        loop_proofs.append(
            dict(
                original=original,
                prepared=local,
                original_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
                prepared_body_sha256=hashlib.sha256(prepared.encode()).hexdigest(),
                policy="Exact parser-extracted body, function/private scope parameter and one JS_Call target/scope argument substituted; no maintained source fork.",
            )
        )
    return virtual, loop_proofs


def adapt(source, object_path, header):
    M = module("callback_coff", "object-adapter.py")
    raw = object_path.read_bytes()
    old = M.Coff(raw)
    c = M.Coff(raw)
    backend = _frame_source_text(source, "quickjs-interpreter-prepared-callback.h")
    ms = any(s["name"] == ".drectve" for s in c.sections)
    virtual, loop_proofs = prepare_source(source)
    # Original array loops inline this static fast-property helper. Keep its
    # exact current-source body in this TU instead of adding a C ABI call per item.
    M.HOT_LOCAL_HELPERS |= {"JS_TryGetPropertyInt64"}
    text, exports, copies = M.generate(virtual, c, backend)
    assert {"frame_callback_array_every", "frame_callback_array_reduce"} <= set(copies)
    assert not {"js_array_every", "js_array_reduce"} & set(copies)
    proto = '#include "quickjs.h"\n#ifdef _MSC_VER\nstatic __forceinline JSValue frame_callback_prepared_call(JSContext *,JSValueConst,JSValueConst,int,JSValueConst *,void *);\n#else\nstatic inline __attribute__((always_inline)) JSValue frame_callback_prepared_call(JSContext *,JSValueConst,JSValueConst,int,JSValueConst *,void *);\n#endif\n'
    proto += proto.replace("frame_callback_prepared_call", "frame_callback_write_prepared_call")
    text = proto + text
    names = {s["name"] for s in c.all_symbols.values()}
    added = []
    for n in exports:
        if "qjs_frame_core_" + n not in names:
            c.expose(n)
            added.append(n)
    routes = []
    targets = [
        ("js_array_every", "JS_FrameCallbackWriteArrayEvery"),
        ("js_array_reduce", "JS_FrameCallbackWriteArrayReduce"),
    ]
    for original, target in targets:
        fn = c.symbols[original]
        external = c.external(target)
        for si, rec in enumerate(c.section_records):
            sec = c.sections[si]
            if rec["flags"] & 0x20000000 or not sec["name"].startswith(".rdata"):
                continue
            for i in range(rec["count"]):
                q = rec["reloc"] + i * 10
                off, sym, kind = struct.unpack_from("<IIH", c.data, q)
                if sym not in c.all_symbols:
                    continue  # Previously routed new external symbol.
                symbol = c.all_symbols[sym]
                if kind != 1 or symbol["section"] != fn["section"]:
                    continue
                addend = struct.unpack_from("<Q", c.data, rec["raw"] + off)[0]
                if addend + symbol["value"] != fn["value"]:
                    continue
                struct.pack_into("<Q", c.data, rec["raw"] + off, 0)
                struct.pack_into("<I", c.data, q + 4, external)
                routes.append(
                    dict(
                        section=si + 1,
                        offset=off,
                        original=original,
                        target=target,
                        original_symbol=sym,
                        original_addend=addend,
                    )
                )
        assert any(r["original"] == original for r in routes), (original, routes)
    old_end = old.string_offset + struct.unpack_from("<I", raw, old.string_offset)[0]
    result = bytearray(c.finish())
    shift = len(result) - len(raw)
    for rec in old.section_records:
        for field in (20, 24, 28):
            q = rec["pos"] + field
            value = struct.unpack_from("<I", raw, q)[0]
            if value and value >= old_end:
                struct.pack_into("<I", result, q, value + shift)
    check = M.Coff(result)
    for si, (x, y) in enumerate(zip(old.section_records, check.section_records), 1):
        a = bytearray(raw[x["raw"] : x["raw"] + x["size"]] if x["raw"] else bytes(x["size"]))
        b = bytearray(result[y["raw"] : y["raw"] + y["size"]] if y["raw"] else bytes(y["size"]))
        for r in routes:
            if r["section"] == si:
                a[r["offset"] : r["offset"] + 8] = b[r["offset"] : r["offset"] + 8] = bytes(8)
        assert a == b and x["size"] == y["size"] and x["flags"] == y["flags"], si
        a = bytearray(raw[x["reloc"] : x["reloc"] + x["count"] * 10])
        b = bytearray(result[y["reloc"] : y["reloc"] + y["count"] * 10])
        for r in routes:
            if r["section"] != si:
                continue
            hits = [
                i
                for i in range(x["count"])
                if struct.unpack_from("<I", a, i * 10)[0] == r["offset"]
            ]
            assert len(hits) == 1
            i = hits[0]
            a[i * 10 + 4 : i * 10 + 8] = b[i * 10 + 4 : i * 10 + 8] = bytes(4)
        assert a == b, ("relocations", si)
    assert all(check.all_symbols[i] == s for i, s in old.all_symbols.items())
    backup = object_path.with_name(object_path.name + ".before-prepared-callback")
    assert not backup.exists()
    backup.write_bytes(raw)
    object_path.write_bytes(result)
    header.write_text(text, encoding="utf-8")
    header.with_suffix(".json").write_text(
        json.dumps(
            dict(
                status="passed",
                routes=routes,
                generated_loops=loop_proofs,
                added_aliases=added,
                copied_helpers=copies,
                before_sha256=sha(backup),
                after_sha256=sha(object_path),
                header_sha256=sha(header),
                source_sha256=sha(_frame_source_file(source, "quickjs.c")),
                runner_sha256=sha(__file__),
                policy="Only original array function-table ADDR64 pointers change. All original loop call relocations and core RX remain unchanged. An admitted activation executes a fresh parser-generated private loop with one direct prepared-call substitution; other activations retain original loops.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Callback scope adapter:", len(routes), "function-table pointers", flush=True)


def compile_extra(source, build, out):
    M = module("callback_compiler", "atod.py")
    original = M.win_argv
    M.win_argv = lambda command: [x for x in original(command) if not x.startswith("-g")] + (
        ["-g0"] if any("mingw" in x.lower() for x in original(command)[:1]) else []
    )

    def generate(source, path):
        path.write_text(
            '#include "quickjs-callback-private.h"\n'
            '#include "'
            + str(_frame_source_file(source, "quickjs-interpreter-prepared-callback.h")).replace(
                "\\", "/"
            )
            + '"\n',
            encoding="utf-8",
        )

    records = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    command = next(x["command"] for x in records if Path(x["file"]).name == "quickjs-interpreter.c")
    late = ".qjszzcf$c" if "/nologo" in command.lower() else ".qjscbck$C"
    if late == ".qjszzcf$c":
        from types import SimpleNamespace

        base = M.coff_module().Coff

        class CallbackCoff(base):
            def finish(self):
                for rec in self.section_records:
                    name = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode("ascii")
                    if name.startswith("/"):
                        at = int(name[1:])
                        name = self.strings[at : self.strings.find(0, at)].decode("ascii")
                    if name in (late, ".qjszzzz$c"):
                        flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                        struct.pack_into(
                            "<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040
                        )
                return super().finish()

        M.coff_module = lambda: SimpleNamespace(Coff=CallbackCoff)
    M.compile_extra(
        source,
        build,
        out,
        generator=generate,
        filename="quickjs-interpreter-prepared-callback.c",
        late_name=late,
    )
    c = module("callback_compiled_proof", "object-adapter.py").Coff(out.read_bytes())
    for sec, rec in zip(c.sections, c.section_records):
        if not rec["flags"] & 0x20000000:
            continue
        for i in range(rec["count"]):
            off, sym, kind = struct.unpack_from("<IIH", c.data, rec["reloc"] + i * 10)
            assert kind != 1, (
                "Absolute relocation in executable extension",
                off,
                c.all_symbols[sym],
            )
    assert not any(s["name"].startswith(".refptr.") for s in c.all_symbols.values())

    if late == ".qjszzcf$c":
        import os

        # These new ASM ranges are RX initialized storage too. All inherited
        # register-object payloads and section flags remain untouched here.
        register = _frame_generated_file(build, "quickjs-interpreter-register.obj")
        raw = register.read_bytes()
        RC = module("callback_register_class", "object-adapter.py").Coff
        rc = RC(raw)
        result = bytearray(raw)
        changed = []
        for sec, rec in zip(rc.sections, rc.section_records):
            name = sec["name"]
            if name.startswith("/"):
                at = int(name[1:])
                name = rc.strings[at : rc.strings.find(0, at)].decode("ascii")
            if name != ".qjszzcf$a":
                continue
            before = struct.unpack_from("<I", raw, rec["pos"] + 36)[0]
            assert before & 0xE0000000 in (0x60000000, 0x40000000)
            after = (before & ~0xE0) | 0x60000040
            struct.pack_into("<I", result, rec["pos"] + 36, after)
            changed.append(dict(section=name, offset=rec["pos"] + 36, before=before, after=after))
        assert len(changed) == 1
        allowed = {x["offset"] + i for x in changed for i in range(4)}
        assert all(i in allowed for i, (a, b) in enumerate(zip(raw, result)) if a != b)
        backup = register.with_name(register.name + ".before-callback-classification")
        receipt = register.with_name(register.name + ".callback-classification.json")
        assert not backup.exists() and not receipt.exists()
        stamp = register.stat()
        backup.write_bytes(raw)
        register.write_bytes(result)
        os.utime(register, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        receipt.write_text(
            json.dumps(
                dict(
                    status="passed",
                    object=str(register),
                    before_sha256=sha(backup),
                    after_sha256=sha(register),
                    changed=changed,
                    contract="Only new callback ASM section classification; no old headers/payloads/relocations/symbols change.",
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # No new MS archive member: append after the existing regexp merge into
        # the retained final member, with separate callback output contributions.
        merger = module("callback_member_merge", "extension-merge.py")
        destination = _frame_generated_file(build, "quickjs-interpreter-null-proto.obj")
        stamp = destination.stat()
        merger.append(
            destination,
            out,
            "JS_FrameCallbackScopeRun",
            "callback",
            keep_all=True,
            code_input=late,
            code_output=late,
            pdata_output=".pdata$zzzzzzcallback",
            metadata_inputs=(".voltbl",),
        )
        os.utime(destination, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        record = out.with_suffix(".compile.json")
        r = json.loads(record.read_text())
        r.update(
            generator_sha256=sha(Path(__file__)),
            ms_callback_merge=str(destination.with_name(destination.name + ".callback-merge.json")),
            register_classification=str(receipt),
            contract="Explicit capsule ABI; isolated callback RX/RW and no new MS archive member.",
        )
        record.write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")

    if late == ".qjszzcf$c":
        return  # MS keeps qualified f95u until linker debug inventory is isolated.
    writable = _frame_generated_file(build, "quickjs-interpreter-callback-write.obj")

    def generate_write(source, path):
        path.write_text(
            '#define QJS_CALLBACK_WRITABLE 1\n#include "quickjs-callback-private.h"\n#include "'
            + str(_frame_source_file(source, "quickjs-interpreter-prepared-callback.h")).replace(
                "\\", "/"
            )
            + '"\n',
            encoding="utf-8",
        )

    write_late = ".qjszzzz$c" if late == ".qjszzcf$c" else ".qjscbwr$C"
    M.compile_extra(
        source,
        build,
        writable,
        generator=generate_write,
        filename="quickjs-interpreter-callback-write.c",
        late_name=write_late,
    )
    if late == ".qjszzcf$c":
        # A compiler string/constant COMDAT must have only one definition per
        # archive member. Give this TU's private constants their own names;
        # payloads and relocation indexes remain untouched, with no old change.
        WC = module("callback_write_constants", "object-adapter.py").Coff
        raw = writable.read_bytes()
        wc = WC(raw)
        renamed = []
        for index, sym in wc.all_symbols.items():
            if sym["storage"] != 2 or sym["type"] != 0 or sym["section"] <= 0:
                continue
            if not sym["name"].startswith(("??_C@", "__xmm@", "__real@")):
                continue
            name = "qjs_callback_write_private_" + sym["name"]
            offset = len(wc.strings)
            wc.strings += name.encode("ascii") + b"\0"
            struct.pack_into("<II", wc.data, wc.table + index * 18, 0, offset)
            renamed.append(dict(old=sym["name"], new=name, symbol_index=index))
        writable.write_bytes(wc.finish())
        record = writable.with_suffix(".compile.json")
        r = json.loads(record.read_text())
        r.update(
            private_constants=renamed,
            before_private_constants_sha256=__import__("hashlib").sha256(raw).hexdigest(),
            after_private_constants_sha256=sha(writable),
        )
        for field in ("sha256", "object_sha256"):
            if field in r:
                r[field] = sha(writable)
        record.write_text(json.dumps(r, indent=2) + "\n")
    merger = module("callback_write_merge", "extension-merge.py")
    destination = (
        _frame_generated_file(build, "quickjs-interpreter-null-proto.obj")
        if late == ".qjszzcf$c"
        else out
    )
    stamp = destination.stat()
    merger.append(
        destination,
        writable,
        "JS_FrameCallbackWriteScopeRun",
        "callback-write",
        keep_all=True,
        code_input=write_late,
        code_output=write_late,
        pdata_output=".qjszzzz$r" if late == ".qjszzcf$c" else ".qjscwfn$C",
        metadata_inputs=(".voltbl",),
        base_owner="JS_FrameCallbackScopeRun",
        baseline_sections=(),
    )
    __import__("os").utime(destination, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))


def append(masm, gas, diagnostics, native_slice):
    # General/public calls keep the accepted f95j path. Only selected original
    # array loop relocations can enter the prepared selector.
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    state = 112
    data = 2560 if diagnostics else 288
    committed = 2304 if diagnostics else 64
    limit = 2312 if diagnostics else 72
    shared = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    owner = 2416 if diagnostics else 96
    checkpoint = 2300 if diagnostics else 164
    fallback = "JS_FrameDispatchInternal"
    select = "JS_FramePreparedCallbackSelect"
    body = "JS_FramePreparedCallbackTrampoline"
    guard = [
        "mov r11, QWORD PTR [rsp+72]",
        "test r11, r11",
        "jz " + fallback,
        "cmp QWORD PTR [r11], rdx",
        "jne " + fallback,
        "cmp QWORD PTR [r8+8], -1",
        "jne " + fallback,
        "mov rax, QWORD PTR [r8]",
        "cmp QWORD PTR [r11+8], rax",
        "jne " + fallback,
        "mov eax, DWORD PTR [rsp+64]",
        "test eax, 4294967293",
        "jnz " + fallback,
        "mov eax, DWORD PTR [r11+48]",
        "cmp DWORD PTR [rsp+48], eax",
        "jne " + fallback,
        "mov QWORD PTR [rsp+8], r11",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "cmp BYTE PTR [JS_FrameSharedCallBypassControl], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "jz " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 3}], 1",
        "jne " + fallback,
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r10d, 3",
        "cmp r10d, 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz " + fallback,
        "CALLBACK_TLS_HOST",
        "mov r11, QWORD PTR [rsp+8]",
        "mov r10, QWORD PTR [r10]",
        "cmp QWORD PTR [r11+40], r10",
        "jne " + fallback,
        "test r10, r10",
        "jz " + fallback,
        "cmp DWORD PTR [r10+16], 0",
        "jne " + fallback,
        "mov r10, QWORD PTR [r10+8]",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "cmp QWORD PTR [r10+56], rax",
        "jne " + fallback,
        "mov r10, QWORD PTR [r10+32]",
        "mov rax, QWORD PTR [r11+40]",
        "mov rax, QWORD PTR [rax+8]",
        f"cmp r10, QWORD PTR [rax+{committed}]",
        "jne " + fallback,
        "mov rax, QWORD PTR [r11+24]",
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}]",
        "and r10d, 7",
        "cmp r10d, 3",
        "jne " + fallback,
        "cmp QWORD PTR [r11+80], 0",
        "jne " + fallback,
        "cmp QWORD PTR [r11+96], 0",
        "jne " + fallback,
        f"cmp QWORD PTR [r11+{state}], 0",
        "jne " + fallback,
        "mov r10, rsp",
        "sub r10, 4344",
        "sub r10, QWORD PTR [r11+32]",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
        "jmp " + body,
    ]
    code = [
        "sub rsp, 56",
        "callback_scope_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov r11, QWORD PTR [rsp+64]",
        "mov QWORD PTR [rsp+40], r11",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        f"lea r8, [r11+{data}]",
        f"lea r10, [r11+{state}]",
        "movdqu xmm1, XMMWORD PTR [r9]",
        "movdqu XMMWORD PTR [r8+88], xmm1",
        "mov rax, QWORD PTR [rsp+112]",
        "mov QWORD PTR [r8+24], rax",
        "mov rax, QWORD PTR [r10+56]",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [r8], rax",
        "mov QWORD PTR [r8+48], 0",
        "mov QWORD PTR [r8+64], 0",
        "mov QWORD PTR [r8+72], 0",
        "mov BYTE PTR [r8+63], 0",
        "mov QWORD PTR [r8+104], 0",
        "mov DWORD PTR [r8+124], 0",
        "mov QWORD PTR [r8+40], 0",
        "mov WORD PTR [r8+56], 0",
        "mov rax, QWORD PTR [r11+24]",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp ecx, DWORD PTR [r11+48]",
        "jbe callback_scope_args_ready",
        # Native loop retains ownership of each actual value through return.
        # Admission excludes parameter writes, arguments/eval and captures.
        "mov rdx, QWORD PTR [rsp+112]",
        "lea r9, [r8+128]",
        "movdqu xmm1, XMMWORD PTR [rdx]",
        "movdqu XMMWORD PTR [r9], xmm1",
        f"movdqu xmm1, XMMWORD PTR [rdx+{abi_layout['sizes']['JSValue']}]",
        "movdqu XMMWORD PTR [r9+16], xmm1",
        "movdqu xmm1, XMMWORD PTR [rdx+32]",
        "movdqu XMMWORD PTR [r9+32], xmm1",
        "cmp DWORD PTR [r11+48], 3",
        "je callback_scope_args_copied",
        "movdqu xmm1, XMMWORD PTR [rdx+48]",
        "movdqu XMMWORD PTR [r9+48], xmm1",
        "callback_scope_args_copied:",
        "mov QWORD PTR [r8+24], r9",
        "callback_scope_args_ready:",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.var_count']}]",
        "mov r9, QWORD PTR [r8+32]",
        "test ecx, ecx",
        "jz callback_scope_vars_ready",
        "callback_scope_init_vars:",
        "mov QWORD PTR [r9], 0",
        "mov QWORD PTR [r9+8], 3",
        "add r9, 16",
        "dec ecx",
        "jnz callback_scope_init_vars",
        "callback_scope_vars_ready:",
        "mov QWORD PTR [r10], r8",
        "lea rdx, [r11+80]",
        "mov QWORD PTR [r10+8], rdx",
        "mov QWORD PTR [r10+24], r9",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [r10+16], rax",
        "mov QWORD PTR [r10+48], 3",
        f"mov BYTE PTR [r10+{exception}], 0",
        f"mov QWORD PTR [r10+{owner}], 0",
        f"mov DWORD PTR [r10+{checkpoint}], 0",
        "mov r9, QWORD PTR [r11+32]",
        "mov DWORD PTR [r8+120], r9d",
        "mov QWORD PTR [rdx+16], r9",
        "mov QWORD PTR [r10+32], r9",
        f"mov QWORD PTR [r10+{committed}], r9",
    ]
    if diagnostics:
        code += ["mov DWORD PTR [r10+128], 1"]
    code += [
        "mov rdx, QWORD PTR [r10+56]",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r9",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}]",
        "test rax, rax",
        "jz callback_scope_unlimited",
        "add rax, r9",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], rax",
        "callback_scope_unlimited:",
        f"mov QWORD PTR [r10+{shared}], rax",
        "test rax, rax",
        "jz callback_scope_limit_ready",
        "sub rax, r9",
        "callback_scope_limit_ready:",
        f"mov QWORD PTR [r10+{limit}], rax",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.current_stack_frame']}], r8",
        "CALLBACK_TLS_PUBLISH",
        "mov QWORD PTR [rsp+48], rdx",
        "mov rax, QWORD PTR [rdx]",
        "mov QWORD PTR [r11+56], rax",
        "lea rax, [r11+56]",
        "mov QWORD PTR [rdx], rax",
        "mov rcx, r10",
        "callback_scope_enter:",
        "call JS_FrameInterp",
        "mov r11, QWORD PTR [rsp+40]",
        f"lea r10, [r11+{state}]",
        "mov rdx, QWORD PTR [r10+56]",
        "mov r9, QWORD PTR [r10+32]",
        f"sub r9, QWORD PTR [r10+{committed}]",
        "jz callback_scope_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r9",
        f"cmp QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je callback_scope_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], r9",
        "callback_scope_charged:",
        "mov rax, QWORD PTR [rsp+48]",
        "mov rdx, QWORD PTR [r11+56]",
        "mov QWORD PTR [rax], rdx",
        "mov rax, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [r10+40]",
        "movdqu XMMWORD PTR [rax], xmm0",
        "callback_scope_epilogue:",
        "add rsp, 56",
        "ret",
    ]

    def tls(which, symbol, target):
        if which == "masm":
            return [
                "mov " + target + ", QWORD PTR gs:[88]",
                "mov eax, DWORD PTR [_tls_index]",
                "mov " + target + ", QWORD PTR [" + target + "+rax*8]",
                "mov eax, SECTIONREL " + symbol,
                "add " + target + ", rax",
            ]
        symbol = "JS_FrameSharedTop" if symbol == "js_frame_shared_top" else symbol
        return [
            "mov " + target + ", QWORD PTR gs:[88]",
            "mov eax, DWORD PTR [rip+_tls_index]",
            "mov " + target + ", QWORD PTR [" + target + "+rax*8]",
            "lea rax, [rip+" + symbol + "]",
            "lea " + ("r11" if target == "r10" else "r8") + ", [rip+_tls_start]",
            "sub rax, " + ("r11" if target == "r10" else "r8"),
            "add " + target + ", rax",
        ]

    assert masm.pop() == "END"
    masm[3:3] = ["EXTERN JS_FrameDispatchInternal:PROC"]
    mssection = ".qjszzcf$a"
    masm += [mssection + " SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjscbck$A,"xr"', ".p2align 4"]
    for name, stream in ((select, guard), (body, code)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in stream:
            if line.startswith("CALLBACK_TLS_"):
                symbol = (
                    "JS_FrameCallbackScopeTop"
                    if line == "CALLBACK_TLS_SCOPE"
                    else "js_frame_shared_top"
                )
                target = "rdx" if line == "CALLBACK_TLS_PUBLISH" else "r10"
                masm += tls("masm", symbol, target)
                gas += tls("gas", symbol, target)
            elif line.endswith(":"):
                masm += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                gas += [".globl " + line[:-1], line]
            else:
                m = line
                for dest in (fallback, body):
                    if (
                        m.split(" ", 1)[0] in ("jmp", "jz", "jne", "jb", "jle")
                        and m.split(" ", 1)[1] == dest
                    ):
                        m = m.split(" ", 1)[0] + " NEAR PTR " + dest
                masm += [m]
                gas += [
                    line.replace(
                        "[JS_FrameSharedCallBypassControl]", "[rip+JS_FrameSharedCallBypassControl]"
                    )
                ]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        select + "_unwind LABEL BYTE",
        "DB 1,0,0,0",
        body + "_unwind LABEL BYTE",
        "DB 1,callback_scope_alloc-" + body + ",1,0",
        "DB callback_scope_alloc-" + body + ",062h",
        "DB 0,0",
        mssection + " ENDS",
        ".pdata$zzqjscallback SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        select + "_unwind:",
        ".byte 1,0,0,0",
        body + "_unwind:",
        ".byte 1,callback_scope_alloc-" + body + ",1,0",
        ".byte callback_scope_alloc-" + body + ",0x62",
        ".short 0",
        '.section .pdata$zzqjscallback,"dr"',
        ".p2align 2",
    ]
    for name in (select, body):
        masm += ["DD IMAGEREL " + name + ",IMAGEREL " + name + "_end,IMAGEREL " + name + "_unwind"]
        gas += [".rva " + name + "," + name + "_end," + name + "_unwind"]
    masm += [
        ".pdata$zzqjscallback ENDS",
        ".qjszzcm SEGMENT ALIGN(1) 'DATA'",
        "PUBLIC JS_FrameCallbackControl, JS_FrameCallbackArityControl",
        "JS_FrameCallbackControl DB 0",
        "JS_FrameCallbackArityControl DB 0",
        ".qjszzcm ENDS",
        "END",
    ]
    gas += [
        '.section .qjscbmt,"dw"',
        ".globl JS_FrameCallbackControl",
        "JS_FrameCallbackControl:",
        ".byte 0",
        ".globl JS_FrameCallbackArityControl",
        "JS_FrameCallbackArityControl:",
        ".byte 0",
    ]
    append_write(masm, gas, diagnostics, native_slice)


def append_write(masm, gas, diagnostics, native_slice):
    # General/public calls keep the accepted f95j path. Only selected original
    # array loop relocations can enter the prepared selector.
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    state = 112
    data = 2560 if diagnostics else 288
    committed = 2304 if diagnostics else 64
    limit = 2312 if diagnostics else 72
    shared = 2320 if diagnostics else 80
    exception = 2296 if diagnostics else 160
    owner = 2416 if diagnostics else 96
    checkpoint = 2300 if diagnostics else 164
    fallback = "JS_FrameDispatchInternal"
    select = "JS_FramePreparedCallbackWriteSelect"
    body = "JS_FramePreparedCallbackTrampoline"
    write_body = "JS_FramePreparedCallbackWriteTrampoline"
    guard = [
        "mov r11, QWORD PTR [rsp+72]",
        "test r11, r11",
        "jz " + fallback,
        "cmp QWORD PTR [r11], rdx",
        "jne " + fallback,
        "cmp QWORD PTR [r8+8], -1",
        "jne " + fallback,
        "mov rax, QWORD PTR [r8]",
        "cmp QWORD PTR [r11+8], rax",
        "jne " + fallback,
        "mov eax, DWORD PTR [rsp+64]",
        "test eax, 4294967293",
        "jnz " + fallback,
        "mov eax, DWORD PTR [r11+48]",
        "cmp DWORD PTR [rsp+48], eax",
        "jne " + fallback,
        "mov QWORD PTR [rsp+8], r11",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "cmp BYTE PTR [JS_FrameSharedCallBypassControl], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}], 4",
        "jz " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.module_normalize_has_attr'] + 3}], 1",
        "jne " + fallback,
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 5}]",
        "and r10d, 3",
        "cmp r10d, 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 1}], 1",
        "jne " + fallback,
        f"cmp BYTE PTR [rax+{abi_fields['JSRuntime.current_stack_frame'] - 3}], 1",
        "jne " + fallback,
        f"test BYTE PTR [rax+{abi_bits['JSRuntime.dump_flags'][0][0]}], 128",
        "jnz " + fallback,
        "CALLBACK_TLS_HOST",
        "mov r11, QWORD PTR [rsp+8]",
        "mov r10, QWORD PTR [r10]",
        "cmp QWORD PTR [r11+40], r10",
        "jne " + fallback,
        "test r10, r10",
        "jz " + fallback,
        "cmp DWORD PTR [r10+16], 0",
        "jne " + fallback,
        "mov r10, QWORD PTR [r10+8]",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        "cmp QWORD PTR [r10+56], rax",
        "jne " + fallback,
        "mov r10, QWORD PTR [r10+32]",
        "mov rax, QWORD PTR [r11+40]",
        "mov rax, QWORD PTR [rax+8]",
        f"cmp r10, QWORD PTR [rax+{committed}]",
        "jne " + fallback,
        "mov rax, QWORD PTR [r11+24]",
        f"movzx r10d, BYTE PTR [rax+{abi_fields['JSFunctionBytecode.byte_code_buf'] - 1}]",
        "and r10d, 7",
        "cmp r10d, 1",
        "jne " + fallback,
        "cmp DWORD PTR [r11+52], 1",
        "jne " + fallback,
        "cmp QWORD PTR [r11+80], 0",
        "jne " + fallback,
        "cmp QWORD PTR [r11+96], 0",
        "jne " + fallback,
        f"cmp QWORD PTR [r11+{state}], 0",
        "jne " + fallback,
        "mov r10, rsp",
        "sub r10, 4344",
        "sub r10, QWORD PTR [r11+32]",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSContext.rt']}]",
        f"cmp r10, QWORD PTR [rax+{abi_fields['JSRuntime.stack_limit']}]",
        "jb " + fallback,
        f"cmp DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}], 1",
        "jle " + fallback,
        "jmp " + write_body,
    ]
    code = [
        "sub rsp, 56",
        "callback_scope_alloc:",
        "mov QWORD PTR [rsp+32], rcx",
        "mov r11, QWORD PTR [rsp+64]",
        "mov QWORD PTR [rsp+40], r11",
        f"dec DWORD PTR [rdx+{abi_fields['JSContext.interrupt_counter']}]",
        f"lea r8, [r11+{data}]",
        f"lea r10, [r11+{state}]",
        "movdqu xmm1, XMMWORD PTR [r9]",
        "movdqu XMMWORD PTR [r8+88], xmm1",
        "mov rax, QWORD PTR [rsp+112]",
        "mov QWORD PTR [r8+24], rax",
        "mov rax, QWORD PTR [r10+56]",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSRuntime.current_stack_frame']}]",
        "mov QWORD PTR [r8], rax",
        "mov QWORD PTR [r8+48], 0",
        "mov QWORD PTR [r8+64], 0",
        "mov QWORD PTR [r8+72], 0",
        "mov BYTE PTR [r8+63], 0",
        "mov QWORD PTR [r8+104], 0",
        "mov DWORD PTR [r8+124], 0",
        "mov QWORD PTR [r8+40], 0",
        "mov WORD PTR [r8+56], 0",
        "mov rax, QWORD PTR [r11+24]",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "cmp ecx, DWORD PTR [r11+48]",
        "jbe callback_scope_args_ready",
        # Native loop retains ownership of each actual value through return.
        # Admission excludes parameter writes, arguments/eval and captures.
        "mov rdx, QWORD PTR [rsp+112]",
        "lea r9, [r8+128]",
        "movdqu xmm1, XMMWORD PTR [rdx]",
        "movdqu XMMWORD PTR [r9], xmm1",
        f"movdqu xmm1, XMMWORD PTR [rdx+{abi_layout['sizes']['JSValue']}]",
        "movdqu XMMWORD PTR [r9+16], xmm1",
        "movdqu xmm1, XMMWORD PTR [rdx+32]",
        "movdqu XMMWORD PTR [r9+32], xmm1",
        "cmp DWORD PTR [r11+48], 3",
        "je callback_scope_args_copied",
        "movdqu xmm1, XMMWORD PTR [rdx+48]",
        "movdqu XMMWORD PTR [r9+48], xmm1",
        "callback_scope_args_copied:",
        "mov QWORD PTR [r8+24], r9",
        "callback_scope_args_ready:",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.var_count']}]",
        "mov r9, QWORD PTR [r8+32]",
        "test ecx, ecx",
        "jz callback_scope_vars_ready",
        "callback_scope_init_vars:",
        "mov QWORD PTR [r9], 0",
        "mov QWORD PTR [r9+8], 3",
        "add r9, 16",
        "dec ecx",
        "jnz callback_scope_init_vars",
        "callback_scope_vars_ready:",
        "mov QWORD PTR [r10], r8",
        "lea rdx, [r11+80]",
        "mov QWORD PTR [r10+8], rdx",
        "mov QWORD PTR [r10+24], r9",
        f"mov rax, QWORD PTR [rax+{abi_fields['JSFunctionBytecode.byte_code_buf']}]",
        "mov QWORD PTR [r10+16], rax",
        "mov QWORD PTR [r10+48], 3",
        f"mov BYTE PTR [r10+{exception}], 0",
        f"mov QWORD PTR [r10+{owner}], 0",
        f"mov DWORD PTR [r10+{checkpoint}], 0",
        "mov r9, QWORD PTR [r11+32]",
        "mov DWORD PTR [r8+120], r9d",
        "mov QWORD PTR [rdx+16], r9",
        "mov QWORD PTR [r10+32], r9",
        f"mov QWORD PTR [r10+{committed}], r9",
    ]
    if diagnostics:
        code += ["mov DWORD PTR [r10+128], 1"]
    code += [
        "mov rdx, QWORD PTR [r10+56]",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r9",
        f"mov rax, QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}]",
        "test rax, rax",
        "jz callback_scope_unlimited",
        "add rax, r9",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], rax",
        "callback_scope_unlimited:",
        f"mov QWORD PTR [r10+{shared}], rax",
        "test rax, rax",
        "jz callback_scope_limit_ready",
        "sub rax, r9",
        "callback_scope_limit_ready:",
        f"mov QWORD PTR [r10+{limit}], rax",
        f"mov QWORD PTR [rdx+{abi_fields['JSRuntime.current_stack_frame']}], r8",
        "CALLBACK_TLS_PUBLISH",
        "mov QWORD PTR [rsp+48], rdx",
        "mov rax, QWORD PTR [rdx]",
        "mov QWORD PTR [r11+56], rax",
        "lea rax, [r11+56]",
        "mov QWORD PTR [rdx], rax",
        "mov rcx, r10",
        "callback_scope_enter:",
        "call JS_FrameInterp",
        "mov r11, QWORD PTR [rsp+40]",
        f"lea r10, [r11+{state}]",
        "mov rdx, QWORD PTR [r10+56]",
        "mov r9, QWORD PTR [r10+32]",
        f"sub r9, QWORD PTR [r10+{committed}]",
        "jz callback_scope_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_top']}], r9",
        f"cmp QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], 0",
        "je callback_scope_charged",
        f"add QWORD PTR [rdx+{abi_fields['JSRuntime.stack_limit']}], r9",
        "callback_scope_charged:",
        "mov rax, QWORD PTR [rsp+48]",
        "mov rdx, QWORD PTR [r11+56]",
        "mov QWORD PTR [rax], rdx",
        "mov rax, QWORD PTR [rsp+32]",
        "movdqu xmm0, XMMWORD PTR [r10+40]",
        "movdqu XMMWORD PTR [rax], xmm0",
        "callback_scope_epilogue:",
        "add rsp, 56",
        "ret",
    ]
    # Preserve the accepted readonly body byte-for-byte. The writable entry
    # owns all formal slots; the existing Interp return/unwind releases them.
    write_code = [x.replace("callback_scope_", "callback_write_") for x in code]
    first = write_code.index("cmp ecx, DWORD PTR [r11+48]")
    last = write_code.index("callback_write_args_ready:") + 1
    write_code[first:last] = [
        "mov WORD PTR [r8+124], cx",
        "lea r9, [r8+128]",
        "mov QWORD PTR [r8+24], r9",
        "mov rdx, QWORD PTR [rsp+112]",
        "cmp ecx, DWORD PTR [r11+48]",
        "jbe callback_write_copy_count",
        "mov ecx, DWORD PTR [r11+48]",
        "callback_write_copy_count:",
        "test ecx, ecx",
        "jz callback_write_tail",
        "callback_write_copy:",
        "movdqu xmm1, XMMWORD PTR [rdx]",
        "movdqu XMMWORD PTR [r9], xmm1",
        "cmp DWORD PTR [rdx+8], 0",
        "jge callback_write_copy_next",
        "mov r10, QWORD PTR [rdx]",
        f"inc DWORD PTR [r10{abi_constants(abi_layout)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
        "callback_write_copy_next:",
        "add rdx, 16",
        "add r9, 16",
        "dec ecx",
        "jnz callback_write_copy",
        "callback_write_tail:",
        f"movzx ecx, WORD PTR [rax+{abi_fields['JSFunctionBytecode.arg_count']}]",
        "sub ecx, DWORD PTR [r11+48]",
        "jbe callback_write_args_ready",
        "callback_write_init_tail:",
        "mov QWORD PTR [r9], 0",
        "mov QWORD PTR [r9+8], 3",
        "add r9, 16",
        "dec ecx",
        "jnz callback_write_init_tail",
        "callback_write_args_ready:",
        f"lea r10, [r11+{state}]",
    ]

    def tls(which, symbol, target):
        if which == "masm":
            return [
                "mov " + target + ", QWORD PTR gs:[88]",
                "mov eax, DWORD PTR [_tls_index]",
                "mov " + target + ", QWORD PTR [" + target + "+rax*8]",
                "mov eax, SECTIONREL " + symbol,
                "add " + target + ", rax",
            ]
        symbol = "JS_FrameSharedTop" if symbol == "js_frame_shared_top" else symbol
        return [
            "mov " + target + ", QWORD PTR gs:[88]",
            "mov eax, DWORD PTR [rip+_tls_index]",
            "mov " + target + ", QWORD PTR [" + target + "+rax*8]",
            "lea rax, [rip+" + symbol + "]",
            "lea " + ("r11" if target == "r10" else "r8") + ", [rip+_tls_start]",
            "sub rax, " + ("r11" if target == "r10" else "r8"),
            "add " + target + ", rax",
        ]

    masm = []
    masm = []
    mssection = ".qjszzzz$a"
    masm += [mssection + " SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjscbwr$A,"xr"', ".p2align 4"]
    for name, stream in ((select, guard), (write_body, write_code)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in stream:
            if line.startswith("CALLBACK_TLS_"):
                symbol = (
                    "JS_FrameCallbackScopeTop"
                    if line == "CALLBACK_TLS_SCOPE"
                    else "js_frame_shared_top"
                )
                target = "rdx" if line == "CALLBACK_TLS_PUBLISH" else "r10"
                masm += tls("masm", symbol, target)
                gas += tls("gas", symbol, target)
            elif line.endswith(":"):
                masm += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                gas += [".globl " + line[:-1], line]
            else:
                m = line
                for dest in (fallback, body, write_body):
                    if (
                        m.split(" ", 1)[0] in ("jmp", "jz", "jne", "jb", "jle")
                        and m.split(" ", 1)[1] == dest
                    ):
                        m = m.split(" ", 1)[0] + " NEAR PTR " + dest
                masm += [m]
                gas += [
                    line.replace(
                        "[JS_FrameSharedCallBypassControl]", "[rip+JS_FrameSharedCallBypassControl]"
                    )
                ]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        select + "_unwind LABEL BYTE",
        "DB 1,0,0,0",
        write_body + "_unwind LABEL BYTE",
        "DB 1,callback_write_alloc-" + write_body + ",1,0",
        "DB callback_write_alloc-" + write_body + ",062h",
        "DB 0,0",
        mssection + " ENDS",
        ".qjszzzz$p SEGMENT ALIGN(4) READONLY 'DATA'",
        'DB "QJSCW_UNWIND_v1!"',
        "DD 0,1,0,0",
        ".qjszzzz$p ENDS",
        ".qjszzzz$q SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    gas += [
        ".p2align 2",
        select + "_unwind:",
        ".byte 1,0,0,0",
        write_body + "_unwind:",
        ".byte 1,callback_write_alloc-" + write_body + ",1,0",
        ".byte callback_write_alloc-" + write_body + ",0x62",
        ".short 0",
        '.section .qjscwfn$0,"dr"',
        ".p2align 2",
        '.ascii "QJSCW_UNWIND_v1!"',
        ".long 0,1,0,0",
        '.section .qjscwfn$A,"dr"',
        ".p2align 2",
    ]
    for name in (select, write_body):
        masm += ["DD IMAGEREL " + name + ",IMAGEREL " + name + "_end,IMAGEREL " + name + "_unwind"]
        gas += [".rva " + name + "," + name + "_end," + name + "_unwind"]
    masm += [
        ".qjszzzz$q ENDS",
        ".qjszzzz$s SEGMENT ALIGN(4) READONLY 'DATA'",
        'DB "QJSCW_END_v1!!!!"',
        "DD 0,1",
        ".qjszzzz$s ENDS",
        ".qjszzzv SEGMENT ALIGN(1) 'DATA'",
        "PUBLIC JS_FrameCallbackWriteControl",
        "JS_FrameCallbackWriteControl DB 0",
        ".qjszzzv ENDS",
        "END",
    ]
    gas += [
        '.section .qjscwfn$Z,"dr"',
        ".p2align 2",
        '.ascii "QJSCW_END_v1!!!!"',
        '.section .qjscbwm,"dw"',
        ".globl JS_FrameCallbackWriteControl",
        "JS_FrameCallbackWriteControl:",
        ".byte 0",
    ]
    return masm


@source_abi
def compile_msvc_write(source, build):
    """Whole new C/ASM/unwind contribution, no additional early MS sections."""
    import os, subprocess
    from types import SimpleNamespace

    M = module("ms_owned_callback_compiler", "atod.py")
    C = module("ms_owned_callback_coff", "object-adapter.py")
    merge = module("ms_owned_callback_merge", "extension-merge.py")

    class OwnedCoff(C.Coff):
        def finish(self):
            for index, sym in self.all_symbols.items():
                if sym["storage"] != 2 or sym["section"] <= 0:
                    continue
                if not sym["name"].startswith(("??_C@", "__xmm@", "__real@")):
                    continue
                name = (
                    "qjs_ms_owned_callback_" + hashlib.sha256(sym["name"].encode()).hexdigest()[:32]
                )
                at = len(self.strings)
                self.strings += name.encode() + b"\0"
                struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
            for number, rec in enumerate(self.section_records, 1):
                name = merge.section_name(self, number)
                if name == ".qjssrc$C" or name.startswith(".pdata"):
                    struct.pack_into(
                        "<I", self.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040
                    )
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=OwnedCoff)
    output = _frame_generated_file(build, "quickjs-interpreter-msvc-callback-write.obj")

    def generate(source, path):
        path.write_text(
            '#define QJS_CALLBACK_WRITABLE 1\n#include "quickjs-callback-private.h"\n'
            '#include "'
            + str(_frame_source_file(source, "quickjs-interpreter-prepared-callback.h")).replace(
                "\\", "/"
            )
            + '"\n',
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-msvc-callback-write.c",
        late_name=".qjssrc$C",
    )
    records = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    command = next(x["command"] for x in records if Path(x["file"]).name == "quickjs-interpreter.c")
    args = M.win_argv(command)
    compiler = Path(args[0])
    diagnostics = any("QJS_INTERP_FRAME_DIAGNOSTICS" in x for x in args)
    # Reuse the exact owned-argument stream, including quota, poll, TLS barrier
    # and original Interp return cleanup. Only contribution names differ.
    stream = append_write([], [], diagnostics, True)
    end = stream.index(".qjszzzz$a ENDS")
    stream = [x.replace(".qjszzzz$a", ".qjssrc$C") for x in stream[: end + 1]]
    lines = [
        "OPTION CASEMAP:NONE",
        "OPTION DOTNAME",
        "EXTERN JS_FrameDispatchInternal:PROC",
        "EXTERN JS_FrameInterp:PROC",
        "EXTERN JS_FramePreparedCallbackTrampoline:PROC",
        "EXTERN JS_FrameSharedCallBypassControl:BYTE",
        "EXTERN js_frame_shared_top:BYTE",
        "EXTERN _tls_index:DWORD",
        *stream,
        ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
    ]
    for name in ("JS_FramePreparedCallbackWriteSelect", "JS_FramePreparedCallbackWriteTrampoline"):
        lines += ["DD IMAGEREL " + name + ",IMAGEREL " + name + "_end,IMAGEREL " + name + "_unwind"]
    lines += [".pdata$zzzzzznullfast ENDS", "END"]
    asm = _frame_generated_file(build, "quickjs-interpreter-msvc-callback-write.asm")
    ao = _frame_generated_file(build, "quickjs-interpreter-msvc-callback-write-entry.obj")
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    cmd = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(ao), str(asm)]
    proc = subprocess.run(cmd, capture_output=True)
    asm.with_suffix(".log").write_bytes(proc.stdout + proc.stderr)
    assert proc.returncode == 0, (cmd, proc.stdout, proc.stderr)
    ac = C.Coff(ao.read_bytes())
    for rec in ac.section_records:
        if rec["size"] and rec["flags"] & 0xE0000000 in (0x40000000, 0x60000000):
            struct.pack_into("<I", ac.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    normalized_rel32 = []
    for number, rec in enumerate(ac.section_records, 1):
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, sym, kind = struct.unpack_from("<IIH", ac.data, at)
            if not 5 <= kind <= 9:
                continue
            assert rec["flags"] & 0x20000000 and off + 4 <= rec["size"]
            value = struct.unpack_from("<i", ac.data, rec["raw"] + off)[0]
            struct.pack_into("<i", ac.data, rec["raw"] + off, value - (kind - 4))
            struct.pack_into("<H", ac.data, at + 8, 4)
            normalized_rel32.append(
                dict(
                    section=number,
                    offset=off,
                    symbol=ac.all_symbols[sym]["name"],
                    before_kind=kind,
                    after_kind=4,
                    before_addend=value,
                    after_addend=value - (kind - 4),
                )
            )
    ao.write_bytes(ac.finish())
    asm.with_suffix(".rel32.json").write_text(
        json.dumps(
            dict(
                status="passed",
                fields=normalized_rel32,
                policy="REL32_n -> REL32 with addend minus n; identical linked "
                "target relative to the end of a 4-byte displacement. All other bytes/fields retained.",
            ),
            indent=2,
        )
        + "\n"
    )
    merge.append(
        output,
        ao,
        "JS_FramePreparedCallbackWriteSelect",
        "ms-owned-callback-entry",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        base_owner="JS_FrameCallbackWriteScopeRun",
        baseline_sections=(),
    )
    (_frame_generated_file(build, "quickjs-msvc-owned-callback-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                diagnostics=diagnostics,
                assembly_sha256=sha(asm),
                entry_object_sha256=sha(ao),
                object_sha256=sha(output),
                core_source_sha256=sha(_frame_source_file(source, "quickjs.c")),
                policy="Existing owned-formal C/ASM mechanism, whole late contribution. No new early "
                "output subsection, TLS slot, frame layout, allocator or readonly code change. "
                "Per-call formal prefix duplicated, undefined tail reset, original owned return "
                "cleanup; actual callback argc and synchronous native activation retained.",
            ),
            indent=2,
        )
        + "\n"
    )
    return output


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--adapt", action="store_true")
    ap.add_argument("--compile", action="store_true")
    for name in ("object", "header", "build", "out"):
        ap.add_argument("--" + name, type=Path)
    a = ap.parse_args()
    assert a.adapt != a.compile
    if a.adapt:
        adapt(a.source, a.object, a.header)
    else:
        compile_extra(a.source, a.build, a.out)
