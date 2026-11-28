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
#if defined(__GNUC__) && !defined(_WIN32)
#define QJS_CVM_HIDDEN __attribute__((visibility("hidden")))
#else
#define QJS_CVM_HIDDEN
#endif
QJS_CVM_HIDDEN extern void JS_CVMRunFastSegment(JSCVMFastState *state);
QJS_CVM_HIDDEN extern const uint8_t JS_CVMFastEligible[256];
#undef QJS_CVM_HIDDEN
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
#if defined(_MSC_VER)
#define QJS_CVM_COLD_CODE __declspec(code_seg(".qjscold")) __declspec(noinline)
#elif defined(__APPLE__)
#define QJS_CVM_COLD_CODE __attribute__((section("__TEXT,__qjs_text"), noinline))
#elif defined(__GNUC__)
#define QJS_CVM_COLD_CODE __attribute__((section(".text.qjs_cvm_cold"), noinline))
#else
#define QJS_CVM_COLD_CODE
#endif
#if !DIRECT_DISPATCH || defined(QJS_CVM_FAST_NATIVE)
static QJS_CVM_COLD_CODE JSValue JS_CVMResumeInternal(JSContext *, JSAsyncFunctionState *,
                                                      uint8_t *);
#endif

/* Configuration is process-start policy, like the existing core-spread path.
 * Off and clone-only are independent ablations of this real execution path.
 */
#ifdef CONFIG_ATOMICS
#ifdef _MSC_VER
__declspec(allocate(".qjcvmm")) static _Atomic(unsigned char) js_cvm_segment_mode_cache;
#else
static _Atomic(unsigned char) js_cvm_segment_mode_cache;
#endif
#endif

static QJS_CVM_COLD_CODE unsigned char js_cvm_segment_mode_init(void)
{
    unsigned char mode;
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
    atomic_store_explicit(&js_cvm_segment_mode_cache, mode, memory_order_relaxed);
#endif
    return mode;
}

static inline unsigned char js_cvm_segment_mode(void)
{
#ifdef CONFIG_ATOMICS
    unsigned char mode = atomic_load_explicit(&js_cvm_segment_mode_cache, memory_order_relaxed);
    if (likely(mode))
        return mode;
#endif
    return js_cvm_segment_mode_init();
}

#if defined(QJS_CVM_FAST_NATIVE)
static QJS_CVM_COLD_CODE uint8_t *
js_cvm_reenter_segment(JSAsyncFunctionState *s, JSFunctionBytecode *b, JSRuntime *rt, uint8_t *pc)
{
    JSStackFrame *sf = &s->frame;
    JSObject *p = JS_VALUE_GET_OBJ(sf->cur_func);
    JSCVMFastState st;
    st.pc = pc;
    st.sp = sf->cur_sp;
    st.locals = sf->var_buf;
    st.args = sf->arg_buf;
    st.refs = p->u.func.var_refs;
    st.ctx = b->realm;
    st.bc = b;
    st.rt = rt;
    JS_CVMRunFastSegment(&st);
    sf->cur_sp = st.sp;
    return st.pc;
}

