"""GNU validated native prototype snapshot load; original invalid-hint fallback, no timing claim."""

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
from pathlib import Path
import hashlib, importlib.util, json, os, re, struct, subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
CODE = ".qjzzdc"
RW = ".qjzzdm$C"
CFI = ".qjzzdf"
MAGIC = b"QJSPD_UNWIND_v1!"
FOOTER = b"QJSPD_END_v1!!!!"
assert len(MAGIC) == len(FOOTER) == 16


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "proto_direct_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BODY = r"""
#include <stdatomic.h>
typedef struct JSFrameProtoDirectData {
 unsigned char mode,diagnostic,reserved[6];
 _Atomic(uint64_t) objects,strings,resumes,misses;
 uint64_t abi;
} JSFrameProtoDirectData;
_Static_assert(sizeof(JSFrameProtoDirectData)==48 && offsetof(JSFrameProtoDirectData,objects)==8 &&
 offsetof(JSFrameProtoDirectData,strings)==16 && offsetof(JSFrameProtoDirectData,resumes)==24 &&
 offsetof(JSFrameProtoDirectData,misses)==32 && offsetof(JSFrameProtoDirectData,abi)==40,
 "direct prototype control ABI");
_Static_assert(sizeof(JSValue)==16 && sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame && sizeof(JSShapeProperty)==8 &&
 offsetof(JSObject,shape)==QJS_ABI_OFF_JSObject_shape && offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop &&
 offsetof(JSObject,class_id)==QJS_ABI_OFF_JSObject_class_id &&
 offsetof(JSShape,prop_count)==QJS_ABI_OFF_JSShape_prop_count && offsetof(JSShape,prop_hash_mask)==QJS_ABI_OFF_JSShape_prop_hash_mask &&
 offsetof(JSShape,proto)==QJS_ABI_OFF_JSShape_proto && offsetof(JSContext,class_proto)==QJS_ABI_OFF_JSContext_class_proto && JS_CLASS_ARRAY==2 &&
 JS_CLASS_STRING==5 && JS_TAG_OBJECT==-1 && JS_TAG_STRING==-7 && JS_PROP_TMASK==48,
 "native prototype load uses the pinned live-object ABI");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define PROTO_DIRECT_DIAG 1
