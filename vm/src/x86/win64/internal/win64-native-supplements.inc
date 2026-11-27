/* Source-level Windows x86-64 native ASM VM supplements.
 * Provides shared entry dispatch, CRT-portable getenv bridge for ASM islands,
 * the decoupled native Property IC / own-bytecode tail controller,
 * JS_FrameSlowDirectData, and 3-tier constructor specialization/continuation. */
#include <stdatomic.h>
#include "src/common/internal/turbo-config.h"

#if defined(_MSC_VER)
#define WIN64_THREAD_LOCAL __declspec(thread)
#else
#define WIN64_THREAD_LOCAL _Thread_local
#endif

unsigned char JS_FrameSlowDirectData = 0;

SHARED_CODE JSValue JS_FrameCallEntryDispatch(JSContext *ctx, JSValueConst func,
                                              JSValueConst this_value, JSValueConst new_target,
                                              int argc, JSValueConst *argv, int flags)
{
    return JS_FrameCallEntryShared(ctx, func, this_value, new_target, argc, argv, flags);
}

/* CRT-portable getenv bridge (works identically under /MD, /MT, MSVC, clang-cl). */
const char *JS_FrameGetenv(const char *name)
{
    return getenv(name);
}

#if defined(_MSC_VER)
#define WIN64_HOST_FAST_CODE __declspec(code_seg(".qjsvm$zzzf")) no_inline
#else
#define WIN64_HOST_FAST_CODE __attribute__((section(".qjsvm$zzzf"), noipa))
#endif

static SHARED_INLINE bool win64_host_stack_ok(JSFrameRegisterState *state, JSRuntime *rt,
                                              size_t need)
{
    if (likely(!rt->stack_limit))
        return true;
    size_t extra = state->used_bytes > state->committed_bytes
                       ? (state->used_bytes - state->committed_bytes)
                       : 0;
    return !js_check_stack_overflow(rt, extra + need);
}

/* Zero-JSStackFrame fast leaves for Win64 direct C-function dispatch (cproto <= 1):
 * Split immediately by cproto (0 = generic, 1 = generic_magic) so misses fall through
 * with minimal branches while hot builtins skip JSStackFrame push/pop and arg padding. */
