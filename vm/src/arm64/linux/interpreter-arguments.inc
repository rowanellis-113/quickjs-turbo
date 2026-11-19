/* Actual-type AAPCS64 bindings for the complete shared argument owners. MIT. */
#include <stdatomic.h>
#define FRAME_INLINE inline __attribute__((always_inline))
#define FRAME_CODE __attribute__((section(".text.qjs_arm_arguments"), noipa))
__attribute__((
    visibility("hidden"),
    section(".data.qjs_arm_arguments"))) _Atomic unsigned char JS_LinuxArgumentsLengthControl;
static FRAME_CODE void JS_LinuxArgumentsInitialize(JSContext *ctx)
{
    JSRuntime *rt = ctx->rt;
    if (!FRAME_STATE(rt))
        FRAME_STATE(rt) =
            !qjs_internal_interp_frame_disabled() && !getenv("QJS_DISABLE_MIN_CALL_FRAME") ? 1 : 2;
    if (!FRAME_INTERNAL_STATE(rt))
        FRAME_INTERNAL_STATE(rt) = qjs_internal_interp_internal_disabled() ? 2 : 1;
    (void)js_frame_register_enabled(rt);
}
