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

typedef struct JSCVMFastState {
    uint8_t *pc;
    JSValue *sp;
    JSValue *locals;
    JSValue *args;
    JSVarRef **refs;
    JSContext *ctx;
    JSFunctionBytecode *bc;
    JSRuntime *rt;
} JSCVMFastState;

#ifdef QJS_CVM_FAST_NATIVE
_Static_assert(sizeof(JSCVMFastState) == 64 && offsetof(JSCVMFastState, pc) == 0 &&
                   offsetof(JSCVMFastState, sp) == 8 && offsetof(JSCVMFastState, locals) == 16 &&
                   offsetof(JSCVMFastState, args) == 24 && offsetof(JSCVMFastState, refs) == 32 &&
                   offsetof(JSCVMFastState, ctx) == 40 && offsetof(JSCVMFastState, bc) == 48 &&
                   offsetof(JSCVMFastState, rt) == 56,
               "native coroutine fast segment boundary record");
extern void JS_CVMRunFastSegment(JSCVMFastState *state);
#endif
#ifdef QJS_CVM_NATIVE_OPS
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
extern void JS_CVMRunSegment(JSCVMSegmentState *state);
#endif
#if !DIRECT_DISPATCH
static JSValue JS_CVMResumeInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                    JSValueConst *, int);
#endif

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
#if defined(QJS_CVM_NATIVE_OPS) || defined(QJS_CVM_FAST_NATIVE)
    mode = 1;
#else
    mode = 3;
#endif
    if (getenv("QJS_DISABLE_CVM_NATIVE_SEGMENTS") || getenv("QJS_DISABLE_COROUTINE_FAST_RESUME") ||
        qjs_internal_interp_frame_disabled() || qjs_internal_interp_internal_disabled() ||
        qjs_internal_interp_register_disabled())
        mode = 2;
    else if (getenv("QJS_DISABLE_CVM_NATIVE_SEGMENT_OPS"))
        mode = 3;
#ifdef CONFIG_ATOMICS
    atomic_store_explicit(&cached, mode, memory_order_relaxed);
#endif
    return mode;
}

#if !DIRECT_DISPATCH
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
#elif defined(QJS_CVM_FAST_NATIVE)
static JSValue JS_CVMResumeEntry(JSContext *caller_ctx, JSValueConst func, JSValueConst this_val,
                                 JSValueConst new_target, int argc, JSValueConst *argv, int flags)
{
    JSAsyncFunctionState *s = JS_VALUE_GET_PTR(func);
    if (likely(!s->throw_flag && caller_ctx->interrupt_counter > 1 && js_cvm_segment_mode() == 1
#ifdef ENABLE_DUMPS
               && !check_dump_flag(caller_ctx->rt, JS_DUMP_BYTECODE_STEP)
#endif
                   )) {
        JSStackFrame *sf = &s->frame;
        JSObject *p = JS_VALUE_GET_OBJ(sf->cur_func);
        JSFunctionBytecode *b = p->u.func.function_bytecode;
        JSCVMFastState st;
        st.pc = sf->cur_pc;
        st.sp = sf->cur_sp;
        st.locals = sf->var_buf;
        st.args = sf->arg_buf;
        st.refs = p->u.func.var_refs;
        st.ctx = b->realm;
        st.bc = b;
        st.rt = caller_ctx->rt;
        JS_CVMRunFastSegment(&st);
        uint8_t op = *st.pc;
        if (op == OP_yield) {
            --caller_ctx->interrupt_counter;
            sf->cur_pc = st.pc + 1;
            sf->cur_sp = st.sp;
            return JS_MKVAL(JS_TAG_INT, FUNC_RET_YIELD);
        }
        if (op == OP_await) {
            --caller_ctx->interrupt_counter;
            sf->cur_pc = st.pc + 1;
            sf->cur_sp = st.sp;
            return JS_MKVAL(JS_TAG_INT, FUNC_RET_AWAIT);
        }
        sf->cur_pc = st.pc;
        sf->cur_sp = st.sp;
    }
#ifdef QJS_CVM_USE_LEGACY_CALL_INTERNAL
    return JS_LegacyCallInternal(caller_ctx, func, this_val, new_target, argc, argv, flags);
#else
    return JS_CallInternal(caller_ctx, func, this_val, new_target, argc, argv, flags);
#endif
}
#endif

/* Switch-dispatch backends may use native segments. The direct-threaded
 * backend retains its complete inherited dispatch loop without this boundary.
 */
#if defined(QJS_CVM_FAST_NATIVE) && !DIRECT_DISPATCH
#define CVM_SEGMENT_TRY()                                                                          \
    do {                                                                                           \
        if (use_native) {                                                                          \
            fast_state.pc = pc;                                                                    \
            fast_state.sp = sp;                                                                    \
            JS_CVMRunFastSegment(&fast_state);                                                     \
            pc = fast_state.pc;                                                                    \
            sp = fast_state.sp;                                                                    \
        }                                                                                          \
    } while (0);
#elif defined(QJS_CVM_NATIVE_OPS)
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
