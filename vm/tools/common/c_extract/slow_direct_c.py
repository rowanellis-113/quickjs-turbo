"""Pure-C slow-direct dispatcher, indexed steps, and instanceof leaf extractor."""

import re
import sys as _frame_sys
from pathlib import Path as _FramePath

_frame_tools_root = str(_FramePath(__file__).resolve().parents[2])
if _frame_tools_root not in _frame_sys.path:
    _frame_sys.path.insert(0, _frame_tools_root)
from common.paths import (
    activate_tools as _frame_activate_tools,
    tool_path as _frame_tool_path,
    source_file as _frame_source_file,
    source_text as _frame_source_text,
    generated_file as _frame_generated_file,
    project_root as _frame_project_root,
    build_file as _frame_build_file,
)

from bellard_backports import writable_array_append

BODY = r"""
#include <stdatomic.h>
typedef struct JSFrameSlowDirectData {
    _Atomic(unsigned char) mode;
    unsigned char reserved[7];
    uint64_t hits;
} JSFrameSlowDirectData;
_Static_assert(sizeof(JSFrameSlowDirectData)==16 &&
    offsetof(JSFrameSlowDirectData,hits)==8 && sizeof(JSFrame)==128 &&
    sizeof(JSStackFrame)==QJS_ABI_SIZE_JSStackFrame,"direct slow control and selected frame ABI");
#ifdef _MSC_VER
#pragma section(".qjszzcm$zzzzzzzzzzzzzzslowdirect",read,write)
__declspec(allocate(".qjszzcm$zzzzzzzzzzzzzzslowdirect"))
#else
__attribute__((section(".qjslcm$zzzzslowdirect"),used))
#endif
JSFrameSlowDirectData JS_FrameSlowDirectData={255};
extern int JS_FrameVarargsSlowSelect(JSFrameRegisterState *state);
extern int JS_FrameVarargsSlow(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameSlowDirectConfigure(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameSlowDirectIndexedGet(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameSlowDirectIndexedGet2(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameSlowDirectIndexedPut(JSFrameRegisterState *state);
static FRAME_CODE int JS_FrameSlowDirectInstanceOf(JSFrameRegisterState *state);

/* Selected operations retain their exact opcode bodies in narrow C steps.
 * Other operations and every pending exception retain the complete ordinary,
 * forward, iterator/checkpoint and varargs executor. set_name still uses its
 * original selector hook. This dispatcher does not mutate VM state.
 */
FRAME_CODE int JS_FrameSlowDirectSelect(JSFrameRegisterState *state)
{
    unsigned char mode=atomic_load_explicit(&JS_FrameSlowDirectData.mode,memory_order_relaxed);
    if(unlikely(mode==255))return JS_FrameSlowDirectConfigure(state);
    if((mode&3)==1) {
        if(!state->exception_pending && *state->pc==OP_set_name)
            return JS_FrameVarargsSlowSelect(state);
        if(mode&4)JS_FrameSlowDirectData.hits++;
        if(!state->exception_pending && *state->pc==OP_instanceof && !(mode&64))
            return JS_FrameSlowDirectInstanceOf(state);
        if(!(mode&8) && !state->exception_pending) {
            switch(*state->pc) {
            case OP_get_array_el: return JS_FrameSlowDirectIndexedGet(state);
            case OP_get_array_el2: return JS_FrameSlowDirectIndexedGet2(state);
            case OP_put_array_el: return JS_FrameSlowDirectIndexedPut(state);
            }
        }
        return JS_FrameVarargsSlow(state);
    }
    return JS_FrameVarargsSlowSelect(state);
}

/* First use is already at the real native C boundary. Publish all live roots
 * and synchronize quota before environment access; complete before dispatch.
 * Configuration has process lifetime, like the existing append control.
 */
static FRAME_CODE int JS_FrameSlowDirectConfigure(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    unsigned char mode;
    js_frame_begin_c(state);
    frame->saved_sp=state->sp;
    frame->sf.cur_sp=state->sp;
    frame->sf.cur_pc=state->pc;
    mode=getenv("QJS_DISABLE_FRAME_SLOW_DIRECT")?2:1;
    if(getenv("QJS_OBSERVE_FRAME_SLOW_DIRECT"))mode|=4;
    if(getenv("QJS_DISABLE_FRAME_INDEXED_STEP"))mode|=8;
    if(getenv("QJS_DISABLE_FRAME_INDEXED_OWN"))mode|=16;
    if(getenv("QJS_DISABLE_FRAME_STACK_INSERT"))mode|=32;
    if(getenv("QJS_DISABLE_FRAME_INSTANCEOF_STEP"))mode|=64;
    if(getenv("QJS_DISABLE_FRAME_INSTANCEOF_LEAF") ||
       getenv("QJS_DISABLE_FRAME_INSTANCEOF") ||
       getenv("QJS_OBSERVE_FRAME_INSTANCEOF"))mode|=128;
    atomic_store_explicit(&JS_FrameSlowDirectData.mode,mode,memory_order_relaxed);
    js_frame_finish_c(state);
    return JS_FrameSlowDirectSelect(state);
}
"""


