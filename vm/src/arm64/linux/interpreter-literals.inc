/* Same actual private C types and standard AAPCS64 boundaries. MIT. */
#undef FRAME_CODE
#undef FRAME_INLINE
#define FRAME_CODE __attribute__((section(".text.qjs_arm_literals"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#include "src/common/call/interpreter-retained-context.inc"
FRAME_CODE int JS_LinuxLiteralEnter(JSFrameRegisterState *) __attribute__((visibility("hidden")));
extern int JS_LinuxLiteralBaseSlow(JSFrameRegisterState *);
QJS_FRAME_SLOW_HOST_CODE int JS_FrameIteratorLiteralSelect(JSFrameRegisterState *);
FRAME_CODE int JS_LinuxLiteralRunVM(JSFrameRegisterState *state)
{
    return JS_FrameInterp(state);
}
