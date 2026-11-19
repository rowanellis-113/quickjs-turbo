/* Exact nonescaping forwarding-constructor scalar replacement. MIT.
 * Only constructor function(){this.<data-method>.apply(this,arguments);} with no formals,
 * captures or other operations is admitted. All descriptor reads are pure.
 * The parent prefix roots every actual argument; its inaccessible local1
 * stays undefined. The native apply stack-frame identity is retained; its
 * unobservable list slot is undefined because no arguments object exists.
 */
__attribute__((section(".data.qjs_linux_arguments"),
               aligned(8))) _Atomic uint64_t JS_LinuxVirtualArgumentsStats[2];

/* Keep the inherited arguments_mode body and masks unchanged. New controls
 * are read only after the exact wrapper proof, in this independent policy. */
__attribute__((section(".data.qjs_linux_arguments"),
               aligned(4))) static _Atomic(unsigned) js_linux_virtual_arguments_policy;

static FRAME_CODE bool js_linux_virtual_arguments_enabled(void)
{
    unsigned mode = atomic_load_explicit(&js_linux_virtual_arguments_policy, memory_order_relaxed);
    if (!mode) {
        mode =
            (getenv("QJS_DISABLE_VIRTUAL_ARGUMENTS") || getenv("QJS_DISABLE_FRAME_APPLY_DIRECT") ||
             getenv("QJS_DISABLE_FRAME_CALL_FORWARD"))
                ? 2
                : 1;
        atomic_store_explicit(&js_linux_virtual_arguments_policy, mode, memory_order_relaxed);
    }
    return mode == 1;
}

