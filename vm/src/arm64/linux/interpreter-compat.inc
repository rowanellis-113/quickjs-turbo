/* Linux LP64 adaptation for the shared owned-frame C semantic executor.
 * No compiler clone ABI, Windows TLS gate, or foreign-arch worker is admitted. */
#include "src/common/linux/interpreter-linux-compat.inc"
#define FRAME_RT_SHARED_BYTE (offsetof(JSRuntime, current_stack_frame) - 5)
#define QJS_FRAME_SHARED_TLS_HEADER "src/common/linux/interpreter-linux-shared-tls.inc"
#define QJS_FRAME_SHARED_SUPPLEMENTS_HEADER "src/arm64/linux/interpreter-shared-supplements.inc"
#define QJS_FRAME_SLOW_HOST_CODE __attribute__((section(".text.qjs_slow_host"), noipa))
_Static_assert(sizeof(long) == 8 && _Alignof(JSValue) == 8 && _Alignof(JSStackFrame) == 8,
               "AArch64 Linux LP64 owned-frame contract");
