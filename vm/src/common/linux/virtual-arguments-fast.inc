/* Fast virtual-arguments step with 8-entry O(1) method/shape/epoch cache. MIT. */
#ifdef QJS_DEFINE_ARGUMENTS_CONSTRUCT_FAST_OK
__attribute__((visibility("hidden"))) int JS_FrameArgumentsConstructFastOk(void)
{
    return atomic_load_explicit(&JS_FrameArgumentsMode, memory_order_relaxed) == 1 &&
           js_linux_arguments_constructor_enabled();
}
#else
__attribute__((section(".data.qjs_linux_arguments"),
               aligned(8))) _Atomic uint64_t JS_LinuxVirtualArgumentsStats[2];

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

_Static_assert(sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame && FRAME_FORWARD_BYTES == 80 &&
                   FRAME_ROOT_OFFSET == 62 && FRAME_FLAGS_OFFSET == 63,
               "virtual arguments uses the qualified logical frame ABI");

static FRAME_CODE int js_linux_virtual_arguments_step(JSFrameRegisterState *state)
{
    JSFrame *parent = state->frame;
    JSFunctionBytecode *caller = parent->bytecode;
    JSContext *ctx = caller->realm;
    JSRuntime *rt = ctx->rt;
    uint8_t *p = caller->byte_code_buf;
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
    if (!JS_IsObject(receiver))
        return 0;
    JSObject *recv_obj = JS_VALUE_GET_OBJ(receiver);
    JSObject *function = NULL, *apply = NULL;
    JSFunctionBytecode *b = NULL;
    static struct {
        JSFunctionBytecode *caller;
        JSContext *ctx;
        JSShape *recv_shape;
        JSObject *proto;
        uint32_t method_slot;
        uint64_t epoch;
        JSObject *function;
        JSObject *apply;
        JSFunctionBytecode *callee_b;
    } va_cache[8];
    uint32_t va_slot =
        (((uint32_t)((uintptr_t)caller >> 4)) ^ ((uint32_t)((uintptr_t)recv_obj->shape >> 4))) & 7u;
    if (!recv_obj->is_exotic && va_cache[va_slot].caller == caller &&
        va_cache[va_slot].ctx == ctx && va_cache[va_slot].recv_shape == recv_obj->shape &&
        va_cache[va_slot].epoch != 0 && va_cache[va_slot].epoch == rt->property_ic_epoch &&
        recv_obj->shape->proto == va_cache[va_slot].proto) {
        JSValue pv = va_cache[va_slot].proto->prop[va_cache[va_slot].method_slot].u.value;
        if (JS_IsObject(pv) && JS_VALUE_GET_OBJ(pv) == va_cache[va_slot].function) {
            func = pv;
            function = va_cache[va_slot].function;
            apply = va_cache[va_slot].apply;
            callee = JS_MKPTR(JS_TAG_OBJECT, apply);
            b = va_cache[va_slot].callee_b;
            goto va_cached_hit;
        }
    }
    if (!js_linux_virtual_arguments_data(recv_obj, get_u32(p + 7), &func) || !JS_IsObject(func))
        return 0;
    function = JS_VALUE_GET_OBJ(func);
    if (function->class_id != JS_CLASS_BYTECODE_FUNCTION ||
        !js_linux_virtual_arguments_data(function, JS_ATOM_apply, &callee) || !JS_IsObject(callee))
        return 0;
    apply = JS_VALUE_GET_OBJ(callee);
    if (apply->class_id != JS_CLASS_C_FUNCTION || apply->u.cfunc.cproto != JS_CFUNC_generic_magic ||
        apply->u.cfunc.magic != 0 || apply->u.cfunc.length != 2 || apply->u.cfunc.realm != ctx ||
        apply->u.cfunc.c_function.generic_magic != js_function_apply)
        return 0;
    b = function->u.func.function_bytecode;
    if (b->realm != ctx || !FRAME_SUPPORTED(b) || b->func_kind != JS_FUNC_NORMAL ||
        b->is_derived_class_constructor || b->arg_count > 128 || b->var_count > 128 ||
        b->stack_size > 256)
        return 0;
    if (!recv_obj->is_exotic && rt->property_ic_epoch && recv_obj->shape->proto &&
        !recv_obj->shape->proto->is_exotic) {
        JSProperty *own_r, *proto_m, *own_f;
        if (!find_own_property(&own_r, recv_obj, get_u32(p + 7)) &&
            !find_own_property(&own_f, function, JS_ATOM_apply)) {
            JSShapeProperty *pm =
                find_own_property(&proto_m, recv_obj->shape->proto, get_u32(p + 7));
            if (pm && (pm->flags & JS_PROP_TMASK) == JS_PROP_NORMAL) {
                va_cache[va_slot].caller = caller;
                va_cache[va_slot].ctx = ctx;
                va_cache[va_slot].recv_shape = recv_obj->shape;
                va_cache[va_slot].proto = recv_obj->shape->proto;
                va_cache[va_slot].method_slot = (uint32_t)(proto_m - recv_obj->shape->proto->prop);
                va_cache[va_slot].epoch = rt->property_ic_epoch;
                va_cache[va_slot].function = function;
                va_cache[va_slot].apply = apply;
                va_cache[va_slot].callee_b = b;
            }
        }
    }
va_cached_hit: {
    unsigned length = original->argc, capacity = max_int(length, b->arg_count);
    size_t regular = FRAME_HEADER_BYTES + sizeof(JSFrameArgumentsRecord) +
                     sizeof(JSValue) * (capacity + b->var_count + b->stack_size) +
                     FRAME_CAPTURE_BYTES(b);
    size_t need = regular + FRAME_FORWARD_BYTES;
    if (need > state->segment->capacity - state->segment->used)
        return 0;
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
    ctx->interrupt_counter--;
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
}

__attribute__((visibility("hidden"))) int JS_LinuxVirtualArgumentsFastOk(void)
{
    return atomic_load_explicit(&JS_FrameArgumentsMode, memory_order_relaxed) == 1 &&
           js_linux_virtual_arguments_enabled();
}
#endif
