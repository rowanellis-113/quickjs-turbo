"""Accepted GNU BigInt/local-add/release and decimal conversion, real SysV."""

import sys as _x86_sys
from pathlib import Path as _X86Path

if str(_X86Path(__file__).resolve().parents[2]) not in _x86_sys.path:
    _x86_sys.path.insert(0, str(_X86Path(__file__).resolve().parents[2]))
from x86.common.paths_x86 import source_file
import hashlib
import json
import re
from admission import function
from arguments import asm_body
from c_workers import module, replace_one

OWNERS = (
    "tools/x86/common/codegen/free-boundary.py",
    "tools/x86/common/codegen/add-local.py",
    "src/common/call/quickjs-interpreter-bigint.inc",
    "src/x86/common/string-to-number.c",
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract(source, layout):
    data = json.loads((source / "src/x86/linux/abi/numeric.json").read_text())
    for name, digest in data["owners"].items():
        if sha(source_file(source, name)) != digest:
            raise ValueError("Review accepted numeric owner: " + name)
    if sha(source_file(source, "quickjs.c")) != data["pinned_core_sha256"]:
        raise ValueError("Review pinned numeric ownership and converter callers")
    if layout["reference_count_model"] != "inline-header":
        raise ValueError("Review original inline BigInt reference header")
    fields = layout["offsets"]
    if fields["JSRuntime.u"] - fields["JSRuntime.module_loader_has_attr"] < 4:
        raise ValueError("Local-add mode must occupy its original measured padding")
    return data


def local_rows(source, layout):
    owner = module(source, "add-local")
    # Only the measured field dictionary is substituted; the source factory
    # supplies every instruction, guard, branch, result and cursor commit.
    owner.current_abi = lambda: layout
    masm, gas = ["END"], []
    owner.append(masm, gas, False)
    rows = asm_body(source, OWNERS[1], "JS_FrameAddLocalBigCold", layout, expanded="\n".join(gas))
    return [
        r.replace("JS_FrameAddLocalStringCold", "JS_FrameLinuxAddLocalStringCold") for r in rows
    ]


def append(source, output, stream, blocks, layout):
    data = contract(source, layout)
    before = "jne JS_FrameLinuxAddLocalStringCold"
    if stream["code"].count(before) != 2:
        raise ValueError("Review both original add_loc nonnumeric misses")
    stream["code"][:] = [
        "jne JS_FrameAddLocalBigCold" if r == before else r for r in stream["code"]
    ]
    rows = local_rows(source, layout)
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        functions=["JS_FrameAddLocalBigCold"],
        native_functions=["JS_FrameBigIntRelease"],
        C_helpers=["JS_FrameAddLocalBig"],
        source_factory="Complete add-local.py factory with measured fields",
        local_add_edges=2,
        local_mode=layout["offsets"]["JSRuntime.module_loader_has_attr"] + 3,
        leaf_abi="void(ctx=RDI,payload=RSI,tag=RDX);tail actual js_free_rt(rt=RDI,ptr=RSI)",
        reference_header=0,
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
    )
    (output / "NUMERIC-VM.json").write_text(json.dumps(record, indent=2) + "\n")
    return [("JS_FrameAddLocalBigCold", rows)], record


