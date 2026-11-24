"""Release slot values from the borrowed native frame, with exact quota sync.

The caller publishes incoming ownership before releasing the old slot. Its
old CALL becomes an equal-length JMP to this appended island; the original
slot handler envelope and the later existing islands remain at their RVAs.
The off branch calls the retained C wrapper from the same native RSP.
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
    upstream_root as _frame_upstream_root,
)

_frame_activate_tools()
from native_abi import current_or_load as load_layout
import re


def append(masm, gas, diagnostics, source=None):
    layout = load_layout(source or _frame_project_root())
    fields = layout["offsets"]
    mode = fields["JSRuntime.module_loader_has_attr"] + 4
    top, limit = fields["JSRuntime.stack_top"], fields["JSRuntime.stack_limit"]
    assert masm.pop() == "END"
    name = "JS_FrameSlotFreeBorrowed"
    committed, native, shared = (2304, 2312, 2320) if diagnostics else (64, 72, 80)
    # This island can call a reentrant finalizer. Always publish the consumed
    # operand cursor and next PC under both reference-count models.
    body = [
        f"mov QWORD PTR [rbp+{fields['JSStackFrame.cur_pc']}], r12",
        f"mov QWORD PTR [rbp+{fields['JSStackFrame.cur_sp']}], r13",
    ]
    body += [
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{mode}], 0",
        "je slot_free_config",
        f"cmp BYTE PTR [r10+{mode}], 1",
        "jne slot_free_legacy",
        "slot_free_fast:",
        "mov r11, QWORD PTR [rbx+32]",
        f"sub r11, QWORD PTR [rbx+{committed}]",
        "jz slot_free_begin_done",
        f"add QWORD PTR [r10+{top}], r11",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2328]"]
    body += [
        f"cmp QWORD PTR [r10+{limit}], 0",
        "je slot_free_begin_done",
        f"add QWORD PTR [r10+{limit}], r11",
        "slot_free_begin_done:",
        "mov rcx, rsi",
        "lea rdx, [rsp+32]",
        "call JS_FreeValue",
        # Native nonvolatiles survive arbitrary finalizer/JS reentry. The
        # root's aligned 72-byte shadow still owns the old JSValue copy.
        "mov r10, QWORD PTR [rbx+56]",
        "mov rax, QWORD PTR [rbx+32]",
        f"mov rdx, QWORD PTR [r10+{limit}]",
        f"cmp rax, QWORD PTR [rbx+{committed}]",
        "jne slot_free_refresh",
        f"cmp rdx, QWORD PTR [rbx+{shared}]",
        "je slot_free_finish_done",
        "slot_free_refresh:",
        f"mov QWORD PTR [rbx+{committed}], rax",
        f"mov QWORD PTR [rbx+{shared}], rdx",
        "test rdx, rdx",
        "jz slot_free_unlimited",
        "sub rdx, rax",
        "slot_free_unlimited:",
        f"mov QWORD PTR [rbx+{native}], rdx",
    ]
    if diagnostics:
        body += ["inc QWORD PTR [rbx+2336]"]
    body += [
        "slot_free_finish_done:",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "slot_free_legacy:",
        "mov rcx, rbx",
        "mov rdx, rsi",
        "lea r8, [rsp+32]",
        "call JS_FrameInterpFree",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
        "slot_free_config:",
        "lea rcx, JS_FrameSlotFreeDisable",
        "call QWORD PTR [__imp_getenv]",
        "test rax, rax",
        "setne r11b",
        "inc r11b",
        "mov r10, QWORD PTR [rbx+56]",
        f"mov BYTE PTR [r10+{mode}], r11b",
        "jmp " + name,
    ]
    masm += [
        ".qjscold SEGMENT ALIGN(16) 'CODE'",
        "ALIGN 16",
        "PUBLIC " + name + ", " + name + "_end",
        name + " PROC",
    ]
    gas += [
        '.section .qjsleaf,"xr"',
        ".p2align 4",
        ".globl " + name + ", " + name + "_end",
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
    ]
    for line in body:
        masm += [line[:-1] + "::" if line.endswith(":") else line]
        gas += [
            line.replace(
                "lea rcx, JS_FrameSlotFreeDisable", "lea rcx, [rip+JS_FrameSlotFreeDisable]"
            ).replace("[__imp_getenv]", "[rip+__imp_getenv]")
        ]
    masm += [
        name + "_end LABEL BYTE",
        name + " ENDP",
        "PUBLIC JS_FrameSlotFreeDisable",
        "JS_FrameSlotFreeDisable LABEL BYTE",
        'DB "QJS_DISABLE_BORROWED_SLOT_FREE", 0',
        ".qjscold ENDS",
        ".pdata$zzqjscold SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + name
        + ", IMAGEREL "
        + name
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzqjscold ENDS",
        "END",
    ]
    gas += [
        name + "_end:",
        ".globl JS_FrameSlotFreeDisable",
        "JS_FrameSlotFreeDisable:",
        '.asciz "QJS_DISABLE_BORROWED_SLOT_FREE"',
        '.section .pdata$zzqjsleaf,"dr"',
        ".p2align 2",
        ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
    ]


BIGINT_RELEASE_BACKEND = r"""
#include <stdatomic.h>
#ifdef _MSC_VER
#define RELEASE_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
extern unsigned char JS_FrameBigIntReleaseControl;
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *,unsigned char *,unsigned char);
#define RELEASE_LOAD() JS_FrameJSONLoad8(&JS_FrameBigIntReleaseControl)
#define RELEASE_CAS(p,v) JS_FrameJSONCAS8(&JS_FrameBigIntReleaseControl,p,v)
#else
#define RELEASE_CODE __attribute__((section(".qjssrc$C"),noipa))
static _Atomic unsigned char JS_FrameBigIntReleaseControl __attribute__((section(".qjssrm"),used));
#define RELEASE_LOAD() atomic_load_explicit(&JS_FrameBigIntReleaseControl,memory_order_relaxed)
#define RELEASE_CAS(p,v) atomic_compare_exchange_strong_explicit(&JS_FrameBigIntReleaseControl,p,v,memory_order_relaxed,memory_order_relaxed)
#endif
/* First invocation and the disabled path preserve the entire original release. */
RELEASE_CODE void JS_FrameBigIntReleaseSlow(JSContext *ctx,JSValue value)
{
    if (!RELEASE_LOAD()) {
        unsigned char expected=0;
        unsigned char mode=getenv("QJS_DISABLE_BIGINT_RELEASE")?2:1;
        (void)RELEASE_CAS(&expected,mode);
    }
    JS_FreeValue(ctx,value);
}
/* Readonly qualification entry; no counters, roots or per-runtime ownership. */
RELEASE_CODE unsigned JS_FrameBigIntReleaseState(void)
{
    return RELEASE_LOAD();
}
"""


def compile_big_release(source, build, *, msvc):
    """Append complete C/leaf contributions after the inherited JSON/slice code."""
    import hashlib, importlib.util, json, struct, subprocess
    from pathlib import Path
    from types import SimpleNamespace

    here = Path(__file__).resolve().parent

    def module(n, f):
        sp = importlib.util.spec_from_file_location(n, _frame_tool_path(f))
        m = importlib.util.module_from_spec(sp)
        sp.loader.exec_module(m)
        return m

    C = module("release_coff", "object-adapter.py")
    M = module("release_compile", "atod.py")
    core = C.Coff((_frame_build_file(build, "CMakeFiles/qjs-core.dir/quickjs.c.obj")).read_bytes())
    original = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    header, exports, copies = C.generate(original, core, BIGINT_RELEASE_BACKEND)
    assert not exports, exports
    prefix = "".join("#define " + n + " bigint_release_" + n + "\n" for n in copies)
    private = _frame_generated_file(build, "quickjs-bigint-release-private.h")
    private.write_text(prefix + header, encoding="utf-8")

    class ReleaseCoff(C.Coff):
        def finish(self):
            roots = ("JS_FrameBigIntReleaseSlow", "JS_FrameBigIntReleaseState")
            for index, s in self.all_symbols.items():
                name = s["name"]
                new = None
                if s["section"] > 0 and name == "JS_FrameBigIntReleaseControl":
                    self.data[self.table + index * self.stride + self.class_offset] = 2
                if s["section"] > 0 and s["storage"] == 2 and s["type"] & 32 and name not in roots:
                    new = "bigint_release_" + name
                if (
                    s["section"] > 0
                    and s["storage"] == 2
                    and name.startswith(("??_C@", "__xmm@", "__real@"))
                ):
                    new = (
                        "qjs_bigint_release_const_" + hashlib.sha256(name.encode()).hexdigest()[:32]
                    )
                if new:
                    at = len(self.strings)
                    self.strings += new.encode() + b"\0"
                    struct.pack_into("<II", self.data, self.table + index * self.stride, 0, at)
            for rec in self.section_records:
                name = self.data[rec["pos"] : rec["pos"] + 8].split(b"\0")[0].decode()
                if name.startswith("/"):
                    at = int(name[1:])
                    name = self.strings[at : self.strings.index(0, at)].decode()
                if name == ".qjssrc$C" or (msvc and name.startswith(".pdata")):
                    flags = struct.unpack_from("<I", self.data, rec["pos"] + 36)[0]
                    struct.pack_into("<I", self.data, rec["pos"] + 36, (flags & ~0xE0) | 0x60000040)
            return super().finish()

    M.coff_module = lambda: SimpleNamespace(Coff=ReleaseCoff)
    argv = M.win_argv
    M.win_argv = lambda cmd: [a for a in argv(cmd) if not a.startswith("-g")] + (
        [] if msvc else ["-g0"]
    )
    output = _frame_generated_file(build, "quickjs-interpreter-bigint-release.obj")

    def generate(source, path):
        path.write_text(
            '#include "quickjs-bigint-release-private.h"\n' + BIGINT_RELEASE_BACKEND,
            encoding="utf-8",
        )

    M.compile_extra(
        source,
        build,
        output,
        generator=generate,
        filename="quickjs-interpreter-bigint-release.c",
        late_name=".qjssrc$C",
    )
    compile_args = json.loads(output.with_suffix(".compile.json").read_text())["compiler_command"]
    compiler = Path(compile_args[0])
    defines = [x for x in compile_args[1:] if x.startswith(("-D", "/D"))]
    crt_flags = [
        "/" + x[1:]
        for x in compile_args[1:]
        if x in ("/MD", "-MD", "/MT", "-MT", "/MDd", "-MDd", "/MTd", "-MTd")
    ]
    crt_flag = crt_flags[-1] if crt_flags else "/MD"
    probe = _frame_generated_file(build, "quickjs-bigint-release-layout.c")
    pe = probe.with_suffix(".exe")
    probe.write_text(
        r"""#include "quickjs-bigint-release-private.h"
