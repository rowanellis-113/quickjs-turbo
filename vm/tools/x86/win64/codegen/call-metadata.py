"""All-site warm PIC activation; original opcode admission and frame ABI retained."""

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
from native_build import source_digest, find_objdump
from c_source_match import replace_one
from pathlib import Path
import hashlib, importlib.util, json, re, struct, subprocess, time

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def module(name, filename):
    sp = importlib.util.spec_from_file_location(name, _frame_tool_path(filename))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def generate_c(source, path):
    L = module("meta_retained_link", "call-link.py")
    t = _frame_source_text(source, "quickjs-interpreter-call-link.h")
    # Reuse the complete actual allocator/refill/weak-link implementation.
    # Existing public helpers remain in their original object, byte-for-byte.
    for name in (
        "JS_FrameCallLinkPrepare",
        "JS_FrameCallLinkStats",
        "JS_FrameCallLinkResetWeak",
        "JS_FrameCallLinkVMState",
    ):
        at = t.index(name + "(")
        start = t.rfind("CALL_LINK_CODE ", 0, at)
        brace = t.index("{", at)
        end = brace + 1
        depth = 1
        while depth:
            depth += (t[end] == "{") - (t[end] == "}")
            end += 1
        t = t[:start] + t[end:]
    before = (
        "allocation_bytes=sizeof(*owner)+(size_t)sites*sizeof(*entry)+(unsigned)cb->byte_code_len;"
    )
    t = replace_one(
        t,
        before,
        "allocation_bytes=sizeof(*owner)+(size_t)sites*sizeof(*entry)+(sites==1 && direct_metadata?5*sizeof(uintptr_t):0)+(unsigned)cb->byte_code_len;",
    )
    before = "map=(uint8_t *)(void *)(owner->entries+sites);"
    t = replace_one(
        t,
        before,
        "map=(uint8_t *)(void *)(owner->entries+sites)+(sites==1 && direct_metadata?5*sizeof(uintptr_t):0);",
    )
    before = "if(call_link_is_site(scan_op) && index<sites) map[pos]=(uint8_t)index++;"
    t = replace_one(
        t,
        before,
        """if(call_link_is_site(scan_op) && index<sites) {
                    map[pos]=(uint8_t)index++;
                    if(sites==1 && direct_metadata) {
                        uintptr_t key=(uintptr_t)(cb->byte_code_buf+pos);
                        memcpy(map-5*sizeof(key),&key,sizeof(key));
                    }
                }""",
    )
    # The existing reset/stats loops derive floor((map-entries)/64).
    # Eight additional bytes keep that count exact and do not alter any entry.
    before = (
        "CALL_LINK_CODE void JS_FrameCallLinkMiss(JSFrameRegisterState *state,unsigned argc)\n{"
    )
    t = replace_one(
        t,
        before,
        """extern void JS_FrameCallLinkMiss(JSFrameRegisterState *,unsigned);
extern unsigned char JS_FrameCallMetaControl;
static CALL_LINK_INLINE unsigned char call_meta_mode(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode=*(volatile unsigned char *)&JS_FrameCallMetaControl;
#else
    __asm__ volatile("movb JS_FrameCallMetaControl(%%rip),%0":"=q"(mode)::"memory");
#endif
    if(!mode) {
        unsigned char desired=getenv("QJS_DISABLE_CALL_META_DIRECT")?2:(getenv("QJS_DISABLE_CALL_META_DESTINATION")?3:1);
#ifdef _MSC_VER
        _InterlockedCompareExchange8((volatile char *)&JS_FrameCallMetaControl,(char)desired,0);
        mode=*(volatile unsigned char *)&JS_FrameCallMetaControl;
#else
        unsigned char expected=0;
        __asm__ volatile("lock cmpxchgb %2,JS_FrameCallMetaControl(%%rip)":"+a"(expected):"0"(expected),"q"(desired):"memory","cc");
        __asm__ volatile("movb JS_FrameCallMetaControl(%%rip),%0":"=q"(mode)::"memory");
#endif
    }
    return mode;
}
CALL_LINK_CODE unsigned JS_FrameCallMetaState(void) { return call_meta_mode(); }
CALL_LINK_CODE unsigned JS_FrameCallMetaExtraBytes(const JSValue *caller)
{
    JSFrameCallLinkOwner *owner;
    if(JS_VALUE_GET_TAG(*caller)!=JS_TAG_OBJECT) return 0;
    owner=call_link_find(JS_VALUE_GET_OBJ(*caller));
    return owner && (uintptr_t)owner->weak.u.weak_ref_data==(uintptr_t)owner+168 ? 40 : 0;
}
CALL_LINK_CODE void JS_FrameCallMetaMiss(JSFrameRegisterState *state,unsigned argc)
{
    /* Nonallocating read only: startup configuration remains inside the
       original published/charged C boundary in call_link_prepare. */
    unsigned char inherited_mode;
#ifdef _MSC_VER
    inherited_mode=*(volatile unsigned char *)&JS_FrameCallMetaControl;
#else
    __asm__ volatile("movb JS_FrameCallMetaControl(%%rip),%0":"=q"(inherited_mode)::"memory");
#endif
    if(inherited_mode==2) {
        JS_FrameCallLinkMiss(state,argc);
        return;
    }""",
    )
    signature = "static CALL_LINK_INLINE JSFrameCallLinkEntry *call_link_prepare(JSRuntime *rt,\n    JSObject *caller,const uint8_t *pc,JSObject *callee,unsigned budget)\n{"
    t = replace_one(
        t,
        signature,
        "static CALL_LINK_INLINE unsigned char call_meta_mode(void);\n"
        + signature
        + "\n    unsigned direct_metadata=(call_meta_mode()&1)!=0;",
    )
    t = destination_c(t)
    # Real out-of-line C ABI leaves are compiler memory barriers. Their actual
    # x64 loads/LOCK CAS remain in ASM, with exact leaf native unwind records.
    t, reads = re.subn(
        r"\*\(volatile unsigned char \*\)&(JS_Frame\w+Control)", r"JS_FrameCallMetaLoadByte(&\1)", t
    )
    t, atomics = re.subn(
        r"_InterlockedCompareExchange8\(\s*\(\s*volatile\s+char\s*\*\s*\)\s*&\s*(JS_Frame\w+Control)\s*,\s*\(\s*char\s*\)\s*desired\s*,\s*0\s*\)",
        r"JS_FrameCallMetaInitByte(&\1,desired)",
        t,
    )
    assert (reads, atomics) == (5, 2), (reads, atomics)
    t = (
        "extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);\nextern unsigned char JS_FrameCallMetaInitByte(unsigned char *,unsigned char);\n"
        + t
    )
    path.write_text(L.native_prelude(source) + t, encoding="utf-8")
    path.with_suffix(".contract.json").write_text(
        json.dumps(
            dict(
                status="passed",
                parent_header_sha256=sha(
                    _frame_source_file(source, "quickjs-interpreter-call-link.h")
                ),
                generated_sha256=sha(path),
                owner_header=64,
                entry=64,
                single_pc_offset=128,
                single_map_offset=168,
                descriptor_bytes=40,
                multi_extra_bytes=0,
                frame_growth=0,
                weak_kinds_unchanged=True,
                cold_backlinks="16-byte native owner allocation prefix; one trailing pointer per primary plus map-tail alignment; one trailing pointer per secondary. Existing public layouts and entry/PC/map offsets retained.",
                unlink_ablation="QJS_DISABLE_CALL_LINK_BACKLINK selects the original list search with identical allocations and hot VM instructions.",
                existing_count_formula_exact_for_every_site_count=all(
                    (64 * n + (40 if n == 1 else 0)) // 64 == n for n in range(1, 256)
                ),
                stats="Legacy Stats payload byte count excludes the forty auxiliary bytes; add JS_FrameCallMetaExtraBytes. Runtime allocator accounts the complete allocation.",
                publication="PC/map complete before caller publication; both native destinations complete before target weak publication; existing nonthrowing allocation reentry and OOM/backoff preserved.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


@source_abi
def compile_objects(source, build, msvc):
    fields = current_abi()["offsets"]
    receipt = _frame_generated_file(build, "quickjs-call-metadata-generation.json")
    if receipt.exists():
        old = json.loads(receipt.read_text())
        assert old["generator_sha256"] == sha(__file__)
        for row in old["objects"]:
            assert sha(row["path"]) == row["sha256"]
        return old
    C = module("meta_coff", "object-adapter.py")
    M = module("meta_compile", "atod.py")
    proof = json.loads(
        (_frame_generated_file(build, "quickjs-interpreter-call-link.compile.json")).read_text()
    )
    compiler = Path(proof["compiler_command"][0])
    diag = any("QJS_INTERP_FRAME_DIAGNOSTICS" in a for a in proof["compiler_command"])
    cobj = _frame_generated_file(build, "quickjs-interpreter-call-metadata-c.obj")
    M.compile_extra(
        source,
        build,
        cobj,
        generator=generate_c,
        filename="quickjs-interpreter-call-metadata.c",
        late_name=".qjzzmd",
    )
    unrenamed = cobj.with_suffix(".unrenamed.obj")
    unrenamed.write_bytes(cobj.read_bytes())
    native = C.Coff(cobj.read_bytes())
    private_names = []
    for index, s in native.all_symbols.items():
        if s["section"] > 0 and s["storage"] == 2 and not s["name"].startswith("JS_FrameCallMeta"):
            name = "call_meta_emitted_" + hashlib.sha256(s["name"].encode()).hexdigest()[:32]
            at = len(native.strings)
            native.strings += name.encode() + b"\0"
            struct.pack_into("<II", native.data, native.table + index * native.stride, 0, at)
            private_names.append(dict(index=index, old=s["name"], new=name))
    cobj.write_bytes(native.finish())
    contracts = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-warm-contract.json")).read_text()
    )["contracts"]
    families = tuple(row["family"] for row in contracts)
    assert families in (("M",), ("M", "P")) and (not (msvc or diag) or families == ("M",)), families
    minimal = {
        tag: next(row["minimal_prefix"] for row in contracts if row["family"] == tag)
        for tag in families
    }
    assert all(
        len(v) == 7 and v[4] == "cmp DWORD PTR [r8-8], -1" and v[5].startswith("jne ")
        for v in minimal.values()
    )
    externals = ["JS_FrameCallLinkControl", "JS_FrameInterpPropertyCold_unwind"]
    if msvc:
        externals += ["JS_FrameCallMetaControl", "JS_FrameCallMetaHits"]
    for tag in families:
        externals += [
            "JS_FrameCallLink" + tag + "Probe",
            "JS_FrameCallLink" + tag + "Secondary",
            "JS_FrameCallMeta" + tag + "MapContinue",
            "JS_FrameCallLink" + tag + "Ready",
            "calllink_" + tag + "_hit",
            "calllink_" + tag + "_no_entry",
            minimal[tag][5].split()[-1],
        ]
    destination_blocks, destination_factory, destination_externals = destination_assembly(
        source, build, module("meta_destination_link", "call-link.py"), msvc, diag, families
    )
    externals = sorted(
        set(externals) | set(destination_externals) | ({"JS_FrameCallDestHits"} if msvc else set())
    )
    lines = (
        [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            *["EXTERN " + n + ":BYTE" for n in externals],
            ".qjzzmd SEGMENT ALIGN(16) 'CODE'",
        ]
        if msvc
        else [".intel_syntax noprefix", '.section .qjzzmd,"xr"']
    )
    rw_section = ".qjszzcm$zzcallmeta" if msvc else ".qjsmmet"
    runtime_rows = []
    cloned_opcodes = []

    def emit_raw(name, stream):
        if msvc:
            lines.extend(["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"])
            for line in stream:
                line = line.replace("rip+", "")
                lines.append(
                    line[:-1] + "::"
                    if line.endswith(":")
                    else re.sub(r"^(j\w+) (\w+)$", r"\1 NEAR PTR \2", line)
                )
            lines.extend([name + "_end LABEL BYTE", name + " ENDP"])
        else:
            lines.extend(
                [
                    ".p2align 4",
                    ".globl " + name + ", " + name + "_end",
                    ".def " + name + "; .scl 2; .type 32; .endef",
                    name + ":",
                    *stream,
                    name + "_end:",
                ]
            )

    # Only the initialized explicit-disable mode2 needs the legacy entry.
    # Mode0 is safe for provisional admission: the sole extended-owner producer
    # initializes real environment controls before allocating/publishing one.
    # Legacy explicit Prepare produces the old schema, which never uses a new
    # destination. Thus no disabled destination can execute before config.
    for tag in families:
        name = "JS_FrameCallMeta" + tag + "Probe"
        stream = [
            "cmp BYTE PTR [rip+JS_FrameCallMetaControl], 2",
            "je meta_" + tag + "_legacy",
            *minimal[tag],
            "cmp BYTE PTR [rip+JS_FrameCallLinkControl], 1",
            "jne calllink_" + tag + "_no_entry",
            "mov r10, QWORD PTR [rbp+8]",
            f"mov r10, QWORD PTR [r10+{fields['JSObject.first_weak_ref']}]",
            "test r10, r10",
            "jz calllink_" + tag + "_no_entry",
            "cmp DWORD PTR [r10], 1279983873",
            "jne calllink_" + tag + "_no_entry",
            "lea r11, [r10+168]",
            "cmp QWORD PTR [r10+16], r11",
            "jne JS_FrameCallMeta" + tag + "MapContinue",
            "cmp QWORD PTR [r10+128], r12",
            "jne JS_FrameCallMeta" + tag + "MapContinue",
            "lea r11, [r10+64]",
            "cmp QWORD PTR [r11+32], rdx",
            "jne meta_" + tag + "_secondary",
        ]

        def hit(offset):
            out = []
            if diag:
                out += ["lock inc QWORD PTR [rip+JS_FrameCallMetaHits]"]
            out += ["cmp BYTE PTR [rip+JS_FrameCallMetaControl], 3", "je calllink_" + tag + "_hit"]
            out += [
                "mov rax, QWORD PTR [r10+" + str(offset) + "]",
                "test rax, rax",
                "jz calllink_" + tag + "_hit",
            ]
            if diag:
                out += ["inc QWORD PTR [r10+32]", "inc QWORD PTR [rbx+2376]"]
            return out + [
                "mov r9, QWORD PTR [r11+40]",
                "mov r10, QWORD PTR [r11+56]",
                "mov QWORD PTR [rsp+40], r10",
                "movq xmm2, QWORD PTR [r11+48]",
                "jmp rax",
            ]

        stream += hit(136 if tag == "M" else 144)
        stream += [
            "meta_" + tag + "_secondary:",
            "mov QWORD PTR [rsp+40], r11",
            "mov r11, QWORD PTR [r11+24]",
            "cmp r11, 1",
            "jbe calllink_" + tag + "_admit",
            "cmp QWORD PTR [r11+32], rdx",
            "jne calllink_" + tag + "_admit",
        ]
        stream += hit(152 if tag == "M" else 160)
        stream += ["meta_" + tag + "_legacy:", "jmp JS_FrameCallLink" + tag + "Probe"]
        emit_raw(name, stream)
        runtime_rows.append((name, name + "_end"))
    # Admission stays in the inherited Probe. Only a live primary or
    # secondary identity match can enter these all-site activation dispatchers.
    # Explicit manager refills use the same complete live entry fields.
    warm_dispatch = []
    for tag in families:
        name = "JS_FrameCallMeta" + tag + "Warm"
        fallback = (
            "JS_FrameCallLinkOld" + tag + "_Ready" if msvc else "JS_FrameCallLink" + tag + "Ready"
        )
        stream = ["cmp BYTE PTR [rip+JS_FrameCallMetaControl], 1", "jne " + fallback]
        if msvc:
            stream += [
                "mov rax, QWORD PTR [r11+56]",
                "mov QWORD PTR [rsp+40], rax",
                "movq xmm2, QWORD PTR [r11+48]",
            ]
        # GNU's inherited hit has already loaded these exact live fields.
        stream += [
            "test WORD PTR [rsp+45], 2303",
            "jnz JS_FrameCallMeta" + tag + "General",
            "cmp BYTE PTR [rsp+44], 0",
            "je JS_FrameCallMeta" + tag + "Exact0",
            "cmp BYTE PTR [rsp+44], 1",
            "je JS_FrameCallMeta" + tag + "Exact1",
            "jmp JS_FrameCallMeta" + tag + "Exact",
        ]
        emit_raw(name, stream)
        runtime_rows.append((name, name + "_end"))
        warm_dispatch.append(
            dict(
                name=name,
                fallback=fallback,
                identity="Existing primary/secondary live callee and bytecode match",
                payload="Live entry geometry at56 and call_flags at48; no private PC or native destination slots",
                modes="Only initialized mode1 activates; modes0/2/3 retain exact inherited Ready",
                no_frame_or_root_or_ownership_changes=True,
            )
        )
    for name, stream in destination_blocks:
        emit_raw(name, stream)
        runtime_rows.append((name, name + "_end"))
    if not msvc:
        inherited = (
            (_frame_generated_file(build, "quickjs-interpreter-call-link-vm.S"))
            .read_text(encoding="utf-8")
            .splitlines()
        )
        for tag in families:
            lines += [".p2align 4"]
            for suffix in (
                "call0",
                "call1",
                "call2",
                "call3",
                "call",
                "tail_call",
                "call_method",
                "tail_call_method",
            ):
                old = "JS_FrameCallLink" + tag + "_" + suffix
                new = "JS_FrameCallMeta" + tag + "_" + suffix
                start = inherited.index(old + ":") + 1
                end = inherited.index(old + "_end:")
                stream = inherited[start:end]
                assert stream[-1] == "jmp JS_FrameCallLink" + tag + "Probe"
                assert not any(re.match(r"^(call|push|pop|ret)\b", s) for s in stream)
                copied = [*stream[:-1], "jmp JS_FrameCallLink" + tag + "Probe"]
                lines += [
                    ".globl " + new + ", " + new + "_end",
                    ".def " + new + "; .scl 2; .type 32; .endef",
                    new + ":",
                    *copied,
                    new + "_end:",
                ]
                cloned_opcodes.append(
                    dict(
                        old=old,
                        new=new,
                        original=stream,
                        copied=copied,
                        private_raw_frame_state=True,
                    )
                )
            runtime_rows.append(
                (
                    "JS_FrameCallMeta" + tag + "_call0",
                    "JS_FrameCallMeta" + tag + "_tail_call_method_end",
                )
            )
    c_leaf_rows = []
    emit_raw("JS_FrameCallMetaDestination", destination_factory)
    c_leaf_rows.append(("JS_FrameCallMetaDestination", "JS_FrameCallMetaDestination_end"))
    if msvc:
        helpers = [
            ("JS_FrameCallMetaLoadByte", ["movzx eax, BYTE PTR [rcx]", "ret"]),
            (
                "JS_FrameCallMetaInitByte",
                [
                    "xor eax, eax",
                    "lock cmpxchg BYTE PTR [rcx], dl",
                    "movzx eax, BYTE PTR [rcx]",
                    "ret",
                ],
            ),
        ]
        for name, body in helpers:
            lines += [
                "ALIGN 16",
                "PUBLIC " + name + ", " + name + "_end",
                name + " PROC",
                *body,
                name + "_end LABEL BYTE",
                name + " ENDP",
            ]
            c_leaf_rows.append((name, name + "_end"))
        lines += [
            "ALIGN 4",
            "PUBLIC JS_FrameCallMetaCLeafUnwind",
            "JS_FrameCallMetaCLeafUnwind LABEL BYTE",
            "DB 1,0,0,0",
        ]
    else:
        lines += [
            ".p2align 2",
            ".globl JS_FrameCallMetaCLeafUnwind",
            "JS_FrameCallMetaCLeafUnwind:",
            ".byte 1,0,0,0",
        ]
    if msvc:
        lines += [".qjzzmd ENDS", ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'"]
        for begin, end in runtime_rows:
            lines += [
                "DD IMAGEREL "
                + begin
                + ", IMAGEREL "
                + end
                + ", IMAGEREL JS_FrameInterpPropertyCold_unwind"
            ]
        for begin, end in c_leaf_rows:
            lines += [
                "DD IMAGEREL "
                + begin
                + ", IMAGEREL "
                + end
                + ", IMAGEREL JS_FrameCallMetaCLeafUnwind"
            ]
        lines += [
            ".pdata$zzzzzznullfast ENDS",
            ".qjs$zzzzzzzzzzzzmetaCFI0 SEGMENT ALIGN(4) READONLY 'CODE'",
            'DB "QJSMC_UNWIND_v1!"',
            "DD 0,1",
            "DQ 0",
            ".qjs$zzzzzzzzzzzzmetaCFI0 ENDS",
            ".qjs$zzzzzzzzzzzzmetaCFI3 SEGMENT ALIGN(4) READONLY 'CODE'",
            'DB "QJSMC_END_v1!!!!"',
            "DD 0,1",
            ".qjs$zzzzzzzzzzzzmetaCFI3 ENDS",
            "END",
        ]
        obj = _frame_generated_file(build, "quickjs-interpreter-call-metadata-asm.obj")
        asm = _frame_generated_file(build, "quickjs-interpreter-call-metadata.asm")
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(obj), str(asm)]
    else:
        lines += ['.section .pdata$zzzzzznullfast,"dr"', ".p2align 2"]
        for begin, end in runtime_rows:
            lines += [".rva " + begin + ", " + end + ", JS_FrameInterpPropertyCold_unwind"]
        for begin, end in c_leaf_rows:
            lines += [".rva " + begin + ", " + end + ", JS_FrameCallMetaCLeafUnwind"]
        lines += [
            ".section " + rw_section + ',"dw"',
            ".p2align 3",
            ".globl JS_FrameCallMetaControl, JS_FrameCallMetaHits, JS_FrameCallDestHits",
            "JS_FrameCallMetaControl:",
            ".byte 0",
            ".p2align 3",
            "JS_FrameCallMetaHits:",
            ".quad 0",
            "JS_FrameCallDestHits:",
            ".quad 0",
        ]
        obj = _frame_generated_file(build, "quickjs-interpreter-call-metadata-asm.obj")
        asm = _frame_generated_file(build, "quickjs-interpreter-call-metadata.S")
        command = [str(compiler), "-c", "-g0", str(asm), "-o", str(obj)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    p = subprocess.run(command, capture_output=True)
    asm.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, (p.stdout + p.stderr).decode(errors="replace"))
    co = C.Coff(obj.read_bytes())
    corrections = []
    for number, rec in enumerate(co.section_records, 1):
        name = module("meta_asm_names", "extension-merge.py").section_name(co, number)
        if name == ".qjzzmd" or name.startswith(".qjs$zzzzzzzzzzzzmetaCFI"):
            struct.pack_into("<I", co.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            offset, index, kind = struct.unpack_from("<IIH", co.data, at)
            if 5 <= kind <= 9:
                field = rec["raw"] + offset
                value = struct.unpack_from("<i", co.data, field)[0]
                struct.pack_into("<i", co.data, field, value - (kind - 4))
                struct.pack_into("<H", co.data, at + 8, 4)
                corrections.append(dict(offset=offset, kind=kind))
    obj.write_bytes(co.finish())
    state = dict(
        status="passed",
        generator_sha256=sha(__file__),
        source_tree_sha256=source_digest(source),
        msvc=msvc,
        diagnostics=diag,
        families=families,
        objects=[dict(path=str(p), sha256=sha(p)) for p in (cobj, obj)],
        asm=str(asm),
        asm_sha256=sha(asm),
        rel32_corrections=corrections,
        native_unrenamed=str(unrenamed),
        native_unrenamed_sha256=sha(unrenamed),
        private_names=private_names,
        cloned_opcodes=cloned_opcodes,
        runtime_rows=runtime_rows,
        c_leaf_runtime_rows=c_leaf_rows,
        warm_dispatch=warm_dispatch,
        opcode_admission="inherited Probe; new metadata Probe not on opcode path",
        cold_control_compiler_barriers=True,
        frame_growth=0,
        register_ABI_changes=0,
        only_single_site_extra_native_bytes=40,
        control="QJS_DISABLE_CALL_META_DIRECT",
    )
    receipt.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state


def packed(raw, C):
    old = C.Coff(raw)
    end = old.string_offset + len(old.strings)
    tail = raw[end:]
    if not tail:
        return raw, dict(post_string_tail_bytes=0, pointers=[])
    assert old.header == 20 and old.stride == 18
    result = bytearray(raw[: old.table] + tail + raw[old.table : end])
    struct.pack_into("<I", result, old.table_offset, old.table + len(tail))
    changes = []
    for number, rec in enumerate(old.section_records, 1):
        for field in (20, 24, 28):
            value = struct.unpack_from("<I", raw, rec["pos"] + field)[0]
            if not value:
                continue
            moved = (
                old.table + (value - end)
                if value >= end
                else value + len(tail)
                if value >= old.table
                else value
            )
            if moved != value:
                struct.pack_into("<I", result, rec["pos"] + field, moved)
                changes.append(dict(section=number, field=field, old=value, new=moved))
    after = C.Coff(bytes(result))
    assert after.all_symbols == old.all_symbols and after.sections == old.sections
    assert after.string_offset + len(after.strings) == len(result)
    for a, b in zip(old.section_records, after.section_records):
        for size, pointer in ((a["size"], 20), (a["relocation_bytes"], 24)):
            x = struct.unpack_from("<I", raw, a["pos"] + pointer)[0]
            y = struct.unpack_from("<I", result, b["pos"] + pointer)[0]
            assert (bytes(size) if not x else raw[x : x + size]) == (
                bytes(size) if not y else result[y : y + size]
            )
    return bytes(result), dict(post_string_tail_bytes=len(tail), pointers=changes)


def adapt(source, build, path, raw, *, msvc=False):
    C = module("meta_adapt_coff", "object-adapter.py")
    merge = module("meta_adapt_merge", "extension-merge.py")
    generation = compile_objects(source, build, msvc)
    before_raw, packing = packed(raw, C)
    before = C.Coff(before_raw)
    co = C.Coff(before_raw)
    scratch = _frame_generated_file(build, "call-metadata-link") / str(time.time_ns())
    scratch.mkdir(parents=True, exist_ok=False)
    target = scratch / "carrier.obj"
    original = scratch / "input.obj"
    original.write_bytes(before_raw)
    routes = []
    aliases = []
    objdump = find_objdump(build)

    def symbol(name):
        found = [s for s in before.all_symbols.values() if s["name"] == name and s["section"] > 0]
        assert len(found) == 1, (name, len(found))
        return found[0]

    def add_alias(name, old, offset):
        record = bytearray(co.stride)
        at = len(co.strings)
        co.strings += name.encode() + b"\0"
        struct.pack_into("<III", record, 0, 0, at, old["value"] + offset)
        struct.pack_into("<hH", record, 12, old["section"], 0)
        record[co.class_offset] = 2
        co.aliases.append(record)
        aliases.append(dict(name=name, section=old["section"], value=old["value"] + offset))

    def route(si, offset, newname, oldname):
        rec = co.section_records[si - 1]
        orig = before.section_records[si - 1]
        found = [
            (rec["reloc"] + 10 * i, struct.unpack_from("<IIH", co.data, rec["reloc"] + 10 * i))
            for i in range(rec["count"])
            if struct.unpack_from("<I", co.data, rec["reloc"] + 10 * i)[0] == offset
        ]
        new_index = co.external(newname)
        old_bytes = bytes(co.data[rec["raw"] + offset : rec["raw"] + offset + 4])
        if found:
            assert len(found) == 1
            at, (_, index, kind) = found[0]
            assert kind == 4
            s = before.all_symbols[index]
            addend = int.from_bytes(old_bytes, "little", signed=True)
            if not (s["name"] == oldname and addend == 0):
                wanted = symbol(oldname)
                assert s["section"] == wanted["section"] and s["value"] + addend == wanted["value"]
            struct.pack_into("<I", co.data, at + 4, new_index)
            record = dict(
                section=si,
                offset=offset,
                kind=4,
                mode="relocation",
                old_symbol=index,
                new_symbol=new_index,
            )
        else:
            wanted = symbol(oldname)
            assert (
                wanted["section"] == si
                and offset + 4 + int.from_bytes(old_bytes, "little", signed=True) == wanted["value"]
            )
            co.extra_relocations.setdefault(si, []).append(
                struct.pack("<IIH", offset, new_index, 4)
            )
            record = dict(
                section=si, offset=offset, kind=4, mode="decoded-direct-rel32", new_symbol=new_index
            )
        co.data[rec["raw"] + offset : rec["raw"] + offset + 4] = bytes(4)
        record.update(old_bytes=old_bytes.hex(), target=newname, original_target=oldname)
        routes.append(record)

    for tag in generation["families"]:
        name = "JS_FrameCallLink" + tag + "Probe"
        s = symbol(name)
        e = symbol(name + "_end")
        rec = before.section_records[s["section"] - 1]
        body = before_raw[rec["raw"] + s["value"] : rec["raw"] + e["value"]]
        pattern = bytes.fromhex("498b4218")
        assert body.count(pattern) == 1
        offset = body.index(pattern)
        exact_body = scratch / (tag + "-probe-body.bin")
        exact_body.write_bytes(body)
        command = [
            str(objdump),
            "-D",
            "-w",
            "-b",
            "binary",
            "-m",
            "i386:x86-64",
            "-M",
            "intel",
            "--adjust-vma=" + str(s["value"]),
            str(exact_body),
        ]
        listing = subprocess.check_output(command, text=True, encoding="utf-8", errors="replace")
        (scratch / (tag + "-probe.asm.txt")).write_text(listing, encoding="utf-8")
        decoded = []
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-fA-F]+):\s+((?:[0-9a-fA-F]{2}[ \t]+)+)(\S.*)$", line)
            if m:
                decoded.append((int(m[1], 16), bytes.fromhex(m[2]), m[3]))
        assert decoded and decoded[0][0] == s["value"]
        assert decoded[-1][0] + len(decoded[-1][1]) == e["value"]
        assert all(a[0] + len(a[1]) == b[0] for a, b in zip(decoded, decoded[1:]))
        hit = [i for i, r in enumerate(decoded) if r[0] == s["value"] + offset]
        assert (
            len(hit) == 1
            and decoded[hit[0]][1] == pattern
            and decoded[hit[0] - 1][2].startswith("jne ")
        )
        add_alias("JS_FrameCallMeta" + tag + "MapContinue", s, offset)
        # The old hit's final JMP is the only new hot operand. Both primary
        # and secondary identities share it. Every old instruction remains.
        finish = symbol(name + "_end")
        assert finish["section"] == s["section"]
        rr = before.section_records[s["section"] - 1]
        body = before_raw[rr["raw"] + s["value"] : rr["raw"] + finish["value"]]
        pattern = bytes.fromhex("4d8b4b28e9" if msvc else "f3410f7e5330e9")
        hits = [i for i in range(len(body)) if body.startswith(pattern, i)]
        assert len(hits) == 1, (name, hits)
        field = s["value"] + hits[0] + len(pattern)
        oldready = (
            "JS_FrameCallLinkOld" + tag + "_Ready" if msvc else "JS_FrameCallLink" + tag + "Ready"
        )
        route(s["section"], field, "JS_FrameCallMeta" + tag + "Warm", oldready)
        cold = symbol("JS_FrameCallLink" + tag + "Cold")
        end = symbol("JS_FrameCallLink" + tag + "Cold_end")
        rr = before.section_records[cold["section"] - 1]
        fields = []
        for i in range(rr["count"]):
            off, index, kind = struct.unpack_from("<IIH", before_raw, rr["reloc"] + 10 * i)
            if (
                cold["value"] <= off < end["value"]
                and before.all_symbols[index]["name"] == "JS_FrameCallLinkMiss"
            ):
                assert kind == 4 and before_raw[rr["raw"] + off - 1] == 0xE8
                fields.append(off)
        assert len(fields) == 1
        route(cold["section"], fields[0], "JS_FrameCallMetaMiss", "JS_FrameCallLinkMiss")
    routed = bytes(co.finish())
    check = C.Coff(routed)
    for index, s in before.all_symbols.items():
        assert check.all_symbols[index] == s
    for si, (a, b) in enumerate(zip(before.section_records, check.section_records), 1):
        old = before_raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])
        new = bytearray(routed[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"]))
        for r in routes:
            if r["section"] == si:
                new[r["offset"] : r["offset"] + 4] = bytes.fromhex(r["old_bytes"])
        assert bytes(new) == old, ("Unlisted old section change", si)
        oldrels = [
            struct.unpack_from("<IIH", before_raw, a["reloc"] + 10 * i) for i in range(a["count"])
        ]
        newrels = [
            list(struct.unpack_from("<IIH", routed, b["reloc"] + 10 * i)) for i in range(b["count"])
        ]
        for r in routes:
            if r["section"] != si:
                continue
            rows = [v for v in newrels if v[0] == r["offset"]]
            assert len(rows) == 1
            assert rows[0][1:] == [r["new_symbol"], 4]
            if r["mode"] == "relocation":
                rows[0][1] = r["old_symbol"]
            else:
                newrels.remove(rows[0])
        assert sorted(map(tuple, newrels)) == sorted(oldrels)
    assert len(routes) == 2 * len(generation["families"])
    routed_unpacked = scratch / "routed-before-pack.obj"
    routed_unpacked.write_bytes(routed)
    routed, routed_packing = packed(routed, C)
    target.write_bytes(routed)
    result = target.read_bytes()
    record = scratch / "adaptation.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                source_tree_sha256=source_digest(source),
                generator_sha256=sha(__file__),
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                packed_sha256=hashlib.sha256(before_raw).hexdigest(),
                packing=packing,
                original_input=str(original),
                routed_unpacked=str(routed_unpacked),
                routed_unpacked_sha256=sha(routed_unpacked),
                routed_packing=routed_packing,
                routed_sha256=hashlib.sha256(routed).hexdigest(),
                output=str(target),
                output_sha256=sha(target),
                routes=routes,
                aliases=aliases,
                old_symbols_preserved=True,
                all_other_old_section_bytes_and_relocations_identical=True,
                generation=str(
                    _frame_generated_file(build, "quickjs-call-metadata-generation.json")
                ),
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(record)


OP_RE = re.compile(r"^JS_FrameCallLink([MP])_(call[0-3]?|tail_call|call_method|tail_call_method)$")


def has_table_refs(coff):
    for rec in coff.section_records:
        for i in range(rec["count"]):
            _, index, _ = struct.unpack_from("<IIH", coff.data, rec["reloc"] + 10 * i)
            s = coff.all_symbols[index]
            if s["section"] == 0 and OP_RE.fullmatch(s["name"]):
                return True
    return False


def route_tables(source, build, path, raw):
    C = module("meta_tables_coff", "object-adapter.py")
    before_raw, packing = packed(raw, C)
    before = C.Coff(before_raw)
    co = C.Coff(before_raw)
    rows = []
    for si, rec in enumerate(co.section_records, 1):
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, index, kind = struct.unpack_from("<IIH", co.data, at)
            s = before.all_symbols[index]
            m = OP_RE.fullmatch(s["name"])
            if not m or s["section"] != 0:
                continue
            assert kind in (1, 4), (path, si, off, kind)
            width = 8 if kind == 1 else 4
            assert bytes(co.data[rec["raw"] + off : rec["raw"] + off + width]) == bytes(width)
            name = "JS_FrameCallMeta" + m[1] + "_" + m[2]
            target = co.external(name)
            struct.pack_into("<I", co.data, at + 4, target)
            rows.append(
                dict(
                    section=si,
                    offset=off,
                    kind=kind,
                    width=width,
                    old_symbol=index,
                    target=name,
                    new_symbol=target,
                )
            )
    result = bytes(co.finish())
    after = C.Coff(result)
    assert after.count == before.count
    assert all(after.all_symbols[index] == s for index, s in before.all_symbols.items())
    for si, (a, b) in enumerate(zip(before.section_records, after.section_records), 1):
        assert (a["size"], a["count"], a["flags"]) == (b["size"], b["count"], b["flags"])
        assert (before_raw[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])) == (
            result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"])
        )
        line_a = struct.unpack_from("<I", before_raw, a["pos"] + 28)[0]
        line_b = struct.unpack_from("<I", result, b["pos"] + 28)[0]
        count_a = struct.unpack_from("<H", before_raw, a["pos"] + 34)[0]
        count_b = struct.unpack_from("<H", result, b["pos"] + 34)[0]
        assert (
            count_a == count_b
            and before_raw[line_a : line_a + 6 * count_a] == result[line_b : line_b + 6 * count_b]
        )
        expected = [
            struct.unpack_from("<IIH", before_raw, a["reloc"] + 10 * i) for i in range(a["count"])
        ]
        actual = [
            list(struct.unpack_from("<IIH", result, b["reloc"] + 10 * i)) for i in range(b["count"])
        ]
        for r in rows:
            if r["section"] != si:
                continue
            hits = [v for v in actual if v[0] == r["offset"]]
            assert len(hits) == 1 and hits[0][1:] == [r["new_symbol"], r["kind"]]
            hits[0][1] = r["old_symbol"]
        assert list(map(tuple, actual)) == expected
    folder = _frame_generated_file(build, "call-metadata-link") / str(time.time_ns())
    folder.mkdir(parents=True, exist_ok=False)
    record = folder / "table-routing.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                packing=packing,
                routes=rows,
                all_old_payloads_and_symbols_identical=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(record)


def coalesce_native_packet(
    raw,
    old_count,
    C,
    merge,
    *,
    prefix=".qjs$zzzzzzzzzzzzmetaCFI",
    group=".qjs$zzzzzzzzzzrvV",
    magic=b"QJSMC_UNWIND_v1!",
    footer_magic=b"QJSMC_END_v1!!!!",
    capacity=0,
):
    """Coalesce only new MS input names; retain every old byte/index/section."""
    before = C.Coff(raw)
    result = bytearray(raw)
    names = {i: merge.section_name(before, i) for i in range(1, before.count + 1)}
    packet = [i for i in range(old_count + 1, before.count + 1) if names[i].startswith(prefix)]
    assert len(packet) >= 4
    headers = [i for i in packet if names[i] == prefix + "0"]
    footers = [i for i in packet if names[i] == prefix + "3"]
    assert len(headers) == len(footers) == 1
    native = [i for i in packet if names[i] in (prefix + "1", prefix + "2")]
    assert len(native) + 2 == len(packet)
    for i in native:
        rec = before.section_records[i - 1]
        assert rec["size"] % 12 == 0 and rec["count"] == rec["size"] // 4
        assert all(
            struct.unpack_from("<H", raw, rec["reloc"] + 10 * j + 8)[0] == 3
            for j in range(rec["count"])
        )
    header = before.section_records[headers[0] - 1]
    footer = before.section_records[footers[0] - 1]
    assert raw[header["raw"] : header["raw"] + 32] == magic + struct.pack("<IIQ", 0, 1, 0)
    assert raw[footer["raw"] : footer["raw"] + 24] == footer_magic + struct.pack("<II", capacity, 1)
    order = [i for i in range(1, before.count + 1) if i not in packet] + headers + native + footers
    assert order[:old_count] == list(range(1, old_count + 1)) and sorted(order) == list(
        range(1, before.count + 1)
    )
    mapping = {old: new for new, old in enumerate(order, 1)}
    at = len(before.strings)
    before.strings += group.encode() + bytes(1)
    for number in packet:
        rec = before.section_records[number - 1]
        label = ("/" + str(at)).encode()
        assert len(label) <= 8
        result[rec["pos"] : rec["pos"] + 8] = label.ljust(8, bytes(1))
    symbols = []
    associations = []
    for index, symbol in before.all_symbols.items():
        pos = before.table + index * before.stride
        if symbol["section"] > 0:
            struct.pack_into("<h", result, pos + 12, mapping[symbol["section"]])
        if (
            symbol["name"].startswith(prefix)
            and symbol["section"] in packet
            and symbol["storage"] == 3
        ):
            struct.pack_into("<II", result, pos, 0, at)
            symbols.append(index)
        if (
            result[pos + 17]
            and symbol["storage"] == 3
            and symbol["type"] == 0
            and symbol["section"] > 0
        ):
            assert result[pos + 17] == 1
            association = struct.unpack_from("<h", result, pos + 18 + 12)[0]
            if result[pos + 18 + 14] == 5 and association > 0:
                struct.pack_into("<h", result, pos + 18 + 12, mapping[association])
                associations.append(dict(index=index, old=association, new=mapping[association]))
    headers_raw = {
        i: bytes(result[r["pos"] : r["pos"] + 40]) for i, r in enumerate(before.section_records, 1)
    }
    for new, old in enumerate(order, 1):
        pos = before.header + 40 * (new - 1)
        result[pos : pos + 40] = headers_raw[old]
    # Append the one new COFF string without relocating any existing payload.
    result[before.string_offset : before.string_offset + len(before.strings)] = before.strings
    struct.pack_into("<I", result, before.string_offset, len(before.strings))
    after = C.Coff(bytes(result))
    for i, old in enumerate(before.sections, 1):
        expected = dict(old)
        if i in packet:
            expected["name"] = "/" + str(at)
        assert merge.section_name(after, mapping[i]) == (group if i in packet else names[i])
        assert after.sections[mapping[i] - 1] == expected, (i, old, after.sections[mapping[i] - 1])
    for index, symbol in before.all_symbols.items():
        expected = {**symbol, "section": mapping.get(symbol["section"], symbol["section"])}
        if index in symbols:
            expected["name"] = group
        assert after.all_symbols[index] == expected
    assert after.sections[:old_count] == before.sections[:old_count]
    return bytes(result), dict(
        old_sections=old_count,
        packet_original_sections=packet,
        section_order=order,
        section_mapping=mapping,
        renamed_definition_indexes=symbols,
        association_changes=associations,
        native_records=sum(before.section_records[i - 1]["size"] // 12 for i in native),
        new_input_group=group,
        all_payloads_and_relocations_identical=True,
        old_sections_and_symbols_identical=True,
    )


def append_control(source, build, path, raw):
    """Append sixteen owned zero bytes in the existing register RW section."""
    assert path.name == "quickjs-interpreter-register.obj"
    C = module("meta_control_coff", "object-adapter.py")
    M = module("meta_control_names", "extension-merge.py")
    packed_raw, packing = packed(raw, C)
    before = C.Coff(packed_raw)
    assert before.header == 20 and before.stride == 18
    assert len(packed_raw) == before.string_offset + len(before.strings)
    found = [i for i in range(1, before.count + 1) if M.section_name(before, i) == ".qjszzcm"]
    assert len(found) == 1
    number = found[0]
    rec = before.section_records[number - 1]
    assert rec["flags"] & 0xE0000000 == 0xC0000000 and rec["size"] % 8 == 0
    names = ("JS_FrameCallMetaControl", "JS_FrameCallMetaHits", "JS_FrameCallDestHits")
    assert not any(s["name"] in names for s in before.all_symbols.values())
    payload = packed_raw[rec["raw"] : rec["raw"] + rec["size"]] + bytes(8 * len(names))
    strings = bytearray(before.strings)
    symbols = bytearray()
    for i, name in enumerate(names):
        offset = len(strings)
        strings += name.encode() + bytes(1)
        symbols += struct.pack("<IIIhHBB", 0, offset, rec["size"] + i * 8, number, 0, 2, 0)
    struct.pack_into("<I", strings, 0, len(strings))
    result = bytearray(
        packed_raw[: before.table]
        + payload
        + packed_raw[before.table : before.string_offset]
        + symbols
        + strings
    )
    table = before.table + len(payload)
    struct.pack_into("<II", result, before.table_offset, table, before.symbol_count + len(names))
    struct.pack_into("<II", result, rec["pos"] + 16, len(payload), before.table)
    aux = []
    for index, symbol in before.all_symbols.items():
        pos = table + index * 18
        if (
            symbol["section"] == number
            and symbol["storage"] == 3
            and symbol["type"] == 0
            and result[pos + 17]
        ):
            assert (
                result[pos + 17] == 1
                and struct.unpack_from("<I", result, pos + 18)[0] == rec["size"]
            )
            struct.pack_into("<I", result, pos + 18, len(payload))
            aux.append(index)
    after = C.Coff(bytes(result))
    assert after.count == before.count and after.symbol_count == before.symbol_count + len(names)
    for i, (old, new) in enumerate(zip(before.sections, after.sections), 1):
        if i == number:
            expected = {**old, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
            assert new == expected
        else:
            assert old == new
    for index, symbol in before.all_symbols.items():
        assert after.all_symbols[index] == symbol
    for i, name in enumerate(names):
        s = after.all_symbols[before.symbol_count + i]
        assert s == dict(name=name, section=number, type=0, storage=2, value=rec["size"] + 8 * i)
    folder = _frame_generated_file(build, "call-metadata-link") / str(time.time_ns())
    folder.mkdir(parents=True, exist_ok=False)
    record = folder / "rw-append.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                packing=packing,
                section=number,
                old_bytes=rec["size"],
                new_bytes=len(payload),
                new_symbols=names,
                updated_size_auxiliaries=aux,
                all_old_payload_prefixes_and_symbols_retained=True,
                no_new_input_section=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return bytes(result), str(record)


def append_module(source, build, path, raw, *, msvc=False):
    C = module("meta_last_carrier_coff", "object-adapter.py")
    merge = module("meta_last_merge", "extension-merge.py")
    assert path.name == (
        "quickjs-interpreter-null-proto.obj" if msvc else "quickjs-interpreter.c.obj"
    )
    base_owner = "JS_FrameNativeCScopeVM" if msvc else "JS_RunFrame"
    generation = compile_objects(source, build, msvc)
    packed_raw, packing = packed(raw, C)
    old = C.Coff(packed_raw)
    assert any(s["name"] == base_owner and s["section"] > 0 for s in old.all_symbols.values())
    if msvc:
        names = [merge.section_name(old, i) for i in range(1, old.count + 1)]
        assert ".qjs$zzzzzzzzzzrvV" in names, (
            "Append after the existing complete source/scope contribution"
        )
    folder = _frame_generated_file(build, "call-metadata-link") / str(time.time_ns())
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / "last-carrier.obj"
    target.write_bytes(packed_raw)
    rw_section = ".qjszzcm$zzcallmeta" if msvc else ".qjsmmet"
    merge.append(
        target,
        Path(generation["objects"][0]["path"]),
        "JS_FrameCallMetaMiss",
        "call-metadata-c",
        keep_all=True,
        code_input=".qjzzmd",
        code_output=".qjs$zzzzzzzzzzrvV" if msvc else ".qjsmeta$C",
        pdata_output=".qjs$zzzzzzzzzzzzmetaCFI1" if msvc else ".qjsmfn$C",
        metadata_inputs=(".voltbl",) if msvc else (),
        base_owner=base_owner,
        baseline_sections=(),
    )
    merge.append(
        target,
        Path(generation["objects"][1]["path"]),
        "JS_FrameCallMetaMProbe",
        "call-metadata-asm",
        keep_all=True,
        code_input=".qjzzmd",
        code_output=".qjs$zzzzzzzzzzrvV" if msvc else ".qjsmeta$A",
        pdata_output=".qjs$zzzzzzzzzzzzmetaCFI2" if msvc else ".qjsmfn$A",
        allocated_metadata_inputs=(".qjs$zzzzzzzzzzzzmetaCFI0", ".qjs$zzzzzzzzzzzzmetaCFI3")
        if msvc
        else (),
        writable_metadata_inputs=() if msvc else (rw_section,),
        base_owner=base_owner,
        baseline_sections=(),
    )
    strict = target.read_bytes()
    co = C.Coff(strict)
    result = bytearray(strict)
    flags = []
    for number, rec in enumerate(co.section_records, 1):
        if number <= old.count:
            continue
        name = merge.section_name(co, number)
        if name in (
            ".qjs$zzzzzzzzzzzzmetaCFI1",
            ".qjs$zzzzzzzzzzzzmetaCFI2",
            ".qjsmfn$C",
            ".qjsmfn$A",
        ):
            assert rec["flags"] & 0xE0000000 in (0x40000000, 0x60000000)
            value = (rec["flags"] & ~0xE0) | 0x60000040 if msvc else rec["flags"] & ~0x20000000
            struct.pack_into("<I", result, rec["pos"] + 36, value)
            flags.append(dict(section=number, old=rec["flags"], new=value))
    after = C.Coff(bytes(result))
    assert after.sections[: old.count] == old.sections
    assert after.all_symbols == co.all_symbols
    for number, (a, b) in enumerate(zip(co.section_records, after.section_records), 1):
        assert (strict[a["raw"] : a["raw"] + a["size"]] if a["raw"] else bytes(a["size"])) == (
            result[b["raw"] : b["raw"] + b["size"]] if b["raw"] else bytes(b["size"])
        )
    coalescing = None
    if msvc:
        result, coalescing = coalesce_native_packet(bytes(result), old.count, C, merge)
    record = folder / "last-carrier.json"
    record.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                packing=packing,
                strict_output=str(target),
                strict_output_sha256=sha(target),
                output_sha256=hashlib.sha256(result).hexdigest(),
                new_native_rows_readonly_headers=flags,
                native_packet_coalescing=coalescing,
                old_sections_and_symbols_preserved=True,
                existing_carrier="existing register RX/RW input"
                if msvc
                else "existing frame C input; explicit terminal GNU groups",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return bytes(result), str(record)


def finalize_image(image, previous, writable):
    """Independent native-row identity, including repeated finalizer invocations."""
    raw = image.read_bytes()
    pe = struct.unpack_from("<I", raw, 60)[0]
    op = pe + 24
    assert raw[:2] == b"MZ" and raw[pe : pe + 4] == b"PE\0\0"
    count = struct.unpack_from("<H", raw, pe + 6)[0]
    at = op + struct.unpack_from("<H", raw, pe + 20)[0]
    sections = []
    for i in range(count):
        pos = at + 40 * i
        name = raw[pos : pos + 8].split(bytes(1))[0].decode("ascii")
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

    def content(rva, size):
        sec = next(
            s for s in sections if s["rva"] <= rva and rva + size <= s["rva"] + s["physical_size"]
        )
        off = sec["physical"] + rva - sec["rva"]
        return raw[off : off + size]

    gnu = next((s for s in sections if s["name"] == ".qjsmfn"), None)
    carrier = gnu or next((s for s in sections if s["name"] == ".qjscold"), None)
    if carrier is None:
        return previous(image, None)
    magic = b"QJSCW_UNWIND_v1!" if gnu else b"QJSMC_UNWIND_v1!"
    footer = b"QJSCW_END_v1!!!!" if gnu else b"QJSMC_END_v1!!!!"
    data = raw[carrier["physical"] : carrier["physical"] + carrier["size"]]
    positions = [i for i in range(len(data)) if data.startswith(magic, i)]
    if not positions:
        return previous(image, None)
    assert len(positions) == 1
    tails = [i for i in range(len(data)) if data.startswith(footer, i)]
    assert len(tails) == 1
    lo = positions[0] + 32
    hi = tails[0]
    assert hi > lo and (hi - lo) % 12 == 0
    native = [data[i : i + 12] for i in range(lo, hi, 12)]
    assert all(any(row) for row in native)
    directory, span = struct.unpack_from("<II", raw, op + 112 + 3 * 8)
    assert span and span % 12 == 0
    table = content(directory, span)
    rows = set(table[i : i + 12] for i in range(0, span, 12))
    present = [row in rows for row in native]
    if all(present):
        return dict(
            status="already-finalized",
            image=str(image),
            image_sha256=sha(image),
            metadata_native_rows=len(native),
            complete_native_row_identity_verified=True,
        )
    assert not any(present), "Partially finalized direct-metadata native rows"
    inherited = previous(image, None)
    options = {} if gnu else dict(magic=magic, footer=footer, directory_in_carrier_is_final=False)
    result = writable(image, None, carrier_name=carrier["name"], **options)
    assert result["status"] == "passed", result
    result["inherited_call_metadata_finalization"] = inherited
    result["direct_metadata_generator_sha256"] = sha(__file__)
    return result


def destination_c(text):
    before = "    entry->weak.next_weak_ref=callee->first_weak_ref;"
    extra = """    if(direct_metadata && (uintptr_t)owner->weak.u.weak_ref_data==(uintptr_t)owner+168) {
        unsigned destination_kind=0;
        if(!padding && !(kind&8)) {
            unsigned locals=((const unsigned char *)b)[FRAME_CALL_LOCALS_OFFSET];
            destination_kind=locals==0?2:locals==1?3:1;
        }
        JS_FrameCallMetaDestination(destination_kind,(uintptr_t *)(void *)
            ((unsigned char *)owner+(entry==primary?136:152)));
    }
"""
    text = replace_one(text, before, extra + before)
    return "extern void JS_FrameCallMetaDestination(unsigned,uintptr_t *);\n" + text


@source_abi
def destination_assembly(source, build, L, msvc, diag, families):
    fields = current_abi()["offsets"]
    old, aliases, external, _ = L._vm_blocks(source, build, msvc=msvc)
    blocks = []
    contracts = []
    for tag in families:
        name = "JS_FrameCallLink" + tag + "Ready"
        original = next(body for label, body in old if label == name)
        for kind in ("General", "Exact", "Exact0", "Exact1"):
            body = list(original)
            if kind != "General":
                # Cold-selected only when cached padding==0 and var_ref_count==0.
                at = body.index(
                    "calllink_"
                    + tag
                    + ("_publish_" if tag == "P" else "_")
                    + "interp_meta_call_arity_ok:"
                )
                body = body[at + 1 :]
                lo = body.index("movzx edx, BYTE PTR [rsp+45]")
                hi = body.index(
                    "calllink_"
                    + tag
                    + ("_publish_" if tag == "P" else "_")
                    + "interp_meta_call_pad_done:"
                )
                body[lo : hi + 1] = []
                lo = body.index("test BYTE PTR [rsp+46], 8")
                hi = body.index(
                    "calllink_"
                    + tag
                    + ("_publish_" if tag == "P" else "_")
                    + "interp_meta_call_refs_done:"
                )
                body[lo : hi + 1] = []
                if kind in ("Exact0", "Exact1"):
                    lo = body.index("movzx ecx, BYTE PTR [rsp+44]")
                    hi = body.index(
                        "calllink_"
                        + tag
                        + ("_publish_" if tag == "P" else "_")
                        + "interp_meta_call_locals_done:"
                    )
                    body[lo : hi + 1] = (
                        ["mov r13, r14"]
                        if kind == "Exact0"
                        else ["movdqu XMMWORD PTR [r14], xmm1", "lea r13, [r14+16]"]
                    )
            body = [
                line.replace("calllink_" + tag + "_", "callmeta_dest_" + tag + kind + "_")
                for line in body
            ]
            assert not any(re.match(r"^(call|push|pop|ret)\b", line) for line in body)
            assert (
                sum(
                    line == f"dec DWORD PTR [rsi+{fields['JSContext.interrupt_counter']}]"
                    for line in body
                )
                == 1
            )
            assert sum("add QWORD PTR [rbx+32]" in line for line in body) == 1
            if diag:
                body.insert(0, "lock inc QWORD PTR [rip+JS_FrameCallDestHits]")
            # The old explicit management helper can refill an existing owner.
            # Revalidate exactly the fields folded by a specialized destination,
            # before any frame/root/depth mutation. General consumes all live fields.
            fallback = "JS_FrameCallMeta" + tag + "General"
            if kind == "Exact":
                body = ["test WORD PTR [rsp+45], 2303", "jnz " + fallback] + body
            elif kind == "Exact0":
                body = ["test DWORD PTR [rsp+44], 589823", "jnz " + fallback] + body
            elif kind == "Exact1":
                body = [
                    "mov eax, DWORD PTR [rsp+44]",
                    "and eax, 589823",
                    "cmp eax, 1",
                    "jne " + fallback,
                ] + body

            label = "JS_FrameCallMeta" + tag + kind
            blocks.append((label, body))
            contracts.append(
                dict(
                    name=label,
                    cold_selection=kind,
                    instructions=len(body),
                    stack_quota_depth_and_frame_ownership_retained=True,
                    pending_tail_method_strict_and_context_fields_retained=True,
                    eliminated_only_cold_selected_and_live_guarded_padding_refs_or_locals=kind
                    != "General",
                )
            )
    # Real C leaf: ECX=kind, RDX=two native pointer slots. No JS/C/GC call.
    factory = []
    for number, kind in ((1, "Exact"), (2, "Exact0"), (3, "Exact1")):
        factory += ["cmp ecx, " + str(number), "je callmeta_factory_" + kind]
    for kind in ("General", "Exact", "Exact0", "Exact1"):
        if kind != "General":
            factory += ["callmeta_factory_" + kind + ":"]
        ptag = "P" if "P" in families else "M"
        factory += [
            "lea r8, [rip+JS_FrameCallMetaM" + kind + "]",
            "lea r9, [rip+JS_FrameCallMeta" + ptag + kind + "]",
            "jmp callmeta_factory_done",
        ]
    factory += [
        "callmeta_factory_done:",
        "mov QWORD PTR [rdx], r8",
        "mov QWORD PTR [rdx+8], r9",
        "ret",
    ]
    external.add("calllink_M_admit")
    if "P" in families:
        external.add("calllink_P_admit")
    (_frame_generated_file(build, "quickjs-call-destination-contract.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                source_tree_sha256=source_digest(source),
                generator_sha256=sha(__file__),
                frame_growth=0,
                entry_bytes=64,
                owner_header_bytes=64,
                single_site_aux_bytes=40,
                primary_destination_offsets=[136, 144],
                secondary_destination_offsets=[152, 160],
                pc_offset=128,
                map_offset=168,
                contracts=contracts,
                lifetime="Null legacy-manager destinations use original Ready; specialized entries revalidate live padding/refs/locals before mutation. Native code pointers only; every use follows live callee identity and exact owner schema/PC. Weak reset clears callee/bytecode/geometry before a pointer could be reused.",
                control="QJS_DISABLE_CALL_META_DESTINATION selects mode3: identical metadata/owner allocation and original guarded hit body; QJS_DISABLE_CALL_META_DIRECT selects old owner format and old miss delegate.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return blocks, factory, external