#else
#define PROTO_DIRECT_DIAG 0
#endif
__attribute__((section(".qjzzdm$C"),used,aligned(8)))
JSFrameProtoDirectData JS_FrameProtoDirectData={0,PROTO_DIRECT_DIAG,{4}};
extern void JS_FrameLengthConfigure(void);
FRAME_CODE void JS_FrameProtoDirectConfigure(void){
 JS_FrameLengthConfigure();
 JSShapeProperty prop={0};JSObject object={0};uint32_t flags;unsigned char exotic;
 prop.flags=JS_PROP_TMASK;object.is_exotic=1;
 memcpy(&flags,&prop,4);memcpy(&exotic,(char *)&object+QJS_ABI_BIT_JSObject_is_exotic_BYTE,1);
 unsigned valid=flags==0xc0000000u && exotic==QJS_ABI_BIT_JSObject_is_exotic_MASK;
 JS_FrameProtoDirectData.abi=valid;
 JS_FrameProtoDirectData.mode=valid && !getenv("QJS_DISABLE_PROTO_DIRECT")?1:2;
}
"""


def generate(source, build, path):
    parent = (_frame_generated_file(build, "quickjs-interpreter-varargs.c")).read_text(
        encoding="utf-8"
    )
    include = next(line for line in parent.splitlines() if line.startswith("#include "))
    start = parent.index("#ifndef QJS_FRAME_CONTEXT_TYPES\n#define QJS_FRAME_CONTEXT_TYPES\n")
    end = parent.index(
        "/* A supported opcode is declared once, for validation and dispatch. */", start
    )
    path.write_text(include + "\n" + parent[start:end] + "\n" + BODY, encoding="utf-8")


def source_blocks(build, msvc):
    abi = current_abi()
    fields = abi["offsets"]
    assert not msvc, "GNU-only native prototype path; MS retained"
    g = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text(
            encoding="utf-8-sig"
        )
    )
    main = (_frame_generated_file(build, "quickjs-interpreter-register-win64.S")).read_text(
        encoding="ascii"
    )
    length = re.search(r"cmp r9d, (\d+)\nje JS_FrameProtoLoadFallback", main)
    assert length
    length_atom = int(length[1])
    blocks = []
    contracts = []
    external = {
        "JS_FrameProtoDirectData",
        "JS_FrameProtoLoadControl",
        "JS_FrameProtoPersistControl",
        "JS_FrameProtoPersistentHints",
        "JS_FrameInterpPropertyCold_unwind",
    }
    for tag in g["aliases"]:
        is_main = tag == "M"
        prefix = "proto_direct_" + tag
        old_try = "JS_FrameProtoPersistentTry" if is_main else "dirty_JS_FrameProtoPersistentTry"
        old_end = (
            "JS_FrameProtoPersistentTry_end" if is_main else "JS_FramePublishDirtyProtoTry_end"
        )
        original = (
            main
            if is_main
            else (_frame_generated_file(build, "quickjs-interpreter-publish-win64.S")).read_text(
                encoding="ascii"
            )
        )
        assert original.count(old_try + ":\n") == original.count(old_end + ":\n") == 1
        stream = original.split(old_try + ":\n", 1)[1].split(old_end + ":\n", 1)[0].splitlines()
        assert all(line and not line.startswith(".") for line in stream)
        labelmap = {line[:-1]: prefix + "_" + line[:-1] for line in stream if line.endswith(":")}
        slow = labelmap["proto_persist_slow" if is_main else "dirty_proto_persist_slow"]
        original_lines = list(stream)
        for i, line in enumerate(stream):
            stream[i] = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: labelmap.get(m[0], m[0]), line)
        old_slow = (
            "JS_FrameProtoPersistentFill"
            if is_main
            else "JS_FramePublishBefore_FrameProtoPersistentFill"
        )
        old_obj = "JS_FrameProtoObjectEntry" if is_main else "dirty_JS_FrameProtoObjectEntry"
        old_str = (
            "JS_FrameProtoLoadEntry" if is_main else "JS_FramePublishDirty_FrameProtoLoadEntry"
        )
        external.update((old_try, old_slow, old_obj, old_str))
        # All global/live-descriptor guards and original empty-slot promotion
        # remain in their original order. Only the full-private-bucket exit is
        # redirected to a direct load, after R8/R10 have already been validated.
        full = prefix + "_validated_full"
        needle = ["cmp QWORD PTR [r11], 0", "jne " + slow, "mov BYTE PTR [rdx+rcx], 0"]
        hits = [i for i in range(len(stream) - 2) if stream[i : i + 3] == needle]
        assert len(hits) == 1
        stream[hits[0] + 1] = "jne " + full
        for a, b in [
            ("mov r9d, DWORD PTR [r12+1]", ["test r9d, r9d", "js " + slow]),
            ("cmp DWORD PTR [r13-8], -7", None),
            (f"cmp WORD PTR [r8+{fields['JSObject.class_id']}], 2", None),
        ]:
            assert stream.count(a) == 1
            at = stream.index(a)
            if b:
                stream[at + 1 : at + 1] = b
            else:
                assert stream[at + 1] == "jne " + slow
                stream[at + 2 : at + 2] = ["cmp r9d, " + str(length_atom), "je " + slow]
        if g["diagnostics"]:
            at = stream.index(slow + ":") + 1
            stream[at:at] = ["lock inc QWORD PTR [rip+JS_FrameProtoDirectData+32]"]
        body = [
            "cmp BYTE PTR [rip+JS_FrameProtoDirectData], 1",
            "jne " + old_try,
            *stream,
            full + ":",
            "mov ecx, r10d",
            "shl rcx, 4",
            f"add rcx, QWORD PTR [r8+{fields['JSObject.prop']}]",
            "mov rax, QWORD PTR [rcx]",
            "mov rdx, QWORD PTR [rcx+8]",
            "test edx, edx",
            "jns " + prefix + "_primitive",
            f"inc DWORD PTR [rax{abi_constants(abi)['QJS_ABI_REF_COUNT_OFFSET']:+d}]",
            prefix + "_primitive:",
        ]
        if g["diagnostics"]:
            body += [
                "cmp DWORD PTR [r13-8], -1",
                "jne " + prefix + "_count_string",
                "lock inc QWORD PTR [rip+JS_FrameProtoDirectData+8]",
                "jmp " + prefix + "_counted",
                prefix + "_count_string:",
                "lock inc QWORD PTR [rip+JS_FrameProtoDirectData+16]",
                prefix + "_counted:",
            ]
        body += [
            "mov QWORD PTR [r13], rax",
            "mov QWORD PTR [r13+8], rdx",
            "add r13, 16",
            "mov eax, 2",
            "ret",
        ]
        name = "JS_FrameProtoDirect" + tag
        blocks.append((name, body))
        for kind, old_target in [("Object", old_obj), ("String", old_str)]:
            resume = ["cmp eax, 2", "jne " + old_target]
            if g["diagnostics"]:
                resume += ["lock inc QWORD PTR [rip+JS_FrameProtoDirectData+24]"]
            resume += ["add r12, 5", "movzx eax, BYTE PTR [r12]", "jmp QWORD PTR [rdi+rax*8]"]
            blocks.append((name + kind, resume))
        contracts.append(
            dict(
                family=tag,
                entry=name,
                original_try=old_try,
                old_slow=old_slow,
                cloned_source="quickjs-interpreter-register-win64.S"
                if is_main
                else "quickjs-interpreter-publish-win64.S",
                cloned_source_sha256=hashlib.sha256(original.encode("ascii")).hexdigest(),
                original_guard_stream=original_lines,
                renamed_labels=labelmap,
                handoff="Only a fully validated persistent live snapshot plus full private two-way bucket reaches the direct loader. Current R8 holder/R10 atom-slot is reused; no second holder/descriptor lookup.",
                controls="Mode2 branches to original Try at the original CALL stack depth. Invalid hints in mode1 use the cloned ORIGINAL C/publication tail; no common-failure direct-loader detour. Counters schema version4: off uses old Try and records no new misses.",
                ABI="Private EAX2/R13 output, one live-value duplicate, original CALL return slot and ordinary RET; EAX0/1 retry/fallback unchanged. Native ASM has no CALL/RSP mutation/GC/allocation/poll. R12 advances only at root-CFI continuation.",
                layout="Old Try body/tail completely unchanged; only original CALL displacement plus two marker-aware retry displacements per family. Clone is isolated in the same separate late module, not appended on top of v1.",
                status="unqualified source only; fresh actual native, two-level all-instruction unwind, loaded-byte/layout gates and paired source-parent-off-stock timings required",
            )
        )
    return blocks, external, g, contracts


def normalize(source, path):
    C = module(source, "object-adapter")
    co = C.Coff(path.read_bytes())
    changes = []
    for number, r in enumerate(co.section_records, 1):
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if 5 <= kind <= 9:
                old = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
                struct.pack_into("<i", co.data, r["raw"] + off, old - (kind - 4))
                struct.pack_into("<H", co.data, at + 8, 4)
                changes.append(
                    dict(
                        section=number,
                        offset=off,
                        old_kind=kind,
                        old_addend=old,
                        new_addend=old - (kind - 4),
                    )
                )
    path.write_bytes(co.finish())
    path.with_name(path.name + ".proto-direct-rel32.json").write_text(
        json.dumps(dict(status="passed", changes=changes), indent=2) + "\n", encoding="utf-8"
    )


def compile_extra(source, build, msvc):
    if msvc:
        return None
    out = _frame_generated_file(build, "quickjs-interpreter-proto-direct.obj")
    module(source, "atod").compile_extra(
        source,
        build,
        out,
        generator=lambda s, p: generate(s, build, p),
        filename="quickjs-interpreter-proto-direct.c",
        late_name=CODE,
    )
    privatize(out, build, source)
    normalize(source, out)
    compile_asm(source, build, msvc)


def append_crt(source, build, output):
    """Retarget the existing length CRT slot to a composed initializer."""
    C = module(source, "object-adapter")
    N = module(source, "extension-merge")
    raw = output.read_bytes()
    co = C.Coff(raw)
    wanted = "JS_FrameProtoDirectConfigure"
    target = [
        i
        for i, s in co.all_symbols.items()
        if s["name"] == wanted and s["section"] > 0 and s["storage"] == 2
    ]
    assert len(target) == 1
    changed = []
    for number, r in enumerate(co.section_records, 1):
        if N.section_name(co, number) != ".CRT$XCU":
            continue
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            s = co.all_symbols[index]
            if s["name"] != "JS_FrameLengthConfigure":
                continue
            assert kind == 1 and struct.unpack_from("<Q", co.data, r["raw"] + off)[0] == 0
            struct.pack_into("<I", co.data, at + 4, target[0])
            changed.append(
                dict(
                    section=number,
                    offset=off,
                    kind=kind,
                    old_target=s["name"],
                    new_target=wanted,
                    width=8,
                )
            )
    assert len(changed) == 1, changed
    result = co.finish()
    after = C.Coff(result)
    for number, (a, b) in enumerate(zip(C.Coff(raw).sections, after.sections), 1):
        assert {k: v for k, v in a.items() if k != "relocations_sha256"} == {
            k: v for k, v in b.items() if k != "relocations_sha256"
        }
        if number != changed[0]["section"]:
            assert a == b
    assert C.Coff(raw).all_symbols == after.all_symbols
    output.write_bytes(result)
    (_frame_generated_file(build, "quickjs-interpreter-proto-direct-crt.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=sha(output),
                routes=changed,
                additional_crt_bytes=0,
                all_old_allocated_section_payloads_held=True,
                initialization_order=[
                    "JS_FrameLengthConfigure",
                    "native direct prototype control initialization",
                ],
                policy="Same standard CRT ADDR64 slot, retargeted to a normal C ABI composed initializer. No table placement or address search.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def has_tables(co):
    return any(
        (s["name"] == "interp_table" and s["section"] > 0)
        or s["name"] == "JS_FramePublishDirtyTable"
        for s in co.all_symbols.values()
    )


def privatize(output, build, source):
    C = module(source, "object-adapter")
    raw = output.read_bytes()
    co = C.Coff(raw)
    renamed = []
    commons = []
    for index, s in co.all_symbols.items():
        if s["section"] == 0 and s["storage"] == 2 and s["value"]:
            providers = []
            for p in (
                _frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj"),
                _frame_build_file(
                    build, "CMakeFiles/qjs.dir/src/x86/win64/common/quickjs-interpreter.c.obj"
                ),
            ):
                pc = C.Coff(p.read_bytes())
                if any(
                    v["name"] == s["name"]
                    and v["storage"] == 2
                    and (v["section"] > 0 or (v["section"] == 0 and v["value"] >= s["value"]))
                    for v in pc.all_symbols.values()
                ):
                    providers.append(str(p))
            assert providers, ("No common provider", s)
            struct.pack_into("<I", co.data, co.table + index * co.stride + 8, 0)
            commons.append(dict(name=s["name"], bytes=s["value"], providers=providers))
        if (
            s["section"] > 0
            and s["storage"] == 2
            and not s["name"].startswith("JS_FrameProtoDirect")
        ):
            name = "proto_direct_emitted_" + hashlib.sha256(s["name"].encode()).hexdigest()[:32]
            at = len(co.strings)
            co.strings += name.encode() + b"\0"
            struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
            renamed.append(dict(old=s["name"], new=name))
    backup = output.with_name(output.name + ".unrenamed")
    assert not backup.exists()
    backup.write_bytes(raw)
    output.write_bytes(co.finish())
    assert C.Coff(raw).sections == C.Coff(output.read_bytes()).sections
    output.with_name(output.name + ".private-symbols.json").write_text(
        json.dumps(
            dict(
                status="passed",
                input_sha256=sha(backup),
                output_sha256=sha(output),
                renamed=renamed,
                commons=commons,
                section_bytes_held=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@source_abi
def compile_asm(source, build, msvc):
    C = module(source, "object-adapter")
    merge = module(source, "extension-merge")
    blocks, external, generation, contracts = source_blocks(build, msvc)
    compiler = Path(
        json.loads(
            (
                _frame_generated_file(build, "quickjs-interpreter-dense-array-pop.compile.json")
            ).read_text(encoding="utf-8-sig")
        )["compiler_command"][0]
    )
    co = C.Coff((_frame_generated_file(build, "quickjs-interpreter-proto-direct.obj")).read_bytes())
    c_pdata = sum(
        r["size"]
        for i, r in enumerate(co.section_records, 1)
        if merge.section_name(co, i).startswith(".pdata")
    )
    capacity = module(source, "varargs").CAPACITY + c_pdata + 12 * len(blocks)
    header = MAGIC + bytes(16)
    footer = FOOTER + struct.pack("<II", capacity, 1) + bytes(capacity)
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-proto-direct.asm" if msvc else "quickjs-interpreter-proto-direct.S",
    )
    obj = _frame_generated_file(build, "quickjs-interpreter-proto-direct-asm.obj")
    if msvc:
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + name + ":BYTE" for name in sorted(external)],
            CODE + " SEGMENT ALIGN(16) 'CODE'",
        ]
        for name, stream in blocks:
            lines += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
            for line in stream:
                line = line.replace("rip+", "")
                if line.endswith(":"):
                    lines += ["PUBLIC " + line[:-1], line[:-1] + "::"]
                else:
                    lines.append(re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", line))
            lines += [name + "_end LABEL BYTE", name + " ENDP"]
        lines += [CODE + " ENDS", ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'"]
        for name, _ in blocks:
            lines += [
                "DD IMAGEREL "
                + name
                + ", IMAGEREL "
                + name
                + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind"
            ]
        lines += [".pdata$zzzzzznullfast ENDS"]
        for name, payload in ((CFI + "$A", header), (CFI + "$Z", footer)):
            lines += [name + " SEGMENT ALIGN(4) READONLY 'CODE'"]
            for i in range(0, len(payload), 32):
                lines += ["DB " + ",".join(str(b) for b in payload[i : i + 32])]
            lines += [name + " ENDS"]
        lines += ["END"]
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        lines = [".intel_syntax noprefix", ".section " + CODE + ',"xr"']
        for name, stream in blocks:
            lines += [
                ".p2align 4",
                ".globl " + name + ", " + name + "_end",
                ".def " + name + "; .scl 2; .type 32; .endef",
                name + ":",
                *stream,
                name + "_end:",
            ]
        lines += [
            ".p2align 2",
            ".globl JS_FrameProtoDirectLeafUnwind",
            "JS_FrameProtoDirectLeafUnwind:",
            ".byte 1,0,0,0",
            '.section .pdata$zzzzzznullfast,"dr"',
            ".p2align 2",
        ]
        for name, _ in blocks:
            unwind = (
                "JS_FrameProtoDirectLeafUnwind"
                if name in ("JS_FrameProtoDirectM", "JS_FrameProtoDirectP")
                else "JS_FrameInterpPropertyCold_unwind"
            )
            lines += [".rva " + name + ", " + name + "_end, " + unwind]
        for name, payload in ((CFI + "$A", header), (CFI + "$Z", footer)):
            lines += [".section " + name + ',"xr"', ".p2align 2"]
            nonzero = len(payload) if name.endswith("$A") else 24
            lines += [".byte " + ",".join(map(str, payload[:nonzero]))]
            if len(payload) > nonzero:
                lines += [".zero " + str(len(payload) - nonzero)]
        command = [str(compiler), "-g0", "-c", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    env = dict(os.environ)
    env["PATH"] = str(compiler.parent) + ";" + env["PATH"]
    p = subprocess.run(
        command, capture_output=True, env=env, creationflags=subprocess.CREATE_NO_WINDOW
    )
    log = asm.with_suffix(".compile.log")
    log.write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, (p.stdout + p.stderr).decode(errors="replace")[-2000:])
    # MASM REL32_n operands are canonicalized exactly like the inherited VM.
    co = C.Coff(obj.read_bytes())
    corrections = []
    for r in co.section_records:
        for j in range(r["count"]):
            at = r["reloc"] + 10 * j
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            if 5 <= kind <= 9:
                assert msvc
                value = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
                struct.pack_into("<i", co.data, r["raw"] + off, value - (kind - 4))
                struct.pack_into("<H", co.data, at + 8, 4)
                corrections.append(dict(offset=off, kind=kind))
    obj.write_bytes(co.finish())
    (_frame_generated_file(build, "quickjs-interpreter-proto-direct-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                msvc=msvc,
                diagnostics=generation["diagnostics"],
                asm=str(asm),
                asm_sha256=sha(asm),
                object=str(obj),
                object_sha256=sha(obj),
                compiler_command=command,
                blocks=[name for name, _ in blocks],
                contracts=contracts,
                rel32_corrections=corrections,
                capacity=capacity,
                compiler_pdata_bytes=c_pdata,
                native_pdata_bytes=12 * len(blocks),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def append_module(source, build, output, msvc, group, prefix, owner, merge):
    if msvc:
        return None
    C = module(source, "object-adapter")
    old = C.Coff(output.read_bytes())
    # Miss is an actual MSVC leaf with no native record; Configure owns compiler
    # CFI. Keep all contributions while anchoring the strict merger to that CFI.
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-proto-direct.obj"),
        "JS_FrameProtoDirectConfigure",
        "proto-direct-c",
        keep_all=True,
        code_input=CODE,
        code_output=CODE + "$C",
        pdata_output=CFI + "$B",
        metadata_inputs=(".voltbl",) if msvc else (),
        writable_metadata_inputs=(RW,),
        base_owner=owner,
        baseline_sections=(),
    )
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-proto-direct-asm.obj"),
        "JS_FrameProtoDirectM",
        "proto-direct-asm",
        keep_all=True,
        code_input=CODE,
        code_output=CODE + "$A",
        pdata_output=CFI + "$C",
        allocated_metadata_inputs=(CFI + "$A", CFI + "$Z"),
        base_owner=owner,
        baseline_sections=(),
    )
    raw = bytearray(output.read_bytes())
    co = C.Coff(raw)
    for i, r in enumerate(co.section_records, 1):
        if i <= old.count:
            continue
        if merge.section_name(co, i).startswith(CFI):
            struct.pack_into("<I", raw, r["pos"] + 36, (r["flags"] & ~0xE00000E0) | 0x40000040)
        if merge.section_name(co, i).startswith(CODE):
            struct.pack_into("<I", raw, r["pos"] + 36, (r["flags"] & ~0xE0) | 0x60000040)
    output.write_bytes(raw)
    if msvc:
        # LINK places ordinary new sections before the existing merged .qjscold.
        # Give all three new groups their own merge layers, declared AFTER the
        # inherited merge directive. This is a fixed semantic ordering, with no
        # addresses, padding, capacity changes or movement of inherited code.
        co = C.Coff(bytes(raw))
        renames = []
        for number, r in enumerate(co.section_records, 1):
            if number <= old.count:
                continue
            name = merge.section_name(co, number)
            wanted = None
            for a, b in ((CODE, ".qjpdrx"), (".qjzzdm", ".qjpdrw"), (CFI, ".qjpdro")):
                if name.startswith(a):
                    wanted = b + name[len(a) :]
                    break
            if not wanted:
                continue
            at = len(co.strings)
            co.strings += wanted.encode() + b"\0"
            co.data[r["pos"] : r["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
            for index, s in co.all_symbols.items():
                if (
                    s["section"] == number
                    and s["name"] == name
                    and s["storage"] == 3
                    and s["type"] == 0
                ):
                    struct.pack_into("<II", co.data, co.table + index * co.stride, 0, at)
            renames.append(dict(section=number, old=name, new=wanted))
        raw = bytes(co.finish())
        co = C.Coff(raw)
        assert co.string_offset + len(co.strings) == len(raw), (
            "Append only after parent packet coalescing"
        )
        directives = [
            (i, r)
            for i, r in enumerate(co.section_records, 1)
            if merge.section_name(co, i) == ".drectve"
        ]
        assert len(directives) == 1
        number, r = directives[0]
        previous = raw[r["raw"] : r["raw"] + r["size"]]
        assert previous.count(b"/MERGE:.qjs=.qjscold") == 1 and b"/MERGE:.qjpdrx=" not in previous
        payload = (
            previous + b" /MERGE:.qjpdrx=.qjzzdc /MERGE:.qjpdrw=.qjzzdm /MERGE:.qjpdro=.qjzzdf "
        )
        # Relocate linker-only directive storage before the symbol table, keeping
        # the canonical packed COFF shape expected by later strict adapters.
        result = bytearray(raw[: co.table] + payload + raw[co.table :])
        struct.pack_into("<I", result, co.table_offset, co.table + len(payload))
        for rr in co.section_records:
            for f in (20, 24, 28):
                value = struct.unpack_from("<I", raw, rr["pos"] + f)[0]
                if not value or value < co.table:
                    continue
                # A legitimate empty footer relocation table can point exactly
                # at the symbol table. Rebase its file pointer across insertion;
                # never permit live section/relocation data in symbol storage.
                assert (
                    (f == 20 and rr["size"] == 0)
                    or (f == 24 and rr["count"] == 0)
                    or (f == 28 and struct.unpack_from("<H", raw, rr["pos"] + 34)[0] == 0)
                )
                struct.pack_into("<I", result, rr["pos"] + f, value + len(payload))
        struct.pack_into("<II", result, r["pos"] + 16, len(payload), co.table)
        for index, s in co.all_symbols.items():
            if (
                s["section"] == number
                and s["storage"] == 3
                and s["type"] == 0
                and raw[co.table + index * co.stride + 17]
            ):
                struct.pack_into(
                    "<I", result, co.table + len(payload) + (index + 1) * co.stride, len(payload)
                )
        check = C.Coff(result)
        assert check.sections[: number - 1] == co.sections[: number - 1]
        for i, (a, b) in enumerate(zip(co.sections, check.sections), 1):
            if i != number:
                assert a == b, (i, a, b)
        output.write_bytes(result)
        (
            _frame_generated_file(build, "quickjs-interpreter-proto-direct-msvc-merge.json")
        ).write_text(
            json.dumps(
                dict(
                    status="passed",
                    renames=renames,
                    old_directive_sha256=hashlib.sha256(previous).hexdigest(),
                    new_directive_sha256=hashlib.sha256(payload).hexdigest(),
                    old_allocated_sections_identical=True,
                    order="Inherited merged cold group, new RX, new RW, new RO CFI. No numeric placement.",
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    append_crt(source, build, output)


def packet(image):
    raw = bytearray(image.read_bytes())
    pe = struct.unpack_from("<I", raw, 60)[0]
    opt = pe + 24
    at = opt + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(struct.unpack_from("<H", raw, pe + 6)[0]):
        pos = at + 40 * i
        name = raw[pos : pos + 8].rstrip(b"\0").decode("ascii")
        size, rva, physical_size, physical = struct.unpack_from("<IIII", raw, pos + 8)
        sections.append(
            dict(
                name=name,
                size=size,
                rva=rva,
                physical_size=physical_size,
                physical=physical,
                flags=struct.unpack_from("<I", raw, pos + 36)[0],
            )
        )
    found = [s for s in sections if s["name"] == CFI]
    if not found:
        return None
    assert len(found) == 1
    s = found[0]
    assert s["flags"] & 0xE0000000 == 0x40000000
    data = raw[s["physical"] : s["physical"] + s["size"]]
    assert data.startswith(MAGIC)
    ends = [i for i in range(len(data)) if data.startswith(FOOTER, i)]
    assert len(ends) == 1
    end = ends[0]
    assert end > 32 and (end - 32) % 12 == 0
    native = [bytes(data[i : i + 12]) for i in range(32, end, 12)]
    capacity, version = struct.unpack_from("<II", data, end + 16)
    assert version == 1 and end + 24 + capacity <= s["size"]
    return raw, opt, sections, s, native, end + 24, capacity


def strip_native_before_parent(image):
    """Parent's fixed RO packet never receives this independent contribution."""
    p = packet(image)
    if not p:
        return
    raw, opt, sections, s, native, relative, capacity = p
    directory = opt + 112 + 3 * 8
    rva, size = struct.unpack_from("<II", raw, directory)
    current = next(
        v for v in sections if v["rva"] <= rva and rva + size <= v["rva"] + v["physical_size"]
    )
    off = current["physical"] + rva - current["rva"]
    rows = [bytes(raw[i : i + 12]) for i in range(off, off + size, 12)]
    extra = set(native)
    filtered = [r for r in rows if r not in extra]
    if len(filtered) == len(rows):
        return
    table = b"".join(filtered)
    assert len(table) <= capacity
    target = s["physical"] + relative
    raw[target : target + capacity] = table + bytes(capacity - len(table))
    struct.pack_into("<II", raw, directory, s["rva"] + relative, len(table))
    image.write_bytes(raw)


