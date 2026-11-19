"""Native .call admission/primitive leaves; the retained H C unit is unchanged."""

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
from native_build import source_digest, find_objdump
from abi_layout import load as load_layout
from native_abi import source_abi
from pathlib import Path
import hashlib, importlib.util, json, re, struct, subprocess, time

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(source, name):
    sp = importlib.util.spec_from_file_location(
        "forward_native_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def lines(source, diagnostics, layout_override=None):
    fields = (layout_override if layout_override is not None else load_layout(source))["offsets"]
    forward = fields["JSFunctionBytecode.pc2line_len"] + 7
    kind = fields["JSFunctionBytecode.byte_code_buf"] - 1
    ids = module(source, "leaf-entry").checked_opcodes(source)
    old = "JS_FrameVarargsForwardTry"
    # Ordinary one-argument Win64 leaf ABI: no native RSP/nonvolatile write.
    # Incoming home space at rsp8/rsp16 is private scratch. The VM's saved
    # fallback/argc at caller rsp32/rsp40 remain outside that home space.
    g = [
        "lea r9, [rip+JS_FrameCallForwardNativeControl]",
        "cmp BYTE PTR [r9], 1",
        "jne native_probe_control",
        "mov r9, QWORD PTR [rcx]",
        "mov r9, QWORD PTR [r9+80]",
        f"movzx eax, BYTE PTR [r9+{forward}]",
        "cmp eax, 1",
        "je native_probe_warm",
        "cmp eax, 5",
        "jne " + old,
        "native_probe_warm:",
        "mov r9, QWORD PTR [rcx+16]",
        "movzx eax, BYTE PTR [r9]",
        f"cmp eax, {ids['call_method']}",
        "je native_probe_method",
        f"cmp eax, {ids['tail_call_method']}",
        "jne " + old,
        "native_probe_method:",
        "movzx r11d, WORD PTR [r9+1]",
        # Original method argc+2 must fit the 15-bit pending operand count.
        "cmp r11d, 32765",
        "ja " + old,
        "mov r8, r11",
        "shl r8, 4",
        "neg r8",
        "add r8, QWORD PTR [rcx+24]",
        "cmp DWORD PTR [r8-24], -1",
        "jne native_probe_reject",
        "mov rdx, QWORD PTR [r8-32]",
        f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], 13",
        "je native_probe_js",
        # A genuine nested .call wrapper is itself a C function. Keep the
        # complete H normalizer for every C target; other classes cannot be
        # admitted by it and retain the original native fallback.
        f"cmp WORD PTR [rdx+{fields['JSObject.class_id']}], 12",
        "je " + old,
        "jmp native_probe_reject",
        "native_probe_js:",
        f"mov rdx, QWORD PTR [rdx+{fields['JSObject.u.func.function_bytecode']}]",
        f"cmp BYTE PTR [rdx+{kind}], 2",
        "je native_probe_reject",
        f"test BYTE PTR [rdx+{kind}], 1",
        "je " + old,
        "mov r9, QWORD PTR [rcx]",
        "mov r9, QWORD PTR [r9+80]",
        f"cmp BYTE PTR [r9+{forward}], 1",
        "jne " + old,
        f"mov eax, DWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_len']}]",
        "cmp eax, 2",
        "je native_probe_shape",
        "cmp eax, 4",
        "jne " + old,
        "native_probe_shape:",
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.var_count']}], 0",
        "jne " + old,
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.var_ref_count']}], 0",
        "jne " + old,
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.closure_var_count']}], 0",
        "jne " + old,
        f"cmp WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}], 2",
        "ja " + old,
        f"mov r10, QWORD PTR [rdx+{fields['JSFunctionBytecode.byte_code_buf']}]",
        "cmp eax, 2",
        "je native_probe_constant",
        "mov eax, DWORD PTR [r10]",
        "and eax, 4294902015",
        f"cmp eax, {ids['get_arg0'] | (ids['add'] << 16) | (ids['return'] << 24)}",
        "jne " + old,
        "cmp r11d, 2",
        "jb " + old,
        "cmp DWORD PTR [r8+24], 0",
        "jne " + old,
        "movzx eax, BYTE PTR [r10+1]",
        f"sub eax, {ids['push_minus1']}",
        "cmp eax, 8",
        "ja " + old,
        "dec eax",
        "add eax, DWORD PTR [r8+16]",
        "jo " + old,
        "jmp native_probe_value",
        "native_probe_constant:",
        f"cmp BYTE PTR [r10+1], {ids['return']}",
        "jne " + old,
        "movzx eax, BYTE PTR [r10]",
        f"sub eax, {ids['push_minus1']}",
        "cmp eax, 8",
        "ja " + old,
        "dec eax",
        "native_probe_value:",
        "mov QWORD PTR [rsp+8], rax",
        # Same available-window geometry as H: ordinary owned child plus
        # exactly one80-byte logical native tail, though neither is allocated.
        "xor eax, eax",
        "test r11d, r11d",
        "jz native_probe_actual",
        "lea eax, [r11-1]",
        "native_probe_actual:",
        f"movzx r9d, WORD PTR [rdx+{fields['JSFunctionBytecode.arg_count']}]",
        "cmp eax, r9d",
        "cmovb eax, r9d",
        f"movzx r9d, WORD PTR [rdx+{fields['JSFunctionBytecode.stack_size']}]",
        "add eax, r9d",
        "shl rax, 4",
        "add rax, 208",
        "mov r9, QWORD PTR [rcx+8]",
        "mov r10, QWORD PTR [r9+8]",
        "sub r10, QWORD PTR [r9+16]",
        "cmp rax, r10",
        "ja " + old,
        # Conservative existing leaf reserve. Accepted code performs no C
        # call, allocation, throw or poll handler; every failure retains H.
        "add rax, QWORD PTR [rcx+32]",
        "add rax, 5280",
        "mov r10, rsp",
        "sub r10, rax",
        f"cmp r10, QWORD PTR [rcx+{2312 if diagnostics else 72}]",
        "jb " + old,
        "mov r9, QWORD PTR [rcx]",
        "mov r9, QWORD PTR [r9+80]",
        f"mov r9, QWORD PTR [r9+{fields['JSFunctionBytecode.realm']}]",
        "mov r10, QWORD PTR [r8-16]",
        f"mov r10, QWORD PTR [r10+{fields['JSObject.u.cfunc.realm']}]",
        "cmp r9, r10",
        "jne native_probe_two_realms",
        f"cmp DWORD PTR [r9+{fields['JSContext.interrupt_counter']}], 2",
        "jle " + old,
        "jmp native_probe_commit",
        "native_probe_two_realms:",
        f"cmp DWORD PTR [r9+{fields['JSContext.interrupt_counter']}], 1",
        "jle " + old,
        f"cmp DWORD PTR [r10+{fields['JSContext.interrupt_counter']}], 1",
        "jle " + old,
        "native_probe_commit:",
        # No failure/observer from this point until the old return consumer.
        f"dec DWORD PTR [r9+{fields['JSContext.interrupt_counter']}]",
        f"dec DWORD PTR [r10+{fields['JSContext.interrupt_counter']}]",
        "mov r9, QWORD PTR [rcx]",
        "mov r10, QWORD PTR [rcx+16]",
        "lea eax, [r11+2]",
        f"cmp BYTE PTR [r10], {ids['tail_call_method']}",
        "jne native_probe_not_tail",
        "or eax, 32768",
        "native_probe_not_tail:",
        "mov WORD PTR [r9+126], ax",
        "add r10, 3",
        "mov QWORD PTR [rcx+16], r10",
        "mov QWORD PTR [r9+48], r10",
        "mov r8, QWORD PTR [rcx+24]",
        "mov QWORD PTR [r9+64], r8",
        "mov QWORD PTR [r9+104], r8",
        "mov rax, QWORD PTR [rsp+8]",
        "mov QWORD PTR [rcx+40], rax",
        "mov QWORD PTR [rcx+48], 0",
        "mov eax, 2",
        "ret",
        "native_probe_reject:",
        "xor eax, eax",
        "ret",
        "native_probe_control:",
        "cmp BYTE PTR [r9], 2",
        "je " + old,
        "jmp JS_FrameCallForwardNativeCold",
    ]
    assert ids["push_7"] - ids["push_minus1"] == 8
    return g