static JSValue JS_CVMResumeEntry(JSContext *caller_ctx, JSValueConst func, JSValueConst this_val,
                                 JSValueConst new_target, int argc, JSValueConst *argv, int flags)
{
    unsigned char mode = js_cvm_segment_mode();
#ifdef ENABLE_DUMPS
    if (check_dump_flag(caller_ctx->rt, JS_DUMP_BYTECODE_STEP))
        mode = 2;
#endif
    if (unlikely(mode == 2)) {
#ifdef QJS_CVM_USE_LEGACY_CALL_INTERNAL
        return JS_LegacyCallInternal(caller_ctx, func, this_val, new_target, argc, argv, flags);
#else
        return JS_CallInternal(caller_ctx, func, this_val, new_target, argc, argv, flags);
#endif
    }
    uint8_t *initial_bail_pc = NULL;
    JSAsyncFunctionState *s = JS_VALUE_GET_PTR(func);
    if (likely(mode == 1 && !s->throw_flag && caller_ctx->interrupt_counter > 1)) {
        JSStackFrame *sf = &s->frame;
        uint8_t *cur_pc = sf->cur_pc;
        if (*cur_pc == OP_iterator_get_value_done) {
            JSValue obj = sf->cur_sp[-1];
            if (likely(JS_VALUE_GET_TAG(obj) == JS_TAG_OBJECT)) {
                JSObject *op_obj = JS_VALUE_GET_OBJ(obj);
                JSShape *sh = op_obj->shape;
                if (likely(!op_obj->is_exotic && sh->prop_count == 2)) {
                    JSShapeProperty *prs = get_shape_prop(sh);
                    if (likely(prs[0].atom == JS_ATOM_value && !(prs[0].flags & JS_PROP_TMASK) &&
                               prs[1].atom == JS_ATOM_done && !(prs[1].flags & JS_PROP_TMASK) &&
                               JS_VALUE_GET_TAG(op_obj->prop[1].u.value) == JS_TAG_BOOL)) {
                        int done = JS_VALUE_GET_BOOL(op_obj->prop[1].u.value);
                        JSValue val = js_dup(op_obj->prop[0].u.value);
                        JSValue *sp = sf->cur_sp;
                        cur_pc += 1;
                        sf->cur_pc = cur_pc;
                        sp[-1] = val;
                        sp[0] = js_bool(done);
                        sf->cur_sp = sp + 1;
                        JS_FreeValue(caller_ctx, obj);
                        if (done) {
                            JSValue iter = sp[-4];
                            sp[-4] = JS_UNDEFINED;
                            JS_FreeValue(caller_ctx, iter);
                        }
                    }
                }
            }
        }
        if (JS_CVMFastEligible[*cur_pc] && likely(caller_ctx->interrupt_counter > 1)) {
            JSObject *p = JS_VALUE_GET_OBJ(sf->cur_func);
            JSFunctionBytecode *b = p->u.func.function_bytecode;
            JSCVMFastState st;
            st.pc = cur_pc;
            st.sp = sf->cur_sp;
            st.locals = sf->var_buf;
            st.args = sf->arg_buf;
            st.refs = p->u.func.var_refs;
            st.ctx = b->realm;
            st.bc = b;
            st.rt = caller_ctx->rt;
            JS_CVMRunFastSegment(&st);
            if (*st.pc == OP_yield && likely(caller_ctx->interrupt_counter > 1)) {
                --caller_ctx->interrupt_counter;
                sf->cur_pc = st.pc + 1;
                sf->cur_sp = st.sp;
                return JS_MKVAL(JS_TAG_INT, FUNC_RET_YIELD);
            }
            if (*st.pc == OP_await && likely(caller_ctx->interrupt_counter > 1)) {
                --caller_ctx->interrupt_counter;
                sf->cur_pc = st.pc + 1;
                sf->cur_sp = st.sp;
                return JS_MKVAL(JS_TAG_INT, FUNC_RET_AWAIT);
            }
            sf->cur_pc = st.pc;
            sf->cur_sp = st.sp;
            initial_bail_pc = st.pc;
        } else if (*cur_pc == OP_yield) {
            --caller_ctx->interrupt_counter;
            sf->cur_pc = cur_pc + 1;
            return JS_MKVAL(JS_TAG_INT, FUNC_RET_YIELD);
        } else if (*cur_pc == OP_await) {
            --caller_ctx->interrupt_counter;
            sf->cur_pc = cur_pc + 1;
            return JS_MKVAL(JS_TAG_INT, FUNC_RET_AWAIT);
        }
    }
    return JS_CVMResumeInternal(caller_ctx, s, initial_bail_pc);
}
#elif !DIRECT_DISPATCH
JSValue JS_CVMResumeEntry(JSContext *ctx, JSValueConst func, JSValueConst this_val,
                          JSValueConst new_target, int argc, JSValueConst *argv, int flags)
{
    unsigned char mode = js_cvm_segment_mode();
#ifdef ENABLE_DUMPS
    if (check_dump_flag(ctx->rt, JS_DUMP_BYTECODE_STEP))
        mode = 2;
#endif
    if (mode != 2)
        return JS_CVMResumeInternal(ctx, JS_VALUE_GET_PTR(func), NULL);
    return JS_CallInternal(ctx, func, this_val, new_target, argc, argv, flags);
}
#endif

/* Switch-dispatch and QJS_CVM_FAST_NATIVE backends re-enter native segments
 * across slow opcodes via a single eligible-opcode check before dispatch.
 */
#if defined(QJS_CVM_FAST_NATIVE) && DIRECT_DISPATCH
#define CVM_SEGMENT_TRY()
#define CVM_SEGMENT_TRY_DIRECT()                                                                   \
    do {                                                                                           \
        uint8_t cvm_s0_, cvm_s1_;                                                                  \
        if (unlikely(use_native && pc + 10 < cvm_bc_end &&                                         \
                     (unsigned)((cvm_s0_ = JS_CVMFastEligible[*pc]) - 1u) < 254u &&                \
                     (unsigned)((cvm_s1_ = JS_CVMFastEligible[pc[cvm_s0_]]) - 1u) < 254u &&        \
                     JS_CVMFastEligible[pc[cvm_s0_ + cvm_s1_]] != 0)) {                            \
            sf->cur_sp = sp;                                                                       \
            pc = js_cvm_reenter_segment(s, b, rt, pc);                                             \
            sp = sf->cur_sp;                                                                       \
            sf->cur_sp = NULL;                                                                     \
        }                                                                                          \
    } while (0);
#elif defined(QJS_CVM_FAST_NATIVE)
#define CVM_SEGMENT_TRY()                                                                          \
    do {                                                                                           \
        if (use_native && JS_CVMFastEligible[*pc]) {                                               \
            if (likely(pc != last_bail_pc)) {                                                      \
                sf->cur_sp = sp;                                                                   \
                pc = js_cvm_reenter_segment(s, b, rt, pc);                                         \
                sp = sf->cur_sp;                                                                   \
                sf->cur_sp = NULL;                                                                 \
                last_bail_pc = pc;                                                                 \
            } else {                                                                               \
                last_bail_pc = NULL;                                                               \
            }                                                                                      \
        } else {                                                                                   \
            last_bail_pc = NULL;                                                                   \
        }                                                                                          \
    } while (0);
#define CVM_SEGMENT_TRY_DIRECT()
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
#define CVM_SEGMENT_TRY_DIRECT()
#else
#define CVM_SEGMENT_TRY()
#define CVM_SEGMENT_TRY_DIRECT()
#endif
