/* Shared GNU global algorithms use only measured,existing activation storage. */
#include <stdatomic.h>
#define GLOBAL_CODE                                                                                \
    __attribute__((section(".text.qjs_linux_global_control"), noipa, visibility("hidden")))
#define GLOBAL_DATA __attribute__((section(".data.qjs_linux_global_control"), visibility("hidden")))
#define GLOBAL_RO __attribute__((section(".rodata.qjs_linux_global_control")))
GLOBAL_DATA _Atomic(unsigned char) JS_FrameGlobalBindingControl;
GLOBAL_DATA _Atomic(unsigned char) JS_FrameGlobalUndefinedControl;
static GLOBAL_RO const char global_binding_disable[] = "QJS_DISABLE_FRAME_GLOBAL_BINDING";
static GLOBAL_RO const char global_undefined_disable[] = "QJS_DISABLE_FRAME_GLOBAL_UNDEFINED";
_Static_assert(sizeof(JSValue) == 16 && offsetof(JSValue, tag) == 8, "actual global value ABI");
_Static_assert(sizeof(JSFrame) == 128 && offsetof(JSFrame, bytecode) == 80 &&
                   offsetof(JSStackFrame, cur_pc) == 48,
               "actual physical frame fields");
_Static_assert(sizeof(JSFrameRegisterState) == 168 &&
                   offsetof(JSFrameRegisterState, sites) == 144 &&
                   offsetof(JSFrameRegisterState, cache_next) == 152,
               "actual existing activation cache");
_Static_assert(FRAME_CACHE_SLOTS == 16 && sizeof(JSFrameCallSite) == 32 &&
                   offsetof(JSFrameCallSite, continuation) == 0 &&
                   offsetof(JSFrameCallSite, identity) == 8 &&
                   offsetof(JSFrameCallSite, code_identity) == 16 &&
                   offsetof(JSFrameCallSite, argc) == 24,
               "source-owned shared call/global weak cells");
_Static_assert(offsetof(JSRefCountHeader, ref_count) == 0 && sizeof(_Atomic(unsigned char)) == 1,
               "actual inline duplicate and byte modes");
GLOBAL_CODE int JS_LinuxGlobalBindingInit(JSFrameRegisterState *state)
{
    (void)state;
    if (!atomic_load_explicit(&JS_FrameGlobalBindingControl, memory_order_acquire)) {
        frame_reference_configure();
        unsigned char expected = 0;
        unsigned char undefined_mode = getenv(global_undefined_disable) ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_FrameGlobalUndefinedControl, &expected,
                                                undefined_mode, memory_order_relaxed,
                                                memory_order_relaxed);
        expected = 0;
        unsigned char mode = getenv(global_binding_disable) ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_FrameGlobalBindingControl, &expected, mode,
                                                memory_order_release, memory_order_relaxed);
    }
    return atomic_load_explicit(&JS_FrameGlobalBindingControl, memory_order_acquire);
}
#undef GLOBAL_CODE
#undef GLOBAL_DATA
#undef GLOBAL_RO
