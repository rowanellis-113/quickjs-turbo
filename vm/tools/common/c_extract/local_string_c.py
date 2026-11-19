"""Pure-C string add_loc extractor."""

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
               "native local-rope selector frame and local-buffer ABI");
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
        QJS_CONTROL_SLOT_ADDR(flag, JS_FrameAddLocalDisable);
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
    raise ValueError("local_string_c requires source_owned=True")
