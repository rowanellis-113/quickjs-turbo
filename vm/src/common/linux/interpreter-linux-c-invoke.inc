/* SysV C invocation owns a real C SF and a typed shared host anchor. The
 * register VM caches this thread's compiler-managed TLS slot in its existing
 * activation scratch word; no ELF TLS offsets are guessed by assembly. MIT. */
#include <stdatomic.h>
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxCInvokeControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxNumericControl;
__attribute__((visibility("hidden"))) _Atomic unsigned char JS_LinuxBuiltinControl;
_Static_assert(sizeof(JSFrameRegisterState) == 168 && offsetof(JSFrameRegisterState, frame) == 0 &&
                   offsetof(JSFrameRegisterState, used_bytes) == 32 &&
                   offsetof(JSFrameRegisterState, result) == 40 &&
                   offsetof(JSFrameRegisterState, rt) == 56 &&
                   offsetof(JSFrameRegisterState, committed_bytes) == 64 &&
                   offsetof(JSFrameRegisterState, native_stack_limit) == 72 &&
                   offsetof(JSFrameRegisterState, shared_stack_limit) == 80 &&
                   offsetof(JSFrameRegisterState, exception_pending) == 160,
               "Linux release invocation state contract");

typedef struct JSLinuxCInvokeFrame {
    JSStackFrame sf;
    uintptr_t dispatch, caller_context;
    int argc;
    unsigned char active, reserved;
    uint16_t formal;
} JSLinuxCInvokeFrame;
_Static_assert(sizeof(JSLinuxCInvokeFrame) == 104 && offsetof(JSLinuxCInvokeFrame, dispatch) == 80 &&
                   offsetof(JSLinuxCInvokeFrame, caller_context) == 88 &&
                   offsetof(JSLinuxCInvokeFrame, argc) == 96 &&
                   offsetof(JSLinuxCInvokeFrame, active) == 100 &&
                   offsetof(JSLinuxCInvokeFrame, formal) == 102,
               "Linux native C invocation frame contract");
typedef JSValue (*JSLinuxGenericC)(JSContext *, JSValueConst, int, JSValueConst *);
typedef JSValue (*JSLinuxMagicC)(JSContext *, JSValueConst, int, JSValueConst *, int);
typedef double (*JSLinuxUnaryC)(double);
typedef double (*JSLinuxBinaryC)(double, double);
_Static_assert(__builtin_types_compatible_p(__typeof__(((JSCFunctionType *)0)->generic),
                                            JSLinuxGenericC) &&
                   __builtin_types_compatible_p(__typeof__(((JSCFunctionType *)0)->generic_magic),
                                                JSLinuxMagicC),
               "Actual generic and magic SysV C function types");
_Static_assert(__builtin_types_compatible_p(__typeof__(((JSCFunctionType *)0)->f_f),
                                            JSLinuxUnaryC) &&
                   __builtin_types_compatible_p(__typeof__(((JSCFunctionType *)0)->f_f_f),
                                                JSLinuxBinaryC),
               "Actual primitive numeric SysV C function types");

/* The slower primitive trampoline is an independent component control. Its
 * caller has checked exact prototypes and INT/FLOAT arguments before commit;
 * original coercing/missing-argument cases keep the complete core boundary. */
__attribute__((visibility("hidden"), section(".text.qjs_linux_numeric"), noipa)) JSValue
JS_LinuxNumericTrampoline(JSStackFrame *sf)
{
    JSObject *function = JS_VALUE_GET_OBJ(sf->cur_func);
    JSValueConst *args = sf->arg_buf;
    double a = JS_VALUE_GET_TAG(args[0]) == JS_TAG_INT ? JS_VALUE_GET_INT(args[0])
                                                       : JS_VALUE_GET_FLOAT64(args[0]);
    if (function->u.cfunc.cproto == JS_CFUNC_f_f)
        return js_number(function->u.cfunc.c_function.f_f(a));
    double b = JS_VALUE_GET_TAG(args[1]) == JS_TAG_INT ? JS_VALUE_GET_INT(args[1])
                                                       : JS_VALUE_GET_FLOAT64(args[1]);
    return js_number(function->u.cfunc.c_function.f_f_f(a, b));
}

__attribute__((visibility("hidden"), noipa)) void *JS_LinuxCInvokeInit(JSFrameRegisterState *state)
{
    unsigned char mode = atomic_load_explicit(&JS_LinuxCInvokeControl, memory_order_relaxed);
    if (!mode) {
        unsigned char expected = 0;
        mode = getenv("QJS_DISABLE_C_INVOKE") ? 2 : 1;
        if (!atomic_compare_exchange_strong_explicit(&JS_LinuxCInvokeControl, &expected, mode,
                                                     memory_order_relaxed, memory_order_relaxed))
            mode = expected;
    }
    if (mode != 1 || !js_frame_shared_enabled(state->rt) || (FRAME_SHARED_BITS(state->rt) & 8))
        return NULL;
    if (!atomic_load_explicit(&JS_LinuxNumericControl, memory_order_relaxed)) {
        unsigned char expected = 0;
        unsigned char desired = 128 | (getenv("QJS_DISABLE_NATIVE_NUMERIC_INVOKE") ? 0 : 1) |
                                (getenv("QJS_DISABLE_NUMERIC_TRAMPOLINE") ? 0 : 2);
        atomic_compare_exchange_strong_explicit(&JS_LinuxNumericControl, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
    }
    if (!atomic_load_explicit(&JS_LinuxBuiltinControl, memory_order_relaxed)) {
        unsigned char expected = 0;
        unsigned char desired = getenv("QJS_DISABLE_NATIVE_SLICE") ||
                                        getenv("QJS_DISABLE_NATIVE_CALL_LINK") ||
                                        getenv("QJS_DISABLE_NATIVE_VM_BRIDGE")
                                    ? 2
                                : getenv("QJS_DISABLE_NATIVE_FRAME_ARENA")    ? 3
                                : getenv("QJS_DISABLE_NATIVE_FRAME_REUSE")    ? 4
                                : getenv("QJS_DISABLE_NATIVE_FRAME_LIFETIME") ? 5
                                                                              : 1;
        if (getenv("QJS_DISABLE_NATIVE_NUMBER_FRAME"))
            desired |= 32;
        atomic_compare_exchange_strong_explicit(&JS_LinuxBuiltinControl, &expected, desired,
                                                memory_order_relaxed, memory_order_relaxed);
    }
    return js_frame_shared_slot();
}

#include "src/common/linux/interpreter-linux-builtin.inc"
