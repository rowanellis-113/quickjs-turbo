/* Activation-owned reusable ordinary C->JS frame. MIT.
 * The original array loops remain unchanged in the core object; admitted
 * activations use generated source bodies with a single prepared-call substitution. This wrapper owns the
 * callable for exactly one native activation and passes the capsule explicitly
 * to its generated loop and callback entry. Dynamic admission and root resets are in the generated assembler.
 * No release diagnostic scratch word is read as a scope pointer. */
#include <stdatomic.h>
#ifdef _MSC_VER
/* @QJS_MSC_INTRIN@ */
#define CALLBACK_CODE __declspec(code_seg(".qjszzcf$c")) __declspec(noinline)
#define CALLBACK_INLINE static __forceinline
#else
#define CALLBACK_CODE __attribute__((section(".qjscbck$C"), noipa))
#define CALLBACK_INLINE static inline __attribute__((always_inline))
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#define CALLBACK_STATE_BYTES 2448
#define CALLBACK_DATA_OFFSET 2560
#define CALLBACK_COMMITTED 2304
#define CALLBACK_CALLER 2272
#define CALLBACK_SITES 2280
#define CALLBACK_NEXT 2288
#define CALLBACK_DIRECT 2297
#else
#define CALLBACK_STATE_BYTES 168
#define CALLBACK_DATA_OFFSET 288
#define CALLBACK_COMMITTED 64
#define CALLBACK_CALLER 136
#define CALLBACK_SITES 144
#define CALLBACK_NEXT 152
#define CALLBACK_DIRECT 161
#endif
typedef struct JSFrameCallbackHost {
    struct JSFrameCallbackHost *prev;
    unsigned char *state;
    unsigned kind;
} JSFrameCallbackHost;
typedef struct JSFrameCallbackSegment {
    struct JSFrameCallbackSegment *next;
    size_t capacity, used;
    unsigned char *data;
} JSFrameCallbackSegment;
typedef struct JSFrameCallbackHeader {
    JSStackFrame sf;
    FRAME_STACK_TAIL_PADDING
    JSFunctionBytecode *bytecode;
    JSValue this_value;
    JSValue *saved_sp;
    JSFrameCallbackSegment *segment;
    uint32_t frame_bytes;
    uint16_t owned_args, pending;
} JSFrameCallbackHeader;
typedef struct JSFrameCallbackScope {
    JSContext *ctx;
    JSValue callee;
    JSFunctionBytecode *bytecode;
    size_t frame_bytes;
    JSFrameCallbackHost *host;
    int callback_argc;
    unsigned reserved;
    JSFrameCallbackHost barrier;
    JSFrameCallbackSegment segment;
    _Alignas(16) unsigned char state[CALLBACK_STATE_BYTES];
    _Alignas(16) unsigned char data[2048];
} JSFrameCallbackScope;
_Static_assert(sizeof(JSFrameCallbackHost) == 24 && sizeof(JSFrameCallbackSegment) == 32 &&
                   sizeof(JSFrameCallbackHeader) == 128 &&
                   offsetof(JSFrameCallbackScope, callee) == 8 &&
                   offsetof(JSFrameCallbackScope, bytecode) == 24 &&
                   offsetof(JSFrameCallbackScope, frame_bytes) == 32 &&
                   offsetof(JSFrameCallbackScope, host) == 40 &&
                   offsetof(JSFrameCallbackScope, callback_argc) == 48 &&
                   offsetof(JSFrameCallbackScope, barrier) == 56 &&
                   offsetof(JSFrameCallbackScope, segment) == 80 &&
                   offsetof(JSFrameCallbackScope, state) == 112 &&
                   offsetof(JSFrameCallbackScope, data) == CALLBACK_DATA_OFFSET,
               "callback capsule ABI");
