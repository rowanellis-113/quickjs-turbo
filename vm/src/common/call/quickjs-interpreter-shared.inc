/* Synchronous VM entry over a paused, explicitly published arena. MIT. */
#if defined(QJS_INTERP_FRAME_REGISTER_ABI) && defined(QJS_INTERP_FRAME_INTERNAL_ENTRY)
#if defined(_MSC_VER)
#define SHARED_CODE __declspec(code_seg(".qjsvm$zzs")) no_inline
#define SHARED_INLINE __forceinline
#elif defined(QJS_INTERP_FRAME_LINUX)
#define SHARED_CODE __attribute__((section(".text.qjs_frame_shared"), noipa))
#define SHARED_INLINE inline __attribute__((always_inline))
#else
#define SHARED_CODE __attribute__((section(".qjsvm$zzs"), noipa))
#define SHARED_INLINE inline __attribute__((always_inline))
#endif
#define FRAME_SHARED_BITS(rt) (((unsigned char *)(rt))[FRAME_RT_SHARED_BYTE])
#define FRAME_SHARED_MODE(rt) (FRAME_SHARED_BITS(rt) & 3)
#define FRAME_SHARED_ACTIVE(rt) (FRAME_SHARED_BITS(rt) & 4)
_Static_assert(offsetof(JSRuntime, in_free) + sizeof(bool) <= FRAME_RT_SHARED_BYTE,
               "shared entry uses only original runtime padding");
_Static_assert(offsetof(JSContext, rt) == QJS_ABI_OFF_JSContext_rt &&
                   offsetof(JSFrameRegisterState, rt) == 56,
               "shared entry leaf selector offsets");

#include "src/common/call/interpreter-shared-types.inc"

#include QJS_FRAME_SHARED_TLS_HEADER

static SHARED_INLINE bool js_frame_shared_enabled(JSRuntime *rt)
{
    if (unlikely(!FRAME_SHARED_MODE(rt))) {
        FRAME_SHARED_BITS(rt) |= getenv("QJS_DISABLE_SHARED_ENTRY") == NULL ? 1 : 2;
        if (getenv("QJS_RETAIN_SCOPED_HOST"))
            FRAME_SHARED_BITS(rt) |= 8;
    }
    return FRAME_SHARED_MODE(rt) == 1;
}

/* Existing bridge bodies retain their quota, poll, C frame and result protocol.
 * No callback can run between publication and their begin_c synchronization. */
#define SHARED_HOST(name, target)                                                                  \
    SHARED_CODE int name(JSFrameRegisterState *state, JSValue *argv, int argc, bool method)        \
    {                                                                                              \
        JSRuntime *rt = state->rt;                                                                 \
        JSFrameSharedAnchor **slot, anchor;                                                        \
        unsigned char active;                                                                      \
        int result;                                                                                \
        if (!js_frame_shared_enabled(rt))                                                          \
            return target(state, argv, argc, method);                                              \
        slot = js_frame_shared_slot();                                                             \
        anchor.prev = *slot;                                                                       \
        anchor.state = state;                                                                      \
        anchor.kind = 0;                                                                           \
        active = FRAME_SHARED_ACTIVE(rt);                                                          \
        FRAME_SHARED_BITS(rt) |= 4;                                                                \
        *slot = &anchor;                                                                           \
        result = target(state, argv, argc, method);                                                \
        *slot = anchor.prev;                                                                       \
        FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | active;                             \
        return result;                                                                             \
    }
SHARED_HOST(JS_FrameInterpHostDirectScoped, JS_FrameInterpHostDirect)
SHARED_HOST(JS_FrameInterpHostScoped, JS_FrameInterpHost)
#undef SHARED_HOST
#include "src/common/call/quickjs-interpreter-shared-host.inc"

/* A private fixture hook proves a host call is in this child entry, rather
 * than in a legacy fallback nested below an older shared VM. No timing-path
 * counters, roots or public ABI are added. Optional words identify the child
 * and paused parent frames/segments for arena containment checks. */