def render_native(source, layout):
    # Exact accepted guard/debit/tail algorithm, expressed using the real SysV
    # by-value JSValue registers. No caller stack frame, Windows home space,
    # private compiler clone or guessed header is involved.
    contract(source, layout)
    ctxrt = layout["offsets"]["JSContext.rt"]
    name = "JS_FrameBigIntRelease"
    return [
        '.section .text.qjs_linux_bigint_release,"ax",@progbits',
        ".p2align 4",
        ".globl " + name,
        ".hidden " + name,
        ".type " + name + ",@function",
        name + ":",
        ".cfi_startproc",
        "endbr64",
        "movzx r11d, BYTE PTR [rip+JS_FrameBigIntReleaseControl]",
        "cmp r11b, 1",
        "jne linux_bigint_release_control",
        "cmp rdx, -9",
        "jne linux_bigint_release_generic",
        "cmp DWORD PTR [rsi], 0",
        "jle linux_bigint_release_generic",
        "sub DWORD PTR [rsi], 1",
        "jg linux_bigint_release_return",
        "mov rdi, QWORD PTR [rdi+" + str(ctxrt) + "]",
        "jmp js_free_rt",
        "linux_bigint_release_return:",
        "ret",
        "linux_bigint_release_generic:",
        "jmp JS_FreeValue",
        "linux_bigint_release_control:",
        "test r11b, r11b",
        "jnz linux_bigint_release_generic",
        "jmp JS_FrameBigIntReleaseSlow",
        ".cfi_endproc",
        ".size " + name + ",.-" + name,
        ".hidden JS_FrameBigIntReleaseControl",
        ".hidden JS_FrameBigIntReleaseSlow",
        '.section .rodata.qjs_linux_add_local,"a",@progbits',
        ".globl JS_FrameAddLocalDisable",
        ".hidden JS_FrameAddLocalDisable",
        ".type JS_FrameAddLocalDisable,@object",
        "JS_FrameAddLocalDisable:",
        '.asciz "QJS_DISABLE_NATIVE_ADD_LOCAL"',
        ".size JS_FrameAddLocalDisable,.-JS_FrameAddLocalDisable",
    ]


