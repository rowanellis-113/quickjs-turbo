/* Actual same-TU private types; no foreign register or aggregate ABI. MIT. */
#pragma push_macro("FRAME_CODE")
#pragma push_macro("FRAME_INLINE")
#undef FRAME_CODE
#undef FRAME_INLINE
#define FRAME_CODE __attribute__((noipa, section(".text.qjs_arm_indexed")))
#define FRAME_INLINE inline __attribute__((always_inline))
#include "src/common/call/interpreter-retained-context.inc"
int JS_LinuxIndexedBaseSlow(JSFrameRegisterState *);
int JS_LinuxIndexedSelect(JSFrameRegisterState *);
int JS_FrameSlowDirectTryInstanceOfLeaf(JSContext *, JSValue *);
static FRAME_INLINE void js_linux_indexed_publish(JSFrameRegisterState *state, JSValue *sp,
                                                  uint8_t *pc)
{
    state->sp = sp;
    state->frame->saved_sp = sp;
    state->frame->sf.cur_sp = sp;
    state->frame->sf.cur_pc = pc;
}
