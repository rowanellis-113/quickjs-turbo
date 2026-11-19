/* Process policy for the immutable ELF Clean/Dirty dispatch tables. MIT. */
#include <stdatomic.h>
__attribute__((visibility("hidden"),
               section(".data.qjs_linux_publish"))) _Atomic unsigned char JS_FramePublishControl =
    0;

__attribute__((visibility("hidden"), section(".text.qjs_linux_publish_policy"), noipa)) int
JS_LinuxPublishInit(JSFrameRegisterState *state)
{
    unsigned char control = atomic_load_explicit(&JS_FramePublishControl, memory_order_relaxed);
    (void)state;
    if (!control) {
        unsigned char expected = 0;
        unsigned char desired = getenv("QJS_DISABLE_DEFERRED_FRAME_PUBLISH") ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_FramePublishControl, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
        control = atomic_load_explicit(&JS_FramePublishControl, memory_order_relaxed);
    }
    return control;
}
