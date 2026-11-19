#if defined(QJS_LINUX_NATIVE_ENTRIES)
#include "src/x86/linux/interpreter-entry.inc"
#else
SHARED_CODE JSValue JS_FrameCallEntryDispatch(JSContext *ctx, JSValueConst func,
                                              JSValueConst this_value, JSValueConst new_target,
                                              int argc, JSValueConst *argv, int flags)
{
    return JS_FrameCallEntryShared(ctx, func, this_value, new_target, argc, argv, flags);
}
#endif

/* Typed read-only observation; geometry alone does not prove an ASM route. */
SHARED_CODE int JS_LinuxJSFrameProbe(JSRuntime *rt, uintptr_t *words)
{
    JSFrameSharedAnchor *top = *js_frame_shared_slot();
    if (!top || top->kind || top->state->rt != rt || !top->state->frame)
        return 0;
    JSFrameRegisterState *state = top->state;
    JSFrame *frame = state->frame;
    if (JS_VALUE_GET_TAG(frame->sf.cur_func) != JS_TAG_OBJECT)
        return 0;
    if (words) {
        words[0] = (uintptr_t)frame->sf.arg_buf;
        words[1] = (uintptr_t)frame + FRAME_HEADER_BYTES;
        words[2] = frame->owned_args;
        words[3] = frame->sf.arg_count;
        words[4] = frame->sf.var_ref_count;
        words[5] = FRAME_KIND(frame->bytecode);
        words[6] = state->used_bytes;
        words[7] = state->committed_bytes;
        words[8] = (uintptr_t)JS_VALUE_GET_OBJ(frame->sf.cur_func);
        words[9] = FRAME_ROOT(frame);
    }
    return 1;
}