def finalize_image(image, previous):
    p = packet(image)
    if not p:
        return previous
    raw, opt, sections, s, native, relative, capacity = p
    directory = opt + 112 + 3 * 8
    rva, size = struct.unpack_from("<II", raw, directory)
    current = next(
        v for v in sections if v["rva"] <= rva and rva + size <= v["rva"] + v["physical_size"]
    )
    off = current["physical"] + rva - current["rva"]
    inherited = [bytes(raw[i : i + 12]) for i in range(off, off + size, 12)]
    rows = sorted(set(inherited) | set(native), key=lambda r: struct.unpack_from("<I", r)[0])
    end = 0
    for row in rows:
        begin, stop, uw = struct.unpack("<III", row)
        assert end <= begin < stop and uw
        end = stop
        for address, truth in ((begin, stop - begin), (uw, 4)):
            assert any(
                v["rva"] <= address and address + truth <= v["rva"] + v["physical_size"]
                for v in sections
            )
    table = b"".join(rows)
    assert len(table) <= capacity
    target = s["physical"] + relative
    raw[target : target + capacity] = table + bytes(capacity - len(table))
    struct.pack_into("<II", raw, directory, s["rva"] + relative, len(table))
    before = sha(image)
    if raw != image.read_bytes():
        image.write_bytes(raw)
    return dict(
        status="passed",
        image=str(image),
        before_sha256=before,
        image_sha256=sha(image),
        inherited_finalization=previous,
        proto_direct_rows=len(native),
        combined_rows=len(rows),
        capacity=capacity,
        directory_rva=s["rva"] + relative,
        all_inherited_rows_retained=True,
        native_storage_readonly=True,
        policy="Independent final RO directory and PE exception pointer only; parent packet kept free of new contribution. No executable or old RW bytes/addresses changed by finalization.",
    )