@source_abi
def compile_extra(source, build, compiler, msvc, diagnostics):
    M = module(source, "atod")

    def guard(src, path):
        interpreter = _frame_source_text(src, "quickjs-interpreter-loop.h")
        types = []
        for tag in ("JSFrameSegment", "JSFrame", "JSFrameCallSite"):
            found = re.findall(
                r"typedef struct " + tag + r" \{.*?\} " + tag + r";", interpreter, re.S
            )
            assert len(found) == 1
            types.append(found[0])
        path.write_text(
            '#include "quickjs-interpreter-private.h"\n'
            + "\n".join(types)
            + '\n#include "src/common/call/quickjs-interpreter-register.h"\n'
            + r"""
_Static_assert(JS_CLASS_BYTECODE_FUNCTION==13 && JS_CLASS_C_FUNCTION==12 &&
    JS_TAG_INT==0 && sizeof(JSValue)==16,"native target/value tags");
_Static_assert(offsetof(JSObject,class_id)==QJS_ABI_OFF_JSObject_class_id &&
    offsetof(JSObject,u.func.function_bytecode)==QJS_ABI_OFF_JSObject_u_func_function_bytecode &&
    offsetof(JSObject,u.cfunc.realm)==QJS_ABI_OFF_JSObject_u_cfunc_realm,"live native/JS function offsets");
_Static_assert(offsetof(JSFunctionBytecode,byte_code_buf)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf &&
    offsetof(JSFunctionBytecode,byte_code_len)==QJS_ABI_OFF_JSFunctionBytecode_byte_code_len &&
    offsetof(JSFunctionBytecode,arg_count)==QJS_ABI_OFF_JSFunctionBytecode_arg_count &&
    offsetof(JSFunctionBytecode,var_count)==QJS_ABI_OFF_JSFunctionBytecode_var_count &&
    offsetof(JSFunctionBytecode,stack_size)==QJS_ABI_OFF_JSFunctionBytecode_stack_size &&
    offsetof(JSFunctionBytecode,var_ref_count)==QJS_ABI_OFF_JSFunctionBytecode_var_ref_count &&
    offsetof(JSFunctionBytecode,closure_var_count)==QJS_ABI_OFF_JSFunctionBytecode_closure_var_count &&
    offsetof(JSFunctionBytecode,realm)==QJS_ABI_OFF_JSFunctionBytecode_realm,"live bytecode fields");
_Static_assert(offsetof(JSContext,interrupt_counter)==QJS_ABI_OFF_JSContext_interrupt_counter &&
    offsetof(JSStackFrame,cur_pc)==48 && offsetof(JSStackFrame,cur_sp)==64 &&
    offsetof(JSFrame,bytecode)==80 && offsetof(JSFrame,saved_sp)==104 &&
    offsetof(JSFrame,pending)==126 && sizeof(JSFrame)==128,"native commit offsets");
_Static_assert(offsetof(JSFrameSegment,capacity)==8 && offsetof(JSFrameSegment,used)==16,
    "native window capacity");
""",
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-native-abi.obj"),
        generator=guard,
        filename="quickjs-interpreter-call-forward-native-abi.c",
        late_name=".qjzzva",
    )

    def config(src, path):
        attr = "extern" if msvc else '__attribute__((section(".qjslcm$zzforward"),used))'
        path.write_text(
            "#include <stdlib.h>\n#ifdef _MSC_VER\n#include <intrin.h>\n#endif\n"
            + attr
            + " unsigned char JS_FrameCallForwardNativeControl"
            + (";" if msvc else "=255;")
            + """
extern const char JS_FrameCallForwardNativeDisable[];
extern int JS_FrameVarargsForwardTry(void *);
"""
            + (
                '__declspec(code_seg(".qjzzva")) __declspec(noinline)'
                if msvc
                else '__attribute__((section(".qjzzva"),noipa))'
            )
            + """
int JS_FrameCallForwardNativeCold(void *state)
{
    const char *name;
#ifdef _MSC_VER
    name=JS_FrameCallForwardNativeDisable;
#else
    __asm__("lea JS_FrameCallForwardNativeDisable(%%rip), %0" : "=r"(name));
#endif
    unsigned char mode=getenv(name)?2:1;
#ifdef _MSC_VER
    _InterlockedExchange8((volatile char *)&JS_FrameCallForwardNativeControl,(char)mode);
#else
    __atomic_store_n(&JS_FrameCallForwardNativeControl,mode,__ATOMIC_RELAXED);
#endif
    return JS_FrameVarargsForwardTry(state);
}
""",
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-native-config.obj"),
        generator=config,
        filename="quickjs-interpreter-call-forward-native-config.c",
        late_name=".qjzzva",
    )
    module(source, "call-forward-owned").compile_extra(source, build, compiler, msvc, diagnostics)
    body = module(source, "call-forward-owned").route_probe(lines(source, diagnostics))
    body = module(source, "call-prepare").route_probe(body)
    name = "JS_FrameCallForwardNativeProbe"
    if msvc:
        text = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            "EXTERN JS_FrameVarargsForwardTry:PROC",
            "EXTERN JS_FrameCallPrepareDeep:PROC",
            "EXTERN JS_FrameCallForwardNativeCold:PROC",
            "EXTERN JS_FrameCallForwardNativeControl:BYTE",
            "EXTERN JS_FrameCallForwardOwnedTry:PROC",
            "EXTERN JS_FrameCallForwardOwnedGeneral:PROC",
            ".qjzzva SEGMENT ALIGN(16) READONLY 'CODE'",
            "PUBLIC " + name + ", " + name + "_end, JS_FrameCallForwardNativeDisable",
            name + " PROC",
        ]
        for line in body:
            line = re.sub(r"\[rip\+([^\]]+)\]", r"\1", line)
            if re.fullmatch(r"j\w+ \w+", line):
                op, target = line.split()
                line = op + " NEAR PTR " + target
            text.append(line)
        text += [
            name + "_end LABEL BYTE",
            name + " ENDP",
            'JS_FrameCallForwardNativeDisable DB "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE",0',
            "ALIGN 4",
            name + "_unwind LABEL BYTE",
            "DB 1,0,0,0",
            ".qjzzva ENDS",
            ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
            "DD IMAGEREL " + name + ", IMAGEREL " + name + "_end, IMAGEREL " + name + "_unwind",
            ".pdata$zzzzzznullfast ENDS",
            "END",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-native.asm")
        obj = path.with_suffix(".obj")
        command = [
            str(compiler.with_name("ml64.exe")),
            "/nologo",
            "/c",
            "/Fo" + str(obj),
            str(path),
        ]
    else:
        text = [
            ".intel_syntax noprefix",
            '.section .qjzzva,"xr"',
            ".p2align 4",
            ".globl " + name + ", " + name + "_end, JS_FrameCallForwardNativeDisable",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
            *body,
            name + "_end:",
            "JS_FrameCallForwardNativeDisable:",
            '.asciz "QJS_DISABLE_FRAME_CALL_FORWARD_NATIVE"',
            ".p2align 2",
            name + "_unwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
            ".rva " + name + "," + name + "_end," + name + "_unwind",
        ]
        path = _frame_generated_file(build, "quickjs-interpreter-call-forward-native.S")
        obj = path.with_suffix(".obj")
        command = [str(compiler), "-c", "-g0", str(path), "-o", str(obj)]
    path.write_text("\n".join(text) + "\n", encoding="ascii")
    p = subprocess.run(command, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    obj.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, (p.stdout + p.stderr).decode(errors="replace")[-2000:])
    obj.with_suffix(".compile.json").write_text(
        json.dumps(
            dict(
                status="passed",
                command=command,
                source_sha256=sha(path),
                object_sha256=sha(obj),
                diagnostics=diagnostics,
                functions=[name],
                protocol="Ordinary one-argument Win64 leaf ABI. No native RSP/nonvolatile write, only two incoming home slots; existing H C helper and VM stack geometry unchanged.",
            ),
            indent=2,
        )
        + "\n"
    )
    module(source, "call-prepare").compile_extra(source, build, compiler, msvc, diagnostics)


def append_module(source, build, output, msvc, code_group, prefix, owner, merge):
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-call-forward-native.obj"),
        "JS_FrameCallForwardNativeProbe",
        "forward-native-asm",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$D",
        pdata_output=prefix + "1",
        base_owner=owner,
        baseline_sections=(),
    )
    C = module(source, "object-adapter")
    path = _frame_generated_file(build, "quickjs-interpreter-call-forward-native-config.obj")
    obj = C.Coff(path.read_bytes())
    if not msvc:
        writable = [
            i for i in range(1, obj.count + 1) if merge.section_name(obj, i) == ".qjslcm$zzforward"
        ]
        assert len(writable) == 1
        rec = obj.section_records[writable[0] - 1]
        assert (
            1 <= rec["size"] <= 16
            and bytes(obj.data[rec["raw"] : rec["raw"] + rec["size"]])
            == bytes([255]) + bytes(rec["size"] - 1)
            and rec["flags"] & 0xE0000000 == 0xC0000000
        )
    merge.append(
        output,
        path,
        "JS_FrameCallForwardNativeCold",
        "forward-native-config",
        keep_all=True,
        code_input=".qjzzva",
        code_output=code_group if msvc else code_group + "$E",
        pdata_output=prefix + "1",
        metadata_inputs=(".voltbl",) if msvc else (),
        writable_metadata_inputs=() if msvc else (".qjslcm$zzforward",),
        base_owner=owner,
        baseline_sections=(),
    )