SHARED_CODE int JS_FrameSharedProbe(JSRuntime *rt, uintptr_t *words)
{
    JSFrameSharedAnchor *top = *js_frame_shared_slot(), *barrier;
    if (!top || top->kind || top->state->rt != rt)
        return 0;
    for (barrier = top->prev; barrier; barrier = barrier->prev) {
        if (barrier->kind && barrier->kind != 3
#if defined(QJS_INTERP_FRAME_LINUX)
            && barrier->kind != 5 /* typed sort scope is not an executing child */
#endif
        ) {
            if (barrier->state != top->state)
                return 0;
            if (words) {
                JSFrameRegisterState *parent = barrier->prev->state;
                words[0] = (uintptr_t)top->state->frame;
                words[1] = (uintptr_t)top->state->segment;
                words[2] = top->state->used_bytes;
                words[3] = (uintptr_t)parent->frame;
                words[4] = (uintptr_t)parent->segment;
                words[5] = parent->used_bytes;
            }
            return 1;
        }
    }
    return 0;
}

static SHARED_CODE JSValue js_frame_run_shared(JSContext *ctx, JSValueConst func,
                                               JSValueConst this_value, int argc,
                                               JSValueConst *argv, int flags, JSFunctionBytecode *b,
                                               JSFrameSharedAnchor *host)
{
    JSRuntime *rt = ctx->rt;
    JSFrameRegisterState state = {0};
    JSFrameSharedAnchor **slot = js_frame_shared_slot(), barrier;
    JSFrameSegment *segment = host->state->segment;
    JSFrame *frame;
    JSStackFrame *sf;
    JSValue *locals, *args, *vars, *stack;
    JSValue result;
    size_t bytes;
    int owned, i;

    /* Caller-realm interrupt poll, before any child charge/publication. */
    if (unlikely(js_poll_interrupts(ctx)))
        return JS_EXCEPTION;
    owned = ((flags & JS_CALL_FLAG_COPY_ARGV) || argc < b->arg_count || FRAME_CAPTURED_ARGS(b))
                ? b->arg_count
                : 0;
    bytes = FRAME_HEADER_BYTES + sizeof(JSValue) * (owned + b->var_count + b->stack_size) +
            FRAME_CAPTURE_BYTES(b);
    state.rt = rt;
    barrier.prev = *slot;
    barrier.state = &state;
    barrier.kind = 1;
    *slot = &barrier;
    /* Finalizers/slow helpers cannot borrow a cursor while this VM executes.
     * Only its own scoped host boundaries may publish a coherent child state. */
    if (unlikely(js_check_stack_overflow(rt, bytes + 4096))) {
        result = JS_ThrowStackOverflow(ctx);
        goto done;
    }
    if (unlikely(bytes > segment->capacity - segment->used)) {
        segment = js_frame_grow(ctx, segment, bytes);
        if (!segment) {
            result = JS_EXCEPTION;
            goto done;
        }
    }
    frame = (JSFrame *)(segment->data + segment->used);
    frame->segment = segment;
    frame->frame_bytes = bytes;
    segment->used += bytes;
    js_frame_charge_stack(rt, bytes);
    frame->bytecode = b;
    frame->this_value = unsafe_unconst(this_value);
    frame->owned_args = owned;
    frame->pending = 0;
    locals = (JSValue *)((uint8_t *)frame + FRAME_HEADER_BYTES);
    args = (JSValue *)argv;
    if (owned) {
        args = locals;
        for (i = 0; i < min_int(argc, b->arg_count); i++)
            args[i] = js_dup(argv[i]);
        for (; i < b->arg_count; i++)
            args[i] = JS_UNDEFINED;
    }
    vars = locals + owned;
    for (i = 0; i < b->var_count; i++)
        vars[i] = JS_UNDEFINED;
    stack = vars + b->var_count;
    sf = &frame->sf;
    sf->prev_frame = rt->current_stack_frame;
    sf->cur_func = unsafe_unconst(func);
    sf->arg_buf = args;
    sf->var_buf = vars;
    sf->var_refs = b->var_ref_count ? (JSVarRef **)(stack + b->stack_size) : NULL;
    sf->var_ref_count = b->var_ref_count;
    for (i = 0; i < sf->var_ref_count; i++)
        sf->var_refs[i] = NULL;
    sf->arg_count = owned ? b->arg_count : max_int(argc, b->arg_count);
    sf->is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = NULL;
    sf->cur_sp = NULL;
    FRAME_FLAGS(frame) = 0;
    FRAME_ROOT(frame) = 1;
    rt->current_stack_frame = sf;
    state.frame = frame;
    state.segment = segment;
    state.pc = b->byte_code_buf;
    state.sp = stack;
    state.used_bytes = bytes;
    state.committed_bytes = bytes;
    state.shared_stack_limit = rt->stack_limit;
    state.native_stack_limit = rt->stack_limit ? rt->stack_limit - bytes : 0;
    state.result = JS_UNDEFINED;
    state.caller_ctx = ctx;
    state.sites = host->state->sites;
    state.cache_next = host->state->cache_next;
    state.direct_host_calls = host->state->direct_host_calls;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state.pushes = 1;
    state.depth = state.max_depth = 1;
    state.peak_bytes = bytes;
#endif
    JS_FrameInterp(&state);
    if (state.used_bytes != state.committed_bytes)
        js_frame_charge_stack(rt, state.used_bytes - state.committed_bytes);
    result = state.result;
    /* Native/slow root pop restores its own cursor/SF and detaches captures.
     * Grown nonmoving segments remain linked to the owning outer activation. */
done:
    *slot = barrier.prev;
    return result;
}