static FRAME_CODE bool js_linux_virtual_arguments_data(JSObject *object, JSAtom atom, JSValue *out)
{
    for (unsigned depth = 0; object && depth < 16; depth++, object = object->shape->proto) {
        if (object->is_exotic)
            return false;
        JSProperty *p;
        JSShapeProperty *s = find_own_property(&p, object, atom);
        if (s) {
            if ((s->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
                return false;
            *out = p->u.value;
            return true;
        }
    }
    return false;
}

/* The measured SysV SF is72 bytes; the existing logical reservation is80. */
_Static_assert(sizeof(JSStackFrame) == 72 && FRAME_FORWARD_BYTES == 80 && FRAME_ROOT_OFFSET == 62 &&
                   FRAME_FLAGS_OFFSET == 63,
               "virtual arguments uses the qualified logical frame ABI");

/* 0 means unchanged decline; 1 child entered; -1 original exception pending. */
static FRAME_CODE int js_linux_virtual_arguments_step(JSFrameRegisterState *state)
{
    JSFrame *parent = state->frame;
    JSFunctionBytecode *caller = parent->bytecode;
    JSContext *ctx = caller->realm;
    JSRuntime *rt = ctx->rt;
    uint8_t *p = caller->byte_code_buf;
    /* Keep actuals owned by the suspended constructor caller. This also
     * preserves last-release ordering: no owned-argument cleanup is moved
     * ahead of the eliminated local arguments object. Public COPY roots
     * and all ordinary forwarding calls retain the original path. */
    if (FRAME_ROOT(parent) != 3 || parent->owned_args || FRAME_KIND(caller) != ARGUMENTS_KIND ||
        ARGUMENTS_MARKER(caller) != ARGUMENTS_READY || caller->byte_code_len != 21 ||
        caller->arg_count || caller->var_count != 2 || caller->var_ref_count ||
        caller->stack_size != 4 || state->pc != p + 2 || p[0] != OP_push_this ||
        p[1] != OP_put_loc0 || p[2] != OP_special_object ||
        (p[3] != OP_SPECIAL_OBJECT_ARGUMENTS && p[3] != OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS) ||
        p[4] != OP_put_loc1 || p[5] != OP_get_loc0 || p[6] != OP_get_field ||
        p[11] != OP_get_field2 || get_u32(p + 12) != JS_ATOM_apply || p[16] != OP_get_loc0_loc1 ||
        p[17] != OP_call_method || get_u16(p + 18) != 2 || p[20] != OP_return_undef ||
        rt->interrupt_handler || ctx->interrupt_counter <= 2)
        return 0;
    unsigned mode = arguments_mode();
    if ((mode & ~4u) != 1 || !js_linux_virtual_arguments_enabled())
        return 0;
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_LinuxVirtualArgumentsStats[0], 1, memory_order_relaxed);
    JSFrameArgumentsRecord *original = (void *)((uint8_t *)parent + FRAME_HEADER_BYTES);
    if (original->signature != ARGUMENTS_SIGNATURE || original->argc > 32765 ||
        original->argv != vc(parent->sf.arg_buf) || state->sp != parent->sf.var_buf + 2 ||
        !JS_IsUndefined(parent->sf.var_buf[1]))
        return 0;
    JSValue receiver = parent->sf.var_buf[0], func, callee;
    if (!JS_IsObject(receiver) ||
        !js_linux_virtual_arguments_data(JS_VALUE_GET_OBJ(receiver), get_u32(p + 7), &func) ||
        !JS_IsObject(func))
        return 0;
    JSObject *function = JS_VALUE_GET_OBJ(func);
    if (function->class_id != JS_CLASS_BYTECODE_FUNCTION ||
        !js_linux_virtual_arguments_data(function, JS_ATOM_apply, &callee) || !JS_IsObject(callee))
        return 0;
    JSObject *apply = JS_VALUE_GET_OBJ(callee);
    if (apply->class_id != JS_CLASS_C_FUNCTION || apply->u.cfunc.cproto != JS_CFUNC_generic_magic ||
        apply->u.cfunc.magic != 0 || apply->u.cfunc.length != 2 || apply->u.cfunc.realm != ctx ||
        apply->u.cfunc.c_function.generic_magic != js_function_apply)
        return 0;
    JSFunctionBytecode *b = function->u.func.function_bytecode;
    if (b->realm != ctx || !FRAME_SUPPORTED(b) || b->func_kind != JS_FUNC_NORMAL ||
        b->is_derived_class_constructor || b->arg_count > 128 || b->var_count > 128 ||
        b->stack_size > 256)
        return 0;
    unsigned length = original->argc, capacity = max_int(length, b->arg_count);
    size_t regular = FRAME_HEADER_BYTES + sizeof(JSFrameArgumentsRecord) +
                     sizeof(JSValue) * (capacity + b->var_count + b->stack_size) +
                     FRAME_CAPTURE_BYTES(b);
    size_t need = regular + FRAME_FORWARD_BYTES;
    /* Do not grow or allocate before the caller and synthetic native apply
     * frame are complete. Existing cached-segment logic can be added only
     * after a separate ownership proof; this prototype declines it. */
    if (need > state->segment->capacity - state->segment->used)
        return 0;
    /* The pure-JS budget may be deferred. Publish it before checking the
     * complete child plus logical native frame, including on a decline. */
    js_frame_begin_c(state);
    if (js_check_stack_overflow(rt, need + 8192)) {
        js_frame_finish_c(state);
        return 0;
    }
    JSValue *sp = state->sp;
    sp[0] = js_dup(func);
    sp[1] = js_dup(callee);
    sp[2] = js_dup(receiver);
    sp[3] = JS_UNDEFINED;
    state->sp = sp + 4;
    state->pc = p + 17;
    parent->saved_sp = sp + 4;
    parent->sf.cur_pc = p + 20;
    parent->sf.cur_sp = sp + 4;
    parent->pending = 4;
    ctx->interrupt_counter--; /* original intrinsic apply entry */
    if (!js_frame_arguments_push(state, func, receiver, b, length, vc(parent->sf.arg_buf),
                                 JS_CALL_FLAG_COPY_ARGV, false)) {
        state->pc = p + 20;
        state->sp = sp + 4;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return -1;
    }
    JSFrame *child = state->frame;
    JSFrameArgumentsRecord *record = (void *)((uint8_t *)child + FRAME_HEADER_BYTES);
    record->argv = vc(child->sf.arg_buf);
    JSStackFrame *logical = (void *)((uint8_t *)child + regular);
    logical->prev_frame = &parent->sf;
    logical->cur_func = sp[1];
    logical->arg_buf = sp + 2;
    logical->arg_count = 2;
    logical->var_buf = NULL;
    logical->var_refs = NULL;
    logical->var_ref_count = 0;
    logical->is_strict_mode = false;
    FRAME_CLEAR_STACK_AUX(logical);
    logical->cur_pc = NULL;
    logical->cur_sp = NULL;
    ((unsigned char *)logical)[62] = 0;
    ((unsigned char *)logical)[63] = FRAME_FORWARD_TAG;
    child->sf.prev_frame = logical;
    FRAME_ROOT(child) = 2;
    state->segment->used += FRAME_FORWARD_BYTES;
    state->used_bytes += FRAME_FORWARD_BYTES;
    js_frame_charge_stack(rt, FRAME_FORWARD_BYTES);
    ctx->interrupt_counter--;
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_LinuxVirtualArgumentsStats[1], 1, memory_order_relaxed);
    js_frame_finish_c(state);
    return 1;
}
