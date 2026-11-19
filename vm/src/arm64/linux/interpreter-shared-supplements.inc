/* Real AAPCS64 calls over the common compiler-TLS activation owner. MIT. */
#ifdef QJS_AARCH64_LITERALS
int JS_LinuxLiteralEnter(JSFrameRegisterState *);
#endif
static SHARED_CODE int JS_FrameAArch64Run(JSFrameRegisterState *state)
{
    JSFrameSharedAnchor **slot = js_frame_shared_slot(), barrier;
    int result;
    barrier.prev = *slot;
    barrier.state = state;
    barrier.kind = 3;
    *slot = &barrier;
#ifdef QJS_AARCH64_LITERALS
    result = JS_LinuxLiteralEnter(state);
#else
    result = JS_FrameInterp(state);
#endif
    *slot = barrier.prev;
    return result;
}

SHARED_CODE JSValue JS_FrameCallEntryDispatch(JSContext *ctx, JSValueConst function,
                                              JSValueConst receiver, JSValueConst new_target,
                                              int argc, JSValueConst *argv, int flags)
{
    return JS_FrameCallEntryShared(ctx, function, receiver, new_target, argc, argv, flags);
}

/* Read-only observation of the actual TLS owner,not reconstructed SF shapes.
 * Return kind+1 (host=1,blocked VM=4),or0 for another runtime/no anchor. */
SHARED_CODE unsigned JS_FrameAArch64ScopeProbe(JSRuntime *rt, uintptr_t *words)
{
    JSFrameSharedAnchor *top = *js_frame_shared_slot();
    if (!top || top->state->rt != rt)
        return 0;
    if (words) {
        JSFrameRegisterState *state = top->state;
        words[0] = top->kind;
        words[1] = state->used_bytes;
        words[2] = state->committed_bytes;
        words[3] = (uintptr_t)state->frame;
        words[4] = (uintptr_t)state->segment;
        words[5] = state->segment ? state->segment->used : 0;
        words[6] = state->segment ? state->segment->capacity : 0;
        words[7] = rt->stack_top;
        words[8] = rt->stack_limit;
    }
    return top->kind + 1;
}
