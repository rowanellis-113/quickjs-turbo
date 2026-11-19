/* Fast non-extended OrdLazy inline setup/teardown for JS_LinuxLiteralEnter. */
FRAME_CODE int JS_LinuxLiteralEnter(JSFrameRegisterState *state)
{
    unsigned char previous_active = ORD_ACTIVE(state), previous_lazy = ORD_LAZY(state);
    /* Every physical VM entry owns a fresh scope, including native assembly
       roots and coherent C reentry. Caller flags/counter pointers survive. */
    ORD_ACTIVE(state) = 0;
    ORD_LAZY(state) = 0;
    JSFunctionBytecode *b = state->frame->bytecode;
    bool extended = (FRAME_ITERATOR_KIND(b) & 1) != 0 ||
                    (FRAME_KIND(b) == 2 && (((unsigned char *)b)[FRAME_CALL_AUX_OFFSET] & 1));
#ifndef QJS_AARCH64_VM_INSTRUMENT
    int event;
    if (extended) {
        event = JS_FrameOrdinaryLiteralEnter(state);
    } else {
        unsigned mode = atomic_load_explicit(&JS_FrameOrdinaryLiteralMode, memory_order_relaxed);
        if (!mode) {
            js_frame_begin_c(state);
            mode = ord_mode();
            js_frame_finish_c(state);
        }
        if (!(mode & 1) || (mode & 256) || !state->cache_next || !state->sites) {
            event = JS_FrameInterp(state);
        } else {
            OrdLazy lazy;
            lazy.scope = NULL;
            lazy.seen = 0;
            uint8_t *previous = state->cache_next;
            memcpy(lazy.cache_next, previous, 8);
            state->cache_next = lazy.cache_next;
            ORD_LAZY(state) = 1;
            event = JS_FrameInterp(state);
            memcpy(previous, state->cache_next, 8);
            state->cache_next = previous;
            ORD_ACTIVE(state) = 0;
            ORD_LAZY(state) = 0;
            if (lazy.scope) {
                js_frame_begin_c(state);
                ord_destroy(state->rt, lazy.scope, mode);
                js_free_rt(state->rt, lazy.scope);
                js_frame_finish_c(state);
            }
        }
    }
#else
    int event =
        extended ? JS_FrameOrdinaryLiteralEnter(state) : JS_FrameOrdinaryLiteralLazyEnter(state);
#endif
    ORD_ACTIVE(state) = previous_active;
    ORD_LAZY(state) = previous_lazy;
    return event;
}