def indexed_steps(source):
    # Keep the already-qualified frame opcode's dense/typed/generic bodies.
    # The pinned C interpreter lacks the retained read fast-path prefixes;
    # prove those reads' complete generic/error tails against the pinned core.
    # The store body is identical in both sources.
    # Only its successful boundary is narrowed: it cannot allocate a JS frame
    # or change the activation's ownership ledger. Exceptions re-enter the
    # existing complete varargs/checkpoint/forward unwinder.
    text = _frame_source_text(source, "quickjs-interpreter-ops.h")
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    output = []
    for opcode, suffix, breaks in [
        ("get_array_el", "Get", 3),
        ("get_array_el2", "Get2", 3),
        ("put_array_el", "Put", 3),
    ]:
        marker = "        CASE(OP_" + opcode + "):\n"
        start = text.index(marker) + len(marker)
        end = text.index("\n        CASE(", start)
        body = text[start:end]
        original_start = core.index(marker) + len(marker)
        original = core[original_start : core.index("\n        CASE(", original_start)]
        if opcode == "put_array_el":
            assert body.strip() == writable_array_append(original).strip(), (
                "Indexed store differs from pinned core",
                opcode,
            )
        else:
            tail = "                sf->cur_pc = pc;"
            assert body[body.index(tail) :].strip() == original[original.index(tail) :].strip(), (
                "Indexed read generic tail differs from pinned core",
                opcode,
            )
        assert body.count("BREAK;") == breaks and body.count("goto exception;") == 1, (opcode, body)
        output.append(
            r"""
/* Original indexed opcode, without the frame/return switch. Readonly array
 * extension has already passed the inherited array-append selector guard. */
static FRAME_CODE int JS_FrameSlowDirectIndexed"""
            + suffix
            + r"""(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSStackFrame *sf=&frame->sf;
    JSContext *ctx=frame->bytecode->realm;
    JSValue *sp=state->sp;
    uint8_t *pc=state->pc+1;
    js_frame_begin_c(state);
"""
            + body.replace("BREAK;", "goto indexed_done;")
            + r"""
indexed_done:
    state->pc=pc;
    state->sp=sp;
    js_frame_finish_c(state);
    return 0;
exception:
    state->pc=pc;
    state->sp=sp;
    state->exception_pending=true;
    js_frame_finish_c(state);
    return JS_FrameVarargsSlow(state);
}
"""
        )
    return "".join(output)


def instanceof_step(source):
    # Keep the pinned opcode and its existing operator/intrinsic implementation.
    # Retained compiler configuration still selects JS_FrameInstanceOf; legacy retains JS_IsInstanceOf. Neither path changes dynamic hasInstance checks.
    marker = "        CASE(OP_instanceof):\n"
    text = _frame_source_text(source, "quickjs-interpreter-ops.h")
    core = _frame_source_file(source, "quickjs.c").read_text(encoding="utf-8")
    start = text.index(marker) + len(marker)
    body = text[start : text.index("\n        CASE(", start)]
    start = core.index(marker) + len(marker)
    original = core[start : core.index("\n        CASE(", start)]
    assert body.strip() == original.strip(), "Review upstream instanceof semantics"
    assert body.count("BREAK;") == body.count("goto exception;") == 1
    return (
        r"""
/* Original instanceof opcode, without the full interpreter state switch.
 * Operands remain owned on failure; the existing complete unwinder handles it.
 * Success keeps the original operator's coercion, poll and release ordering. */
static FRAME_CODE int JS_FrameSlowDirectInstanceOf(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSStackFrame *sf=&frame->sf;
    JSContext *ctx=frame->bytecode->realm;
    JSValue *sp=state->sp;
    uint8_t *pc=state->pc+1;
    js_frame_begin_c(state);
"""
        + body.replace("BREAK;", "goto instanceof_done;")
        + r"""
instanceof_done:
    state->pc=pc;
    state->sp=sp;
    js_frame_finish_c(state);
    return 0;
exception:
    state->pc=pc;
    state->sp=sp;
    state->exception_pending=true;
    js_frame_finish_c(state);
    return JS_FrameVarargsSlow(state);
}
"""
    )