def generate(source, output, core, layout):
    data = contract(source, layout)
    declaration = """
__attribute__((visibility("hidden"))) void JS_FrameBigIntRelease(JSContext *,JSValue);
double JS_FrameAtod(const char *,const char **,int,int,JSATODTempMem *);
"""
    # dtoa.h owns JSATODTempMem, so place actual declarations after that include.
    core = replace_one(
        core,
        '#include "dtoa.h"',
        '#include "dtoa.h"\n' + declaration,
        "actual numeric C signatures",
    )
    # The raw core has one real converter call and one comment mentioning it.
    call = "d = js_atod(buf, NULL, radix, is_float ? 0 : JS_ATOD_INT_ONLY,"
    core = replace_one(
        core,
        call,
        call.replace("js_atod(", "JS_FrameAtod("),
        "single actual core decimal converter call",
    )

    primitive = (source / OWNERS[2]).read_text()
    for name in ("JS_FrameInterpPrimitive_add", "JS_FrameInterpPrimitive_mul"):
        body = function(primitive, "FRAME_PROPERTY_CODE int " + name + "(")
        if body.count("JS_FreeValue(ctx, ") != 2:
            raise ValueError("Review original two BigInt input owners: " + name)
        primitive = replace_one(
            primitive,
            body,
            body.replace("JS_FreeValue(ctx, ", "JS_FrameBigIntRelease(ctx, "),
            "two original primitive input-release calls " + name,
        )
    primitive_path = output / "quickjs-linux-bigint.h"
    primitive_path.write_text(primitive)
    loop = output / "quickjs-linux-loop.h"
    before = sha(loop)
    loop.write_text(
        replace_one(
            loop.read_text(),
            '#include "src/common/call/quickjs-interpreter-bigint.inc"',
            '#include "quickjs-linux-bigint.h"',
            "same original primitive body owner",
        )
    )
    admission = output / "ADMISSION.json"
    receipt = json.loads(admission.read_text())
    if receipt["generated_loop_sha256"] != before:
        raise ValueError("Review previous loop producer before numeric include routing")
    receipt["before_numeric_generated_loop_sha256"] = before
    receipt["generated_loop_sha256"] = sha(loop)
    receipt["post_numeric_loop_before_sha256"] = before
    receipt["post_numeric_loop_sha256"] = sha(loop)
    receipt["post_numeric_transform"] = (
        "Only the BigInt source include is routed to four exact release-call substitutions"
    )
    admission.write_text(json.dumps(receipt, indent=2) + "\n")

    local = module(source, "add-local").generate(source)
    if local.count("JS_FreeValue(ctx, ") != 2:
        raise ValueError("Review local BigInt duplicate and RHS releases")
    local = local.replace("JS_FreeValue(ctx, ", "JS_FrameBigIntRelease(ctx, ")
    local = replace_one(
        local,
        "    set_value(ctx,pv,result);",
        "    JSValue old_local=*pv;\n    *pv=result;\n    JS_FrameBigIntRelease(ctx,old_local);",
        "third inlined set_value release,after publishing the result",
    )
    local = local.replace(
        "FRAME_NULL_CODE",
        '__attribute__((section(".text.qjs_linux_add_local"),noipa,visibility("hidden")))',
    )
    release = module(source, "free-boundary").BIGINT_RELEASE_BACKEND
    release = release.replace(".qjssrc$C", ".text.qjs_linux_bigint_release")
    release = release.replace(".qjssrm", ".data.qjs_linux_bigint_release")
    release = replace_one(
        release,
        "static _Atomic unsigned char JS_FrameBigIntReleaseControl",
        '__attribute__((visibility("hidden"))) _Atomic unsigned char JS_FrameBigIntReleaseControl',
        "actual byte control shared with SysV leaf",
    )
    assertions = """
_Static_assert(sizeof(JSValue)==16 && offsetof(JSValue,tag)==8,"SysV JSValue pair");
_Static_assert(offsetof(JSBigInt,header.ref_count)==0,"actual inline BigInt reference header");
_Static_assert(JS_TAG_BIG_INT==-9 && JS_TAG_SHORT_BIG_INT==7,"retained BigInt tags");
_Static_assert(offsetof(JSRuntime,u)>offsetof(JSRuntime,module_loader_has_attr)+3,"original local-add padding");
_Static_assert(sizeof(_Atomic unsigned char)==1,"one-byte release policy");
_Static_assert(__builtin_types_compatible_p(__typeof__(&js_free_rt),void (*)(JSRuntime *,void *)),"actual original final BigInt allocator ABI");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FreeValue),void (*)(JSContext *,JSValue)),"actual original generic release ABI");
"""
    path = output / "quickjs-linux-numeric.h"
    path.write_text(
        "#include <stdatomic.h>\n"
        + assertions
        + release
        + "\n"
        + local
        + "\n#undef RELEASE_CODE\n#undef RELEASE_LOAD\n#undef RELEASE_CAS\n"
    )
    core += '\n#include "quickjs-linux-numeric.h"\n'
    decimal = (source / "src/x86/common/string-to-number.c").read_text()
    decimal = decimal.replace(".qjsleaf$zzzatod", ".text.qjs_linux_atod")
    decimal_path = output / "quickjs-linux-atod.c"
    decimal_path.write_text(decimal)
    record = dict(
        status="generated-not-qualified",
        owners=data["owners"],
        source_files={"tools/x86/linux/numeric.py": sha(source / "tools/x86/linux/numeric.py")},
        generated_sha256=sha(path),
        primitive_sha256=sha(primitive_path),
        decimal_sha256=sha(decimal_path),
        decimal_callers=1,
        release_calls=dict(primitive_add=2, primitive_mul=2, add_local=3),
        entries=[
            "JS_FrameAddLocalBig",
            "JS_FrameBigIntReleaseSlow",
            "JS_FrameBigIntReleaseState",
            "JS_FrameAtod",
        ],
        decimal_source="Complete unchanged common converter body;ELF section spelling only",
        local_source="Complete source-owned primitive arithmetic and local owner;original begin/finish C and fallbacks",
        loop_after_sha256=sha(loop),
        frame_growth=0,
        state_growth=0,
        new_strong_roots=0,
        per_runtime_heap_growth=0,
    )
    (output / "NUMERIC.json").write_text(json.dumps(record, indent=2) + "\n")
    return core
