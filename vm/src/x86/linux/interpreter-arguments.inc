/* Actual-type bindings for the shared GNU argument workers. MIT. */
#include <stdatomic.h>
#define FRAME_INLINE inline __attribute__((always_inline))
#define FRAME_CODE __attribute__((section(".text.qjs_linux_arguments"), noipa))
__attribute__((
    visibility("hidden"),
    section(".data.qjs_linux_arguments"))) _Atomic unsigned char JS_LinuxArgumentsLengthControl;

static FRAME_CODE void JS_LinuxArgumentsInitialize(JSContext *ctx)
{
    JSRuntime *rt = ctx->rt;
    if (!FRAME_STATE(rt))
        FRAME_STATE(rt) =
            !qjs_internal_interp_frame_disabled() && !getenv("QJS_DISABLE_MIN_CALL_FRAME") ? 1 : 2;
    if (!FRAME_INTERNAL_STATE(rt))
        FRAME_INTERNAL_STATE(rt) = qjs_internal_interp_internal_disabled() ? 2 : 1;
    js_frame_linux_js_calls_init();
}

__attribute__((visibility("hidden"))) bool JS_LinuxArgumentsCandidate(JSContext *, JSValueConst);
__attribute__((visibility("hidden"))) JSValue JS_FrameArgumentsRootBridge(JSContext *, JSValueConst,
                                                                          JSValueConst,
                                                                          JSValueConst, int,
                                                                          JSValueConst *, int);
__attribute__((visibility("hidden"))) int JS_FrameArgumentsTry(JSFrameRegisterState *);
__attribute__((visibility("hidden"))) int JS_FrameArgumentsStep(JSFrameRegisterState *);
__attribute__((visibility("hidden"))) int JS_FrameArgumentsForwardTry(JSFrameRegisterState *);
__attribute__((visibility("hidden"))) int JS_FrameArgumentsConstructCall(JSFrameRegisterState *);