WIN64_HOST_FAST_CODE int JS_Win64HostDirectFast(JSFrameRegisterState *state, JSValue *argv,
                                                int argc, bool method)
{
    JSObject *fn = JS_VALUE_GET_OBJ(argv[-1]);
    uint8_t cproto = fn->u.cfunc.cproto;
    void *fp = (void *)fn->u.cfunc.c_function.generic;

    if (cproto == JS_CFUNC_generic) {
        if (method) {
            if (fp == (void *)js_string_charCodeAt && JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_STRING) {
                int t0 = argc >= 1 ? JS_VALUE_GET_TAG(argv[0]) : JS_TAG_UNDEFINED;
                if (likely(t0 == JS_TAG_INT || t0 == JS_TAG_UNDEFINED)) {
                    JSContext *ctx = state->frame->bytecode->realm;
                    JSRuntime *rt = state->rt;
                    if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                               win64_host_stack_ok(state, rt, 256))) {
                        JSString *p = JS_VALUE_GET_STRING(argv[-2]);
                        int idx = t0 == JS_TAG_INT ? JS_VALUE_GET_INT(argv[0]) : 0;
                        ctx->interrupt_counter--;
                        state->result = (idx < 0 || (uint32_t)idx >= p->len)
                                            ? JS_NAN
                                            : js_int32(string_get(p, idx));
                        state->exception_pending = false;
                        return 0;
                    }
                }
            } else if (fp == (void *)js_string_slice &&
                       JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_STRING) {
                int t0 = argc >= 1 ? JS_VALUE_GET_TAG(argv[0]) : JS_TAG_UNDEFINED;
                int t1 = argc >= 2 ? JS_VALUE_GET_TAG(argv[1]) : JS_TAG_UNDEFINED;
                if (likely((t0 == JS_TAG_INT || t0 == JS_TAG_UNDEFINED) &&
                           (t1 == JS_TAG_INT || t1 == JS_TAG_UNDEFINED))) {
                    JSContext *ctx = state->frame->bytecode->realm;
                    JSRuntime *rt = state->rt;
                    if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                               fn->u.cfunc.realm == ctx && win64_host_stack_ok(state, rt, 256))) {
                        JSString *p = JS_VALUE_GET_STRING(argv[-2]);
                        int len = (int)p->len;
                        int start = 0;
                        int end = len;
                        if (t0 == JS_TAG_INT) {
                            int n = JS_VALUE_GET_INT(argv[0]);
                            start = n < 0 ? max_int(n + len, 0) : min_int(n, len);
                        }
                        if (t1 == JS_TAG_INT) {
                            int n = JS_VALUE_GET_INT(argv[1]);
                            end = n < 0 ? max_int(n + len, 0) : min_int(n, len);
                        }
                        JSFrame *frame = state->frame;
                        frame->sf.cur_sp = state->sp;
                        js_frame_begin_c(state);
                        JSValue res = js_sub_string(ctx, p, start, max_int(end, start));
                        if (!FRAME_CHECKPOINT(frame))
                            frame->sf.cur_sp = NULL;
                        js_frame_finish_c(state);
                        ctx->interrupt_counter--;
                        state->result = res;
                        state->exception_pending = JS_IsException(res);
                        return state->exception_pending;
                    }
                }
            } else if (fp == (void *)js_string_concat &&
                       JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_STRING) {
                JSContext *ctx = state->frame->bytecode->realm;
                JSRuntime *rt = state->rt;
                if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                           fn->u.cfunc.realm == ctx && win64_host_stack_ok(state, rt, 256))) {
                    if (argc == 0) {
                        ctx->interrupt_counter--;
                        state->result = js_dup(argv[-2]);
                        state->exception_pending = false;
                        return 0;
                    }
                    if (argc == 1 && JS_VALUE_GET_TAG(argv[0]) == JS_TAG_STRING) {
                        JSFrame *frame = state->frame;
                        frame->sf.cur_sp = state->sp;
                        js_frame_begin_c(state);
                        JSValue res = js_string_concat(ctx, argv[-2], 1, (JSValueConst *)argv);
                        if (!FRAME_CHECKPOINT(frame))
                            frame->sf.cur_sp = NULL;
                        js_frame_finish_c(state);
                        ctx->interrupt_counter--;
                        state->result = res;
                        state->exception_pending = JS_IsException(res);
                        return state->exception_pending;
                    }
                }
            }
        }
        if (fp == (void *)js_Date_now) {
            JSContext *ctx = state->frame->bytecode->realm;
            JSRuntime *rt = state->rt;
            if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                       win64_host_stack_ok(state, rt, 256))) {
                ctx->interrupt_counter--;
                state->result = js_int64(date_now());
                state->exception_pending = false;
                return 0;
            }
        } else if (fp == (void *)js_math_imul && argc == 2 &&
                   JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT &&
                   JS_VALUE_GET_TAG(argv[1]) == JS_TAG_INT) {
            JSContext *ctx = state->frame->bytecode->realm;
            JSRuntime *rt = state->rt;
            if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                       win64_host_stack_ok(state, rt, 256))) {
                ctx->interrupt_counter--;
                int32_t prod = (int32_t)((uint32_t)JS_VALUE_GET_INT(argv[0]) *
                                         (uint32_t)JS_VALUE_GET_INT(argv[1]));
                state->result = JS_MKVAL(JS_TAG_INT, prod);
                state->exception_pending = false;
                return 0;
            }
        }
    } else if (cproto == JS_CFUNC_generic_magic) {
        if (method) {
            if (fp == (void *)js_array_push && argc == 1 && fn->u.cfunc.magic == 0 &&
                JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_OBJECT) {
                JSContext *ctx = state->frame->bytecode->realm;
                JSRuntime *rt = state->rt;
                if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                           fn->u.cfunc.realm == ctx && ctx->std_array_prototype &&
                           JS_IsObject(ctx->class_proto[JS_CLASS_ARRAY]) &&
                           win64_host_stack_ok(state, rt, 256))) {
                    JSObject *arr = JS_VALUE_GET_OBJ(argv[-2]);
                    if (likely(arr->class_id == JS_CLASS_ARRAY && arr->fast_array &&
                               arr->extensible && arr->is_exotic && arr->shape->prop_count > 0 &&
                               arr->shape->proto ==
                                   JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_ARRAY]) &&
                               get_shape_prop(arr->shape)[0].atom == JS_ATOM_length &&
                               get_shape_prop(arr->shape)[0].flags ==
                                   (JS_PROP_WRITABLE | JS_PROP_LENGTH) &&
                               JS_VALUE_GET_TAG(arr->prop[0].u.value) == JS_TAG_INT)) {
                        uint32_t count = arr->u.array.count;
                        if (likely((uint32_t)JS_VALUE_GET_INT(arr->prop[0].u.value) == count &&
                                   count < (uint32_t)INT32_MAX && count < arr->u.array.u1.size)) {
                            ctx->interrupt_counter--;
                            arr->u.array.u.values[count] = js_dup(argv[0]);
                            count++;
                            arr->u.array.count = count;
                            arr->prop[0].u.value = JS_MKVAL(JS_TAG_INT, (int32_t)count);
                            state->result = JS_MKVAL(JS_TAG_INT, (int32_t)count);
                            state->exception_pending = false;
                            return 0;
                        }
                    }
                }
            } else if (fp == (void *)js_array_pop && argc == 0 && fn->u.cfunc.magic == 0 &&
                       JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_OBJECT) {
                JSContext *ctx = state->frame->bytecode->realm;
                JSRuntime *rt = state->rt;
                if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                           win64_host_stack_ok(state, rt, 256))) {
                    JSObject *arr = JS_VALUE_GET_OBJ(argv[-2]);
                    if (likely(arr->class_id == JS_CLASS_ARRAY && arr->fast_array &&
                               arr->extensible && arr->is_exotic && arr->shape->prop_count > 0 &&
                               get_shape_prop(arr->shape)[0].atom == JS_ATOM_length &&
                               get_shape_prop(arr->shape)[0].flags ==
                                   (JS_PROP_WRITABLE | JS_PROP_LENGTH) &&
                               JS_VALUE_GET_TAG(arr->prop[0].u.value) == JS_TAG_INT)) {
                        uint32_t count = arr->u.array.count;
                        if (likely((uint32_t)JS_VALUE_GET_INT(arr->prop[0].u.value) == count &&
                                   count <= (uint32_t)INT32_MAX)) {
                            ctx->interrupt_counter--;
                            if (count == 0) {
                                state->result = JS_UNDEFINED;
                            } else {
                                count--;
                                JSValue v = arr->u.array.u.values[count];
                                arr->u.array.count = count;
                                arr->prop[0].u.value = JS_MKVAL(JS_TAG_INT, (int32_t)count);
                                state->result = v;
                            }
                            state->exception_pending = false;
                            return 0;
                        }
                    }
                }
            } else if ((fp == (void *)js_map_get || fp == (void *)js_map_has) &&
                       JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_OBJECT) {
                JSObject *mobj = JS_VALUE_GET_OBJ(argv[-2]);
                int magic = fn->u.cfunc.magic;
                if (likely(mobj->class_id == (uint16_t)(JS_CLASS_MAP + magic) &&
                           mobj->u.map_state != NULL)) {
                    JSContext *ctx = state->frame->bytecode->realm;
                    JSRuntime *rt = state->rt;
                    if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                               fn->u.cfunc.realm == ctx && win64_host_stack_ok(state, rt, 256))) {
                        JSValueConst key =
                            argc >= 1 ? map_normalize_key_const(ctx, argv[0]) : JS_UNDEFINED;
                        int ktag = JS_VALUE_GET_TAG(key);
                        if (likely(ktag == JS_TAG_STRING || ktag == JS_TAG_OBJECT ||
                                   ktag == JS_TAG_INT || ktag == JS_TAG_SYMBOL)) {
                            uint32_t raw_h;
                            JSMapRecord *mr =
                                js_map_find_record_hash(ctx, mobj->u.map_state, key, &raw_h);
                            ctx->interrupt_counter--;
                            if (fp == (void *)js_map_get)
                                state->result = mr ? js_dup(mr->value) : JS_UNDEFINED;
                            else
                                state->result = js_bool(mr != NULL);
                            state->exception_pending = false;
                            return 0;
                        }
                    }
                }
            } else if (fp == (void *)js_map_set && JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_OBJECT) {
                JSObject *mobj = JS_VALUE_GET_OBJ(argv[-2]);
                int magic = fn->u.cfunc.magic;
                JSMapState *ms = mobj->u.map_state;
                if (likely(mobj->class_id == (uint16_t)(JS_CLASS_MAP + magic) && ms != NULL)) {
                    JSContext *ctx = state->frame->bytecode->realm;
                    JSRuntime *rt = state->rt;
                    JSValueConst key =
                        argc >= 1 ? map_normalize_key_const(ctx, argv[0]) : JS_UNDEFINED;
                    if (likely((!ms->is_weak || is_valid_weakref_target(key)) &&
                               ctx->interrupt_counter > 1 && !rt->dump_flags &&
                               fn->u.cfunc.realm == ctx && win64_host_stack_ok(state, rt, 256))) {
                        JSValueConst val = (magic & MAGIC_SET)
                                               ? JS_UNDEFINED
                                               : (argc >= 2 ? argv[1] : JS_UNDEFINED);
                        uint32_t raw_h;
                        JSMapRecord *mr = js_map_find_record_hash(ctx, ms, key, &raw_h);
                        JSFrame *frame = state->frame;
                        frame->sf.cur_sp = state->sp;
                        js_frame_begin_c(state);
                        if (mr) {
                            JS_FreeValue(ctx, mr->value);
                            mr->value = js_dup(val);
                        } else {
                            mr = map_add_record_hashed(ctx, ms, key, raw_h);
                            if (unlikely(!mr)) {
                                if (!FRAME_CHECKPOINT(frame))
                                    frame->sf.cur_sp = NULL;
                                js_frame_finish_c(state);
                                ctx->interrupt_counter--;
                                state->result = JS_EXCEPTION;
                                state->exception_pending = true;
                                return 1;
                            }
                            mr->value = js_dup(val);
                        }
                        if (!FRAME_CHECKPOINT(frame))
                            frame->sf.cur_sp = NULL;
                        js_frame_finish_c(state);
                        ctx->interrupt_counter--;
                        state->result = js_dup(argv[-2]);
                        state->exception_pending = false;
                        return 0;
                    }
                }
            } else if (fp == (void *)js_map_delete && JS_VALUE_GET_TAG(argv[-2]) == JS_TAG_OBJECT) {
                JSObject *mobj = JS_VALUE_GET_OBJ(argv[-2]);
                int magic = fn->u.cfunc.magic;
                JSMapState *ms = mobj->u.map_state;
                if (likely(mobj->class_id == (uint16_t)(JS_CLASS_MAP + magic) && ms != NULL)) {
                    JSContext *ctx = state->frame->bytecode->realm;
                    JSRuntime *rt = state->rt;
                    if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                               fn->u.cfunc.realm == ctx && win64_host_stack_ok(state, rt, 256))) {
                        JSValueConst key =
                            argc >= 1 ? map_normalize_key_const(ctx, argv[0]) : JS_UNDEFINED;
                        uint32_t raw_h;
                        JSMapRecord *mr = js_map_find_record_hash(ctx, ms, key, &raw_h);
                        if (!mr) {
                            ctx->interrupt_counter--;
                            state->result = JS_FALSE;
                            state->exception_pending = false;
                            return 0;
                        }
                        JSFrame *frame = state->frame;
                        frame->sf.cur_sp = state->sp;
                        js_frame_begin_c(state);
                        map_delete_record(rt, ms, mr);
                        if (!FRAME_CHECKPOINT(frame))
                            frame->sf.cur_sp = NULL;
                        js_frame_finish_c(state);
                        ctx->interrupt_counter--;
                        state->result = JS_TRUE;
                        state->exception_pending = false;
                        return 0;
                    }
                }
            } else if (fp == (void *)js_number_toString && fn->u.cfunc.magic == 0 &&
                       (argc == 0 || JS_IsUndefined(argv[0]))) {
                int rtag = JS_VALUE_GET_TAG(argv[-2]);
                if (likely(rtag == JS_TAG_INT || rtag == JS_TAG_FLOAT64)) {
                    JSContext *ctx = state->frame->bytecode->realm;
                    JSRuntime *rt = state->rt;
                    if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                               fn->u.cfunc.realm == ctx && win64_host_stack_ok(state, rt, 256))) {
                        JSFrame *frame = state->frame;
                        JSValue res;
                        frame->sf.cur_sp = state->sp;
                        js_frame_begin_c(state);
                        if (rtag == JS_TAG_INT) {
#ifdef QJS_INT_TO_STRING_FAST_AVAILABLE
                            res = qjs_int_to_string_fast(ctx, JS_VALUE_GET_INT(argv[-2]));
#else
                            char buf[16];
                            int len = (int)i32toa(buf, JS_VALUE_GET_INT(argv[-2]));
                            res = js_new_string8_len(ctx, buf, len);
#endif
                        } else {
                            res = js_dtoa2(ctx, JS_VALUE_GET_FLOAT64(argv[-2]), 10, 0,
                                           JS_DTOA_FORMAT_FREE);
                        }
                        if (!FRAME_CHECKPOINT(frame))
                            frame->sf.cur_sp = NULL;
                        js_frame_finish_c(state);
                        ctx->interrupt_counter--;
                        state->result = res;
                        state->exception_pending = JS_IsException(res);
                        return state->exception_pending;
                    }
                }
            }
        }
        if (fp == (void *)js_math_min_max && argc == 2 && JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT &&
            JS_VALUE_GET_TAG(argv[1]) == JS_TAG_INT) {
            JSContext *ctx = state->frame->bytecode->realm;
            JSRuntime *rt = state->rt;
            if (likely(ctx->interrupt_counter > 1 && !rt->dump_flags &&
                       win64_host_stack_ok(state, rt, 256))) {
                int32_t a = JS_VALUE_GET_INT(argv[0]);
                int32_t b = JS_VALUE_GET_INT(argv[1]);
                int32_t r = fn->u.cfunc.magic ? (a > b ? a : b) : (a < b ? a : b);
                ctx->interrupt_counter--;
                state->result = JS_MKVAL(JS_TAG_INT, r);
                state->exception_pending = false;
                return 0;
            }
        }
    }
    return JS_FrameInterpHostDirectShared(state, argv, argc, method);
}

/* Zero-JSStackFrame fast lane for pure C math builtins (JS_CFUNC_f_f / JS_CFUNC_f_f_f).
 * Pure double(*)(double[,double]) callbacks cannot throw, allocate, or reenter JS. */
