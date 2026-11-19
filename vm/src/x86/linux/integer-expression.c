/* MIT. Cold Linux controls remain outside the inherited interpreter TU. */
#include <stdatomic.h>
#include <stdlib.h>

__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxIntExpressionControl;
_Static_assert(sizeof(JS_LinuxIntExpressionControl) == 1, "native scalar mode byte");

__attribute__((visibility("hidden"), section(".text.qjs_linux_scalar_config"), noipa)) void
JS_LinuxIntExpressionInit(void)
{
    if (atomic_load_explicit(&JS_LinuxIntExpressionControl, memory_order_relaxed))
        return;
    unsigned char expected = 0;
    unsigned char mode = getenv("QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF") ? 2 : 1;
    atomic_compare_exchange_strong_explicit(&JS_LinuxIntExpressionControl, &expected, mode,
                                            memory_order_relaxed, memory_order_relaxed);
}
