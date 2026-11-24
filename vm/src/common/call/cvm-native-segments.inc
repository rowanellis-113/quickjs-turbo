/* Private persistent-frame execution view. No frame/slot/ABI ownership change.
 * Native segments make no calls and stop before guards requiring the original
 * C semantics. That original opcode is then executed once by the retained loop.
 * Copyright (c) 2026. MIT license, as in quickjs.c.
 */
#include "src/common/internal/interpreter-env.h"
#ifdef _MSC_VER
#pragma section(".qjcvmm", read, write)
#endif

typedef struct JSCVMSegmentState {
    uint8_t *pc;
    JSValue *sp;
    JSValue *locals;
    JSValue *args;
    JSVarRef **refs;
    JSContext *ctx;
} JSCVMSegmentState;

_Static_assert(sizeof(JSCVMSegmentState) == 48 && offsetof(JSCVMSegmentState, pc) == 0 &&
                   offsetof(JSCVMSegmentState, sp) == 8 &&
                   offsetof(JSCVMSegmentState, locals) == 16 &&
                   offsetof(JSCVMSegmentState, args) == 24 &&
                   offsetof(JSCVMSegmentState, refs) == 32 &&
                   offsetof(JSCVMSegmentState, ctx) == 40,
               "native coroutine segment boundary record");
_Static_assert(sizeof(JSValue) == 16 && offsetof(JSValue, tag) == 8 && JS_TAG_FIRST == -9 &&
                   JS_TAG_INT == 0 && JS_TAG_BOOL == 1 && JS_TAG_NULL == 2 &&
                   JS_TAG_UNDEFINED == 3 && JS_TAG_UNINITIALIZED == 4 &&
                   offsetof(JSMallocBlockHeader, user_data) -
                           offsetof(JSMallocBlockHeader, ref_count) ==
                       4 &&
                   sizeof(int) == 4 &&
                   (offsetof(JSContext, interrupt_counter) == 548 ||
                    offsetof(JSContext, interrupt_counter) == 556) &&
                   offsetof(JSVarRef, pvalue) == 24,
               "native coroutine reads the pinned value/RC/context/capture contract");
#ifdef QJS_CVM_NATIVE_OPS
extern void JS_CVMRunSegment(JSCVMSegmentState *state);
#endif
static JSValue JS_CVMResumeInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                    JSValueConst *, int);

/* Configuration is process-start policy, like the existing core-spread path.
 * Off and clone-only are independent ablations of this real execution path.
 */
static unsigned char js_cvm_segment_mode(void)
{
#ifdef CONFIG_ATOMICS
#ifdef _MSC_VER
    __declspec(allocate(".qjcvmm")) static _Atomic(unsigned char) cached;
#else
    static _Atomic(unsigned char) cached;
#endif
    unsigned char mode = atomic_load_explicit(&cached, memory_order_relaxed);
    if (mode)
        return mode;
#else
    unsigned char mode;
#endif
#ifdef QJS_CVM_NATIVE_OPS
    mode = 1;
#else
    mode = 3;
#endif
    if (getenv("QJS_DISABLE_CVM_NATIVE_SEGMENTS") || qjs_internal_interp_frame_disabled() ||
        qjs_internal_interp_internal_disabled() || qjs_internal_interp_register_disabled())
        mode = 2;
    else if (getenv("QJS_DISABLE_CVM_NATIVE_SEGMENT_OPS"))
        mode = 3;
#ifdef CONFIG_ATOMICS
    atomic_store_explicit(&cached, mode, memory_order_relaxed);
#endif
    return mode;
}

JSValue JS_CVMResumeEntry(JSContext *ctx, JSValueConst func, JSValueConst this_val,
                          JSValueConst new_target, int argc, JSValueConst *argv, int flags)
{
    unsigned char mode = js_cvm_segment_mode();
#ifdef ENABLE_DUMPS
    if (check_dump_flag(ctx->rt, JS_DUMP_BYTECODE_STEP))
        mode = 2;
#endif
    if (mode != 2)
        return JS_CVMResumeInternal(ctx, func, this_val, new_target, argc, argv, flags);
    return JS_CallInternal(ctx, func, this_val, new_target, argc, argv, flags);
}

/* Switch-dispatch backends may use native segments. The direct-threaded
 * backend retains its complete inherited dispatch loop without this boundary.
 */
#ifdef QJS_CVM_NATIVE_OPS
#include "src/common/call/cvm-native-segment-opcodes.inc"
#define CVM_SEGMENT_TRY()                                                                          \
    do {                                                                                           \
        if (use_native && js_cvm_segment_eligible[*pc]) {                                          \
            native_state.pc = pc;                                                                  \
            native_state.sp = sp;                                                                  \
            JS_CVMRunSegment(&native_state);                                                       \
            pc = native_state.pc;                                                                  \
            sp = native_state.sp;                                                                  \
        }                                                                                          \
    } while (0);

#else
#define CVM_SEGMENT_TRY()
#endif