WIN64_HOST_FAST_CODE int JS_Win64HostNumericFast(JSFrameRegisterState *state, JSValue *argv,
                                                 int argc, bool method)
{
    JSContext *ctx = state->frame->bytecode->realm;
    JSRuntime *rt = state->rt;
    JSObject *fn = JS_VALUE_GET_OBJ(argv[-1]);
    int formal = fn->u.cfunc.length;
    if (likely(argc >= formal && formal >= 1 && ctx->interrupt_counter > 1 && !rt->dump_flags &&
               win64_host_stack_ok(state, rt, sizeof(JSValue) * (size_t)formal + 256))) {
        int t0 = JS_VALUE_GET_TAG(argv[0]);
        if (likely(t0 == JS_TAG_INT || t0 == JS_TAG_FLOAT64)) {
            double d0 = (t0 == JS_TAG_INT) ? (double)JS_VALUE_GET_INT(argv[0])
                                           : JS_VALUE_GET_FLOAT64(argv[0]);
            if (fn->u.cfunc.cproto == JS_CFUNC_f_f) {
                ctx->interrupt_counter--;
                state->result = js_number(fn->u.cfunc.c_function.f_f(d0));
                state->exception_pending = false;
                return 0;
            }
            if (likely(argc >= 2)) {
                int t1 = JS_VALUE_GET_TAG(argv[1]);
                if (likely(t1 == JS_TAG_INT || t1 == JS_TAG_FLOAT64)) {
                    double d1 = (t1 == JS_TAG_INT) ? (double)JS_VALUE_GET_INT(argv[1])
                                                   : JS_VALUE_GET_FLOAT64(argv[1]);
                    ctx->interrupt_counter--;
                    state->result = js_number(fn->u.cfunc.c_function.f_f_f(d0, d1));
                    state->exception_pending = false;
                    return 0;
                }
            }
        }
    }
    return JS_FrameInterpHostShared(state, argv, argc, method);
}

static _Atomic unsigned char win64_local_rope_mode;

static SHARED_INLINE unsigned JS_Win64LocalRopeModeGet(void)
{
    unsigned char mode = atomic_load_explicit(&win64_local_rope_mode, memory_order_relaxed);
    if (unlikely(!mode)) {
        unsigned char desired = getenv("QJS_DISABLE_LOCAL_ROPE_APPEND") ? 2 : (1 | 16);
        atomic_compare_exchange_strong_explicit(&win64_local_rope_mode, &mode, desired,
                                                memory_order_relaxed, memory_order_relaxed);
        if (!mode)
            mode = desired;
    }
    return mode;
}

