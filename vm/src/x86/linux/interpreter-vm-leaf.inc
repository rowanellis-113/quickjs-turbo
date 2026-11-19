/* Process startup policy for the shared immutable bytecode leaf kernels. */
#include <stdatomic.h>
__attribute__((visibility("hidden"),
               section(".data.qjs_linux_vm_leaf"))) _Atomic unsigned char JS_FrameLeafControl = 0;
#if defined(QJS_PROPERTY_IC)
__attribute__((visibility("hidden"),
               section(".data.qjs_linux_vm_leaf"))) _Atomic unsigned char JS_FrameCompoundControl =
    0;
__attribute__((
    visibility("hidden"),
    section(".data.qjs_linux_vm_leaf"))) _Atomic unsigned char JS_FrameCharacterSetControl = 0;
#endif

static FRAME_INLINE void js_frame_linux_vm_leaf_init(void)
{
    unsigned char expected = 0;
    if (!atomic_load_explicit(&JS_FrameLeafControl, memory_order_relaxed)) {
        unsigned char desired = getenv("QJS_DISABLE_FRAME_LEAF_ENTRY") ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_FrameLeafControl, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
    }
#if defined(QJS_PROPERTY_IC)
    if (!atomic_load_explicit(&JS_FrameCompoundControl, memory_order_relaxed)) {
        unsigned char desired =
            getenv("QJS_DISABLE_FRAME_COMPOUND_LEAF") || getenv("QJS_DISABLE_LOCALE_COMPARE_LATIN1")
                ? 2
                : 1;
        expected = 0;
        atomic_compare_exchange_strong_explicit(&JS_FrameCompoundControl, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
    }
    if (!atomic_load_explicit(&JS_FrameCharacterSetControl, memory_order_relaxed)) {
        unsigned char desired = getenv("QJS_DISABLE_FRAME_CHARACTER_SET_LEAF") ? 2 : 1;
        expected = 0;
        atomic_compare_exchange_strong_explicit(&JS_FrameCharacterSetControl, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
    }
#endif
}
