"""Pure-C BigInt add_loc extractor."""

import hashlib
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


def generate(source):
    path = _frame_source_file(source, "quickjs-interpreter-bigint.h")
    text = path.read_text()
    start = text.index("    if (tag1==JS_TAG_SHORT_BIG_INT && tag2==JS_TAG_SHORT_BIG_INT) {")
    end = text.index("\nbigint_done:", start)
    arithmetic = text[start:end]
    assert arithmetic.count("sp[-2] = ") == 3
    arithmetic = arithmetic.replace("sp[-2] = ", "result = ")
    return """/* Retained primitive body SHA256: %s. */
extern int JS_FrameInterpSlow(JSFrameRegisterState *state);
extern const char JS_FrameAddLocalDisable[];
_Static_assert(offsetof(JSRuntime, module_loader_has_attr)==QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
               offsetof(JSRuntime, u)==QJS_ABI_OFF_JSRuntime_u, "add-local mode uses measured padding");
FRAME_NULL_CODE int JS_FrameAddLocalBig(JSFrameRegisterState *state)
{
    JSFrame *frame=state->frame;
    JSStackFrame *sf=&frame->sf;
    JSContext *ctx=frame->bytecode->realm;
    JSRuntime *rt=state->rt;
    unsigned char *mode=(unsigned char *)rt+offsetof(JSRuntime,module_loader_has_attr)+3;
    const char *flag;
    JSValue *sp=state->sp, *pv=&sf->var_buf[state->pc[1]];
    JSValue op1, op2, result;
    uint32_t tag1, tag2;
    uint8_t *pc=state->pc+2;
    if (!*mode) {
        QJS_CONTROL_SLOT_ADDR(flag, JS_FrameAddLocalDisable);
        *mode=getenv(flag)==NULL ? 1 : 2;
    }
    if (*mode!=1) return JS_FrameInterpSlow(state);
    /* The ASM gate has checked both tags before reaching the C boundary. */
    assert(JS_IsBigInt(*pv) && JS_IsBigInt(sp[-1]));
    op1=js_dup(*pv);
    op2=sp[-1];
    tag1=JS_VALUE_GET_TAG(op1);
    tag2=JS_VALUE_GET_TAG(op2);
    js_frame_begin_c(state);
    sf->cur_pc=pc;
    /* The RHS ownership is transferred to the retained arithmetic. */
    state->pc=pc;
    state->sp=sp-1;
%s
bigint_done:
    /* Publish the result before releasing the old local, as set_value does. */
    set_value(ctx,pv,result);
    js_frame_finish_c(state);
    return 2; /* success in this same frame; the native cursor can resume */
exception:
    /* Retained arithmetic consumed the RHS and the duplicate of the local.
     * The original local remains owned and no dead operand is visited. */
    sp[-1]=JS_UNDEFINED;
    state->exception_pending=true;
    js_frame_finish_c(state);
    return JS_FrameInterpSlow(state);
}
""" % (hashlib.sha256(path.read_bytes()).hexdigest(), arithmetic)
