void JS_FrameLooseEqConfigure(void)
{
    if (atomic_load_explicit(&JS_FrameLooseEqMode, memory_order_acquire))
        return;
    /* CRT environment only; no engine state, GC, callbacks or reentry. */
    unsigned mode = 16u;
    if (!getenv("QJS_DISABLE_FRAME_LOOSE_EQ")) {
        if (!getenv("QJS_DISABLE_FRAME_LOOSE_EQ_STRINGS"))
            mode |= 1u;
        if (!getenv("QJS_DISABLE_FRAME_LOOSE_EQ_NULL")) {
            mode |= 2u;
            if (!getenv("QJS_DISABLE_FRAME_LOOSE_EQ_OBJECT_NULL"))
                mode |= 4u;
        }
    }
    if (getenv("QJS_OBSERVE_FRAME_LOOSE_EQ"))
        mode |= 32u;
    unsigned expected = 0;
    atomic_compare_exchange_strong_explicit(&JS_FrameLooseEqMode, &expected, mode,
                                            memory_order_release, memory_order_relaxed);
}