_Static_assert(
    offsetof(JSRuntime, current_stack_frame) == QJS_ABI_OFF_JSRuntime_current_stack_frame &&
        offsetof(JSRuntime, stack_limit) == QJS_ABI_OFF_JSRuntime_stack_limit &&
        offsetof(JSContext, interrupt_counter) == QJS_ABI_OFF_JSContext_interrupt_counter &&
        offsetof(JSFunctionBytecode, arg_count) == QJS_ABI_OFF_JSFunctionBytecode_arg_count &&
        offsetof(JSFunctionBytecode, var_count) == QJS_ABI_OFF_JSFunctionBytecode_var_count &&
        offsetof(JSFunctionBytecode, stack_size) == QJS_ABI_OFF_JSFunctionBytecode_stack_size &&
        offsetof(JSFunctionBytecode, var_ref_count) ==
            QJS_ABI_OFF_JSFunctionBytecode_var_ref_count &&
        offsetof(JSObject, u.func.function_bytecode) ==
            QJS_ABI_OFF_JSObject_u_func_function_bytecode &&
        JS_CLASS_BYTECODE_FUNCTION == 13,
    "callback dynamic admission ABI");
/* @QJS_CALLBACK_TLS_SP@ */
extern _Atomic unsigned char JS_FrameCallbackControl, JS_FrameCallbackArityControl;
#ifdef _MSC_VER
/* Reuse the already-qualified native byte-atomic leaves. C11 volatile metadata
 * for a new C-level access grows the linker's early readonly directory and
 * moves the inherited Interp table. These leaves preserve the same relaxed
 * atomic load / compare-exchange semantics without adding such access sites. */
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *, unsigned char *, unsigned char);
#endif
#ifdef _MSC_VER
#define frame_callback_control JS_FrameCallbackControl
#define frame_callback_arity_control JS_FrameCallbackArityControl
#else
CALLBACK_INLINE _Atomic unsigned char *frame_callback_control_slot(void)
{
    _Atomic unsigned char *p;
    QJS_CONTROL_SLOT_ADDR(p, JS_FrameCallbackControl);
    return p;
}
#define frame_callback_control (*frame_callback_control_slot())
CALLBACK_INLINE _Atomic unsigned char *frame_callback_arity_control_slot(void)
{
    _Atomic unsigned char *p;
    QJS_CONTROL_SLOT_ADDR(p, JS_FrameCallbackArityControl);
    return p;
}
#define frame_callback_arity_control (*frame_callback_arity_control_slot())
#endif
typedef JSValue (*JSFrameCallbackLoop)(JSContext *, JSValueConst, int, JSValueConst *, int);
typedef JSValue (*JSFramePreparedCallbackLoop)(JSContext *, JSValueConst, int, JSValueConst *, int,
                                               void *);
extern JSValue JS_FramePreparedCallbackSelect(JSContext *, JSValueConst, JSValueConst, JSValueConst,
                                              int, JSValueConst *, int, void *);
CALLBACK_INLINE JSValue frame_callback_prepared_call(JSContext *ctx, JSValueConst func,
                                                     JSValueConst this_val, int argc,
                                                     JSValueConst *argv, void *scope)
{
    return JS_FramePreparedCallbackSelect(ctx, func, this_val, JS_UNDEFINED, argc, argv, 2, scope);
}

/* Keep recognized primitive ChildLeaf bytecode on its established interpreter-free
 * path. These masks mirror child-leaf.py; operand/type checks stay there.
 * A false positive only retains the previous implementation. */
CALLBACK_INLINE int frame_callback_may_have_leaf(JSFunctionBytecode *b)
{
    uint64_t word;
    if (b->var_count)
        return 0;
    if (b->byte_code_len == 4) {
        uint32_t small;
        memcpy(&small, b->byte_code_buf, 4);
        return (small & UINT32_C(0xffff00ff)) == UINT32_C(681312471);
    }
    if (b->byte_code_len == 8) {
        memcpy(&word, b->byte_code_buf, 8);
        return (word & UINT64_C(0xffffffff00ffffff)) == UINT64_C(0x28a3ba9c009cd8d7);
    }
    return b->byte_code_len == 14 && b->closure_var_count == 1 && b->stack_size == 2;
}

