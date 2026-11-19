/* Shared fast path for OP_for_of_next when iterating native C iterator_next objects. */
extern int JS_FrameVarargsSlow(JSFrameRegisterState *state);

static inline int js_fast_cfunc_for_of_next_impl(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSFrameSegment *segment = state->segment;
    JSContext *ctx = frame->bytecode->realm;
    JSRuntime *rt = ctx->rt;
    size_t used = state->used_bytes;
    uint8_t *pc = state->pc;
    JSValue *sp = state->sp;
    int offset = -3 - (int)pc[1];
    JSFrameSharedAnchor anchor, **slot = NULL;
    unsigned char active = 0;
    int shared_pushed = 0;

    js_frame_begin_c(state);
    js_frame_finish_c(state);
    if (js_frame_shared_enabled(rt) && state->rt == rt && state->frame == frame &&
        state->segment == segment && state->used_bytes == used &&
        rt->current_stack_frame == &frame->sf) {
        unsigned char control =
            atomic_load_explicit(&js_frame_slow_host_control, memory_order_relaxed);
        if (unlikely(!control)) {
            unsigned char expected = 0;
            control = getenv("QJS_DISABLE_SLOW_HOST_SHARE") ? 2 : 1;
            if (!atomic_compare_exchange_strong_explicit(&js_frame_slow_host_control, &expected,
                                                         control, memory_order_relaxed,
                                                         memory_order_relaxed))
                control = expected;
        }
        if (control == 1) {
            state->pc = pc;
            state->sp = sp;
            js_frame_finish_c(state);
            slot = js_frame_shared_slot();
            anchor.prev = *slot;
            anchor.state = state;
            anchor.kind = 0;
            active = FRAME_SHARED_ACTIVE(rt);
            FRAME_SHARED_BITS(rt) |= 4;
            *slot = &anchor;
            shared_pushed = 1;
        }
    }

    js_frame_begin_c(state);
    pc += 2;
    frame->sf.cur_pc = pc;
    frame->saved_sp = sp;
    int rc = js_for_of_next(ctx, sp, offset);
    if (shared_pushed) {
        *slot = anchor.prev;
        FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | active;
    }
    if (unlikely(rc < 0)) {
        state->pc = pc;
        state->sp = sp;
        frame->saved_sp = sp;
        frame->sf.cur_pc = pc;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameVarargsSlow(state);
    }
    sp += 2;
    if (unlikely(state->frame != frame || state->segment != segment)) {
        state->pc = pc;
        state->sp = sp;
        frame->saved_sp = sp;
        frame->sf.cur_pc = pc;
        if (state->frame && !FRAME_CHECKPOINT(state->frame))
            state->frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 0;
    }
    if (pc[0] == OP_if_false8 && JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_BOOL &&
        ctx->interrupt_counter > 1) {
        int done = JS_VALUE_GET_BOOL(sp[-1]);
        sp -= 1;
        ctx->interrupt_counter--;
        if (!done)
            pc = pc + 1 + (int8_t)pc[1];
        else
            pc += 2;
    }
    state->pc = pc;
    state->sp = sp;
    frame->saved_sp = sp;
    frame->sf.cur_pc = pc;
    if (!FRAME_CHECKPOINT(frame))
        frame->sf.cur_sp = NULL;
    js_frame_finish_c(state);
    return 2;
}

#ifdef QJS_EMIT_FAST_FOR_OF_NEXT_SYMBOL
__attribute__((visibility("hidden"), section(".text.qjs_frame"),
               noipa)) int JS_FastCfuncForOfNext(JSFrameRegisterState *state)
{
    return js_fast_cfunc_for_of_next_impl(state);
}
#endif
