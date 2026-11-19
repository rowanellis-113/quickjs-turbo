/* Generated public API compatibility for this prepared upstream. */
#include "quickjs.h"
#if QJS_VERSION_MAJOR == 0 && QJS_VERSION_MINOR == 15
#define QJS_FRAME_INTERRUPT_CONTEXT 0
#elif QJS_VERSION_MAJOR == 0 && QJS_VERSION_MINOR == 17
#define QJS_FRAME_INTERRUPT_CONTEXT 1
#else
#error Review the selected upstream interrupt callback ABI
#endif
#if QJS_FRAME_INTERRUPT_CONTEXT
typedef JSContext FrameInterruptSource;
static inline JSRuntime *frame_interrupt_runtime(FrameInterruptSource *s)
{
    return JS_GetRuntime(s);
}
#else
typedef JSRuntime FrameInterruptSource;
static inline JSRuntime *frame_interrupt_runtime(FrameInterruptSource *s)
{
    return s;
}
#endif
