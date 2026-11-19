"""Native get_length; exact logical length, guarded RC consumption, inherited slow exits."""

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
CODE = ".qjzzlc"
RW = ".qjzzlm$C"
CFI = ".qjzzlf"
MAGIC = b"QJSLN_UNWIND_v1!"
FOOTER = b"QJSLN_END_v1!!!!"
assert len(MAGIC) == len(FOOTER) == 16


def module(source, name):
    spec = importlib.util.spec_from_file_location(
        "length_" + name.replace("-", "_"), _frame_tool_path(name + ".py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BODY = r"""
#include <stdatomic.h>
typedef struct JSFrameLengthData {
    _Atomic(unsigned char) mode;
    unsigned char diagnostic;
    unsigned char reserved[6];
    _Atomic(uint64_t) strings,arrays,misses,abi;
} JSFrameLengthData;
_Static_assert(sizeof(JSFrameLengthData)==40 && offsetof(JSFrameLengthData,strings)==8 &&
    offsetof(JSFrameLengthData,arrays)==16 && offsetof(JSFrameLengthData,misses)==24 &&
    offsetof(JSFrameLengthData,abi)==32,"length control ABI");
_Static_assert(sizeof(JSValue)==16 && JS_TAG_INT==0 && JS_TAG_FLOAT64==8 &&
    JS_TAG_STRING==-7 && JS_TAG_OBJECT==-1 && JS_CLASS_ARRAY==2 &&
    offsetof(JSObject,class_id)==QJS_ABI_OFF_JSObject_class_id &&
    offsetof(JSObject,prop)==QJS_ABI_OFF_JSObject_prop,
    "length native object/tag ABI");
#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(offsetof(JSMallocBlockHeader,user_data)-offsetof(JSMallocBlockHeader,ref_count)==-QJS_ABI_REF_COUNT_OFFSET,
    "length prefix reference count ABI");
#else
_Static_assert(offsetof(JSObject,header.ref_count)==QJS_ABI_REF_COUNT_OFFSET &&
    offsetof(JSString,header.ref_count)==QJS_ABI_REF_COUNT_OFFSET,
    "length inline reference count ABI");
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define LENGTH_DIAG 1
#else
#define LENGTH_DIAG 0
#endif
#ifdef _MSC_VER
#pragma section(".qjzzlm$C",read,write)
__declspec(allocate(".qjzzlm$C"))
#else
__attribute__((section(".qjzzlm$C"),used,aligned(8)))
#endif
JSFrameLengthData JS_FrameLengthData={0,LENGTH_DIAG,{1}};
FRAME_CODE void JS_FrameLengthConfigure(void)
{
    JSString s={0};JSObject object={0};uint32_t bits;unsigned char flags;
    s.len=0x1234;s.is_wide_char=1;object.fast_array=1;
    memcpy(&bits,(char *)&s+QJS_ABI_BIT_JSString_len_BYTE,sizeof(bits));
    memcpy(&flags,(char *)&object+QJS_ABI_BIT_JSObject_fast_array_BYTE,1);
    unsigned valid=bits==0x80001234u && flags==QJS_ABI_BIT_JSObject_fast_array_MASK;
    unsigned char mode=valid && !getenv("QJS_DISABLE_NATIVE_LENGTH")?1:2;
    atomic_store_explicit(&JS_FrameLengthData.abi,valid,memory_order_relaxed);
    atomic_store_explicit(&JS_FrameLengthData.mode,mode,memory_order_release);
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
    values = abi_constants(abi)
    ref = values["QJS_ABI_REF_COUNT_OFFSET"]
    length = values["QJS_ABI_BIT_JSString_len_BYTE"]
    string_length = "mov eax, DWORD PTR [rcx" + (f"+{length}" if length else "") + "]"
    g = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text(
            encoding="utf-8-sig"
        )
    )
    blocks = []
    contracts = []
    external = {"JS_FrameLengthData", "JS_FrameInterpPropertyCold_unwind"}
    for tag in g["aliases"]:
        name = "JS_FrameLength" + tag
        fallback = "interp_slow" if tag == "M" else "dirty_interp_slow"
        external.add(fallback)
        fail = "length_" + tag + "_miss"
        string = "length_" + tag + "_string"
        commit = "length_" + tag + "_array_commit"
        b = [
            "cmp BYTE PTR [rip+JS_FrameLengthData], 1",
            "jne " + fail,
            "mov rdx, QWORD PTR [r13-8]",
            "mov rcx, QWORD PTR [r13-16]",
            "cmp rdx, -7",
            "je " + string,
            "cmp rdx, -1",
            "jne " + fail,
            f"cmp WORD PTR [rcx+{fields['JSObject.class_id']}], 2",
            "jne " + fail,
            f"test BYTE PTR [rcx+{values['QJS_ABI_BIT_JSObject_fast_array_BYTE']}], {values['QJS_ABI_BIT_JSObject_fast_array_MASK']}",
            "jz " + fail,
            f"cmp DWORD PTR [rcx{ref:+d}], 1",
            "jle " + fail,
            f"mov rdx, QWORD PTR [rcx+{fields['JSObject.prop']}]",
            "mov rax, QWORD PTR [rdx]",
            "mov r8, QWORD PTR [rdx+8]",
            "test r8, r8",
            "jz " + commit,
            "cmp r8, 8",
            "jne " + fail,
            commit + ":",
        ]
        if g["diagnostics"]:
            b += ["lock inc QWORD PTR [rip+JS_FrameLengthData+16]"]
        b += [
            f"dec DWORD PTR [rcx{ref:+d}]",
            "mov QWORD PTR [r13-16], rax",
            "mov QWORD PTR [r13-8], r8",
            "inc r12",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
            string + ":",
            f"cmp DWORD PTR [rcx{ref:+d}], 1",
            "jle " + fail,
            string_length,
            "and eax, 2147483647",
        ]
        if g["diagnostics"]:
            b += ["lock inc QWORD PTR [rip+JS_FrameLengthData+8]"]
        b += [
            f"dec DWORD PTR [rcx{ref:+d}]",
            "mov QWORD PTR [r13-16], rax",
            "mov QWORD PTR [r13-8], 0",
            "inc r12",
            "movzx eax, BYTE PTR [r12]",
            "jmp QWORD PTR [rdi+rax*8]",
            fail + ":",
        ]
        if g["diagnostics"]:
            b += ["lock inc QWORD PTR [rip+JS_FrameLengthData+24]"]
        b += ["jmp " + fallback]
        blocks.append((name, b))
        contracts.append(
            dict(
                family=tag,
                entry=name,
                fallback=fallback,
                opcode="get_length",
                no_call_allocation_or_rsp_change=True,
                logical_array_length="prop[0].u.value, not dense count",
                reference_count="strictly >1, decrement once",
                all_guards_before_mutation=True,
                release_counter_writes=False,
                diagnostic_counters=g["diagnostics"],
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
    path.with_name(path.name + ".length-rel32.json").write_text(
        json.dumps(dict(status="passed", changes=changes), indent=2) + "\n", encoding="utf-8"
    )


def compile_extra(source, build, msvc):
    out = _frame_generated_file(build, "quickjs-interpreter-length.obj")
    module(source, "atod").compile_extra(
        source,
        build,
        out,
        generator=lambda s, p: generate(s, build, p),
        filename="quickjs-interpreter-length.c",
        late_name=CODE,
    )
    privatize(out, build, source)
    normalize(source, out)
    compile_asm(source, build, msvc)


def append_crt(source, build, output):
    """One standard CRT initializer pointer, after strict C/ASM merge. No merger relaxation."""
    C = module(source, "object-adapter")
    raw = output.read_bytes()
    co = C.Coff(raw)
    assert co.header == 20 and co.stride == 18 and co.string_offset + len(co.strings) == len(raw)
    found = [
        i
        for i, s in co.all_symbols.items()
        if s["name"] == "JS_FrameLengthConfigure" and s["section"] > 0 and s["storage"] == 2
    ]
    assert len(found) == 1
    # Insert one COFF section header; retain every old section/symbol index.
    headend = co.header + 40 * co.count
    buf = bytearray(raw[:headend] + bytes(40) + raw[headend:])
    struct.pack_into("<H", buf, 2, co.count + 1)
    table = co.table + 40
    struct.pack_into("<I", buf, 8, table)
    for r in co.section_records:
        for f in (20, 24, 28):
            value = struct.unpack_from("<I", raw, r["pos"] + f)[0]
            if value:
                struct.pack_into("<I", buf, r["pos"] + f, value + 40)
    pad = (-table) % 8
    payload = bytes(pad + 8) + struct.pack("<IIH", 0, found[0], 1)
    buf[table:table] = payload
    for r in co.section_records:
        for f in (20, 24, 28):
            value = struct.unpack_from("<I", buf, r["pos"] + f)[0]
            if value >= table and value:
                struct.pack_into("<I", buf, r["pos"] + f, value + len(payload))
    struct.pack_into("<I", buf, 8, table + len(payload))
    buf[headend : headend + 8] = b".CRT$XCU"
    struct.pack_into(
        "<IIIIHHI", buf, headend + 16, 8, table + pad, table + pad + 8, 0, 1, 0, 0x40400040
    )
    check = C.Coff(buf)
    assert check.sections[:-1] == co.sections and check.all_symbols == co.all_symbols
    output.write_bytes(buf)
    (_frame_generated_file(build, "quickjs-interpreter-length-crt.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=sha(output),
                section=".CRT$XCU",
                kind=1,
                target="JS_FrameLengthConfigure",
                old_sections_and_symbols_held=True,
                policy="Standard CRT startup pointer; normal linker relocation/ASLR, no fixed base.",
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


def route_tables(source, build, path, raw, msvc):
    C = module(source, "object-adapter")
    N = module(source, "extension-merge")
    raw, _ = module(source, "call-metadata").packed(raw, C)
    co = C.Coff(raw)
    routes = []
    globals = []
    originals = C.Coff(raw)
    g = json.loads(
        (_frame_generated_file(build, "quickjs-call-link-vm-generation.json")).read_text(
            encoding="utf-8-sig"
        )
    )
    opfile = _frame_source_file(source, "quickjs-opcode.h").read_text(encoding="utf-8")
    # The actual generator emits every runtime opcode in exact table order.
    lines = (
        (_frame_generated_file(build, "quickjs-interpreter-register-win64.S"))
        .read_text(encoding="ascii")
        .splitlines()
    )
    begin = lines.index("interp_table:") + 1
    names = re.findall(r"^\s*DEF\(\s*(\w+)", opfile, re.M)
    opcode = names.index("get_length")
    assert re.search(r"^\s*DEF\(\s*get_length\s*,\s*1\s*,", opfile, re.M)
    assert lines[begin + opcode] == ".quad interp_slow"

    def external(name):
        hits = [
            i
            for i, s in co.all_symbols.items()
            if s["name"] == name and s["section"] == 0 and s["storage"] == 2
        ]
        return hits[0] if hits else co.external(name)

    for index, s in co.all_symbols.items():
        if s["name"] == "interp_table" and s["section"] > 0:
            r = co.section_records[s["section"] - 1]
            wanted = s["value"] + opcode * 8
            hits = [
                (j, struct.unpack_from("<IIH", co.data, r["reloc"] + 10 * j))
                for j in range(r["count"])
                if struct.unpack_from("<I", co.data, r["reloc"] + 10 * j)[0] == wanted
            ]
            assert len(hits) == 1
            num, (off, target, kind) = hits[0]
            addend = struct.unpack_from("<Q", co.data, r["raw"] + off)[0]
            old = co.all_symbols[target]
            slow = next(
                v
                for v in co.all_symbols.values()
                if v["name"] == "interp_slow" and v["section"] > 0
            )
            assert (
                kind == 1
                and old["section"] == slow["section"]
                and old["value"] + addend == slow["value"]
            )
            struct.pack_into("<I", co.data, r["reloc"] + 10 * num + 4, external("JS_FrameLengthM"))
            struct.pack_into("<Q", co.data, r["raw"] + off, 0)
            routes.append(
                dict(
                    role="base table",
                    section=s["section"],
                    offset=off,
                    kind=kind,
                    width=8,
                    old="interp_slow",
                    new="JS_FrameLengthM",
                    old_addend=addend,
                    new_addend=0,
                )
            )
    if "P" in g["aliases"]:
        tables = [v for v in co.all_symbols.values() if v["name"] == "JS_FramePublishDirtyTable"]
        if tables and any(v["name"] == "dirty_interp_slow" for v in co.all_symbols.values()):
            assert len(tables) == 1
            table = tables[0]
            slow = next(v for v in co.all_symbols.values() if v["name"] == "dirty_interp_slow")
            for number, r in enumerate(co.section_records, 1):
                rels = {
                    struct.unpack_from("<I", co.data, r["reloc"] + 10 * j)[0]: (
                        j,
                        *struct.unpack_from("<IIH", co.data, r["reloc"] + 10 * j)[1:],
                    )
                    for j in range(r["count"])
                }
                for off, (j, target, kind) in rels.items():
                    if kind != 4:
                        continue
                    sym = co.all_symbols[target]
                    addend = struct.unpack_from("<i", co.data, r["raw"] + off)[0]
                    if (
                        sym["section"] != table["section"]
                        or sym["value"] + addend != table["value"] + opcode * 8
                    ):
                        continue
                    if table["section"] == 0 and sym["name"] != table["name"]:
                        continue
                    a = r["raw"] + off
                    assert (
                        bytes(co.data[a - 10 : a - 7]) == b"\x4c\x8d\x15"
                        and bytes(co.data[a - 3 : a]) == b"\x4c\x89\x15"
                    )
                    lea_off = off - 7
                    old_addend = struct.unpack_from("<i", co.data, r["raw"] + lea_off)[0]
                    before = rels.get(lea_off)
                    new_target = external("JS_FrameLengthP")
                    if before:
                        num, old_target, old_kind = before
                        v = co.all_symbols[old_target]
                        assert (
                            old_kind == 4
                            and v["section"] == slow["section"]
                            and v["value"] + old_addend == slow["value"]
                        )
                        assert slow["section"] > 0 or v["name"] == slow["name"]
                        struct.pack_into("<I", co.data, r["reloc"] + 10 * num + 4, new_target)
                    else:
                        assert (
                            number == slow["section"] and lea_off + 4 + old_addend == slow["value"]
                        )
                        co.extra_relocations.setdefault(number, []).append(
                            struct.pack("<IIH", lea_off, new_target, 4)
                        )
                    struct.pack_into("<i", co.data, r["raw"] + lea_off, 0)
                    routes.append(
                        dict(
                            role="dirty table initializer",
                            section=number,
                            offset=lea_off,
                            kind=4,
                            width=4,
                            old="dirty_interp_slow",
                            new="JS_FrameLengthP",
                            slot=opcode,
                            old_addend=old_addend,
                            new_addend=0,
                            source_relocation=bool(before),
                            two_instructions="lea r10,[rip+old_slow]; mov [rip+dirtytable+slot*8],r10",
                        )
                    )
    for index, s in co.all_symbols.items():
        if (
            s["name"] in ("interp_slow", "dirty_interp_slow")
            and s["section"] > 0
            and s["storage"] == 3
        ):
            co.data[co.table + index * co.stride + co.class_offset] = 2
            globals.append(s["name"])
    result = co.finish()
    after = C.Coff(result)
    restored = bytearray(result)
    for row in routes:
        r = after.section_records[row["section"] - 1]
        struct.pack_into(
            "<Q" if row["width"] == 8 else "<i",
            restored,
            r["raw"] + row["offset"],
            row["old_addend"],
        )
    assert [s["sha256"] for s in C.Coff(restored).sections] == [
        s["sha256"] for s in originals.sections
    ]

    if not routes and not globals:
        return raw, None
    folder = _frame_generated_file(build, "length-link")
    folder.mkdir(exist_ok=True)
    receipt = folder / (path.name + ".json")
    assert not receipt.exists()
    receipt.write_text(
        json.dumps(
            dict(
                status="passed",
                input=str(path),
                input_sha256=hashlib.sha256(raw).hexdigest(),
                output_sha256=hashlib.sha256(result).hexdigest(),
                opcode=opcode,
                routes=routes,
                exposed=globals,
                all_other_section_and_operand_bytes_held=True,
                typed_or_proven_local_instruction_targets_only=True,
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return result, str(receipt)


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
        if s["section"] > 0 and s["storage"] == 2 and not s["name"].startswith("JS_FrameLength"):
            name = "length_emitted_" + hashlib.sha256(s["name"].encode()).hexdigest()[:32]
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
    co = C.Coff((_frame_generated_file(build, "quickjs-interpreter-length.obj")).read_bytes())
    c_pdata = sum(
        r["size"]
        for i, r in enumerate(co.section_records, 1)
        if merge.section_name(co, i).startswith(".pdata")
    )
    capacity = module(source, "varargs").CAPACITY + c_pdata + 12 * len(blocks)
    header = MAGIC + bytes(16)
    footer = FOOTER + struct.pack("<II", capacity, 1) + bytes(capacity)
    asm = _frame_build_file(
        build, "quickjs-interpreter-length.asm" if msvc else "quickjs-interpreter-length.S"
    )
    obj = _frame_generated_file(build, "quickjs-interpreter-length-asm.obj")
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
        lines += ['.section .pdata$zzzzzznullfast,"dr"', ".p2align 2"]
        for name, _ in blocks:
            lines += [".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind"]
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
    (_frame_generated_file(build, "quickjs-interpreter-length-generation.json")).write_text(
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
    C = module(source, "object-adapter")
    old = C.Coff(output.read_bytes())
    # Miss is an actual MSVC leaf with no native record; Configure owns compiler
    # CFI. Keep all contributions while anchoring the strict merger to that CFI.
    merge.append(
        output,
        _frame_generated_file(build, "quickjs-interpreter-length.obj"),
        "JS_FrameLengthConfigure",
        "length-c",
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
        _frame_generated_file(build, "quickjs-interpreter-length-asm.obj"),
        "JS_FrameLengthM",
        "length-asm",
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
            for a, b in ((CODE, ".qjlnrx"), (".qjzzlm", ".qjlnrw"), (CFI, ".qjlnro")):
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
        assert previous.count(b"/MERGE:.qjs=.qjscold") == 1 and b"/MERGE:.qjlnrx=" not in previous
        payload = (
            previous + b" /MERGE:.qjlnrx=.qjzzlc /MERGE:.qjlnrw=.qjzzlm /MERGE:.qjlnro=.qjzzlf "
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
        (_frame_generated_file(build, "quickjs-interpreter-length-msvc-merge.json")).write_text(
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
        for address, length in ((begin, stop - begin), (uw, 4)):
            assert any(
                v["rva"] <= address and address + length <= v["rva"] + v["physical_size"]
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
        length_rows=len(native),
        combined_rows=len(rows),
        capacity=capacity,
        directory_rva=s["rva"] + relative,
        all_inherited_rows_retained=True,
        native_storage_readonly=True,
        policy="Independent final RO directory and PE exception pointer only; parent packet kept free of new contribution. No executable or old RW bytes/addresses changed by finalization.",
    )
