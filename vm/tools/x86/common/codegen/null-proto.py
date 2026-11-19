"""Native-only NULL_PROTO qualification and opcode, preserving old C bodies.

The validator hook is reached only on the first bytecode eligibility scan.
Its ABI thunk preserves ALL Win64 volatile argument/SIMD registers, because
the compiler may specialize the clobber set of the original static validator.
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
from abi_layout import load as load_layout
import argparse, ctypes, hashlib, importlib.util, json, re, struct, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def coff_module():
    sp = importlib.util.spec_from_file_location("null_coff", _frame_tool_path("object-adapter"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m


def generate(source, out):
    frame = _frame_source_text(source, "quickjs-interpreter-loop.h")
    start = frame.index("static FRAME_CODE bool js_frame_validate(")
    end = frame.index("\nstatic FRAME_INLINE JSFunctionBytecode *js_frame_target", start)
    prefix = frame[:start]
    table_start = prefix.index("static const uint8_t js_frame_opcode_sizes[]")
    prefix = (
        prefix[:table_start]
        + """extern const uint8_t JS_FrameOpcodeSizesOriginal[OP_COUNT];
#if defined(_MSC_VER)
#define js_frame_opcode_sizes JS_FrameOpcodeSizesOriginal
#else
static FRAME_INLINE const uint8_t *js_frame_null_sizes(void)
{
    const uint8_t *p;
    __asm__("lea JS_FrameOpcodeSizesOriginal(%%rip), %0" : "=r"(p));
    return p;
}
#define js_frame_opcode_sizes (js_frame_null_sizes())
#endif
"""
    )
    validator = frame[start:end].replace(
        "static FRAME_CODE bool js_frame_validate(",
        "static FRAME_NULL_CODE bool js_frame_validate_null(",
    )
    assert validator.count("bool captured_args = false;") == 1
    validator = validator.replace(
        "bool captured_args = false;", "bool captured_args = false;\n    bool seen_null = false;"
    )
    needle = """            break;
        default:
            return false;
"""
    assert validator.count(needle) == 1
    validator = validator.replace(
        needle,
        """            break;
        case OP_special_object:
            if (code[pos + 1] != 7) return false;
            seen_null = true;
            break;
        default:
            return false;
""",
    )
    validator = validator.replace(
        "    FRAME_KIND(b) = (captured_args",
        "    if (!seen_null) return false;\n    FRAME_KIND(b) = (captured_args",
    )
    validator = validator.replace("(b->var_ref_count ? 8 : 0);", "(b->var_ref_count ? 8 : 0) | 32;")
    validator = validator.replace("countof(js_frame_opcode_sizes)", "OP_COUNT")
    text = _frame_source_file(source, "quickjs.c").read_text()
    enum = text[
        text.index("/* argument of OP_special_object */") : text.index("} OPSpecialObjectEnum;")
    ]
    assert (
        re.findall(r"^\s*(OP_SPECIAL_OBJECT_\w+),", enum, re.M).index(
            "OP_SPECIAL_OBJECT_NULL_PROTO"
        )
        == 7
    )
    code = (
        """/* Generated from the retained validator, only NULL_PROTO is added. */
#include "quickjs-interpreter-private.h"
#if defined(_MSC_VER)
#define FRAME_NULL_CODE __declspec(code_seg(".qjscold")) no_inline
#else
#define FRAME_NULL_CODE __attribute__((section(".qjsleaf"), noipa))
#endif
"""
        + prefix
        + validator
        + """
extern bool JS_FrameValidateOriginal(JSFunctionBytecode *b);
extern void JS_FrameCapturedReadonlyClassify(JSFunctionBytecode *b);
extern const char JS_FrameNullProtoDisable[];
_Static_assert(sizeof(((JSRuntime *)0)->module_loader_has_attr)==1 &&
               offsetof(JSRuntime, module_loader_has_attr)==QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
               offsetof(JSRuntime, u)==QJS_ABI_OFF_JSRuntime_u, "null mode uses measured runtime padding");
