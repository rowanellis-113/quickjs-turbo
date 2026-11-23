/* Cold, source-owned policy/proof for native JS frame construction. MIT. */
#include <stdatomic.h>
#include "src/x86/linux/interpreter-vm-leaf.inc"
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxJSOwnedControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxJSCapturedControl;
_Static_assert(sizeof(JSFrame) == 128 && offsetof(JSFrame, bytecode) == 80 &&
                   offsetof(JSFrame, this_value) == 88 && offsetof(JSFrame, saved_sp) == 104 &&
                   offsetof(JSFrame, segment) == 112 && offsetof(JSFrame, frame_bytes) == 120 &&
                   offsetof(JSFrame, owned_args) == 124 && offsetof(JSFrame, pending) == 126 &&
                   offsetof(JSStackFrame, arg_buf) == 24 && offsetof(JSStackFrame, var_buf) == 32 &&
                   offsetof(JSStackFrame, var_refs) == 40 && offsetof(JSStackFrame, cur_pc) == 48 &&
                   offsetof(JSStackFrame, var_ref_count) == 56 &&
                   offsetof(JSStackFrame, arg_count) == 58 &&
                   offsetof(JSStackFrame, is_strict_mode) == 60 &&
                   offsetof(JSStackFrame, cur_sp) == 64 &&
                   (offsetof(JSMallocBlockHeader, user_data) -
                        offsetof(JSMallocBlockHeader, ref_count) ==
                    -QJS_ABI_REF_COUNT_OFFSET),
               "Actual Linux owned-argument/closure frame and reference contract");

static FRAME_INLINE void js_frame_linux_js_calls_init(void)
{
    js_frame_linux_vm_leaf_init();
    unsigned char expected = 0;
    if (!atomic_load_explicit(&JS_LinuxJSOwnedControl, memory_order_relaxed)) {
        unsigned char mode = getenv("QJS_DISABLE_FRAME_JS_OWNED_MISSING") ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_LinuxJSOwnedControl, &expected, mode,
                                                memory_order_relaxed, memory_order_relaxed);
    }
    if (!atomic_load_explicit(&JS_LinuxJSCapturedControl, memory_order_relaxed)) {
        unsigned char mode = getenv("QJS_DISABLE_FRAME_JS_CAPTURED") ? 2 : 1;
        expected = 0;
        atomic_compare_exchange_strong_explicit(&JS_LinuxJSCapturedControl, &expected, mode,
                                                memory_order_relaxed, memory_order_relaxed);
    }
}

/* Exact shared64-node/64KiB-code/4096-pool proof. No recursion or allocation. */
#include "quickjs-linux-captured-proof.h"

#include "src/common/call/interpreter-captured-readonly.inc"