extern JSValue JS_FramePreparedCallbackWriteSelect(JSContext *, JSValueConst, JSValueConst,
                                                   JSValueConst, int, JSValueConst *, int, void *);
CALLBACK_INLINE JSValue frame_callback_write_prepared_call(JSContext *ctx, JSValueConst func,
                                                           JSValueConst this_val, int argc,
                                                           JSValueConst *argv, void *scope)
{
    return JS_FramePreparedCallbackWriteSelect(ctx, func, this_val, JS_UNDEFINED, argc, argv, 2,
                                               scope);
}

#ifndef QJS_CALLBACK_WRITABLE
CALLBACK_CODE JSValue JS_FrameCallbackScopeRun(JSContext *ctx, JSValueConst this_val, int argc,
                                               JSValueConst *argv, int special,
                                               JSFrameCallbackHost *host, JSFunctionBytecode *b,
                                               size_t bytes, int callback_argc,
                                               JSFramePreparedCallbackLoop loop)
{
    _Alignas(16) JSFrameCallbackScope call;
    JSFrameCallbackHeader *frame = (JSFrameCallbackHeader *)call.data;
    JSFrameCallbackSegment *next, *following;
    JSValue result;
    unsigned window = b->arg_count > callback_argc ? b->arg_count : 0;
    int i;
    call.ctx = ctx;
    call.callee = js_dup(argv[0]);
    call.bytecode = b;
    call.frame_bytes = bytes;
    call.host = host;
    call.callback_argc = callback_argc;
    call.reserved = 0;
    call.segment.next = NULL;
    call.segment.capacity = sizeof(call.data);
    call.segment.used = 0;
    call.segment.data = call.data;
    memset(call.state, 0, sizeof(call.state));
    memcpy(call.state + 56, &ctx->rt, 8);
    memcpy(call.state + CALLBACK_CALLER, &ctx, 8);
    memcpy(call.state + CALLBACK_SITES, host->state + CALLBACK_SITES, 8);
    memcpy(call.state + CALLBACK_NEXT, host->state + CALLBACK_NEXT, 8);
    call.state[CALLBACK_DIRECT] = host->state[CALLBACK_DIRECT];
    call.barrier.state = call.state;
    call.barrier.kind = 4;
    memset(frame, 0, sizeof(*frame));
    frame->sf.cur_func = call.callee;
    frame->sf.arg_buf = (JSValue *)(call.data + 128);
    frame->sf.var_buf = frame->sf.arg_buf + window;
    frame->sf.arg_count = window ? window : callback_argc;
    /* Only validated readonly, noncaptured parameter slots enter this window.
     * The original native loop owns all actual values until JS returns.
     * Copies of that live prefix are borrowed, not dup'ed or freed here.
     * Unsupported arguments/eval/writes/captures retain the original call.
     * Padding is immutable for this activation; locals/operand roots reset
     * on every callback. owned_args stays zero so cleanup starts at var_buf. */
    for (i = callback_argc; i < (int)window; i++)
        frame->sf.arg_buf[i] = JS_UNDEFINED;
    frame->sf.is_strict_mode = b->is_strict_mode;
    ((unsigned char *)&frame->sf)[62] = 1;
    frame->bytecode = b;
    frame->segment = &call.segment;
    frame->frame_bytes = bytes;
    result = loop(ctx, this_val, argc, argv, special, &call);
    for (next = call.segment.next; next; next = following) {
        following = next->next;
        js_free(ctx, next);
    }
    JS_FreeValue(ctx, call.callee);
    return result;
}
CALLBACK_INLINE JSValue frame_callback_loop(JSContext *ctx, JSValueConst this_val, int argc,
                                            JSValueConst *argv, int special, int callback_argc,
                                            JSFrameCallbackLoop loop,
                                            JSFramePreparedCallbackLoop prepared)
{
    JSFrameCallbackHost *host;
    JSFunctionBytecode *b;
    JSObject *p;
    JSRuntime *host_rt;
    size_t bytes, used, committed;
    unsigned char control;
    if (argc < 1 || JS_VALUE_GET_TAG(argv[0]) != JS_TAG_OBJECT)
        goto original;
    p = JS_VALUE_GET_OBJ(argv[0]);
    if (p->class_id != JS_CLASS_BYTECODE_FUNCTION)
        goto original;
    b = p->u.func.function_bytecode;
    /* No validator or other observable work precedes the original loop. Cold
     * bytecode falls back and is admitted normally on its first callback. */
    if ((FRAME_KIND(b) & 7) != 3 || b->var_ref_count || frame_callback_may_have_leaf(b))
        goto original;
    control = atomic_load_explicit(&frame_callback_control, memory_order_relaxed);
    if (!control) {
        unsigned char expected = 0;
        control = getenv("QJS_DISABLE_PREPARED_CALLBACK") ? 2 : 1;
        if (!atomic_compare_exchange_strong_explicit(&frame_callback_control, &expected, control,
                                                     memory_order_relaxed, memory_order_relaxed))
            control = expected;
    }
    if (control != 1)
        goto original;
    if (b->arg_count > callback_argc) {
#ifdef _MSC_VER
        control = JS_FrameJSONLoad8((const unsigned char *)&frame_callback_arity_control);
#else
        control = atomic_load_explicit(&frame_callback_arity_control, memory_order_relaxed);
#endif
        if (!control) {
            unsigned char expected = 0;
            control = getenv("QJS_DISABLE_CALLBACK_ARITY") ? 2 : 1;
#ifdef _MSC_VER
            if (!JS_FrameJSONCAS8((unsigned char *)&frame_callback_arity_control, &expected,
                                  control))
                control = expected;
#else
            if (!atomic_compare_exchange_strong_explicit(&frame_callback_arity_control, &expected,
                                                         control, memory_order_relaxed,
                                                         memory_order_relaxed))
                control = expected;
#endif
        }
        if (control != 1)
            goto original;
    }
    host = frame_callback_host();
    if (!host || host->kind)
        goto original;
    memcpy(&host_rt, host->state + 56, 8);
    memcpy(&used, host->state + 32, 8);
    memcpy(&committed, host->state + CALLBACK_COMMITTED, 8);
    if (host_rt != ctx->rt || used != committed)
        goto original;
    bytes = 128 + sizeof(JSValue) * ((b->arg_count > callback_argc ? b->arg_count : 0) +
                                     b->var_count + b->stack_size);
    if (bytes > 2048 || frame_callback_sp() < sizeof(JSFrameCallbackScope) + 4096 ||
        frame_callback_sp() - (sizeof(JSFrameCallbackScope) + 4096) < ctx->rt->stack_limit)
        goto original;
    return JS_FrameCallbackScopeRun(ctx, this_val, argc, argv, special, host, b, bytes,
                                    callback_argc, prepared);
original:
    return loop(ctx, this_val, argc, argv, special);
}
CALLBACK_CODE JSValue JS_FrameCallbackArrayEvery(JSContext *ctx, JSValueConst this_val, int argc,
                                                 JSValueConst *argv, int special)
{
#ifdef _MSC_VER
    return frame_callback_loop(ctx, this_val, argc, argv, special, 3, js_array_every,
                               frame_callback_array_every);
#else
    JSFrameCallbackLoop loop;
    QJS_CONTROL_SLOT_ADDR(loop, qjs_frame_core_js_array_every);
    return frame_callback_loop(ctx, this_val, argc, argv, special, 3, loop,
                               frame_callback_array_every);
#endif
}
CALLBACK_CODE JSValue JS_FrameCallbackArrayReduce(JSContext *ctx, JSValueConst this_val, int argc,
                                                  JSValueConst *argv, int special)
{
#ifdef _MSC_VER
    return frame_callback_loop(ctx, this_val, argc, argv, special, 4, js_array_reduce,
                               frame_callback_array_reduce);
#else
    JSFrameCallbackLoop loop;
    QJS_CONTROL_SLOT_ADDR(loop, qjs_frame_core_js_array_reduce);
    return frame_callback_loop(ctx, this_val, argc, argv, special, 4, loop,
                               frame_callback_array_reduce);
#endif
}
/* Private qualification probe: output stable activation/state/frame identities
 * without adding counters or writes to the timed entry. */