static WIN64_HOST_FAST_CODE int win64_string_concat_step(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSValue *sp = state->sp;
    JSContext *ctx = frame->bytecode->realm;
    uint8_t *pc = state->pc;
    JSValue left = sp[-2];
    JSValue right = sp[-1];
    frame->saved_sp = sp;
    frame->sf.cur_sp = sp;
    frame->sf.cur_pc = pc + 1;
    js_frame_begin_c(state);
    sp[-2] = JS_UNDEFINED;
    sp[-1] = JS_UNDEFINED;
    JSValue res = JS_ConcatString(ctx, left, right);
    if (unlikely(JS_IsException(res))) {
        state->sp = sp - 2;
        state->pc = pc + 1;
        frame->saved_sp = sp - 2;
        frame->sf.cur_sp = sp - 2;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    sp[-2] = res;
    state->sp = sp - 1;
    state->pc = pc + 1;
    if (!FRAME_CHECKPOINT(frame))
        frame->sf.cur_sp = NULL;
    js_frame_finish_c(state);
    return 0;
}

#define FRAME_INLINE SHARED_INLINE
#define LOCAL_STRING_CODE static WIN64_HOST_FAST_CODE
#define JS_FrameLocalRopeModeGet JS_Win64LocalRopeModeGet
#define JS_FrameInterpAddTrampoline win64_string_concat_step
#define qjs_frame_core_js_new_string_rope js_new_string_rope
#include "src/common/string/local-rope-append.inc"
#undef qjs_frame_core_js_new_string_rope
#undef JS_FrameInterpAddTrampoline
#undef JS_FrameLocalRopeModeGet
#undef LOCAL_STRING_CODE
#undef FRAME_INLINE

/* Fast Win64 OP_add slow boundary: handles in-place local/arg rope append and
 * direct string/rope concatenation before delegating BigInt/general ops. */
WIN64_HOST_FAST_CODE int JS_Win64AddSlow(JSFrameRegisterState *state)
{
    JSValue *sp = state->sp;
    int left = JS_VALUE_GET_TAG(sp[-2]);
    int right = JS_VALUE_GET_TAG(sp[-1]);
    if (left == JS_TAG_STRING_ROPE && right == JS_TAG_STRING &&
        JS_REF_COUNT(JS_VALUE_GET_STRING_ROPE(sp[-2])) == 2) {
        int ret = JS_FrameLocalRopeAppendStep(state);
        if (ret == 0 && state->frame && !FRAME_CHECKPOINT(state->frame))
            state->frame->sf.cur_sp = NULL;
        return ret;
    }
    if ((left == JS_TAG_STRING || left == JS_TAG_STRING_ROPE) &&
        (right == JS_TAG_STRING || right == JS_TAG_STRING_ROPE)) {
        return win64_string_concat_step(state);
    }
    return JS_FrameInterpBig_add(state);
}

/* Fast Win64 OP_add_loc string/rope boundary: zero-allocation in-place append
 * on unaliased flat strings and rope tails, returning 2 for fast PC/SP resume. */
WIN64_HOST_FAST_CODE int JS_Win64AddLocalString(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSContext *ctx = frame->bytecode->realm;
    uint8_t *pc = state->pc;
    JSValue *sp = state->sp;
    JSValue *pv = &frame->sf.var_buf[pc[1]];
    JSValue op1 = sp[-1];
    int ltag = JS_VALUE_GET_TAG(*pv);
    int rtag = JS_VALUE_GET_TAG(op1);

    if (ltag == JS_TAG_STRING_ROPE && rtag == JS_TAG_STRING) {
        JSString *part = JS_VALUE_GET_STRING(op1);
        uint32_t added = part->len;
        if (unlikely(added == 0)) {
            sp[-1] = JS_UNDEFINED;
            if (likely(JS_REF_COUNT(part) > 1)) {
                --JS_REF_COUNT(part);
            } else {
                frame->saved_sp = sp - 1;
                frame->sf.cur_sp = sp - 1;
                frame->sf.cur_pc = pc + 2;
                js_frame_begin_c(state);
                JS_FreeValue(ctx, op1);
                if (!FRAME_CHECKPOINT(frame))
                    frame->sf.cur_sp = NULL;
                js_frame_finish_c(state);
            }
            state->sp = sp - 1;
            state->pc = pc + 2;
            return 2;
        }
        JSStringRope *rope = JS_VALUE_GET_STRING_ROPE(*pv);
        if (likely(JS_REF_COUNT(rope) == 1 && JS_VALUE_GET_TAG(rope->right) == JS_TAG_STRING &&
                   added <= JS_STRING_ROPE_SHORT_LEN && rope->len <= JS_STRING_LEN_MAX - added)) {
            JSString *tail = JS_VALUE_GET_STRING(rope->right);
            bool wide = part->is_wide_char;
            size_t new_len = (size_t)tail->len + added;
            if (likely(tail->len <= JS_STRING_ROPE_SHORT_LEN && JS_REF_COUNT(tail) == 1 &&
                       !tail->atom_type && tail->kind == JS_STRING_KIND_NORMAL &&
                       tail->is_wide_char == wide &&
                       js_malloc_usable_size(ctx, tail) >=
                           sizeof(*tail) + (new_len << wide) + (size_t)(!wide))) {
                if (wide) {
                    memcpy(str16(tail) + tail->len, str16(part), (size_t)added * 2);
                } else {
                    memcpy(str8(tail) + tail->len, str8(part), added);
                    str8(tail)[new_len] = '\0';
                }
                tail->len = (uint32_t)new_len;
                if (unlikely(tail->hash))
                    tail->hash = 0;
                rope->len += added;
                rope->is_wide_char |= wide;
                sp[-1] = JS_UNDEFINED;
                if (likely(JS_REF_COUNT(part) > 1)) {
                    --JS_REF_COUNT(part);
                } else {
                    frame->saved_sp = sp - 1;
                    frame->sf.cur_sp = sp - 1;
                    frame->sf.cur_pc = pc + 2;
                    js_frame_begin_c(state);
                    JS_FreeValue(ctx, op1);
                    if (!FRAME_CHECKPOINT(frame))
                        frame->sf.cur_sp = NULL;
                    js_frame_finish_c(state);
                }
                state->sp = sp - 1;
                state->pc = pc + 2;
                return 2;
            }
        }
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 2;
        js_frame_begin_c(state);
        sp[-1] = JS_UNDEFINED;
        if (unlikely(js_frame_append_local_rope(ctx, pv, op1) < 0)) {
            state->sp = sp - 1;
            state->pc = pc + 2;
            frame->saved_sp = sp - 1;
            frame->sf.cur_sp = sp - 1;
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        state->sp = sp - 1;
        state->pc = pc + 2;
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 2;
    }

    if (ltag == JS_TAG_STRING && rtag == JS_TAG_STRING) {
        JSString *p1 = JS_VALUE_GET_STRING(*pv);
        JSString *p2 = JS_VALUE_GET_STRING(op1);
        if (unlikely(p2->len == 0)) {
            sp[-1] = JS_UNDEFINED;
            if (likely(JS_REF_COUNT(p2) > 1)) {
                --JS_REF_COUNT(p2);
            } else {
                frame->saved_sp = sp - 1;
                frame->sf.cur_sp = sp - 1;
                frame->sf.cur_pc = pc + 2;
                js_frame_begin_c(state);
                JS_FreeValue(ctx, op1);
                if (!FRAME_CHECKPOINT(frame))
                    frame->sf.cur_sp = NULL;
                js_frame_finish_c(state);
            }
            state->sp = sp - 1;
            state->pc = pc + 2;
            return 2;
        }
        bool wide = p1->is_wide_char;
        if (likely(JS_REF_COUNT(p1) == 1 && !p1->atom_type && p1->kind == JS_STRING_KIND_NORMAL &&
                   wide == p2->is_wide_char && p1->len <= JS_STRING_LEN_MAX - p2->len &&
                   js_malloc_usable_size(ctx, p1) >=
                       sizeof(*p1) + (((size_t)p1->len + (size_t)p2->len) << wide) +
                           (size_t)(!wide))) {
            if (wide) {
                memcpy(str16(p1) + p1->len, str16(p2), (size_t)p2->len << 1);
                p1->len += p2->len;
            } else {
                memcpy(str8(p1) + p1->len, str8(p2), p2->len);
                p1->len += p2->len;
                str8(p1)[p1->len] = '\0';
            }
            if (unlikely(p1->hash))
                p1->hash = 0;
            sp[-1] = JS_UNDEFINED;
            if (likely(JS_REF_COUNT(p2) > 1)) {
                --JS_REF_COUNT(p2);
            } else {
                frame->saved_sp = sp - 1;
                frame->sf.cur_sp = sp - 1;
                frame->sf.cur_pc = pc + 2;
                js_frame_begin_c(state);
                JS_FreeValue(ctx, op1);
                if (!FRAME_CHECKPOINT(frame))
                    frame->sf.cur_sp = NULL;
                js_frame_finish_c(state);
            }
            state->sp = sp - 1;
            state->pc = pc + 2;
            return 2;
        }
    }

    frame->saved_sp = sp;
    frame->sf.cur_sp = sp;
    frame->sf.cur_pc = pc + 2;
    js_frame_begin_c(state);
    sp[-1] = JS_UNDEFINED;
    JSValue res = JS_ConcatString(ctx, js_dup(*pv), op1);
    if (unlikely(JS_IsException(res))) {
        state->sp = sp - 1;
        state->pc = pc + 2;
        frame->saved_sp = sp - 1;
        frame->sf.cur_sp = sp - 1;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    set_value(ctx, pv, res);
    state->sp = sp - 1;
    state->pc = pc + 2;
    if (!FRAME_CHECKPOINT(frame))
        frame->sf.cur_sp = NULL;
    js_frame_finish_c(state);
    return 2;
}
#undef WIN64_HOST_FAST_CODE

static _Atomic(unsigned) win64_construct_policy = 0;

static SHARED_INLINE bool win64_construct_enabled(void)
{
    unsigned policy = atomic_load_explicit(&win64_construct_policy, memory_order_relaxed);
    if (unlikely(!policy)) {
        policy = getenv("QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION") ? 2 : 1;
        atomic_store_explicit(&win64_construct_policy, policy, memory_order_relaxed);
    }
    return policy == 1;
}

enum {
    WIN64_CTOR_SRC_ARG = 1,
    WIN64_CTOR_SRC_I32 = 2,
    WIN64_CTOR_SRC_NULL = 3,
    WIN64_CTOR_SRC_UNDEF = 4,
    WIN64_CTOR_SRC_BOOL = 5,
    WIN64_CTOR_SRC_CPOOL = 6,
};

#define WIN64_CTOR_THIS_TAG 99

typedef struct Win64FastCtorMeta {
    uintptr_t rt_id;
    uintptr_t callee_id;
    uintptr_t bc_id;
    uintptr_t callee_shape_id;
    uintptr_t proto_id;
    uintptr_t proto_shape_id;
    uintptr_t shape_id;
    uintptr_t init_holder_id;
    uintptr_t init_holder_shape_id;
    uintptr_t init_fn_id;
    uintptr_t init_fn_shape_id;
    uintptr_t fn_proto_id;
    uintptr_t fn_proto_shape_id;
    uintptr_t apply_id;
    uint64_t epoch;
    uint32_t shape_hash;
    uint32_t proto_slot;
    uint32_t init_slot;
    uint32_t apply_slot;
    uint8_t init_depth;
    uint8_t tier; /* 1=leaf fields, 2=general shared child, 3=va_wrapper, 4=declined */
    uint8_t n_fields;
    uint8_t need_undef_varref0;
    uint8_t ret_this;
    uint8_t want_inline;
    uint8_t src_kind[16];
    int32_t src_imm[16];
    JSAtom atoms[16];
} Win64FastCtorMeta;

#define WIN64_FAST_CTOR_CACHE_SIZE 256u
static WIN64_THREAD_LOCAL Win64FastCtorMeta win64_fast_ctor_cache[WIN64_FAST_CTOR_CACHE_SIZE];

static SHARED_INLINE bool win64_ctor_parse_val(JSFunctionBytecode *b, const uint8_t *buf,
                                               uint32_t len, uint32_t *pk, uint8_t *kind,
                                               int32_t *imm)
{
    uint32_t k = *pk;
    if (k >= len)
        return false;
    uint8_t op = buf[k];
    if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        *kind = WIN64_CTOR_SRC_ARG;
        *imm = op - OP_get_arg0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_get_arg) {
        if (k + 3 > len)
            return false;
        *kind = WIN64_CTOR_SRC_ARG;
        *imm = (int32_t)get_u16(buf + k + 1);
        *pk = k + 3;
        return true;
    }
    if (op >= OP_push_minus1 && op <= OP_push_7) {
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int32_t)op - OP_push_0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_i8) {
        if (k + 2 > len)
            return false;
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int8_t)buf[k + 1];
        *pk = k + 2;
        return true;
    }
    if (op == OP_push_i16) {
        if (k + 3 > len)
            return false;
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int16_t)get_u16(buf + k + 1);
        *pk = k + 3;
        return true;
    }
    if (op == OP_push_i32) {
        if (k + 5 > len)
            return false;
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int32_t)get_u32(buf + k + 1);
        *pk = k + 5;
        return true;
    }
    if (op == OP_null) {
        *kind = WIN64_CTOR_SRC_NULL;
        *imm = 0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_undefined) {
        *kind = WIN64_CTOR_SRC_UNDEF;
        *imm = 0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_false || op == OP_push_true) {
        *kind = WIN64_CTOR_SRC_BOOL;
        *imm = (op == OP_push_true);
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_const8 || op == OP_push_const) {
        uint32_t idx;
        if (op == OP_push_const8) {
            if (k + 2 > len)
                return false;
            idx = buf[k + 1];
            *pk = k + 2;
        } else {
            if (k + 5 > len)
                return false;
            idx = get_u32(buf + k + 1);
            *pk = k + 5;
        }
        if (idx >= b->cpool_count)
            return false;
        int tag = JS_VALUE_GET_TAG(b->cpool[idx]);
        if (tag != JS_TAG_INT && tag != JS_TAG_FLOAT64 && tag != JS_TAG_STRING &&
            tag != JS_TAG_BOOL && tag != JS_TAG_NULL && tag != JS_TAG_UNDEFINED)
            return false;
        *kind = WIN64_CTOR_SRC_CPOOL;
        *imm = (int32_t)idx;
        return true;
    }
    return false;
}

static SHARED_INLINE bool win64_ctor_proto_ok(JSObject *proto_obj, JSAtom atom)
{
    if (atom == JS_ATOM___proto__ || __JS_AtomIsTaggedInt(atom))
        return false;
    unsigned depth = 0;
    for (JSObject *cur = proto_obj; cur; cur = cur->shape->proto) {
        JSProperty *p2;
        JSShapeProperty *prs;
        if (++depth > 16 || cur->is_exotic)
            return false;
        cur->is_prototype = true;
        prs = find_own_property(&p2, cur, atom);
        if (prs)
            return (prs->flags & (JS_PROP_TMASK | JS_PROP_WRITABLE | JS_PROP_LENGTH)) ==
                   JS_PROP_WRITABLE;
    }
    return true;
}

static SHARED_INLINE int win64_ctor_to_bool(JSValueConst v)
{
    switch (JS_VALUE_GET_TAG(v)) {
    case JS_TAG_INT:
    case JS_TAG_BOOL:
        return JS_VALUE_GET_INT(v) != 0;
    case JS_TAG_NULL:
    case JS_TAG_UNDEFINED:
        return 0;
    case JS_TAG_FLOAT64: {
        double d = JS_VALUE_GET_FLOAT64(v);
        return !(d != d) && d != 0.0;
    }
    case JS_TAG_STRING:
        return JS_VALUE_GET_STRING(v)->len != 0;
    case JS_TAG_OBJECT:
        return !JS_VALUE_GET_OBJ(v)->is_HTMLDDA;
    default:
        return -1;
    }
}

