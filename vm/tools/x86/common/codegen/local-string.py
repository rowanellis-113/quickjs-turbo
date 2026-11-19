"""String add_loc uses one dedicated C boundary and returns to the same frame.

Borrow the original concat and set_value semantics. A local retains its own
reference until concat succeeds, including allocation failure. No coercing
object or Symbol reaches this path. This module emits a separate late native
range; it never inserts instructions into old dispatch/BigInt code.
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
from native_abi import current as current_abi
import argparse, hashlib, importlib.util, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def generate(source, out, *, source_owned=False):
    frame = _frame_source_text(source, "quickjs-interpreter-loop.h")
    prefix = frame[: frame.index("static const uint8_t js_frame_opcode_sizes[]")]
    code = (
        """/* Generated string-only add_loc boundary. */
#include "quickjs-interpreter-private.h"
#if defined(_MSC_VER)
#define LOCAL_STRING_CODE __declspec(code_seg(".qjscold$zznullfast")) no_inline
#else
#define LOCAL_STRING_CODE __attribute__((section(".qjsleaf$zzzzlocal"), noipa))
#endif
"""
        + prefix
        + """
extern int JS_FrameInterpSlow(JSFrameRegisterState *state);
extern int JS_FrameInterpAddTrampoline(JSFrameRegisterState *state);
extern unsigned char JS_FrameLocalRopeModeGet(void);
extern JSValue qjs_frame_core_js_new_string_rope(JSContext *, JSValue, JSValue);
_Static_assert(offsetof(JSFrame, sf)==0 && offsetof(JSFrame, bytecode)==80 &&
               offsetof(JSStackFrame,var_buf)==QJS_ABI_OFF_JSStackFrame_var_buf,
               "Win64 local-rope selector frame and local-buffer ABI");
extern const char JS_FrameAddLocalDisable[];
_Static_assert(JS_TAG_STRING==-7 && JS_TAG_STRING_ROPE==-6, "native string guard tags");
_Static_assert(offsetof(JSRuntime,module_loader_has_attr)==QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
               offsetof(JSRuntime,u)==QJS_ABI_OFF_JSRuntime_u, "local mode uses measured runtime padding");
