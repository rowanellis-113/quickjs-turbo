/* The NULL_PROTO opcode produces one new owning value. The original warm
 * allocator pins its shape before GC/allocator reentry and releases it on
 * either allocation failure. Publish only the preexisting live stack while
 * allocating; commit the result before resuming the register VM. */
static QJS_LINUX_NULL_CODE int js_linux_null_proto_body(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *sp = state->sp, result;
    uint8_t *pc = state->pc;
    if (*pc != OP_special_object || pc[1] != OP_SPECIAL_OBJECT_NULL_PROTO)
        return JS_FrameInterpSlow(state);
    js_frame_begin_c(state);
    state->pc = pc + 2;
    sf->cur_pc = pc + 2;
    state->sp = frame->saved_sp = sf->cur_sp = sp;
    result = JS_LinuxNewNullObject(ctx, JS_NULL, JS_CLASS_OBJECT);
    *sp++ = result;
    state->sp = frame->saved_sp = sp;
    js_frame_finish_c(state);
    if (unlikely(JS_IsException(result))) {
        state->exception_pending = true;
        return JS_FrameInterpSlow(state);
    }
    return 0;
}
