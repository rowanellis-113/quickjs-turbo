/* Publish only a coherent, suspended C opcode call. The legacy interpreter,
 * including generator resumptions, keeps its own SF/PC/SP and value ownership.
 * Nested ordinary JS callbacks may borrow the paused owner's nonmoving arena.
 * No generator frame is migrated or treated as an owned native frame. MIT. */
#include <stdatomic.h>
static _Atomic unsigned char js_frame_slow_host_control;

static QJS_FRAME_SLOW_HOST_CODE JSValue
js_frame_slow_host_call(JSFrameRegisterState *state, JSFrame *frame, JSFrameSegment *segment,
                        size_t used, uint8_t *pc, JSValue *sp, JSContext *ctx, JSValueConst callee,
                        JSValueConst receiver, int argc, JSValueConst *argv)
{
    JSRuntime *rt = ctx->rt;
    JSFrameSharedAnchor anchor, **slot;
    JSValue result;
    unsigned char control, active;
    /* The C step can change its local frame/cursor before its final state
     * writeback. Such paths retain the original call, never a stale anchor. */
    if (!js_frame_shared_enabled(rt) || state->rt != rt || state->frame != frame ||
        state->segment != segment || state->used_bytes != used ||
        rt->current_stack_frame != &frame->sf)
        goto original;
    control = atomic_load_explicit(&js_frame_slow_host_control, memory_order_relaxed);
    if (unlikely(!control)) {
        unsigned char expected = 0;
        control = getenv("QJS_DISABLE_SLOW_HOST_SHARE") ? 2 : 1;
        if (!atomic_compare_exchange_strong_explicit(&js_frame_slow_host_control, &expected,
                                                     control, memory_order_relaxed,
                                                     memory_order_relaxed))
            control = expected;
    }
    if (control != 1)
        goto original;
    state->pc = pc;
    state->sp = sp;
    /* begin_c already charged this exact live count. Publish the completed
     * commitment before the child admission checks it. cur_sp retains the
     * original running-frame convention; saved_sp/cur_pc own the call cursor. */
    js_frame_finish_c(state);
    slot = js_frame_shared_slot();
    anchor.prev = *slot;
    anchor.state = state;
    anchor.kind = 0;
    active = FRAME_SHARED_ACTIVE(rt);
    FRAME_SHARED_BITS(rt) |= 4;
    *slot = &anchor;
    result = js_frame_legacy_call(ctx, callee, receiver, argc, argv);
    *slot = anchor.prev;
    FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | active;
    return result;
original:
    return js_frame_legacy_call(ctx, callee, receiver, argc, argv);
}