def append_control(
    source,
    build,
    path,
    raw,
    name="JS_FrameCallForwardNativeControl",
    previous="JS_FrameSharedCallBypassControl",
    original_bytes=60,
):
    """Extend one existing MSVC RW section; retain every old symbol/index/prefix."""
    assert path.name == "quickjs-interpreter-register.obj"
    C = module(source, "object-adapter")
    merge = module(source, "extension-merge")
    before = C.Coff(raw)
    assert before.header == 20 and before.stride == 18
    assert not any(s["name"] == name for s in before.all_symbols.values())
    sections = [i for i in range(1, before.count + 1) if merge.section_name(before, i) == ".qjszlm"]
    assert len(sections) == 1
    number = sections[0]
    r = before.section_records[number - 1]
    assert r["flags"] & 0xE0000000 == 0xC0000000 and r["size"] == original_bytes and r["count"] == 0
    shared = next(s for s in before.all_symbols.values() if s["name"] == previous)
    assert shared["section"] == number and shared["value"] == r["size"] - 1
    payload = raw[r["raw"] : r["raw"] + r["size"]] + bytes([255])
    data = bytearray(raw[: before.table]) + payload + bytearray(raw[before.table :])
    struct.pack_into("<I", data, 8, before.table + len(payload))
    struct.pack_into("<II", data, r["pos"] + 16, len(payload), before.table)
    co = C.Coff(data)
    defs = [
        (i, s)
        for i, s in co.all_symbols.items()
        if s["name"] == ".qjszlm" and s["section"] == number and s["storage"] == 3
    ]
    assert len(defs) == 1
    index, s = defs[0]
    at = co.table + index * 18
    assert co.data[at + 17] == 1
    assert struct.unpack_from("<I", co.data, at + 18)[0] == r["size"]
    assert co.data[at + 18 + 14] == 0
    struct.pack_into("<I", co.data, at + 18, len(payload))
    symbol = co.external(name)
    record = co.aliases[-1]
    struct.pack_into("<IhH", record, 8, r["size"], number, 0)
    result = bytearray(co.finish())
    old_end = before.string_offset + struct.unpack_from("<I", raw, before.string_offset)[0]
    tail_shift = len(result) - len(raw)
    tail_pointers = []
    for old in before.section_records:
        for field in (20, 24, 28):
            value = struct.unpack_from("<I", raw, old["pos"] + field)[0]
            assert not value or value < before.table or value >= old_end
            if value and value >= old_end:
                assert struct.unpack_from("<I", result, old["pos"] + field)[0] == value
                struct.pack_into("<I", result, old["pos"] + field, value + tail_shift)
                tail_pointers.append(
                    dict(section_header=old["pos"], field=field, old=value, new=value + tail_shift)
                )
    result = bytes(result)
    after = C.Coff(result)
    assert after.count == before.count and after.symbol_count == before.symbol_count + 1
    assert all(after.all_symbols[i] == s for i, s in before.all_symbols.items())
    assert after.all_symbols[symbol] == dict(
        name=name, section=number, type=0, storage=2, value=r["size"]
    )
    for i, (old, new) in enumerate(zip(before.section_records, after.section_records), 1):
        a = raw[old["raw"] : old["raw"] + old["size"]] if old["raw"] else bytes(old["size"])
        b = result[new["raw"] : new["raw"] + new["size"]] if new["raw"] else bytes(new["size"])
        assert b == (a + bytes([255]) if i == number else a), i
        assert old["flags"] == new["flags"] and old["count"] == new["count"]
        assert (
            raw[old["reloc"] : old["reloc"] + old["count"] * 10]
            == result[new["reloc"] : new["reloc"] + new["count"] * 10]
        )
    folder = _frame_generated_file(build, "forward-native-control") / str(time.time_ns())
    folder.mkdir(parents=True)
    report = folder / "append.json"
    report.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=hashlib.sha256(result).hexdigest(),
                section=".qjszlm",
                original_bytes=r["size"],
                appended_bytes=1,
                source_tree_sha256=source_digest(source),
                runner_sha256=sha(Path(__file__)),
                new_symbol=name,
                new_symbol_index=symbol,
                new_symbol_offset=r["size"],
                rebased_tail_pointers=tail_pointers,
                old_section_count_and_names_retained=True,
                all_old_symbol_indexes_and_values_retained=True,
                all_old_payload_prefixes_and_relocations_retained=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(report)
