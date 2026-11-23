/* Actual-type Linux boundary for the common activation-owned callback capsule.
 * The common array/JSON/sort bodies retain their source algorithms. MIT. */
#define LINUX_CALLBACK_CODE __attribute__((section(".text.qjs_callback_entry"), noipa))
#define LINUX_CALLBACK_CONTROL __attribute__((section(".bss.qjs_callback")))
LINUX_CALLBACK_CONTROL _Atomic unsigned char JS_FrameCallbackControl;
LINUX_CALLBACK_CONTROL _Atomic unsigned char JS_FrameCallbackArityControl;
LINUX_CALLBACK_CONTROL _Atomic unsigned char JS_FrameCallbackWriteControl;
static LINUX_CALLBACK_CONTROL _Atomic unsigned char js_linux_callback_bypass;
_Static_assert(CALLBACK_STATE_BYTES == sizeof(JSFrameRegisterState) &&
                   CALLBACK_COMMITTED == offsetof(JSFrameRegisterState, committed_bytes) &&
                   CALLBACK_CALLER == offsetof(JSFrameRegisterState, caller_ctx) &&
                   CALLBACK_SITES == offsetof(JSFrameRegisterState, sites) &&
                   CALLBACK_NEXT == offsetof(JSFrameRegisterState, cache_next) &&
                   CALLBACK_DIRECT == offsetof(JSFrameRegisterState, direct_host_calls) &&
                   FRAME_HEADER_BYTES == sizeof(JSFrameCallbackHeader),
               "Common callback capsule compiled against actual Linux types");

static inline unsigned char js_linux_callback_bypass_mode(void)
{
    unsigned char mode = atomic_load_explicit(&js_linux_callback_bypass, memory_order_relaxed);
    if (!mode) {
        unsigned char expected = 0;
        mode = getenv("QJS_DISABLE_SHARED_CALL_BYPASS") ? 2 : 1;
        if (!atomic_compare_exchange_strong_explicit(&js_linux_callback_bypass, &expected, mode,
                                                     memory_order_relaxed, memory_order_relaxed))
            mode = expected;
    }
    return mode;
}

static LINUX_CALLBACK_CODE JSValue js_linux_prepared_callback(JSContext *ctx, JSValueConst func,
                                                              JSValueConst this_value,
                                                              JSValueConst new_target, int argc,
                                                              JSValueConst *argv, int flags,
                                                              void *opaque, bool writable)
{
    JSFrameCallbackScope *call = opaque;
    JSRuntime *rt = ctx->rt;
    JSFrameSharedAnchor **slot, *host;
    JSFrameRegisterState *state;
    JSFunctionBytecode *b;
    JSFrame *frame;
    JSStackFrame *sf;
    JSValue *args, *vars;
    size_t bytes;
    unsigned kind, window;
    int i;

    if (!call || call->ctx != ctx || JS_VALUE_GET_TAG(func) != JS_TAG_OBJECT ||
        JS_VALUE_GET_PTR(func) != JS_VALUE_GET_PTR(call->callee) || !JS_IsUndefined(new_target) ||
        (flags & ~JS_CALL_FLAG_COPY_ARGV) || argc != call->callback_argc ||
        js_linux_callback_bypass_mode() != 1 || !FRAME_SHARED_ACTIVE(rt) ||
        FRAME_SHARED_MODE(rt) != 1 || FRAME_STATE(rt) != 1 || FRAME_INTERNAL_STATE(rt) != 1 ||
        FRAME_REGISTER_STATE(rt) != 1)
        goto original;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(rt, JS_DUMP_BYTECODE_STEP))
        goto original;
