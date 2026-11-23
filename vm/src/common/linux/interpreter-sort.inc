/* Real-type SysV consumers for accepted cached/prepared sort capsules. MIT.
 * The private kind5 barrier proves the enclosing stack capsule before a cast.
 * A coherent kind0 shadow keeps ordinary reentrant calls on the existing host.
 * No TLS variable, public field or guessed pointer tag is introduced. */
typedef struct JSFrameLinuxSortScope {
    JSFrameSharedAnchor barrier;
    JSFrameSharedAnchor shadow;
    JSFrameCachedSort *cache;
    JSFramePreparedSort *prepared;
} JSFrameLinuxSortScope;
_Static_assert(SORT_PREP_STATE_BYTES == sizeof(JSFrameRegisterState) &&
                   SORT_CACHE_OWNER == offsetof(JSFrameRegisterState, arities) &&
                   SORT_CACHE_COMMITTED == offsetof(JSFrameRegisterState, committed_bytes) &&
                   SORT_PREP_CALLER == offsetof(JSFrameRegisterState, caller_ctx) &&
                   SORT_PREP_SITES == offsetof(JSFrameRegisterState, sites) &&
                   SORT_PREP_NEXT == offsetof(JSFrameRegisterState, cache_next) &&
                   SORT_PREP_DIRECT == offsetof(JSFrameRegisterState, direct_host_calls),
               "Sort capsule uses the actual Linux state contract");

static NATIVE_SORT_CODE JSValue js_linux_sort_loop(JSContext *ctx, JSValueConst self, int argc,
                                                   JSValueConst *argv, JSFrameCachedSort *cache,
                                                   JSFramePreparedSort *prepared,
                                                   JSFrameCachedHost *host)
{
    JSFrameSharedAnchor **slot = js_frame_shared_slot();
    JSFrameLinuxSortScope scope;
    JSValue result;
    scope.barrier.prev = *slot;
    scope.barrier.state = host->state;
    scope.barrier.kind = 5;
    scope.shadow.prev = &scope.barrier;
    scope.shadow.state = host->state;
    scope.shadow.kind = 0;
    scope.cache = cache;
    scope.prepared = prepared;
    *slot = &scope.shadow;
    result = js_array_sort(ctx, self, argc, argv);
    *slot = scope.barrier.prev;
    return result;
}

NATIVE_SORT_CODE JSValue JS_FramePreparedSortInvoke(JSFramePreparedSort *call, JSValueConst *argv,
                                                    JSFrameCachedHost *host)
{
    JSContext *ctx = call->cache.ctx;
    JSRuntime *rt = ctx->rt;
    JSFrameSharedAnchor **slot = js_frame_shared_slot();
    JSFrameRegisterState *state = &call->native_state;
    JSFunctionBytecode *b = call->cache.bytecode;
    JSFrame *frame;
    JSStackFrame *sf;
    JSValue *vars;
    size_t bytes = call->cache.frame_bytes;
    uintptr_t owner;
    memcpy(&owner, &host->state->arities, sizeof(owner));
    if (*slot != host || host->kind || host->state->rt != rt ||
        host->state->used_bytes != host->state->committed_bytes || owner != ((uintptr_t)call | 3) ||
        call->segment.next || call->segment.used || state->frame || FRAME_SHARED_MODE(rt) != 1 ||
        !FRAME_SHARED_ACTIVE(rt) || FRAME_STATE(rt) != 1 || FRAME_INTERNAL_STATE(rt) != 1 ||
        FRAME_REGISTER_STATE(rt) != 1 || js_linux_callback_bypass_mode() != 1 ||
        (FRAME_KIND(b) & 7) != 3 || b->var_ref_count || b->arg_count > 2 ||
        ctx->interrupt_counter <= 1 || js_check_stack_overflow(rt, bytes + 4096))
        goto original;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(rt, JS_DUMP_BYTECODE_STEP))
        goto original;
