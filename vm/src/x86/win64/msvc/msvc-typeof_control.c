
#include <stdlib.h>
#include <stdint.h>
#include <stdatomic.h>
#ifndef FRAME_TYPEOF_INITIAL_MODE
#define FRAME_TYPEOF_INITIAL_MODE 0
#endif
#pragma section(".qztpd$typeof", read, write)
__declspec(allocate(".qztpd$typeof")) _Atomic(unsigned) JS_FrameTypeofNativeMode =
    FRAME_TYPEOF_INITIAL_MODE;
_Static_assert(sizeof(JS_FrameTypeofNativeMode) == 4, "native mode word");
__declspec(noinline) __declspec(code_seg(".qztpc$typeof")) void JS_FrameTypeofNativeConfigure(void)
{
    unsigned known = atomic_load_explicit(&JS_FrameTypeofNativeMode, memory_order_acquire);
    if (known)
        return;
    /* This cold leaf touches only CRT environment state; no engine pointer,
       engine allocation, JS callback, quota update or GC/reentry is possible. */
    unsigned mode = getenv("QJS_DISABLE_FRAME_TYPEOF") ? 2u : 1u;
    if (getenv("QJS_OBSERVE_FRAME_TYPEOF"))
        mode |= 4u;
    unsigned expected = 0;
    atomic_compare_exchange_strong_explicit(&JS_FrameTypeofNativeMode, &expected, mode,
                                            memory_order_release, memory_order_relaxed);
}