#endif
    slot = js_frame_shared_slot();
    host = *slot;
    if (!host || host != call->host || host->kind || host->state->rt != rt ||
        host->state->used_bytes != host->state->committed_bytes)
        goto original;
    state = &call->native_state;
    b = call->bytecode;
    kind = FRAME_KIND(b) & 7;
    if (kind != (writable ? 1u : 3u) || call->reserved != (writable ? 1u : 0u) ||
        b->var_ref_count || call->segment.next || call->segment.used || state->frame ||
        ctx->interrupt_counter <= 1 || js_check_stack_overflow(rt, call->frame_bytes + 4096))
        goto original;

    /* The original caller-realm poll is preserved. A slow poll goes through
     * the original entry without publishing or reserving this capsule. */
    --ctx->interrupt_counter;
    frame = (JSFrame *)call->data;
    sf = &frame->sf;
    bytes = call->frame_bytes;
    window = (writable || b->arg_count > argc) ? b->arg_count : 0;
    args = window ? (JSValue *)(call->data + FRAME_HEADER_BYTES) : (JSValue *)argv;
    if (writable) {
        for (i = 0; i < min_int(argc, b->arg_count); ++i)
            args[i] = js_dup(argv[i]);
        for (; i < b->arg_count; ++i)
            args[i] = JS_UNDEFINED;
    } else if (window) {
        for (i = 0; i < argc; ++i)
            args[i] = unsafe_unconst(argv[i]);
        /* The readonly padding remains undefined for the entire scope. */
    }
    vars = (JSValue *)(call->data + FRAME_HEADER_BYTES) + window;
    for (i = 0; i < b->var_count; ++i)
        vars[i] = JS_UNDEFINED;
    sf->prev_frame = rt->current_stack_frame;
    sf->cur_func = call->callee;
    sf->arg_buf = args;
    sf->var_buf = vars;
    sf->var_refs = NULL;
    sf->var_ref_count = 0;
    sf->arg_count = window ? window : argc;
    sf->is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = NULL;
    sf->cur_sp = NULL;
    FRAME_ROOT(frame) = 1;
    FRAME_FLAGS(frame) = 0;
    frame->bytecode = b;
    frame->this_value = unsafe_unconst(this_value);
    frame->saved_sp = NULL;
    frame->segment = &call->segment;
    frame->frame_bytes = bytes;
    frame->owned_args = writable ? b->arg_count : 0;
    frame->pending = 0;
    call->segment.used = bytes;
    state->frame = frame;
    state->segment = &call->segment;
    state->pc = b->byte_code_buf;
    state->sp = vars + b->var_count;
    state->used_bytes = bytes;
    state->committed_bytes = bytes;
    state->result = JS_UNDEFINED;
    state->exception_pending = false;
    state->arities = 0; /* release scratch96: no active native C owner */
    state->iterator_checkpoint_depth = 0;
    js_frame_charge_stack(rt, bytes);
    state->shared_stack_limit = rt->stack_limit;
    state->native_stack_limit = rt->stack_limit ? rt->stack_limit - bytes : 0;
    rt->current_stack_frame = sf;
    call->barrier.prev = *slot;
    call->barrier.state = state;
    call->barrier.kind = 4;
    *slot = &call->barrier;
    JS_FrameInterp(state);
    if (state->used_bytes != state->committed_bytes)
        js_frame_charge_stack(rt, state->used_bytes - state->committed_bytes);
    *slot = call->barrier.prev;
    return state->result;
original:
    return JS_CallInternal(ctx, func, this_value, new_target, argc, argv, flags);
}

LINUX_CALLBACK_CODE JSValue JS_FramePreparedCallbackSelect(JSContext *ctx, JSValueConst func,
                                                           JSValueConst this_value,
                                                           JSValueConst new_target, int argc,
                                                           JSValueConst *argv, int flags,
                                                           void *scope)
{
    return js_linux_prepared_callback(ctx, func, this_value, new_target, argc, argv, flags, scope,
                                      false);
}

LINUX_CALLBACK_CODE JSValue JS_FramePreparedCallbackWriteSelect(JSContext *ctx, JSValueConst func,
                                                                JSValueConst this_value,
                                                                JSValueConst new_target, int argc,
                                                                JSValueConst *argv, int flags,
                                                                void *scope)
{
    return js_linux_prepared_callback(ctx, func, this_value, new_target, argc, argv, flags, scope,
                                      true);
}
#undef LINUX_CALLBACK_CONTROL
#undef LINUX_CALLBACK_CODE