static bool win64_ctor_eval_init(JSFunctionBytecode *ib, uint16_t incoming_argc,
                                 const JSValue *argv, JSObject *proto_obj, Win64FastCtorMeta *m,
                                 JSAtom *out_atoms, JSValue *out_vals, uint8_t *out_n,
                                 bool *hit_unsupported_op)
{
    const uint8_t *ibuf = ib->byte_code_buf;
    uint32_t len = ib->byte_code_len;
    *out_n = 0;
    *hit_unsupported_op = false;
    if (ib->arg_count > 8)
        return false;
    if (ib->var_count == 0) {
        if (len == 1 && ibuf[0] == OP_return_undef)
            return true;
        *hit_unsupported_op = true;
        return false;
    }
    if (ib->var_count != 1 || len < 3 || ibuf[0] != OP_push_this || ibuf[1] != OP_put_loc0) {
        *hit_unsupported_op = true;
        return false;
    }
    JSValue loc_args[8];
    for (uint32_t i = 0; i < ib->arg_count; i++)
        loc_args[i] = i < incoming_argc ? argv[i] : JS_UNDEFINED;
    JSValue eval_sp[16];
    int sp_top = 0;
    JSValue this_sentinel = JS_MKVAL(WIN64_CTOR_THIS_TAG, 0);
    uint32_t ip = 2;
    uint8_t n = 0;
    for (unsigned step = 0; step < 64; step++) {
        if (ip >= len) {
            *hit_unsupported_op = true;
            return false;
        }
        uint8_t op = ibuf[ip];
        switch (op) {
        case OP_return_undef:
            if (sp_top != 0) {
                *hit_unsupported_op = true;
                return false;
            }
            *out_n = n;
            return true;
        case OP_get_loc0:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = this_sentinel;
            ip += 1;
            break;
        case OP_get_arg0:
        case OP_get_arg1:
        case OP_get_arg2:
        case OP_get_arg3: {
            uint32_t idx = (uint32_t)(op - OP_get_arg0);
            if (idx >= ib->arg_count || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = loc_args[idx];
            ip += 1;
            break;
        }
        case OP_get_arg: {
            if (ip + 3 > len) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = get_u16(ibuf + ip + 1);
            if (idx >= ib->arg_count || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = loc_args[idx];
            ip += 3;
            break;
        }
        case OP_put_arg0:
        case OP_put_arg1:
        case OP_put_arg2:
        case OP_put_arg3: {
            uint32_t idx = (uint32_t)(op - OP_put_arg0);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[--sp_top];
            ip += 1;
            break;
        }
        case OP_put_arg: {
            if (ip + 3 > len) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = get_u16(ibuf + ip + 1);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[--sp_top];
            ip += 3;
            break;
        }
        case OP_set_arg0:
        case OP_set_arg1:
        case OP_set_arg2:
        case OP_set_arg3: {
            uint32_t idx = (uint32_t)(op - OP_set_arg0);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[sp_top - 1];
            ip += 1;
            break;
        }
        case OP_set_arg: {
            if (ip + 3 > len) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = get_u16(ibuf + ip + 1);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[sp_top - 1];
            ip += 3;
            break;
        }
        case OP_dup:
            if (sp_top < 1 || sp_top >= 16 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top] = eval_sp[sp_top - 1];
            sp_top++;
            ip += 1;
            break;
        case OP_drop:
            if (sp_top < 1) {
                *hit_unsupported_op = true;
                return false;
            }
            sp_top--;
            ip += 1;
            break;
        case OP_push_minus1:
        case OP_push_0:
        case OP_push_1:
        case OP_push_2:
        case OP_push_3:
        case OP_push_4:
        case OP_push_5:
        case OP_push_6:
        case OP_push_7:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int32_t)op - OP_push_0);
            ip += 1;
            break;
        case OP_push_i8:
            if (ip + 2 > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int8_t)ibuf[ip + 1]);
            ip += 2;
            break;
        case OP_push_i16:
            if (ip + 3 > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int16_t)get_u16(ibuf + ip + 1));
            ip += 3;
            break;
        case OP_push_i32:
            if (ip + 5 > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int32_t)get_u32(ibuf + ip + 1));
            ip += 5;
            break;
        case OP_undefined:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = JS_UNDEFINED;
            ip += 1;
            break;
        case OP_null:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = JS_NULL;
            ip += 1;
            break;
        case OP_push_false:
        case OP_push_true:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = JS_MKVAL(JS_TAG_BOOL, op == OP_push_true);
            ip += 1;
            break;
        case OP_push_const8:
        case OP_push_const: {
            uint32_t ilen = (op == OP_push_const8) ? 2 : 5;
            if (ip + ilen > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = (op == OP_push_const8) ? ibuf[ip + 1] : get_u32(ibuf + ip + 1);
            if (idx >= ib->cpool_count) {
                *hit_unsupported_op = true;
                return false;
            }
            int ctag = JS_VALUE_GET_TAG(ib->cpool[idx]);
            if (ctag != JS_TAG_INT && ctag != JS_TAG_FLOAT64 && ctag != JS_TAG_STRING &&
                ctag != JS_TAG_BOOL && ctag != JS_TAG_NULL && ctag != JS_TAG_UNDEFINED) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = ib->cpool[idx];
            ip += ilen;
            break;
        }
        case OP_lnot: {
            if (sp_top < 1 || JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            int bval = win64_ctor_to_bool(eval_sp[sp_top - 1]);
            if (bval < 0)
                return false;
            eval_sp[sp_top - 1] = JS_MKVAL(JS_TAG_BOOL, !bval);
            ip += 1;
            break;
        }
        case OP_if_false8:
        case OP_if_true8:
        case OP_if_false:
        case OP_if_true: {
            bool is8 = (op == OP_if_false8 || op == OP_if_true8);
            bool want_true = (op == OP_if_true8 || op == OP_if_true);
            uint32_t ilen = is8 ? 2 : 5;
            if (ip + ilen > len || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            int bval = win64_ctor_to_bool(eval_sp[--sp_top]);
            if (bval < 0)
                return false;
            if ((bval != 0) == want_true) {
                int32_t disp = is8 ? (int8_t)ibuf[ip + 1] : (int32_t)get_u32(ibuf + ip + 1);
                int32_t next_ip = (int32_t)(ip + 1) + disp;
                if (next_ip < 2 || (uint32_t)next_ip >= len) {
                    *hit_unsupported_op = true;
                    return false;
                }
                ip = (uint32_t)next_ip;
            } else {
                ip += ilen;
            }
            break;
        }
        case OP_goto8:
        case OP_goto16:
        case OP_goto: {
            uint32_t ilen = (op == OP_goto8) ? 2 : (op == OP_goto16 ? 3 : 5);
            if (ip + ilen > len) {
                *hit_unsupported_op = true;
                return false;
            }
            int32_t disp = (op == OP_goto8) ? (int8_t)ibuf[ip + 1]
                                            : (op == OP_goto16 ? (int16_t)get_u16(ibuf + ip + 1)
                                                               : (int32_t)get_u32(ibuf + ip + 1));
            int32_t next_ip = (int32_t)(ip + 1) + disp;
            if (next_ip < 2 || (uint32_t)next_ip >= len) {
                *hit_unsupported_op = true;
                return false;
            }
            ip = (uint32_t)next_ip;
            break;
        }
        case OP_put_field: {
            if (ip + 5 > len || sp_top < 2 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 2]) != WIN64_CTOR_THIS_TAG ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            JSValue val = eval_sp[--sp_top];
            sp_top--;
            JSAtom atom = get_u32(ibuf + ip + 1);
            bool updated_slot = false;
            for (uint8_t j = 0; j < n; j++) {
                if (out_atoms[j] == atom) {
                    out_vals[j] = val;
                    updated_slot = true;
                    break;
                }
            }
            if (!updated_slot) {
                if (n >= 16) {
                    *hit_unsupported_op = true;
                    return false;
                }
                if (!(m->n_fields != 0xFF && n < m->n_fields && m->atoms[n] == atom)) {
                    if (!win64_ctor_proto_ok(proto_obj, atom))
                        return false;
                }
                out_atoms[n] = atom;
                out_vals[n] = val;
                n++;
            }
            ip += 5;
            break;
        }
        default:
            *hit_unsupported_op = true;
            return false;
        }
    }
    *hit_unsupported_op = true;
    return false;
}

/* Borrowed shape lookup: verifies cached shape inside rt->shape_hash without holding
 * an owned refcount in TLS so runtime destruction never leaks shapes or atoms. */
static JSShape *win64_ctor_ensure_shape(JSContext *ctx, JSRuntime *rt, Win64FastCtorMeta *m,
                                        JSObject *proto_obj, uint8_t n_fields, const JSAtom *atoms)
{
    if (m->rt_id == (uintptr_t)rt && m->shape_id != 0) {
        uint32_t h = get_shape_hash(m->shape_hash, rt->shape_hash_bits);
        for (JSShape *p = rt->shape_hash[h]; p; p = p->shape_hash_next) {
            if ((uintptr_t)p == m->shape_id && p->hash == m->shape_hash && p->proto == proto_obj &&
                p->is_hashed && !p->deleted_prop_count && p->prop_count == n_fields) {
                bool match = true;
                JSShapeProperty *props = get_shape_prop(p);
                for (uint8_t f = 0; f < n_fields; f++) {
                    if (props[f].atom != atoms[f] || props[f].flags != JS_PROP_C_W_E) {
                        match = false;
                        break;
                    }
                }
                if (match)
                    return js_dup_shape(p);
            }
        }
    }
    JSShape *sh = find_hashed_shape_proto(rt, proto_obj);
    sh = sh ? js_dup_shape(sh) : js_new_shape(ctx, proto_obj);
    if (!sh)
        return NULL;
    for (uint8_t f = 0; f < n_fields; f++) {
        JSShape *next = find_hashed_shape_prop(rt, sh, atoms[f], JS_PROP_C_W_E);
        if (next) {
            JSShape *old_sh = sh;
            sh = js_dup_shape(next);
            js_free_shape(rt, old_sh);
        } else {
            if (JS_REF_COUNT(sh) != 1) {
                JSShape *clone = js_clone_shape(ctx, sh);
                if (!clone) {
                    js_free_shape(rt, sh);
                    return NULL;
                }
                clone->is_hashed = true;
                js_shape_hash_link(rt, clone);
                js_free_shape(rt, sh);
                sh = clone;
            }
            if (add_shape_property(ctx, &sh, NULL, atoms[f], JS_PROP_C_W_E)) {
                js_free_shape(rt, sh);
                return NULL;
            }
        }
    }
    m->rt_id = (uintptr_t)rt;
    m->shape_id = (uintptr_t)sh;
    m->shape_hash = sh->hash;
    return sh;
}