def route_input(source, build, path, raw, msvc):
    if msvc:
        return raw, None
    before = raw
    C = module(source, "object-adapter")
    raw, _ = module(source, "call-metadata").packed(raw, C)
    co = C.Coff(raw)
    original = C.Coff(raw)
    routes = []
    exports = []
    generation = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text(
            encoding="utf-8-sig"
        )
    )

    def symbols(name):
        return [(i, s) for i, s in co.all_symbols.items() if s["name"] == name and s["section"] > 0]

    def symbol(name):
        hits = symbols(name)
        assert len(hits) == 1, (name, hits)
        return hits[0]

    def public(name):
        i, s = symbol(name)
        if s["storage"] == 3:
            co.data[co.table + i * co.stride + co.class_offset] = 2
            exports.append(dict(index=i, name=name, old_storage=3, new_storage=2))
        else:
            assert s["storage"] == 2

    def external(name):
        hits = [
            i
            for i, s in co.all_symbols.items()
            if s["name"] == name and s["storage"] == 2 and s["section"] == 0 and s["value"] == 0
        ]
        return hits[0] if hits else co.external(name)

    def patch(section, off, old_name, new_name, role, family, opcode):
        rec = co.section_records[section - 1]
        _, old = symbol(old_name) if symbols(old_name) else (None, None)
        rels = [
            (j, *struct.unpack_from("<IIH", co.data, rec["reloc"] + 10 * j))
            for j in range(rec["count"])
            if struct.unpack_from("<I", co.data, rec["reloc"] + 10 * j)[0] == off
        ]
        assert len(rels) <= 1
        value = struct.unpack_from("<i", co.data, rec["raw"] + off)[0]
        if rels:
            j, at, index, kind = rels[0]
            s = co.all_symbols[index]
            assert kind == 4
            if old is None:
                assert s["name"] == old_name and s["section"] == 0 and s["value"] + value == 0
            else:
                assert s["section"] == old["section"] and s["value"] + value == old["value"]
        else:
            assert old is not None and old["section"] == section and off + 4 + value == old["value"]
        target = external(new_name)
        if rels:
            struct.pack_into("<I", co.data, rec["reloc"] + 10 * rels[0][0] + 4, target)
        else:
            co.extra_relocations.setdefault(section, []).append(struct.pack("<IIH", off, target, 4))
        struct.pack_into("<i", co.data, rec["raw"] + off, 0)
        routes.append(
            dict(
                role=role,
                family=family,
                section=section,
                offset=off,
                width=4,
                opcode=opcode,
                kind=4,
                old=old_name,
                new=new_name,
                old_addend=value,
                new_addend=0,
                target_symbol=target,
                source_relocation=bool(rels),
            )
        )

    for tag in generation["aliases"]:
        is_main = tag == "M"
        try_name = "JS_FrameProtoPersistentTry" if is_main else "JS_FramePublishDirtyProtoTry"
        entry_name = (
            "JS_FrameProtoLoadEntry" if is_main else "JS_FramePublishDirty_FrameProtoLoadEntry"
        )
        if not symbols(try_name) and not symbols(entry_name):
            continue
        _, entry = symbol(entry_name)
        _, end = symbol(entry_name + "_end")
        assert entry["section"] == end["section"]
        rr = co.section_records[entry["section"] - 1]
        payload = bytes(co.data[rr["raw"] : rr["raw"] + rr["size"]])
        # The complete source-bound entry contains exactly one genuine native
        # Try CALL. Prove its local/typed target and its whole following sequence.
        wanted = "JS_FrameProtoPersistentTry" if is_main else "dirty_JS_FrameProtoPersistentTry"
        _, tr = symbol(wanted)
        assert tr["section"] == entry["section"] or is_main
        candidates = []
        old_rels = {
            struct.unpack_from("<I", co.data, rr["reloc"] + 10 * j)[0]: struct.unpack_from(
                "<IIH", co.data, rr["reloc"] + 10 * j
            )
            for j in range(rr["count"])
        }
        for pos in range(entry["value"], end["value"] - 7):
            if payload[pos : pos + 1] != b"\xe8" or payload[pos + 5 : pos + 7] != b"\x85\xc0":
                continue
            off = pos + 1
            value = struct.unpack_from("<i", payload, off)[0]
            if off in old_rels:
                _, index, kind = old_rels[off]
                s = co.all_symbols[index]
                match = (
                    kind == 4
                    and s["section"] == tr["section"]
                    and s["value"] + value == tr["value"]
                )
            else:
                match = entry["section"] == tr["section"] and off + 4 + value == tr["value"]
            if match:
                candidates.append(pos)
        assert len(candidates) == 1, (tag, candidates)
        call = candidates[0]
        public(wanted)
        patch(
            entry["section"],
            call + 1,
            wanted,
            "JS_FrameProtoDirect" + tag,
            "validated producer CALL",
            tag,
            "e8",
        )
        pos = call + 7
        if payload[pos : pos + 1] == b"\x74":
            pos += 2
        else:
            assert payload[pos : pos + 2] == b"\x0f\x84"
            pos += 6
        assert payload[pos : pos + 5] == bytes.fromhex("41837df8ff")
        pos += 5
        assert payload[pos : pos + 2] == b"\x0f\x84" and payload[pos + 6 : pos + 7] == b"\xe9"
        obj = "JS_FrameProtoObjectEntry" if is_main else "dirty_JS_FrameProtoObjectEntry"
        public(obj)
        public(entry_name)
        patch(
            entry["section"],
            pos + 2,
            obj,
            "JS_FrameProtoDirect" + tag + "Object",
            "object retry target",
            tag,
            "0f84",
        )
        patch(
            entry["section"],
            pos + 7,
            entry_name,
            "JS_FrameProtoDirect" + tag + "String",
            "string retry target",
            tag,
            "e9",
        )
    if not routes:
        return before, None
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    for r in routes:
        rec = after.section_records[r["section"] - 1]
        struct.pack_into("<i", restored, rec["raw"] + r["offset"], r["old_addend"])
    assert [
        {k: v for k, v in s.items() if k != "relocations_sha256"} for s in C.Coff(restored).sections
    ] == [{k: v for k, v in s.items() if k != "relocations_sha256"} for s in original.sections]
    for number, (oldrec, newrec) in enumerate(
        zip(original.section_records, after.section_records), 1
    ):
        oldrels = [
            struct.unpack_from("<IIH", original.data, oldrec["reloc"] + 10 * j)
            for j in range(oldrec["count"])
        ]
        newrels = [
            struct.unpack_from("<IIH", after.data, newrec["reloc"] + 10 * j)
            for j in range(newrec["count"])
        ]
        for r in routes:
            if r["section"] != number:
                continue
            newrels.remove((r["offset"], r["target_symbol"], 4))
            if r["source_relocation"]:
                newrels += [v for v in oldrels if v[0] == r["offset"]]
        assert sorted(oldrels) == sorted(newrels)
    for i, s in original.all_symbols.items():
        wanted = dict(s)
        if any(v["index"] == i for v in exports):
            wanted["storage"] = 2
        assert after.all_symbols[i] == wanted, (i, s, after.all_symbols[i])
    folder = _frame_generated_file(build, "proto-direct-link")
    folder.mkdir(exist_ok=True)
    receipt = folder / (path.name + ".json")
    assert not receipt.exists()
    receipt.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(before).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                routes=routes,
                exports=exports,
                original_native_CALL_opcode_TEST_JZ_tag_compare_held=True,
                all_other_section_payloads_and_typed_relocations_held=True,
                private_result2_requires_fresh_native_semantics_and_two_level_unwind=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(receipt)
