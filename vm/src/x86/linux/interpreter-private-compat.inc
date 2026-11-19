/* Adapt owned executor names to this measured Linux core, without changing
 * upstream types. The extra word is the owned frame's explicit tail padding. */
#define FRAME_RT_SHARED_BYTE (offsetof(JSRuntime, current_stack_frame) - 5)
#define QJS_FRAME_SHARED_TLS_HEADER "src/x86/linux/interpreter-shared-tls.inc"
#define QJS_FRAME_SHARED_SUPPLEMENTS_HEADER "src/x86/linux/interpreter-shared-supplements.inc"
#define QJS_FRAME_SLOW_HOST_CODE __attribute__((section(".text.qjs_slow_host"), noipa))
#include "src/common/linux/interpreter-linux-compat.inc"