FRAME_NULL_CODE bool JS_FrameValidateNativeNull(JSFunctionBytecode *b)
{
    JSRuntime *rt;
    unsigned char *mode;
    const char *flag;
    if (JS_FrameValidateOriginal(b)) {
        JS_FrameCapturedReadonlyClassify(b);
        return true;
    }
    rt=b->realm->rt;
    if (FRAME_STATE(rt)!=1 || !js_frame_register_enabled(rt)) return false;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(rt,JS_DUMP_BYTECODE_STEP)) return false;
#endif
    mode=(unsigned char *)rt+offsetof(JSRuntime,module_loader_has_attr)+2;
    if (!*mode) {
#if defined(_MSC_VER)
        flag=JS_FrameNullProtoDisable;
#else
        __asm__("lea JS_FrameNullProtoDisable(%%rip), %0" : "=r"(flag));
#endif
        *mode=getenv(flag)==NULL ? 1 : 2;
    }
    if (*mode!=1) return false;
    if (!js_frame_validate_null(b)) return false;
    JS_FrameCapturedReadonlyClassify(b);
    return true;
}
"""
    )
    sp = importlib.util.spec_from_file_location("add_local", _frame_tool_path("add-local"))
    local = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(local)
    code += local.generate(source)
    out.write_text(code)
    out.with_suffix(".source.json").write_text(
        json.dumps(
            {
                "source_sha256": sha(_frame_source_file(source, "quickjs-interpreter-loop.h")),
                "core_sha256": sha(_frame_source_file(source, "quickjs.c")),
                "generated_sha256": sha(out),
                "null_kind": 7,
                "native_only_metadata_bit": 32,
                "mode_padding": load_layout(source)["offsets"]["JSRuntime.module_loader_has_attr"]
                + 2,
            },
            indent=2,
        )
        + "\n"
    )


def win_argv(command):
    import ctypes.wintypes as w

    api = ctypes.windll.shell32.CommandLineToArgvW
    api.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    api.restype = ctypes.POINTER(w.LPWSTR)
    n = ctypes.c_int()
    p = api(command, ctypes.byref(n))
    assert p
    try:
        return [p[i] for i in range(n.value)]
    finally:
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(p)


def compile_extra(source, build, out):
    sp = importlib.util.spec_from_file_location(
        "generated_epoch", _frame_tool_path("adapter-restart")
    )
    epoch = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(epoch)
    epoch.retire_generated(out, build)
    cfile = _frame_generated_file(build, "quickjs-interpreter-null-proto.c")
    generate(source, cfile)
    records = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    original = next(x for x in records if Path(x["file"]).name == "quickjs-interpreter.c")
    args = win_argv(original["command"])
    new = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "-o":
            new.extend([a, str(out)])
            i += 2
            continue
        if a.lower().startswith("/fo") or a.lower().startswith("-fo"):
            new.append(a[:3] + str(out))
            i += 1
            continue
        if a == "-MF":
            new.extend([a, str(out) + ".d"])
            i += 2
            continue
        if Path(a).name.lower() == "quickjs-interpreter.c":
            a = str(cfile)
        new.append(a)
        i += 1
    assert str(cfile) in new and any(str(out) in x for x in new)
    p = subprocess.run(new, cwd=original["directory"], capture_output=True)
    out.with_suffix(".compile.log").write_bytes(p.stdout + p.stderr)
    if p.returncode:
        raise RuntimeError((p.stdout + p.stderr).decode(errors="replace"))
    C = coff_module().Coff
    obj = C(out.read_bytes())
    # Its functions are appended after the register object's late code. Keep
    # compiler-generated runtime-function entries after the matching ASM ones.
    late = ".qjscold" if any(x.lower() == "/nologo" for x in new) else ".qjsleaf"
    for section_index, (sec, rec) in enumerate(zip(obj.sections, obj.section_records), 1):
        name = sec["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = obj.strings[at : obj.strings.find(0, at)].decode()
        renamed = (
            ".pdata$zzzzqjsnull"
            if name.startswith(".pdata")
            else (
                late
                if (
                    name.startswith((".rdata", ".text", ".xdata"))
                    or rec["flags"] & 0x20000000
                    and name != late
                )
                and rec["size"]
                else None
            )
        )
        if renamed:
            at = len(obj.strings)
            obj.strings += renamed.encode() + b"\0"
            encoded = ("/" + str(at)).encode()
            assert len(encoded) <= 8
            obj.data[rec["pos"] : rec["pos"] + 8] = encoded.ljust(8, b"\0")
            if renamed == late:
                flags = (rec["flags"] & ~0xE0) | 0x60000040
                struct.pack_into("<I", obj.data, rec["pos"] + 36, flags)
            # Match section-definition symbols, preserving COMDAT auxiliaries.
            for index, sym in obj.all_symbols.items():
                if (
                    sym["section"] == section_index
                    and sym["name"] == name
                    and sym["storage"] == 3
                    and sym["type"] == 0
                ):
                    struct.pack_into("<II", obj.data, obj.table + index * obj.stride, 0, at)
    if late == ".qjsleaf":
        for sec, rec in zip(obj.sections, obj.section_records):
            if not rec["flags"] & 0x20000000 and not sec["name"].startswith(".rdata"):
                continue
            for i in range(rec["count"]):
                off, sym, kind = struct.unpack_from("<IIH", obj.data, rec["reloc"] + i * 10)
                assert kind != 1, (
                    "Allocated new native/data island must have no absolute 64-bit relocation",
                    sec["name"],
                    off,
                    obj.all_symbols[sym],
                )
    out.write_bytes(obj.finish())
    out.with_suffix(".compile.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "compiler_command": new,
                "original_command": original,
                "compiler_sha256": sha(Path(new[0])),
                "source_sha256": sha(cfile),
                "object_sha256": sha(out),
                "runner_sha256": sha(Path(__file__)),
            },
            indent=2,
        )
        + "\n"
    )
    print("NULL EXTRA C COMPILED", out, flush=True)


def route(path, objdump):
    evidence = path.with_name(path.name + ".null-route.json")
    if evidence.exists():
        x = json.loads(evidence.read_text())
        raw = bytearray(path.read_bytes())
        ext = path.with_name(path.name + ".extension.json")
        if ext.exists():
            for s in json.loads(ext.read_text())["sections"]:
                struct.pack_into("<I", raw, s["header_offset"] + 36, int(s["before"], 16))
        assert hashlib.sha256(raw).hexdigest() == x["after_sha256"]
        assert sha(path.with_name(path.name + ".before-null-route")) == x["before_sha256"]
        return
    M = coff_module()
    raw = path.read_bytes()
    obj = M.Coff(raw)
    assert obj.stride == 18
    original = obj.symbols["js_frame_validate"]
    target = obj.external("JS_FrameValidateNativeNullThunk")
    for old, new in (
        ("js_frame_validate", "JS_FrameValidateOriginal"),
        ("js_frame_opcode_sizes", "JS_FrameOpcodeSizesOriginal"),
    ):
        info = next(v for v in obj.all_symbols.values() if v["name"] == old and v["section"] > 0)
        offset = len(obj.strings)
        obj.strings += new.encode() + b"\0"
        symbol = struct.pack(
            "<IIIhHBB", 0, offset, info["value"], info["section"], info["type"], 2, 0
        )
        assert len(symbol) == 18
        obj.aliases.append(bytearray(symbol))
    routes = []
    relocated = set()
    for ix, rec in enumerate(obj.section_records, 1):
        if not rec["flags"] & 0x20:
            continue
        for j in range(rec["count"]):
            pos = rec["reloc"] + j * 10
            off, sym, kind = struct.unpack_from("<IIH", obj.data, pos)
            target_info = obj.all_symbols[sym]
            if kind != 4 or target_info["section"] != original["section"]:
                continue
            addend = struct.unpack_from("<i", obj.data, rec["raw"] + off)[0]
            if target_info["value"] + addend != original["value"]:
                continue
            # ASan also retains function-address LEA references. Those are
            # metadata, not calls, and must continue to name the original body.
            if not off or obj.data[rec["raw"] + off - 1] not in (0xE8, 0xE9):
                continue
            obj.data[rec["raw"] + off : rec["raw"] + off + 4] = bytes(4)
            struct.pack_into("<I", obj.data, pos + 4, target)
            relocated.add((ix, off))
            routes.append(
                {
                    "section": ix,
                    "offset": off,
                    "kind": "existing-rel32",
                    "old_symbol": sym,
                    "old_addend": addend,
                }
            )
    ix = original["section"]
    rec = obj.section_records[ix - 1]
    name = obj.sections[ix - 1]["name"]
    if name.startswith("/"):
        at = int(name[1:])
        name = obj.strings[at : obj.strings.find(0, at)].decode()
    if not any(x["section"] == ix for x in routes):
        listing = subprocess.check_output(
            [str(objdump), "-d", "-Mintel", "--insn-width=16", "-j", name, str(path)], text=True
        )
        for line in listing.splitlines():
            m = re.match(r"^\s*([0-9a-f]+):\s*((?:[0-9a-f]{2} )+)\s*(.*)", line)
            if not m:
                continue
            off = int(m[1], 16)
            code = bytes.fromhex(m[2])
            if (
                len(code) != 5
                or code[0] not in (0xE8, 0xE9)
                or off + 5 + struct.unpack_from("<i", code, 1)[0] != original["value"]
            ):
                continue
            if (ix, off + 1) in relocated:
                continue
            assert bytes(obj.data[rec["raw"] + off : rec["raw"] + off + 5]) == code
            obj.data[rec["raw"] + off + 1 : rec["raw"] + off + 5] = bytes(4)
            obj.extra_relocations.setdefault(ix, []).append(struct.pack("<IIH", off + 1, target, 4))
            routes.append(
                {
                    "section": ix,
                    "offset": off + 1,
                    "kind": "decoded-rel32",
                    "old_bytes": code[1:].hex(),
                }
            )
    assert routes
    result = obj.finish()
    backup = path.with_name(path.name + ".before-null-route")
    backup.write_bytes(raw)
    path.write_bytes(result)
    evidence.write_text(
        json.dumps(
            {
                "status": "passed",
                "before_sha256": sha(backup),
                "after_sha256": sha(path),
                "routes": routes,
                "target": "JS_FrameValidateNativeNullThunk",
                "aliases": ["JS_FrameValidateOriginal", "JS_FrameOpcodeSizesOriginal"],
                "contract": "Only decoded validator CALL/JMP operands and their typed relocations plus appended aliases change; volatile clobber set preserved by thunk.",
            },
            indent=2,
        )
        + "\n"
    )
    print("NULL VALIDATOR ROUTES", len(routes), flush=True)


def append(masm, gas, diagnostics):
    from native_abi import current as current_abi

    fields = current_abi()["offsets"]
    assert masm.pop() == "END"
    thunk = "JS_FrameValidateNativeNullThunk"
    cold = "JS_FrameNullProtoCold"
    masm[3:3] = ["EXTERN JS_FrameValidateNativeNull:PROC", "EXTERN JS_FrameNewNullObject:PROC"]
    body = ["sub rsp, 184", "null_validate_alloc:"]
    for i, r in enumerate(("rcx", "rdx", "r8", "r9", "r10", "r11")):
        body.append(f"mov QWORD PTR [rsp+{32 + i * 8}], {r}")
    for i in range(6):
        body.append(f"movdqa XMMWORD PTR [rsp+{80 + i * 16}], xmm{i}")
    body.append("call JS_FrameValidateNativeNull")
    for i in range(6):
        body.append(f"movdqa xmm{i}, XMMWORD PTR [rsp+{80 + i * 16}]")
    for i, r in enumerate(("rcx", "rdx", "r8", "r9", "r10", "r11")):
        body.append(f"mov {r}, QWORD PTR [rsp+{32 + i * 8}]")
    body += ["add rsp, 184", "ret"]
    committed, native, shared = (2304, 2312, 2320) if diagnostics else (64, 72, 80)
    pending = 2296 if diagnostics else 160
    null = [
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
    ]
    if diagnostics:
        null += [
            "inc QWORD PTR [rbx+80]",
            "movzx eax, BYTE PTR [r12]",
            "inc QWORD PTR [rbx+rax*8+144]",
        ]
    null += [
        "mov r10, QWORD PTR [rbx+56]",
        "mov r11, QWORD PTR [rbx+32]",
        f"sub r11, QWORD PTR [rbx+{committed}]",
        "jz null_proto_begin_done",
        f"add QWORD PTR [r10+{fields['JSRuntime.stack_top']}], r11",
    ]
    if diagnostics:
        null += ["inc QWORD PTR [rbx+2328]"]
    null += [
        f"cmp QWORD PTR [r10+{fields['JSRuntime.stack_limit']}], 0",
        "je null_proto_begin_done",
        f"add QWORD PTR [r10+{fields['JSRuntime.stack_limit']}], r11",
        "null_proto_begin_done:",
        "lea rax, [r12+2]",
        "mov QWORD PTR [rbp+48], rax",
        "mov QWORD PTR [rsp+48], 0",
        "mov QWORD PTR [rsp+56], 2",
        # A live frame's operand storage never moves during C allocation.
        # Write the hidden JSValue result directly there, avoiding a SIMD
        # reload that overlaps the callee's two scalar return stores.
        "mov rcx, r13",
        "mov rdx, rsi",
        "lea r8, [rsp+48]",
        "mov r9d, 1",
        "call JS_FrameNewNullObject",
        "mov r10, QWORD PTR [rbx+56]",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r10+{fields['JSRuntime.stack_limit']}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne null_proto_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared}]",
        "je null_proto_finish_done",
        "null_proto_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared}], rdx",
        "test rdx, rdx",
        "jz null_proto_unlimited",
        "sub rdx, rax",
        "null_proto_unlimited:",
        f"mov QWORD PTR [rbx+{native}], rdx",
    ]
    if diagnostics:
        null += ["inc QWORD PTR [rbx+2336]"]
    null += [
        "null_proto_finish_done:",
        "add r12, 2",
        "mov QWORD PTR [rbx+16], r12",
        "cmp QWORD PTR [r13+8], 6",
        "je null_proto_exception",
        "add r13, 16",
        "mov QWORD PTR [rbx+24], r13",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "null_proto_exception:",
        f"mov BYTE PTR [rbx+{pending}], 1",
        "jmp interp_slow",
    ]
    masm += [".qjscold SEGMENT ALIGN(16) 'CODE'"]
    gas += ['.section .qjsleaf,"xr"']
    for name, lines in ((thunk, body), (cold, null)):
        masm += ["ALIGN 16", "PUBLIC " + name + ", " + name + "_end", name + " PROC"]
        gas += [
            ".p2align 4",
            ".globl " + name + ", " + name + "_end",
            ".def " + name + "; .scl 2; .type 32; .endef",
            name + ":",
        ]
        for line in lines:
            masm += [
                line[:-1] + "::"
                if line.endswith(":")
                else line.replace("jmp interp_slow", "jmp NEAR PTR interp_slow")
            ]
            gas += [line]
        masm += [name + "_end LABEL BYTE", name + " ENDP"]
        gas += [name + "_end:"]
    masm += [
        "ALIGN 4",
        thunk + "_unwind LABEL BYTE",
        "DB 1, null_validate_alloc - " + thunk + ", 2, 0",
        "DB null_validate_alloc - " + thunk + ", 1",
        "DW 23",
        "PUBLIC JS_FrameNullProtoDisable",
        "JS_FrameNullProtoDisable LABEL BYTE",
        'DB "QJS_DISABLE_NATIVE_NULL_PROTO", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL " + thunk + ", IMAGEREL " + thunk + "_end, IMAGEREL " + thunk + "_unwind",
        "DD IMAGEREL "
        + cold
        + ", IMAGEREL "
        + cold
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        "END",
    ]
    gas += [
        ".p2align 2",
        thunk + "_unwind:",
        ".byte 1, null_validate_alloc - " + thunk + ", 2, 0",
        ".byte null_validate_alloc - " + thunk + ", 1",
        ".short 23",
        ".globl JS_FrameNullProtoDisable",
        "JS_FrameNullProtoDisable:",
        '.asciz "QJS_DISABLE_NATIVE_NULL_PROTO"',
        '.section .pdata$zzqjscold,"dr"',
        ".p2align 2",
        ".rva " + thunk + ", " + thunk + "_end, " + thunk + "_unwind",
        ".rva " + cold + ", " + cold + "_end, JS_FrameInterpPropertyCold_unwind",
    ]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--compile", action="store_true")
    p.add_argument("--route", type=Path)
    p.add_argument("--source", type=Path)
    p.add_argument("--build", type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--objdump", type=Path)
    a = p.parse_args()
    if a.compile:
        compile_extra(a.source, a.build, a.out)
    else:
        route(a.route, a.objdump)
