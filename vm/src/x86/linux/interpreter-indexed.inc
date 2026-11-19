/* Actual Linux types; private VM registers meet a checked SysV C bridge. */
#define FRAME_CODE __attribute__((section(".text.qjs_frame"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#include "src/common/call/interpreter-retained-context.inc"
FRAME_CODE int JS_LinuxIndexedBaseSlow(JSFrameRegisterState *state);
QJS_FRAME_SLOW_HOST_CODE int JS_LinuxIndexedSelect(JSFrameRegisterState *state);
FRAME_CODE int JS_FrameSlowDirectTryInstanceOfLeaf(JSContext *ctx, JSValue *sp);
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameSlowDirectTryInstanceOfLeaf),
                                            int (*)(JSContext *, JSValue *)),
               "actual SysV pure instanceof signature");
static FRAME_INLINE void js_linux_indexed_publish(JSFrameRegisterState *state, JSValue *sp,
                                                  uint8_t *pc)
{
    state->sp = sp;
    state->frame->saved_sp = sp;
    state->frame->sf.cur_sp = sp;
    state->frame->sf.cur_pc = pc;
}