CALLBACK_CODE int JS_FrameCallbackScopeProbe(JSContext *ctx, uintptr_t *words)
{
    JSFrameCallbackHost *top = frame_callback_host(), *barrier;
    JSFrameCallbackScope *call;
    if (!top || top->kind)
        return 0;
    for (barrier = top->prev; barrier && !barrier->kind; barrier = barrier->prev) {}
    /* Only our published private barrier supplies a capsule. Generic barriers
     * and uninitialized release scratch words are never treated as pointers. */
    if (!barrier || barrier->kind != 4 || barrier->state != top->state)
        return 0;
    call = (JSFrameCallbackScope *)((unsigned char *)barrier - 56);
    if (call->ctx->rt != ctx->rt)
        return 0;
    if (words) {
        words[0] = (uintptr_t)call;
        words[1] = (uintptr_t)call->state;
        words[2] = (uintptr_t)call->data;
        words[3] = (uintptr_t)call->host;
        words[4] = call->segment.used;
        words[5] = (uintptr_t)call->segment.next;
    }
    return 1;
}

#endif /* inherited readonly implementation */

#if defined(QJS_CALLBACK_WRITABLE)
#ifdef _MSC_VER
#define CALLBACK_WRITE_CODE __declspec(code_seg(".qjssrc$C")) __declspec(noinline)
#define frame_callback_write_control JS_FrameCallbackWriteControl
#else
#define CALLBACK_WRITE_CODE __attribute__((section(".qjscbwr$C"), noipa))
CALLBACK_INLINE _Atomic unsigned char *frame_callback_write_control_slot(void)
{
    _Atomic unsigned char *p;
    QJS_CONTROL_SLOT_ADDR(p, JS_FrameCallbackWriteControl);
    return p;
}
#define frame_callback_write_control (*frame_callback_write_control_slot())
#endif
extern _Atomic unsigned char JS_FrameCallbackWriteControl;
extern JSValue JS_FrameCallbackArrayEvery(JSContext *, JSValueConst, int, JSValueConst *, int);
extern JSValue JS_FrameCallbackArrayReduce(JSContext *, JSValueConst, int, JSValueConst *, int);
CALLBACK_WRITE_CODE JSValue JS_FrameCallbackWriteScopeRun(JSContext *ctx, JSValueConst this_val,
                                                          int argc, JSValueConst *argv, int special,
                                                          JSFrameCallbackHost *host,
                                                          JSFunctionBytecode *b, size_t bytes,
                                                          int callback_argc,
                                                          JSFramePreparedCallbackLoop loop)
{
    _Alignas(16) JSFrameCallbackScope call;
    JSFrameCallbackHeader *frame = (JSFrameCallbackHeader *)call.data;
    JSFrameCallbackSegment *next, *following;
    JSValue result;
    unsigned window = b->arg_count;
    int i;
    call.ctx = ctx;
    call.callee = js_dup(argv[0]);
    call.bytecode = b;
    call.frame_bytes = bytes;
    call.host = host;
    call.callback_argc = callback_argc;
    call.reserved = 1;
    call.segment.next = NULL;
    call.segment.capacity = sizeof(call.data);
    call.segment.used = 0;
    call.segment.data = call.data;
    memset(call.state, 0, sizeof(call.state));
    memcpy(call.state + 56, &ctx->rt, 8);
    memcpy(call.state + CALLBACK_CALLER, &ctx, 8);
    memcpy(call.state + CALLBACK_SITES, host->state + CALLBACK_SITES, 8);
    memcpy(call.state + CALLBACK_NEXT, host->state + CALLBACK_NEXT, 8);
    call.state[CALLBACK_DIRECT] = host->state[CALLBACK_DIRECT];
    call.barrier.state = call.state;
    call.barrier.kind = 4;
    memset(frame, 0, sizeof(*frame));
    frame->sf.cur_func = call.callee;
    frame->sf.arg_buf = (JSValue *)(call.data + 128);
    frame->sf.var_buf = frame->sf.arg_buf + window;
    frame->sf.arg_count = window ? window : callback_argc;
    /* Every formal slot is owned per call. The separate ASM entry duplicates
     * the actual prefix and resets the undefined tail, then the inherited
     * Interp return/unwind consumes owned_args and releases all live values.
     * The template remains allocated until the native activation returns. */
    for (i = callback_argc; i < (int)window; i++)
        frame->sf.arg_buf[i] = JS_UNDEFINED;
    frame->sf.is_strict_mode = b->is_strict_mode;
    ((unsigned char *)&frame->sf)[62] = 1;
    frame->bytecode = b;
    frame->segment = &call.segment;
    frame->frame_bytes = bytes;
    result = loop(ctx, this_val, argc, argv, special, &call);
    for (next = call.segment.next; next; next = following) {
        following = next->next;
        js_free(ctx, next);
    }
    JS_FreeValue(ctx, call.callee);
    return result;
}
CALLBACK_INLINE JSValue frame_callback_write_loop(JSContext *ctx, JSValueConst this_val, int argc,
                                                  JSValueConst *argv, int special,
                                                  int callback_argc, JSFrameCallbackLoop loop,
                                                  JSFramePreparedCallbackLoop prepared)
{
    JSFrameCallbackHost *host;
    JSFunctionBytecode *b;
    JSObject *p;
    JSRuntime *host_rt;
    size_t bytes, used, committed;
    unsigned char control;
    if (argc < 1 || JS_VALUE_GET_TAG(argv[0]) != JS_TAG_OBJECT)
        goto original;
    p = JS_VALUE_GET_OBJ(argv[0]);
    if (p->class_id != JS_CLASS_BYTECODE_FUNCTION)
        goto original;
    b = p->u.func.function_bytecode;
    /* No validator or other observable work precedes the original loop. Cold
     * bytecode falls back and is admitted normally on its first callback. */
    if ((FRAME_KIND(b) & 7) != 1 || b->var_ref_count || frame_callback_may_have_leaf(b))
        goto original;
#ifdef _MSC_VER
    control = JS_FrameJSONLoad8((const unsigned char *)&frame_callback_control);
#else
    control = atomic_load_explicit(&frame_callback_control, memory_order_relaxed);
#endif
    if (!control) {
        unsigned char expected = 0;
        control = getenv("QJS_DISABLE_PREPARED_CALLBACK") ? 2 : 1;
#ifdef _MSC_VER
        if (!JS_FrameJSONCAS8((unsigned char *)&frame_callback_control, &expected, control))
            control = expected;
#else
        if (!atomic_compare_exchange_strong_explicit(&frame_callback_control, &expected, control,
                                                     memory_order_relaxed, memory_order_relaxed))
            control = expected;
#endif
    }
    if (control != 1)
        goto original;
    if ((FRAME_KIND(b) & 7) == 1) {
#ifdef _MSC_VER
        control = JS_FrameJSONLoad8((const unsigned char *)&frame_callback_write_control);
#else
        control = atomic_load_explicit(&frame_callback_write_control, memory_order_relaxed);
#endif
        if (!control) {
            unsigned char expected = 0;
            control = getenv("QJS_DISABLE_CALLBACK_WRITE") ? 2 : 1;
#ifdef _MSC_VER
            if (!JS_FrameJSONCAS8((unsigned char *)&frame_callback_write_control, &expected,
                                  control))
                control = expected;
#else
            if (!atomic_compare_exchange_strong_explicit(&frame_callback_write_control, &expected,
                                                         control, memory_order_relaxed,
                                                         memory_order_relaxed))
                control = expected;
#endif
        }
        if (control != 1)
            goto original;
    }
    if (b->arg_count > callback_argc) {
#ifdef _MSC_VER
        control = JS_FrameJSONLoad8((const unsigned char *)&frame_callback_arity_control);
#else
        control = atomic_load_explicit(&frame_callback_arity_control, memory_order_relaxed);
#endif
        if (!control) {
            unsigned char expected = 0;
            control = getenv("QJS_DISABLE_CALLBACK_ARITY") ? 2 : 1;
#ifdef _MSC_VER
            if (!JS_FrameJSONCAS8((unsigned char *)&frame_callback_arity_control, &expected,
                                  control))
                control = expected;
#else
            if (!atomic_compare_exchange_strong_explicit(&frame_callback_arity_control, &expected,
                                                         control, memory_order_relaxed,
                                                         memory_order_relaxed))
                control = expected;
#endif
        }
        if (control != 1)
            goto original;
    }
    host = frame_callback_host();
    if (!host || host->kind)
        goto original;
    memcpy(&host_rt, host->state + 56, 8);
    memcpy(&used, host->state + 32, 8);
    memcpy(&committed, host->state + CALLBACK_COMMITTED, 8);
    if (host_rt != ctx->rt || used != committed)
        goto original;
    bytes =
        128 + sizeof(JSValue) *
                  ((((FRAME_KIND(b) & 7) == 1 || b->arg_count > callback_argc) ? b->arg_count : 0) +
                   b->var_count + b->stack_size);
    if (bytes > 2048 || frame_callback_sp() < sizeof(JSFrameCallbackScope) + 4096 ||
        frame_callback_sp() - (sizeof(JSFrameCallbackScope) + 4096) < ctx->rt->stack_limit)
        goto original;
    return JS_FrameCallbackWriteScopeRun(ctx, this_val, argc, argv, special, host, b, bytes,
                                         callback_argc, prepared);
original:
    return loop(ctx, this_val, argc, argv, special);
}
CALLBACK_WRITE_CODE JSValue JS_FrameCallbackWriteArrayEvery(JSContext *ctx, JSValueConst this_val,
                                                            int argc, JSValueConst *argv,
                                                            int special)
{
#ifdef _MSC_VER
    return frame_callback_write_loop(ctx, this_val, argc, argv, special, 3,
                                     JS_FrameCallbackArrayEvery, frame_callback_write_array_every);
#else
    JSFrameCallbackLoop loop;
    QJS_CONTROL_SLOT_ADDR(loop, JS_FrameCallbackArrayEvery);
    return frame_callback_write_loop(ctx, this_val, argc, argv, special, 3, loop,
                                     frame_callback_write_array_every);
#endif
}
CALLBACK_WRITE_CODE JSValue JS_FrameCallbackWriteArrayReduce(JSContext *ctx, JSValueConst this_val,
                                                             int argc, JSValueConst *argv,
                                                             int special)
{
#ifdef _MSC_VER
    return frame_callback_write_loop(ctx, this_val, argc, argv, special, 4,
                                     JS_FrameCallbackArrayReduce,
                                     frame_callback_write_array_reduce);
#else
    JSFrameCallbackLoop loop;
    QJS_CONTROL_SLOT_ADDR(loop, JS_FrameCallbackArrayReduce);
    return frame_callback_write_loop(ctx, this_val, argc, argv, special, 4, loop,
                                     frame_callback_write_array_reduce);
#endif
}

#endif /* writable implementation */