LOCAL_STRING_CODE int JS_FrameAddLocalString(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSStackFrame *sf=&frame->sf;
    JSContext *ctx=frame->bytecode->realm;
    unsigned char *mode=(unsigned char *)state->rt+offsetof(JSRuntime,module_loader_has_attr)+3;
    JSValue *sp=state->sp, *pv=&sf->var_buf[state->pc[1]];
    JSValue result;
    const char *flag;
    if (!*mode) {
#if defined(_MSC_VER)
        flag=JS_FrameAddLocalDisable;
#else
        __asm__("lea JS_FrameAddLocalDisable(%%rip), %0" : "=r"(flag));
#endif
        *mode=getenv(flag)==NULL ? 1 : 2;
    }
    if (*mode!=1) return JS_FrameInterpSlow(state);
    assert(tag_is_string(JS_VALUE_GET_TAG(*pv)) && tag_is_string(JS_VALUE_GET_TAG(sp[-1])));
    js_frame_begin_c(state);
    state->pc+=2;
    state->sp=sp-1;
    sf->cur_pc=state->pc;
    /* Already-string operands need no ToPrimitive callback. Concat owns the
       RHS and a duplicate of the local; the original local is still a root. */
    result=JS_ConcatString(ctx,js_dup(*pv),sp[-1]);
    if (JS_IsException(result)) {
        sp[-1]=JS_UNDEFINED; /* consumed RHS must never be freed twice */
        state->exception_pending=true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    set_value(ctx,pv,result); /* publish result before releasing old local */
    js_frame_finish_c(state);
    return 2;
}
"""
    )
    code += "\n" + _frame_source_text(source, "string-local-rope-append.inc")
    if source_owned:
        return code
    out.write_text(code, encoding="utf-8")
    out.with_suffix(".source.json").write_text(
        json.dumps(
            dict(
                generator_sha256=sha(Path(__file__)),
                core_sha256=sha(_frame_source_file(source, "quickjs.c")),
                frame_header_sha256=sha(_frame_source_file(source, "quickjs-interpreter-loop.h")),
                generated_sha256=sha(out),
                ownership="Original local retained; duplicate local plus RHS consumed by core concat; success publishes before releasing old local; failure keeps original local and poisons consumed RHS.",
            ),
            indent=2,
        )
        + "\n"
    )


def emit(out):
    abi_layout = current_abi()
    abi_fields, abi_bits = abi_layout["offsets"], abi_layout["bits"]
    name = "JS_FrameAddLocalStringCold"
    lines = [
        "mov eax, DWORD PTR [r8+8]",
        "sub eax, -7",
        "cmp eax, 1",
        "ja interp_slow",
        "mov eax, DWORD PTR [r13-8]",
        "sub eax, -7",
        "cmp eax, 1",
        "ja interp_slow",
        "mov r10, QWORD PTR [rbx+56]",
        f"cmp BYTE PTR [r10+{abi_fields['JSRuntime.module_loader_has_attr'] + 3}], 2",
        "je interp_slow",
        "mov QWORD PTR [rbx], rbp",
        "mov QWORD PTR [rbx+16], r12",
        "mov QWORD PTR [rbx+24], r13",
        "mov rcx, rbx",
        "call JS_FrameAddLocalString",
        "cmp eax, 2",
        "je local_string_done",
        "test eax, eax",
        "jne interp_exit",
        "jmp interp_reload",
        "local_string_done:",
        "mov r12, QWORD PTR [rbx+16]",
        "mov r13, QWORD PTR [rbx+24]",
        "movzx eax, BYTE PTR [r12]",
        "jmp QWORD PTR [rdi+rax*8]",
    ]
    asm = [
        "OPTION CASEMAP:NONE",
        "OPTION DOTNAME",
        "EXTERN JS_FrameAddLocalString:PROC",
        "EXTERN interp_slow:PROC",
        "EXTERN interp_exit:PROC",
        "EXTERN interp_reload:PROC",
        "EXTERN JS_FrameInterpPropertyCold_unwind:BYTE",
        ".qjscold$zznullfast SEGMENT ALIGN(16) 'CODE'",
        "PUBLIC " + name + ", " + name + "_end",
        name + " PROC",
    ]
    gas = [
        ".intel_syntax noprefix",
        '.section .qjsleaf$zzzzlocalguard,"xr"',
        ".p2align 4",
        ".globl " + name + ", " + name + "_end",
        ".def " + name + "; .scl 2; .type 32; .endef",
        name + ":",
    ]
    for x in lines:
        asm.append(x[:-1] + "::" if x.endswith(":") else x.replace(" interp_", " NEAR PTR interp_"))
        gas.append(x)
    asm += [
        name + "_end LABEL BYTE",
        name + " ENDP",
        ".qjscold$zznullfast ENDS",
        ".pdata$zzzzzznullfast SEGMENT ALIGN(4) READONLY 'DATA'",
        "DD IMAGEREL "
        + name
        + ", IMAGEREL "
        + name
        + "_end, IMAGEREL JS_FrameInterpPropertyCold_unwind",
        ".pdata$zzzzzznullfast ENDS",
        "END",
    ]
    gas += [
        name + "_end:",
        '.section .pdata$zzzzzznullfast,"dr"',
        ".p2align 2",
        ".rva " + name + ", " + name + "_end, JS_FrameInterpPropertyCold_unwind",
    ]
    (out / "quickjs-interpreter-local-string-win64.asm").write_text(
        "\n".join(asm) + "\n", encoding="utf-8"
    )
    (out / "quickjs-interpreter-local-string-win64.S").write_text(
        "\n".join(gas) + "\n", encoding="utf-8"
    )


def compile_extra(source, build, out):
    sp = importlib.util.spec_from_file_location("local_compile", _frame_tool_path("atod"))
    m = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    # Share the original compiler argument and COFF checks, using explicit
    # generation/placement parameters. No extra original C TU is changed.
    records = json.loads((_frame_build_file(build, "compile_commands.json")).read_text())
    original = next(x for x in records if Path(x["file"]).name == "quickjs-interpreter.c")
    late = (
        ".qjscold$zznullfast"
        if any(x.lower() == "/nologo" for x in m.win_argv(original["command"]))
        else ".qjsleaf$zzzzlocal"
    )
    m.compile_extra(
        source,
        build,
        out,
        generator=generate,
        filename="quickjs-interpreter-local-string.c",
        late_name=late,
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--build", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    assert a.compile
    compile_extra(a.source, a.build, a.out)
