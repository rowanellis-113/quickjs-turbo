/* Existing cold configuration runs before VM execution. Explicit address
 * construction avoids late GNU PE auto-import refptr fixups. */
extern unsigned char JS_FrameReferenceMode[], JS_FrameLargeGlobalMode[];
static FRAME_CODE void frame_reference_configure(void)
{
    _Atomic(unsigned) *control = (_Atomic(unsigned) *)OWN_PRIVATE_ADDRESS(JS_FrameReferenceMode);
    unsigned expected = 0;
    if (!atomic_load_explicit(control, memory_order_relaxed)) {
        unsigned desired = getenv("QJS_DISABLE_FRAME_REFERENCE_EQUALITY") ? 2 : 1;
        atomic_compare_exchange_strong_explicit(control, &expected, desired, memory_order_relaxed,
                                                memory_order_relaxed);
    }
    control = (_Atomic(unsigned) *)OWN_PRIVATE_ADDRESS(JS_FrameLargeGlobalMode);
    expected = 0;
    if (!atomic_load_explicit(control, memory_order_relaxed)) {
        unsigned desired = getenv("QJS_DISABLE_FRAME_LARGE_GLOBAL_BYPASS") ? 2 : 1;
        atomic_compare_exchange_strong_explicit(control, &expected, desired, memory_order_relaxed,
                                                memory_order_relaxed);
    }
}
