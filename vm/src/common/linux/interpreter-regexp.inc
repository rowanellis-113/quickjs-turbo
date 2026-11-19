/* RegExp semantic workers use the actual complete core TU and public SysV ABI. */
#include <stdatomic.h>
#define QJS_LINUX_REGEXP_CODE __attribute__((section(".text.qjs_linux_regexp"), noipa))
static _Atomic(unsigned char) js_linux_regexp_control
    __attribute__((section(".data.qjs_linux_regexp"))) = 0;
static inline unsigned js_linux_regexp_mode(void)
{
    unsigned char mode = atomic_load_explicit(&js_linux_regexp_control, memory_order_relaxed);
    if (!mode) {
        unsigned char expected = 0;
        unsigned char desired = getenv("QJS_DISABLE_LINUX_REGEXP_WORKERS") ? 2 : 1;
        if (getenv("QJS_DISABLE_LINUX_REGEXP_OWNED_ARGV"))
            desired |= 4;
        atomic_compare_exchange_strong_explicit(&js_linux_regexp_control, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
        mode = atomic_load_explicit(&js_linux_regexp_control, memory_order_relaxed);
    }
    return mode;
}
_Static_assert(sizeof(JSValue) == 16 && sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame,
               "Actual SysV value/core types for the complete RegExp workers");