#endif
    --ctx->interrupt_counter;
    frame = (JSFrame *)call->data;
    sf = &frame->sf;
    vars = (JSValue *)(call->data + FRAME_HEADER_BYTES);
    for (int i = 0; i < b->var_count; ++i)
        vars[i] = JS_UNDEFINED;
    sf->prev_frame = rt->current_stack_frame;
    sf->cur_func = call->cache.callee;
    sf->arg_buf = (JSValue *)argv;
    sf->var_buf = vars;
    sf->var_refs = NULL;
    sf->var_ref_count = 0;
    sf->arg_count = 2;
    sf->is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = NULL;
    sf->cur_sp = NULL;
    FRAME_ROOT(frame) = 1;
    FRAME_FLAGS(frame) = 0;
    frame->bytecode = b;
    frame->this_value = JS_UNDEFINED;
    frame->saved_sp = NULL;
    frame->segment = &call->segment;
    frame->frame_bytes = bytes;
    frame->owned_args = 0;
    frame->pending = 0;
    call->segment.used = bytes;
    state->frame = frame;
    state->segment = &call->segment;
    state->pc = b->byte_code_buf;
    state->sp = vars + b->var_count;
    state->used_bytes = state->committed_bytes = bytes;
    state->result = JS_UNDEFINED;
    state->exception_pending = false;
    state->arities = 0;
    state->iterator_checkpoint_depth = 0;
    js_frame_charge_stack(rt, bytes);
    state->shared_stack_limit = rt->stack_limit;
    state->native_stack_limit = rt->stack_limit ? rt->stack_limit - bytes : 0;
    rt->current_stack_frame = sf;
    call->barrier.prev = *slot;
    call->barrier.state = state;
    call->barrier.kind = 6; /* private, typed Linux sort capsule */
    *slot = &call->barrier;
    JS_FrameInterp(state);
    if (state->used_bytes != state->committed_bytes)
        js_frame_charge_stack(rt, state->used_bytes - state->committed_bytes);
    *slot = call->barrier.prev;
    return state->result;
original:
    return JS_Call(ctx, call->cache.callee, JS_UNDEFINED, 2, argv);
}

NATIVE_SORT_CODE JSValue JS_FrameLinuxSortCall(JSContext *ctx, JSValueConst callee,
                                               JSValueConst self, int argc, JSValueConst *argv)
{
    JSFrameSharedAnchor *top = *js_frame_shared_slot();
    JSFrameLinuxSortScope *scope;
    JSFrameCachedSort *cache;
    JSFunctionBytecode *b;
    JSRuntime *rt = ctx->rt;
    if (!top || top->kind || !top->prev || top->prev->kind != 5 || top->state != top->prev->state ||
        top->state->rt != rt || top->state->used_bytes != top->state->committed_bytes ||
        argc != 2 || !JS_IsUndefined(self))
        goto original;
    scope = (JSFrameLinuxSortScope *)top->prev;
    cache = scope->cache;
    if (cache->ctx != ctx || JS_VALUE_GET_TAG(callee) != JS_TAG_OBJECT ||
        JS_VALUE_GET_PTR(callee) != JS_VALUE_GET_PTR(cache->callee) || FRAME_SHARED_MODE(rt) != 1 ||
        !FRAME_SHARED_ACTIVE(rt) || FRAME_STATE(rt) != 1 || FRAME_INTERNAL_STATE(rt) != 1 ||
        FRAME_REGISTER_STATE(rt) != 1 || js_linux_callback_bypass_mode() != 1)
        goto original;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(rt, JS_DUMP_BYTECODE_STEP))
        goto original;
#endif
    b = cache->bytecode;
    if ((FRAME_KIND(b) & 7) != 3 || b->var_ref_count || b->arg_count > 2)
        goto original;
    if (scope->prepared)
        return JS_FramePreparedSortInvoke(scope->prepared, argv, top);
    /* The cached-only control retains normal child allocation, root/poll and
     * quota construction while reusing immutable validated target metadata. */
    return JS_FrameLinuxCachedSortInvoke(ctx, callee, self, argc, argv, 0, b, top,
                                         cache->frame_bytes);
original:
    return JS_Call(ctx, callee, self, argc, argv);
}

/* Read-only qualification hook. Only our private kind6 barrier proves the
 * stack container; ordinary native children must never be cast as a capsule. */
NATIVE_SORT_CODE int JS_FrameLinuxPreparedSortProbe(JSContext *ctx, uintptr_t *words)
{
    JSFrameSharedAnchor *top = *js_frame_shared_slot(), *barrier;
    JSFramePreparedSort *call;
    if (!top || top->kind || top->state->rt != ctx->rt)
        return 0;
    for (barrier = top->prev; barrier && (!barrier->kind || barrier->kind == 3);
         barrier = barrier->prev) {}
    if (!barrier || barrier->kind != 6 || barrier->state != top->state)
        return 0;
    call =
        (JSFramePreparedSort *)((unsigned char *)barrier - offsetof(JSFramePreparedSort, barrier));
    if (call->cache.ctx->rt != ctx->rt || &call->native_state != top->state ||
        !call->native_state.frame || call->native_state.segment != &call->segment)
        return 0;
    if (words) {
        words[0] = (uintptr_t)call;
        words[1] = (uintptr_t)&call->native_state;
        words[2] = (uintptr_t)call->data;
        words[3] = (uintptr_t)call->native_state.frame;
        words[4] = call->segment.used;
        words[5] = (uintptr_t)call->segment.next;
    }
    return 1;
}