def instance_leaf(
    source,
    *,
    leaf_condition="#if defined(__linux__)",
    bind_has_instance=(
        "    JSCFunction *builtin_has_instance = qjs_frame_core_js_function_hasInstance;\n"
    ),
):
    # Copy the already-qualified pure proof into this append-only module.
    # Leave the original value module byte-for-byte unchanged: adding another
    # caller there changes GCC inlining and shifts unrelated .text functions.
    text = (source / "src/common/value/instanceof.c").read_text(encoding="utf-8")
    start = text.index("static int instance_try(")
    end = text.index("\nint JS_FrameInstanceOf(", start)
    proof = text[start:end].replace("instance_try(", "js_frame_instance_leaf_try(")
    plain = re.sub(r"/\*.*?\*/|//[^\n]*", "", proof, flags=re.S)
    calls = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", plain))
    assert calls <= {
        "js_frame_instance_leaf_try",
        "if",
        "for",
        "while",
        "JS_IsObject",
        "JS_VALUE_GET_OBJ",
        "find_own_property",
    }, ("Review leaf proof purity before admitting new calls", sorted(calls))
    # The iterator-pruned header deliberately omits this unrelated C built-in.
    # GNU's existing instanceof adapter already exports the exact core alias.
    declaration = (
        "extern JSValue qjs_frame_core_js_function_hasInstance("
        "JSContext *, JSValueConst, int, JSValueConst *);\n"
    )
    assert proof.count("js_function_hasInstance") == 1
    proof = proof.replace("js_function_hasInstance", "builtin_has_instance")
    bind = bind_has_instance
    proof = proof.replace("{\n", "{\n" + bind, 1)
    return (
        "\n"
        + leaf_condition
        + "\n"
        + declaration
        + proof
        + r"""/* Private native opcode ABI. The caller retains its Dirty table and live
 * registers: no allocation, callback, finalizer, quota synchronization or GC
 * observer may run here. Configuration is performed only by the original slow-direct
 * boundary. Observer mode retains the original counted intrinsic path. Reject before changing any state, including the poll debit.
 * Two aliased operands consume TWO references, so separate >1 tests would be
 * insufficient. A successful proof leaves both objects alive on release.
 */
FRAME_CODE int JS_FrameSlowDirectTryInstanceOfLeaf(JSContext *ctx, JSValue *sp)
{
    unsigned mode = atomic_load_explicit(&JS_FrameSlowDirectData.mode, memory_order_relaxed);
    JSObject *value, *ctor;
    int result;
    if ((mode & 3) != 1 || (mode & (64 | 128)) || !JS_IsObject(sp[-2]) || !JS_IsObject(sp[-1]))
        return 0;
    value = JS_VALUE_GET_OBJ(sp[-2]);
    ctor = JS_VALUE_GET_OBJ(sp[-1]);
    if (value == ctor ? JS_REF_COUNT(value) <= 2
                      : JS_REF_COUNT(value) <= 1 || JS_REF_COUNT(ctor) <= 1)
        return 0;
    if (js_frame_instance_leaf_try(ctx, sp[-2], sp[-1], &result))
        return 0;
    --JS_REF_COUNT(value);
    --JS_REF_COUNT(ctor);
    sp[-2] = JS_MKVAL(JS_TAG_BOOL, result);
    return 1;
}
"""
        + "\n#endif\n"
    )