#include "src/common/call/fast-root-leaf.inc"

SHARED_CODE JSValue JS_FrameCallEntryShared(JSContext *ctx, JSValueConst func,
                                            JSValueConst this_value, JSValueConst new_target,
                                            int argc, JSValueConst *argv, int flags)
{
    JSFrameSharedAnchor *host = *js_frame_shared_slot();
    JSFunctionBytecode *b;
#ifndef QJS_AARCH64_VM_INSTRUMENT
    if (JS_IsUndefined(new_target) && (flags == 0 || flags == JS_CALL_FLAG_COPY_ARGV)) {
        JSValue leaf_res;
        if (js_try_fast_borrowed_leaf(ctx, func, this_value, argc, argv, &leaf_res))
            return leaf_res;
    }
#endif
    if (host && !host->kind && host->state->rt == ctx->rt && FRAME_SHARED_MODE(ctx->rt) == 1 &&
        FRAME_STATE(ctx->rt) == 1 && FRAME_REGISTER_STATE(ctx->rt) == 1 &&
        (flags == 0 || flags == JS_CALL_FLAG_COPY_ARGV)
#ifdef ENABLE_DUMPS
        && !check_dump_flag(ctx->rt, JS_DUMP_BYTECODE_STEP)
#endif
        && (b = js_frame_target(func))) {
        /* Check before reserving the child boundary record (larger in the
         * diagnostic build), including space for its subsequent C helpers. */
        if (unlikely(js_check_stack_overflow(ctx->rt, 4096)))
            return JS_ThrowStackOverflow(ctx);
        return js_frame_run_shared(ctx, func, this_value, argc, argv, flags, b, host);
    }
    return js_frame_call_entry(ctx, func, this_value, new_target, argc, argv, flags);
}
#include QJS_FRAME_SHARED_SUPPLEMENTS_HEADER
#undef SHARED_CODE
#undef SHARED_INLINE
#else
#define JS_FrameCallEntryDispatch js_frame_call_entry
#endif
