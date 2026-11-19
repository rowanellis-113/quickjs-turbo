/* Linux literal owners share their actual types with the complete core TU. */
#define FRAME_CODE __attribute__((section(".text.qjs_frame"), noipa))
#define FRAME_INLINE inline __attribute__((always_inline))
#include "src/common/call/interpreter-retained-context.inc"
_Static_assert(sizeof(JSFrameRegisterState) == 168 && sizeof(bool) == 1 &&
                   offsetof(JSFrameRegisterState, frame) == 0 &&
                   offsetof(JSFrameRegisterState, pc) == 16 &&
                   offsetof(JSFrameRegisterState, sp) == 24 &&
                   offsetof(JSFrameRegisterState, cache_next) == 152 &&
                   offsetof(JSFrameRegisterState, exception_pending) == 160 &&
                   offsetof(JSFrameRegisterState, direct_host_calls) == 161 &&
                   offsetof(JSFrameRegisterState, iterator_checkpoint_depth) == 164,
               "Linux release literal ASM uses the compiler-checked state profile");
FRAME_CODE int JS_LinuxLiteralRunVM(JSFrameRegisterState *) __attribute__((visibility("hidden")));
FRAME_CODE int JS_LinuxLiteralEnter(JSFrameRegisterState *) __attribute__((visibility("hidden")));
extern int JS_LinuxLiteralBaseSlow(JSFrameRegisterState *);
extern int JS_LinuxUnifiedSlowSelect(JSFrameRegisterState *)
    __attribute__((visibility("hidden"), noipa));
QJS_FRAME_SLOW_HOST_CODE int JS_FrameIteratorLiteralSelect(JSFrameRegisterState *);
