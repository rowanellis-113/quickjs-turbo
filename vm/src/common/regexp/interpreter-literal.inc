/* The original literal constructor consumes both owning operands. Remove
 * their old stack slots before any allocation/finalizer can observe them;
 * their ownership stays in these C locals until transferred to the helper.
 * The public source, constant pool and serialized bytecode stay unchanged. */
QJS_FRAME_LITERAL_CODE int JS_FrameInterpRegExp(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *sp = state->sp;
    JSValue pattern = sp[-2], bytecode = sp[-1], result;
    uint8_t *pc = state->pc + 1;
    js_frame_begin_c(state);
    sp -= 2;
    sp[0] = sp[1] = JS_UNDEFINED;
    state->pc = pc;
    sf->cur_pc = pc;
    state->sp = frame->saved_sp = sp;
    result = js_regexp_constructor_internal(ctx, JS_UNDEFINED, pattern, bytecode);
    *sp++ = result;
    state->sp = frame->saved_sp = sp;
    js_frame_finish_c(state);
    if (unlikely(JS_IsException(result))) {
        state->exception_pending = true;
        return JS_FrameInterpSlow(state);
    }
    return 0;
}