static bool win64_ctor_has_check_ctor(JSFunctionBytecode *b)
{
    const uint8_t *buf = b->byte_code_buf;
    for (int pos = 0; pos < b->byte_code_len; pos += js_frame_opcode_sizes[buf[pos]]) {
        if (buf[pos] == OP_check_ctor)
            return true;
    }
    return false;
}

int JS_FrameVarargsConstructCall(JSFrameRegisterState *state)
{
#ifndef QJS_PROPERTY_IC
    (void)state;
    return -1;
#else
    uint8_t *pc = state->pc;
    uint16_t incoming_argc = get_u16(pc + 1);
    if (!win64_construct_enabled() || incoming_argc > 32765)
        return -1;
    JSFrame *frame = state->frame;
    JSRuntime *rt = state->rt;
    JSContext *ctx = frame->bytecode->realm;
    if (FRAME_REGISTER_STATE(rt) != 1 || rt->dump_flags || rt->property_ic_mode != 1 ||
        !rt->property_ic_epoch || ctx->interrupt_counter <= 2)
        return -1;
    JSValue *sp = state->sp;
    JSValue *argv = sp - incoming_argc;
    JSValue func_obj = argv[-2];
    if (!JS_IsObject(func_obj) || !JS_IsObject(argv[-1]) ||
        JS_VALUE_GET_OBJ(func_obj) != JS_VALUE_GET_OBJ(argv[-1]))
        return -1;
    JSObject *callee = JS_VALUE_GET_OBJ(func_obj);
    if (incoming_argc == 0 && callee->class_id == JS_CLASS_C_FUNCTION && callee->is_constructor &&
        !callee->is_exotic &&
        (callee->u.cfunc.cproto == JS_CFUNC_constructor ||
         callee->u.cfunc.cproto == JS_CFUNC_constructor_or_func) &&
        callee->u.cfunc.c_function.constructor == js_object_constructor &&
        callee->u.cfunc.realm == ctx) {
        if (rt->dump_flags || ctx->interrupt_counter <= 2 ||
            !JS_IsObject(ctx->class_proto[JS_CLASS_OBJECT]))
            return -1;
        JSObject *op_proto = JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_OBJECT]);
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc + 3;
        state->sp = sp;
        js_frame_begin_c(state);
        JSShape *sh = find_hashed_shape_proto(rt, op_proto);
        sh = sh ? js_dup_shape(sh) : js_new_shape(ctx, op_proto);
        if (!sh) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSValue this_obj = JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, NULL);
        if (JS_IsException(this_obj)) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter--;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        argv[-1] = JS_UNDEFINED;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        if (JS_REF_COUNT(callee) > 2) {
            JS_REF_COUNT(callee) -= 2;
        } else {
            JS_FreeValue(ctx, old_f0);
            JS_FreeValue(ctx, old_f1);
        }
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 0;
    }
    if (callee->class_id != JS_CLASS_BYTECODE_FUNCTION || !callee->is_constructor ||
        callee->is_exotic)
        return -1;
    JSFunctionBytecode *b = callee->u.func.function_bytecode;
    if (b->is_derived_class_constructor || b->func_kind != JS_FUNC_NORMAL || b->realm != ctx)
        return -1;
    if (!FRAME_KIND(b) && !js_frame_validate(b))
        FRAME_KIND(b) = 2;
    bool is_kind1 = FRAME_SUPPORTED(b) != 0;
    bool is_va_wrapper =
        !is_kind1 && FRAME_KIND(b) == 2 && !rt->interrupt_handler && ctx->interrupt_counter > 4 &&
        b->byte_code_len == 21 && b->arg_count == 0 && b->var_count == 2 && b->var_ref_count == 0 &&
        b->closure_var_count == 0 && b->stack_size == 4 && b->byte_code_buf[0] == OP_push_this;
    if (!is_kind1 && !is_va_wrapper)
        return -1;

    uint32_t slot =
        (uint32_t)((((uintptr_t)callee >> 4) ^ ((uintptr_t)callee >> 10) ^ ((uintptr_t)b >> 4)) &
                   (WIN64_FAST_CTOR_CACHE_SIZE - 1u));
    Win64FastCtorMeta *m = &win64_fast_ctor_cache[slot];
    JSObject *proto_obj = NULL;
    JSFunctionBytecode *init_b = NULL;
    if (m->rt_id == (uintptr_t)rt && m->tier != 0 &&
        (is_va_wrapper ? (m->tier >= 3) : (m->tier <= 2 || m->tier == 4)) &&
        m->callee_id == (uintptr_t)callee && m->bc_id == (uintptr_t)b &&
        m->callee_shape_id == (uintptr_t)callee->shape && m->epoch == rt->property_ic_epoch &&
        m->proto_slot < (uint32_t)callee->shape->prop_count &&
        get_shape_prop(callee->shape)[m->proto_slot].atom == JS_ATOM_prototype &&
        (get_shape_prop(callee->shape)[m->proto_slot].flags & JS_PROP_TMASK) == JS_PROP_NORMAL) {
        JSValue pval = callee->prop[m->proto_slot].u.value;
        if (JS_IsObject(pval)) {
            JSObject *po = JS_VALUE_GET_OBJ(pval);
            if ((uintptr_t)po == m->proto_id && po->is_prototype && !po->is_exotic &&
                (uintptr_t)po->shape == m->proto_shape_id) {
                proto_obj = po;
            }
        }
    }
    if (proto_obj && is_va_wrapper) {
        if (m->tier == 4)
            return -1;
        JSObject *cur = proto_obj;
        for (uint8_t d = 1; d < m->init_depth && cur; d++) {
            if (cur->is_exotic || !cur->is_prototype) {
                cur = NULL;
                break;
            }
            cur = cur->shape->proto;
        }
        if (cur && (uintptr_t)cur == m->init_holder_id && !cur->is_exotic && cur->is_prototype &&
            (uintptr_t)cur->shape == m->init_holder_shape_id &&
            m->init_slot < (uint32_t)cur->shape->prop_count &&
            get_shape_prop(cur->shape)[m->init_slot].atom == get_u32(b->byte_code_buf + 7) &&
            (get_shape_prop(cur->shape)[m->init_slot].flags & JS_PROP_TMASK) == JS_PROP_NORMAL) {
            JSValue iv = cur->prop[m->init_slot].u.value;
            if (JS_IsObject(iv)) {
                JSObject *ifo = JS_VALUE_GET_OBJ(iv);
                if ((uintptr_t)ifo == m->init_fn_id &&
                    ifo->class_id == JS_CLASS_BYTECODE_FUNCTION && !ifo->is_exotic &&
                    (uintptr_t)ifo->shape == m->init_fn_shape_id && ifo->shape->proto &&
                    (uintptr_t)ifo->shape->proto == m->fn_proto_id &&
                    ifo->shape->proto->is_prototype && !ifo->shape->proto->is_exotic &&
                    (uintptr_t)ifo->shape->proto->shape == m->fn_proto_shape_id &&
                    m->apply_slot < (uint32_t)ifo->shape->proto->shape->prop_count &&
                    get_shape_prop(ifo->shape->proto->shape)[m->apply_slot].atom == JS_ATOM_apply &&
                    (get_shape_prop(ifo->shape->proto->shape)[m->apply_slot].flags &
                     JS_PROP_TMASK) == JS_PROP_NORMAL) {
                    JSValue apv = ifo->shape->proto->prop[m->apply_slot].u.value;
                    if (JS_IsObject(apv) && (uintptr_t)JS_VALUE_GET_OBJ(apv) == m->apply_id)
                        init_b = ifo->u.func.function_bytecode;
                }
            }
        }
        if (!init_b)
            proto_obj = NULL;
    }
    if (!proto_obj) {
        JSProperty *pr = NULL;
        JSShapeProperty *ps = find_own_property(&pr, callee, JS_ATOM_prototype);
        if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL || !JS_IsObject(pr->u.value))
            return -1;
        proto_obj = JS_VALUE_GET_OBJ(pr->u.value);
        if (proto_obj->is_exotic || proto_obj->class_id != JS_CLASS_OBJECT)
            return -1;
        proto_obj->is_prototype = true;

        m->rt_id = (uintptr_t)rt;
        m->callee_id = (uintptr_t)callee;
        m->bc_id = (uintptr_t)b;
        m->callee_shape_id = (uintptr_t)callee->shape;
        m->proto_id = (uintptr_t)proto_obj;
        m->proto_shape_id = (uintptr_t)proto_obj->shape;
        m->shape_id = 0;
        m->shape_hash = 0;
        m->proto_slot = (uint32_t)(pr - callee->prop);
        m->epoch = rt->property_ic_epoch;
        m->init_holder_id = 0;
        m->init_holder_shape_id = 0;
        m->init_depth = 0;
        m->init_fn_id = 0;
        m->init_fn_shape_id = 0;
        m->fn_proto_id = 0;
        m->fn_proto_shape_id = 0;
        m->apply_id = 0;
        m->init_slot = 0;
        m->apply_slot = 0;
        m->tier = 4;
        m->n_fields = 0;
        m->need_undef_varref0 = 0;
        m->ret_this = 0;
        m->want_inline = 0;

        const uint8_t *buf = b->byte_code_buf;
        uint32_t len = b->byte_code_len;
        if (is_va_wrapper) {
            if (buf[1] != OP_put_loc0 || buf[2] != OP_special_object ||
                (buf[3] != OP_SPECIAL_OBJECT_ARGUMENTS &&
                 buf[3] != OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS) ||
                buf[4] != OP_put_loc1 || buf[5] != OP_get_loc0 || buf[6] != OP_get_field ||
                buf[11] != OP_get_field2 || get_u32(buf + 12) != JS_ATOM_apply ||
                buf[16] != OP_get_loc0_loc1 || buf[17] != OP_call_method ||
                get_u16(buf + 18) != 2 || buf[20] != OP_return_undef) {
                return -1;
            }
            JSAtom init_atom = get_u32(buf + 7);
            JSObject *init_holder = proto_obj;
            JSProperty *init_pr = NULL, *own_apply = NULL, *proto_apply = NULL;
            JSShapeProperty *init_ps = NULL;
            uint8_t init_depth = 0;
            for (uint8_t d = 0; d < 8 && init_holder; d++) {
                if (init_holder->is_exotic || (d > 0 && !init_holder->is_prototype)) {
                    init_holder = NULL;
                    break;
                }
                init_holder->is_prototype = true;
                init_ps = find_own_property(&init_pr, init_holder, init_atom);
                if (init_ps) {
                    init_depth = (uint8_t)(d + 1);
                    break;
                }
                init_holder = init_holder->shape->proto;
            }
            if (!init_holder || !init_ps || (init_ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                !JS_IsObject(init_pr->u.value)) {
                m->tier = 0;
                return -1;
            }
            JSObject *init_fn = JS_VALUE_GET_OBJ(init_pr->u.value);
            if (init_fn->class_id != JS_CLASS_BYTECODE_FUNCTION || init_fn->is_exotic ||
                find_own_property(&own_apply, init_fn, JS_ATOM_apply)) {
                m->tier = 0;
                return -1;
            }
            JSObject *fn_proto = init_fn->shape->proto;
            if (!fn_proto || fn_proto->is_exotic) {
                m->tier = 0;
                return -1;
            }
            JSShapeProperty *apply_ps = find_own_property(&proto_apply, fn_proto, JS_ATOM_apply);
            if (!apply_ps || (apply_ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                !JS_IsObject(proto_apply->u.value)) {
                m->tier = 0;
                return -1;
            }
            JSObject *apply_obj = JS_VALUE_GET_OBJ(proto_apply->u.value);
            if (apply_obj->class_id != JS_CLASS_C_FUNCTION ||
                apply_obj->u.cfunc.cproto != JS_CFUNC_generic_magic ||
                apply_obj->u.cfunc.magic != 0 || apply_obj->u.cfunc.length != 2 ||
                apply_obj->u.cfunc.realm != ctx ||
                apply_obj->u.cfunc.c_function.generic_magic != js_function_apply) {
                m->tier = 0;
                return -1;
            }
            init_b = init_fn->u.func.function_bytecode;
            if (!FRAME_KIND(init_b) && !js_frame_validate(init_b))
                FRAME_KIND(init_b) = 2;
            if (init_b->realm != ctx || !(FRAME_KIND(init_b) & 1) ||
                init_b->func_kind != JS_FUNC_NORMAL || init_b->is_derived_class_constructor ||
                init_b->arg_count > 8 || init_b->var_count > 1 || init_b->var_ref_count != 0 ||
                init_b->closure_var_count != 0 || init_b->stack_size > 8 ||
                init_b->byte_code_len > 128) {
                m->tier = 4;
                return -1;
            }
            fn_proto->is_prototype = true;
            m->init_holder_id = (uintptr_t)init_holder;
            m->init_holder_shape_id = (uintptr_t)init_holder->shape;
            m->init_depth = init_depth;
            m->init_fn_id = (uintptr_t)init_fn;
            m->init_fn_shape_id = (uintptr_t)init_fn->shape;
            m->fn_proto_id = (uintptr_t)fn_proto;
            m->fn_proto_shape_id = (uintptr_t)fn_proto->shape;
            m->apply_id = (uintptr_t)apply_obj;
            m->init_slot = (uint32_t)(init_pr - init_holder->prop);
            m->apply_slot = (uint32_t)(proto_apply - fn_proto->prop);
            m->tier = 3;
            m->n_fields = 0xFF;
        } else if (len == 1 && buf[0] == OP_return_undef && b->var_count == 0 &&
                   b->var_ref_count == 0 && b->closure_var_count == 0) {
            m->tier = 1;
        } else if (b->var_count == 1 && b->var_ref_count == 0 && len >= 3 &&
                   buf[0] == OP_push_this && buf[1] == OP_put_loc0) {
            uint32_t k = 2;
            uint8_t n_f = 0, need_vr0 = 0, ret_this = 0;
            bool ok = true;
            if (b->closure_var_count == 1) {
                if (len >= 15 && buf[2] == OP_check_ctor && buf[3] == OP_get_var_ref_check &&
                    buf[4] == 0 && buf[5] == 0 && buf[6] == OP_dup && buf[7] == OP_if_false8 &&
                    buf[8] == 6 && buf[9] == OP_get_loc0 && buf[10] == OP_swap &&
                    buf[11] == OP_call_method && buf[12] == 0 && buf[13] == 0 &&
                    buf[14] == OP_drop) {
                    need_vr0 = 1;
                    k = 15;
                } else {
                    ok = false;
                }
            } else if (b->closure_var_count == 0) {
                if (k < len && buf[k] == OP_check_ctor)
                    k++;
            } else {
                ok = false;
            }
            while (ok && k < len && buf[k] == OP_get_loc0) {
                if (k + 2 == len && buf[k + 1] == OP_return) {
                    ret_this = 1;
                    k += 2;
                    break;
                }
                if (n_f >= 16) {
                    ok = false;
                    break;
                }
                k++;
                uint8_t kind = 0;
                int32_t imm = 0;
                if (!win64_ctor_parse_val(b, buf, len, &k, &kind, &imm) || k + 5 > len ||
                    buf[k] != OP_put_field) {
                    ok = false;
                    break;
                }
                JSAtom atom = get_u32(buf + k + 1);
                k += 5;
                for (uint8_t j = 0; j < n_f; j++) {
                    if (m->atoms[j] == atom) {
                        ok = false;
                        break;
                    }
                }
                if (!ok || !win64_ctor_proto_ok(proto_obj, atom)) {
                    ok = false;
                    break;
                }
                m->src_kind[n_f] = kind;
                m->src_imm[n_f] = imm;
                m->atoms[n_f] = atom;
                n_f++;
            }
            if (ok && ((ret_this && k == len) ||
                       (!ret_this && k + 1 == len && buf[k] == OP_return_undef))) {
                m->tier = 1;
                m->n_fields = n_f;
                m->need_undef_varref0 = need_vr0;
                m->ret_this = ret_this;
            }
        }
        if (m->tier == 4 && is_kind1) {
            if (!win64_ctor_has_check_ctor(b)) {
                uint8_t puts = 0;
                bool has_call = false;
                for (uint32_t pos = 0; pos < len && puts <= 4;) {
                    uint8_t op = buf[pos];
                    uint8_t sz =
                        op < countof(js_frame_opcode_sizes) ? js_frame_opcode_sizes[op] : 0;
                    if (unlikely(!sz))
                        break;
                    if (op == OP_put_field || op == OP_define_field)
                        puts++;
                    else if (op == OP_call || op == OP_tail_call || op == OP_call_method ||
                             op == OP_tail_call_method || op == OP_apply ||
                             (op >= OP_call0 && op <= OP_call3)) {
                        has_call = true;
                        break;
                    }
                    pos += sz;
                }
                m->tier = 2;
                m->want_inline = (!has_call && puts >= 1 && puts <= 4) ? 1 : 0;
            }
        }
    }

    /* Tier 3: Prototype.js 21-byte varargs wrapper around pure this.initialize(...) */
    if (is_va_wrapper) {
        if (m->tier != 3 || !init_b)
            return -1;
        JSAtom out_atoms[16];
        JSValue out_vals[16];
        uint8_t n_f = 0;
        bool hit_unsup = false;
        if (!win64_ctor_eval_init(init_b, incoming_argc, argv, proto_obj, m, out_atoms, out_vals,
                                  &n_f, &hit_unsup)) {
            if (hit_unsup)
                m->tier = 4;
            return -1;
        }
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc + 3;
        state->sp = sp;
        js_frame_begin_c(state);
        if (m->n_fields == 0xFF) {
            m->n_fields = n_f;
            if (n_f)
                memcpy(m->atoms, out_atoms, (size_t)n_f * sizeof(JSAtom));
        }
        JSShape *sh = win64_ctor_ensure_shape(ctx, rt, m, proto_obj, n_f, out_atoms);
        if (!sh) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSProperty props[16];
        props[0].u.value = JS_UNDEFINED;
        for (unsigned f = 0; f < n_f; f++)
            props[f].u.value = js_dup(out_vals[f]);
        JSValue this_obj = JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, n_f ? props : NULL);
        if (JS_IsException(this_obj)) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter -= 4;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        argv[-1] = JS_UNDEFINED;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        if (likely(JS_REF_COUNT(callee) > 2)) {
            JS_REF_COUNT(callee) -= 2;
        } else {
            JS_FreeValue(ctx, old_f0);
            JS_FreeValue(ctx, old_f1);
        }
        for (int i = 0; i < incoming_argc; i++) {
            JSValue a = argv[i];
            argv[i] = JS_UNDEFINED;
            if (JS_VALUE_HAS_REF_COUNT(a)) {
                void *ap = JS_VALUE_GET_PTR(a);
                if (likely(JS_REF_COUNT(ap) > 1))
                    --JS_REF_COUNT(ap);
                else
                    JS_FreeValue(ctx, a);
            }
        }
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 0;
    }

    /* Tier 1: Direct leaf constructor object materialization */
    if (m->tier == 1 &&
        (!m->need_undef_varref0 || (callee->u.func.var_refs && callee->u.func.var_refs[0] &&
                                    JS_IsUndefined(*callee->u.func.var_refs[0]->pvalue)))) {
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc + 3;
        state->sp = sp;
        js_frame_begin_c(state);
        JSShape *sh = win64_ctor_ensure_shape(ctx, rt, m, proto_obj, m->n_fields, m->atoms);
        if (!sh) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSProperty props[16];
        uint32_t moved_mask = 0;
        props[0].u.value = JS_UNDEFINED;
        for (unsigned f = 0; f < m->n_fields; f++) {
            JSValue v;
            switch (m->src_kind[f]) {
            case WIN64_CTOR_SRC_ARG: {
                uint32_t aidx = (uint32_t)m->src_imm[f];
                if (aidx < incoming_argc) {
                    if (likely(aidx < 32u && !(moved_mask & (1u << aidx)))) {
                        moved_mask |= (1u << aidx);
                        v = argv[aidx];
                    } else {
                        v = js_dup(argv[aidx]);
                    }
                } else {
                    v = JS_UNDEFINED;
                }
                break;
            }
            case WIN64_CTOR_SRC_I32:
                v = js_int32(m->src_imm[f]);
                break;
            case WIN64_CTOR_SRC_NULL:
                v = JS_NULL;
                break;
            case WIN64_CTOR_SRC_UNDEF:
                v = JS_UNDEFINED;
                break;
            case WIN64_CTOR_SRC_BOOL:
                v = JS_MKVAL(JS_TAG_BOOL, m->src_imm[f]);
                break;
            default:
                v = js_dup(b->cpool[m->src_imm[f]]);
                break;
            }
            props[f].u.value = v;
        }
        JSValue this_obj =
            JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, m->n_fields ? props : NULL);
        if (unlikely(JS_IsException(this_obj))) {
            for (uint32_t i = 0; i < incoming_argc && i < 32u; i++) {
                if (moved_mask & (1u << i))
                    argv[i] = JS_UNDEFINED;
            }
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter -= 2;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        argv[-1] = JS_UNDEFINED;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        if (likely(JS_REF_COUNT(callee) > 2)) {
            JS_REF_COUNT(callee) -= 2;
        } else {
            JS_FreeValue(ctx, old_f0);
            JS_FreeValue(ctx, old_f1);
        }
        for (int i = 0; i < incoming_argc; i++) {
            if (likely((uint32_t)i < 32u && (moved_mask & (1u << (uint32_t)i)))) {
                argv[i] = JS_UNDEFINED;
            } else {
                JSValue a = argv[i];
                argv[i] = JS_UNDEFINED;
                if (JS_VALUE_HAS_REF_COUNT(a)) {
                    void *ap = JS_VALUE_GET_PTR(a);
                    if (likely(JS_REF_COUNT(ap) > 1))
                        --JS_REF_COUNT(ap);
                    else
                        JS_FreeValue(ctx, a);
                }
            }
        }
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 0;
    }

    /* Tier 2: General ordinary bytecode constructor via shared-segment ASM execution */
    if (m->tier != 2 || !is_kind1 || !js_frame_shared_enabled(rt) ||
        unlikely(js_check_stack_overflow(rt, 4096)))
        return -1;

    frame->saved_sp = sp;
    frame->sf.cur_sp = sp;
    frame->sf.cur_pc = pc + 3;
    state->pc = pc + 3;
    state->sp = sp;
    js_frame_begin_c(state);
    JSShape *sh = win64_ctor_ensure_shape(ctx, rt, m, proto_obj, 0, NULL);
    if (!sh) {
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    JSProperty dummy_prop;
    dummy_prop.u.value = JS_UNDEFINED;
    JSValue this_obj =
        JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, m->want_inline ? &dummy_prop : NULL);
    if (JS_IsException(this_obj)) {
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }

    /* Root this_obj in argv[-2]; argv[-1] still roots callee across the shared call. */
    JSValue old_m2 = argv[-2];
    argv[-2] = this_obj;
    JS_FreeValue(ctx, old_m2);
    js_frame_finish_c(state);

    JSFrameSharedAnchor **slot_ptr = js_frame_shared_slot(), anchor;
    anchor.prev = *slot_ptr;
    anchor.state = state;
    anchor.kind = 0;
    unsigned char prev_active = FRAME_SHARED_ACTIVE(rt);
    FRAME_SHARED_BITS(rt) |= 4;
    *slot_ptr = &anchor;
    JSValue res = js_frame_run_shared(ctx, argv[-1], argv[-2], incoming_argc, (JSValueConst *)argv,
                                      0, b, &anchor);
    *slot_ptr = anchor.prev;
    FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | prev_active;

    js_frame_begin_c(state);
    JSValue constructed = argv[-2];
    JSValue old_callee = argv[-1];
    argv[-2] = JS_UNDEFINED;
    argv[-1] = JS_UNDEFINED;
    JS_FreeValue(ctx, old_callee);
    for (int i = 0; i < incoming_argc; i++) {
        JSValue a = argv[i];
        argv[i] = JS_UNDEFINED;
        JS_FreeValue(ctx, a);
    }
    if (JS_IsException(res)) {
        JS_FreeValue(ctx, constructed);
        state->sp = argv - 2;
        frame->saved_sp = argv - 2;
        frame->sf.cur_sp = argv - 2;
        state->pc = pc + 3;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    if (JS_IsObject(res)) {
        JS_FreeValue(ctx, constructed);
        constructed = res;
    } else {
        JS_FreeValue(ctx, res);
    }
    argv[-2] = constructed;
    JSValue *new_sp = argv - 1;
    state->sp = new_sp;
    frame->saved_sp = new_sp;
    frame->sf.cur_sp = new_sp;
    state->pc = pc + 3;
    if (!FRAME_CHECKPOINT(frame))
        frame->sf.cur_sp = NULL;
    js_frame_finish_c(state);
    return 0;
#endif
}