#include <stdio.h>
#if QJS_ABI_HAS_PREFIX_RC
#define FRAME_REF_DATA offsetof(JSMallocBlockHeader,user_data)
#define FRAME_REF_COUNT offsetof(JSMallocBlockHeader,ref_count)
#else
#define FRAME_REF_DATA 0
#define FRAME_REF_COUNT offsetof(JSBigInt,header.ref_count)
#endif
int main(void) {
    printf("RELEASE_LAYOUT %zu %zu %zu %zu %zu %d\n",sizeof(JSValue),offsetof(JSValue,tag),
        offsetof(JSContext,rt),(size_t)FRAME_REF_DATA,FRAME_REF_COUNT,JS_TAG_BIG_INT);
    return 0;
}
""",
        encoding="ascii",
    )
    command = (
        [
            str(compiler),
            "/nologo",
            "/O2",
            crt_flag,
            "/std:c11",
            "/I" + str(build),
            "/I" + str(source),
            "/I" + str(_frame_upstream_root(source)),
            *defines,
            str(probe),
            "/Fe:" + str(pe),
            "/Fo:" + str(probe.with_suffix(".obj")),
        ]
        if msvc
        else [
            str(compiler),
            "-O2",
            "-g0",
            "-I" + str(build),
            "-I" + str(source),
            "-I" + str(_frame_upstream_root(source)),
            *defines,
            str(probe),
            "-o",
            str(pe),
        ]
    )
    p = subprocess.run(command, capture_output=True)
    probe.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, p.stdout, p.stderr)
    p = subprocess.run([str(pe)], capture_output=True)
    assert p.returncode == 0
    match = re.search(rb"RELEASE_LAYOUT ([0-9 -]+)", p.stdout)
    assert match, p.stdout
    size, tag, ctxrt, data, ref, big = list(map(int, match[1].split()))
    abi = load_layout(source)
    fields = abi["offsets"]
    inline = abi["reference_count_model"] == "inline-header"
    assert (size, tag, ctxrt, data, ref, big) == (
        abi["sizes"]["JSValue"],
        fields["JSValue.tag"],
        fields["JSContext.rt"],
        0 if inline else fields["JSMallocBlockHeader.user_data"],
        fields["JSGCObjectHeader.ref_count"] if inline else fields["JSMallocBlockHeader.ref_count"],
        -9,
    )
    ins = [
        "mov r11b, BYTE PTR [rip+JS_FrameBigIntReleaseControl]",
        "cmp r11b, 1",
        "jne release_control",
        f"cmp QWORD PTR [rdx+{tag}], {big}",
        "jne release_generic",
        "mov r10, QWORD PTR [rdx]",
        f"cmp DWORD PTR [r10{ref - data:+}], 0",
        "jle release_generic",
        f"sub DWORD PTR [r10{ref - data:+}], 1",
        "jg release_return",
        "mov rdx, r10",
        f"mov rcx, QWORD PTR [rcx+{ctxrt}]",
        "jmp js_free_rt",
        "release_return:",
        "ret",
        "release_generic:",
        "jmp JS_FreeValue",
        "release_control:",
        "test r11b, r11b",
        "jnz release_generic",
        "release_slow:",
        "jmp JS_FrameBigIntReleaseSlow",
    ]
    root = "JS_FrameBigIntRelease"
    ao = _frame_generated_file(build, "quickjs-interpreter-bigint-release-entry.obj")
    asm = _frame_build_file(
        build,
        "quickjs-interpreter-bigint-release-entry.asm"
        if msvc
        else "quickjs-interpreter-bigint-release-entry.S",
    )
    if msvc:
        lines = [
            "OPTION CASEMAP:NONE",
            "OPTION DOTNAME",
            "EXTERN JS_FrameBigIntReleaseControl:BYTE",
            "EXTERN JS_FrameBigIntReleaseSlow:PROC",
            "EXTERN JS_FreeValue:PROC",
            "EXTERN js_free_rt:PROC",
            ".qjssrc$C SEGMENT ALIGN(16) 'CODE'",
            "PUBLIC " + root + ", " + root + "_end",
            root + " PROC FRAME",
            ".endprolog",
            *[x.replace("rip+", "") for x in ins],
            root + "_end LABEL BYTE",
            root + " ENDP",
            ".qjssrc$C ENDS",
            "END",
        ]
        command = [str(compiler.with_name("ml64.exe")), "/nologo", "/c", "/Fo" + str(ao), str(asm)]
    else:
        lines = [
            ".intel_syntax noprefix",
            '.section .qjssrc$C,"xr"',
            ".p2align 4",
            ".globl " + root + ", " + root + "_end",
            ".def " + root + "; .scl 2; .type 32; .endef",
            ".seh_proc " + root,
            root + ":",
            ".seh_endprologue",
            *ins,
            root + "_end:",
            ".seh_endproc",
        ]
        command = [str(compiler), "-c", str(asm), "-o", str(ao)]
    asm.write_text("\n".join(lines) + "\n", encoding="ascii")
    p = subprocess.run(command, capture_output=True)
    asm.with_suffix(".log").write_bytes(p.stdout + p.stderr)
    assert p.returncode == 0, (command, p.stdout, p.stderr)
    ac = C.Coff(ao.read_bytes())
    for number, rec in enumerate(ac.section_records, 1):
        name = ac.sections[number - 1]["name"]
        if name.startswith("/"):
            at = int(name[1:])
            name = ac.strings[at : ac.strings.index(0, at)].decode()
        renamed = (
            ".pdata$zzzzzznullfast"
            if name.startswith(".pdata")
            else ".qjssrc$C"
            if name.startswith(".xdata")
            else None
        )
        if renamed:
            at = len(ac.strings)
            ac.strings += renamed.encode() + b"\0"
            ac.data[rec["pos"] : rec["pos"] + 8] = ("/" + str(at)).encode().ljust(8, b"\0")
            for index, sym in ac.all_symbols.items():
                if (
                    sym["section"] == number
                    and sym["storage"] == 3
                    and sym["type"] == 0
                    and sym["name"] == name
                ):
                    struct.pack_into("<II", ac.data, ac.table + index * ac.stride, 0, at)
        if name.startswith((".pdata", ".xdata")) or name == ".qjssrc$C":
            struct.pack_into("<I", ac.data, rec["pos"] + 36, (rec["flags"] & ~0xE0) | 0x60000040)
    ao.write_bytes(ac.finish())
    merge = module("release_merge", "extension-merge.py")
    merge.append(
        output,
        ao,
        root,
        "bigint-release-entry",
        keep_all=True,
        code_input=".qjssrc$C",
        code_output=".qjssrc$C",
        pdata_output=".pdata$zzzzzznullfast",
        base_owner="JS_FrameBigIntReleaseSlow",
        baseline_sections=(),
    )
    (_frame_generated_file(build, "quickjs-bigint-release-generation.json")).write_text(
        json.dumps(
            dict(
                status="passed",
                layout=[size, tag, ctxrt, data, ref, big],
                exports=exports,
                copied_helpers=copies,
                source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                private_sha256=hashlib.sha256((prefix + header).encode()).hexdigest(),
                assembly_sha256=hashlib.sha256(asm.read_bytes()).hexdigest(),
                leaf_object_sha256=hashlib.sha256(ao.read_bytes()).hexdigest(),
                policy="Typed primitive boundary only, guarded exact heap BigInt tag and positive original refcount. "
                "Original decrement semantics; last reference tail-enters original js_free_rt accounting/arena/backing allocator. "
                "All other values and disabled/uninitialized state preserve original JS_FreeValue ABI. No native frame, roots, "
                "allocator/layout change, code padding, PGO or address selection.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def route_big_release(path):
    """Exactly seven existing CALL operands, no original instruction changes."""
    import hashlib, importlib.util, json, os, struct
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "release_route_coff", _frame_tool_path("object-adapter")
    )
    C = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(C)
    names = (
        ("JS_FrameInterpPrimitive_add", "JS_FrameInterpPrimitive_mul")
        if path.name == "quickjs-interpreter.c.obj"
        else ("JS_FrameAddLocalBig",)
    )
    report = path.with_name(path.name + ".bigint-release.json")
    backup = path.with_name(path.name + ".before-bigint-release")
    stamp = path.stat()
    raw = path.read_bytes()
    if report.exists():
        r = json.loads(report.read_text())
        assert r["status"] == "passed"
        assert r["after_sha256"] == hashlib.sha256(raw).hexdigest()
        assert r["before_sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
        return
    assert not backup.exists()
    c = C.Coff(raw)
    old = C.Coff(raw)
    idx = c.external("JS_FrameBigIntRelease")
    routes = []
    for name in names:
        sym = c.symbols[name]
        rec = c.section_records[sym["section"] - 1]
        end = min(
            [
                x["value"]
                for x in c.all_symbols.values()
                if x["type"] & 32 and x["section"] == sym["section"] and x["value"] > sym["value"]
            ]
            + [rec["size"]]
        )
        own = []
        for i in range(rec["count"]):
            at = rec["reloc"] + 10 * i
            off, sy, kind = struct.unpack_from("<IIH", c.data, at)
            if not sym["value"] <= off < end or c.all_symbols[sy]["name"] != "JS_FreeValue":
                continue
            assert kind == 4 and c.data[rec["raw"] + off - 1] == 0xE8, (name, off, kind)
            struct.pack_into("<I", c.data, at + 4, idx)
            own.append(
                dict(
                    caller=name,
                    section=sym["section"],
                    offset=off,
                    kind=kind,
                    old="JS_FreeValue",
                    target="JS_FrameBigIntRelease",
                )
            )
        assert len(own) == (3 if name == "JS_FrameAddLocalBig" else 2), (name, own)
        routes.extend(own)
    result = bytearray(c.finish())
    delta = len(result) - len(raw)
    old_end = old.string_offset + struct.unpack_from("<I", raw, old.string_offset)[0]
    for rec in old.section_records:
        for field in (20, 24, 28):
            at = rec["pos"] + field
            value = struct.unpack_from("<I", raw, at)[0]
            if value and value >= old_end:
                struct.pack_into("<I", result, at, value + delta)
    after = C.Coff(result)
    assert all(after.all_symbols[i] == s for i, s in old.all_symbols.items())
    for number, (a, b) in enumerate(zip(old.section_records, after.section_records), 1):
        assert a["size"] == b["size"] and a["count"] == b["count"] and a["flags"] == b["flags"]
        assert raw[a["raw"] : a["raw"] + a["size"]] == result[b["raw"] : b["raw"] + b["size"]]
        oldrr = bytearray(raw[a["reloc"] : a["reloc"] + a["count"] * 10])
        newrr = bytearray(result[b["reloc"] : b["reloc"] + b["count"] * 10])
        for r in routes:
            if r["section"] != number:
                continue
            hits = [
                i
                for i in range(a["count"])
                if struct.unpack_from("<I", oldrr, 10 * i)[0] == r["offset"]
            ]
            assert len(hits) == 1
            at = 10 * hits[0] + 4
            newrr[at : at + 4] = oldrr[at : at + 4]
        assert newrr == oldrr, number
    backup.write_bytes(raw)
    path.write_bytes(result)
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    report.write_text(
        json.dumps(
            dict(
                status="passed",
                before_sha256=hashlib.sha256(raw).hexdigest(),
                after_sha256=hashlib.sha256(result).hexdigest(),
                routes=routes,
                policy="Only typed REL32 CALL symbol operands inside three proven BigInt boundaries; all original "
                "payloads, symbols, section order/size/flags/unwind and all other relocations retained.",
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