/* Native Property IC & own-bytecode control block (80-byte ABI).
 * Byte 0: tail mode (1 = tail ON, 2 = OFF, 4 = PIC-only no tail)
 * Byte 5 (reserved[3]): PIC dispatch active (1 = native PIC ON, 2 = OFF) */
struct JSFrameOwnBytecodeState {
    unsigned char mode;
    unsigned char initialized;
    unsigned char reserved[6];
    uint64_t counts[9];
};

struct JSFrameOwnBytecodeState JS_FrameOwnBytecodeData = {0};

static void qjs_win64_own_bytecode_apply_mode(unsigned char mode)
{
    unsigned char pic_active = (mode == 1 || mode == 4) ? 1 : 2;
    JS_FrameOwnBytecodeData.mode = mode;
    JS_FrameOwnBytecodeData.reserved[1] =
        (pic_active == 1 && getenv("QJS_DISABLE_BORROWED_FIELD") == NULL) ? 1 : 2;
    JS_FrameOwnBytecodeData.reserved[3] = pic_active;
    JS_FrameOwnBytecodeData.initialized = 1;
}

static void qjs_win64_own_bytecode_set_tail(int enabled)
{
#ifdef QJS_PROPERTY_IC
    /* Win64 source-level VM uses PIC-only mode (zero tail copy overhead) when
     * Property IC is enabled, regardless of tail toggle, unless PIC is disabled. */
    (void)enabled;
    int pic_disabled = (qjs_turbo_default_property_ic_mode() != 1);
    qjs_win64_own_bytecode_apply_mode(pic_disabled ? 2 : 4);
#else
    (void)enabled;
    qjs_win64_own_bytecode_apply_mode(2);
#endif
}

static int qjs_win64_own_bytecode_tail_active(void)
{
    return JS_FrameOwnBytecodeData.mode == 1 ? 1 : 0;
}

static void qjs_win64_own_bytecode_init(void)
{
    if (!JS_FrameOwnBytecodeData.initialized) {
#ifdef QJS_PROPERTY_IC
        int pic_disabled = (qjs_turbo_default_property_ic_mode() != 1);
        qjs_win64_own_bytecode_apply_mode(pic_disabled ? 2 : 4);
#else
        qjs_win64_own_bytecode_apply_mode(2);
#endif
    }
    qjs_turbo_register_own_bytecode_hooks(qjs_win64_own_bytecode_set_tail,
                                          qjs_win64_own_bytecode_tail_active);
}

#if defined(_MSC_VER)
#pragma section(".CRT$XCU", read)
__declspec(allocate(".CRT$XCU")) void (*const qjs_win64_own_bytecode_ctor)(void) =
    qjs_win64_own_bytecode_init;
#pragma comment(linker, "/include:qjs_win64_own_bytecode_ctor")
#else
__attribute__((constructor)) static void qjs_win64_own_bytecode_ctor(void)
{
    qjs_win64_own_bytecode_init();
}
#endif
