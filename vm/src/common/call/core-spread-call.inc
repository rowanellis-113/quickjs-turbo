/* Fuse one ordinary call's already-evaluated prefix and dense-array spread.
 * No opcode/serialized input/frame layout changes. No VM allocation or JS
 * runs between the live protocol proof and the owned argument snapshot.
 */
static int check_function(JSContext *ctx, JSValueConst obj);
#define CORE_SPREAD_ARGV_CAP 16u /* Fixed, bounded C scratch; larger calls fall back. */
#if defined(_MSC_VER)
#define CORE_SPREAD_CODE __declspec(noinline)
#elif defined(__GNUC__) && !defined(__clang__) && __GNUC__ >= 9
#define CORE_SPREAD_CODE __attribute__((noipa))
#elif defined(__GNUC__) || defined(__clang__)
#define CORE_SPREAD_CODE __attribute__((noinline))
#else
#define CORE_SPREAD_CODE
#endif

#ifdef CONFIG_ATOMICS
static _Atomic unsigned char js_core_spread_mode;
static inline bool js_core_spread_enabled(void)
{
    unsigned char mode = atomic_load_explicit(&js_core_spread_mode, memory_order_relaxed);
    if (!mode) {
        mode = getenv("QJS_DISABLE_CORE_SPREAD_CALL") ? 2 : 1;
        atomic_store_explicit(&js_core_spread_mode, mode, memory_order_relaxed);
    }
    return mode == 1;
}
#else
static inline bool js_core_spread_enabled(void)
{
    return getenv("QJS_DISABLE_CORE_SPREAD_CALL") == NULL;
}
#endif

static bool js_core_spread_data(JSObject *p, JSAtom atom, JSValue *value)
{
    for (unsigned depth = 0; p && depth < 32; depth++, p = p->shape->proto) {
        JSProperty *property;
        JSShapeProperty *shape;
        if (p->class_id != JS_CLASS_OBJECT && p->class_id != JS_CLASS_ARRAY)
            return false;
        if (p->is_exotic && p->class_id != JS_CLASS_ARRAY)
            return false;
        shape = find_own_property(&property, p, atom);
        if (shape) {
            if (shape->flags & JS_PROP_TMASK)
                return false;
            *value = property->u.value;
            return true;
        }
    }
    return false;
}

static bool js_core_spread_dense(JSContext *ctx, JSValueConst value, JSObject **array_out)
{
    JSObject *array, *function;
    JSShapeProperty *first;
    JSContext *iterator_realm;
    JSValue method, next, length;
    JSCFunctionType create = {.generic_magic = js_create_array_iterator};
    JSCFunctionType advance = {.iterator_next = js_array_iterator_next};
    if (!JS_IsObject(value))
        return false;
    array = JS_VALUE_GET_OBJ(value);
    if (array->class_id != JS_CLASS_ARRAY || !array->fast_array || array->shape->prop_count < 1)
        return false;
    first = array->shape->prop;
    if (first->atom != JS_ATOM_length || (first->flags & JS_PROP_TMASK) ||
        !(first->flags & JS_PROP_LENGTH))
        return false;
    length = array->prop[0].u.value;
    if (JS_VALUE_GET_TAG(length) != JS_TAG_INT || JS_VALUE_GET_INT(length) < 0 ||
        (uint32_t)JS_VALUE_GET_INT(length) != array->u.array.count)
        return false; /* Holes may require observable prototype reads. */
    if (!js_core_spread_data(array, JS_ATOM_Symbol_iterator, &method) ||
        !JS_IsCFunction(ctx, method, create.generic, JS_ITERATOR_KIND_VALUE))
        return false;
    function = JS_VALUE_GET_OBJ(method);
    if (function->u.cfunc.cproto != JS_CFUNC_generic_magic)
        return false;
    iterator_realm = function->u.cfunc.realm;
    if (!JS_IsObject(iterator_realm->class_proto[JS_CLASS_ARRAY_ITERATOR]) ||
        !js_core_spread_data(JS_VALUE_GET_OBJ(iterator_realm->class_proto[JS_CLASS_ARRAY_ITERATOR]),
                             JS_ATOM_next, &next) ||
        !JS_IsCFunction(ctx, next, advance.generic, 0) ||
        JS_VALUE_GET_OBJ(next)->u.cfunc.cproto != JS_CFUNC_iterator_next)
        return false;
    *array_out = array;
    return true;
}

/* pc points at array_from's u16 immediate. Zero declines without changing
 * operand owners/SP/PC/interrupts; positive skip commits a result on the
 * existing stack, negative status commits complete call-operand cleanup and
 * lets the original exception loop unwind the remaining caller stack.
 * abs(status) low8 bits are PC skip;remaining bits are caller SP drop.
 * The exact preexisting normal C cursor is restored before returning.
 */
static CORE_SPREAD_CODE int js_core_spread_call(JSContext *ctx, JSFunctionBytecode *b,
                                                JSStackFrame *sf, const uint8_t *pc, JSValue *sp)
{
    const uint8_t *start = pc, *end = b->byte_code_buf + b->byte_code_len;
    JSValue source, callee, receiver, result;
    JSValue args[CORE_SPREAD_ARGV_CAP];
    JSValue *stack_begin = sf->var_buf + b->var_count, *base;
    JSValue *saved_cursor = sf->cur_sp;
    char stack_marker;
    char *volatile stack_address = &stack_marker;
    JSObject *array;
    unsigned prefix, index, op, method, count, i;
    int skip;
    if (!js_core_spread_enabled() || b->func_kind != JS_FUNC_NORMAL || end - pc < 3 ||
        (uintptr_t)stack_address - 1024 < ctx->rt->stack_limit)
        return 0;
    prefix = get_u16(pc);
    if (prefix > CORE_SPREAD_ARGV_CAP)
        return 0;
    pc += 2;
    if (*pc >= OP_push_0 && *pc <= OP_push_7) {
        if ((unsigned)(*pc - OP_push_0) != prefix)
            return 0;
        pc++;
    } else if (end - pc >= 2 && *pc == OP_push_i8) {
        if ((int8_t)pc[1] != (int)prefix)
            return 0;
        pc += 2;
    } else if (end - pc >= 3 && *pc == OP_push_i16) {
        if ((int16_t)get_u16(pc + 1) != (int)prefix)
            return 0;
        pc += 3;
    } else if (end - pc >= 5 && *pc == OP_push_i32 && get_u32(pc + 1) == prefix)
        pc += 5;
    else
        return 0;
    if (pc == end)
        return 0;
    op = *pc++;
    if (op >= OP_get_loc0 && op <= OP_get_loc3) {
        index = op - OP_get_loc0;
        if (index >= b->var_count)
            return 0;
        source = sf->var_buf[index];
    } else if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        index = op - OP_get_arg0;
        if (index >= b->arg_count)
            return 0;
        source = sf->arg_buf[index];
    } else if (op >= OP_get_var_ref0 && op <= OP_get_var_ref3) {
        index = op - OP_get_var_ref0;
        if (index >= b->closure_var_count)
            return 0;
        source = *JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs[index]->pvalue;
    } else if (op == OP_get_loc8) {
        if (pc == end || (index = *pc++) >= b->var_count)
            return 0;
        source = sf->var_buf[index];
    } else if (op == OP_get_loc || op == OP_get_loc_check || op == OP_get_arg ||
               op == OP_get_var_ref || op == OP_get_var_ref_check) {
        if (end - pc < 2)
            return 0;
        index = get_u16(pc);
        pc += 2;
        if (op == OP_get_arg) {
            if (index >= b->arg_count)
                return 0;
            source = sf->arg_buf[index];
        } else if (op == OP_get_loc || op == OP_get_loc_check) {
            if (index >= b->var_count)
                return 0;
            source = sf->var_buf[index];
        } else {
            if (index >= b->closure_var_count)
                return 0;
            source = *JS_VALUE_GET_OBJ(sf->cur_func)->u.func.var_refs[index]->pvalue;
        }
    } else
        return 0;
    if (end - pc < 6 || pc[0] != OP_append || pc[1] != OP_drop)
        return 0;
    pc += 2;
    if (*pc == OP_perm3) {
        method = 1;
        pc++;
    } else if (end - pc >= 2 && pc[0] == OP_undefined && pc[1] == OP_swap) {
        method = 0;
        pc += 2;
    } else
        return 0;
    if (end - pc < 3 || *pc != OP_apply || get_u16(pc + 1) != 0)
        return 0;
    pc += 3;
    if (sp - stack_begin < prefix + 1 + method || !js_core_spread_dense(ctx, source, &array) ||
        array->u.array.count > CORE_SPREAD_ARGV_CAP - prefix || ctx->interrupt_counter <= 1)
        return 0;
    count = prefix + array->u.array.count;
    base = sp - prefix - 1 - method;
    callee = base[method];
    receiver = method ? base[0] : JS_UNDEFINED;
    /* This is the original apply's const argv protocol: every actual value,
       including extras, has a C-owned ref before any call/poll/reentry.
       No borrowed source buffer is dereferenced after this snapshot. */
    for (i = 0; i < prefix; i++)
        args[i] = js_dup(base[1 + method + i]);
    for (; i < count; i++)
        args[i] = js_dup(array->u.array.u.values[i - prefix]);
    skip = (int)(pc - start);
    sf->cur_pc = (uint8_t *)pc;
    sf->cur_sp = sp;
    ctx->interrupt_counter--; /* Original builtin iterator creation call. */
    result = check_function(ctx, callee) ? JS_EXCEPTION
                                         : JS_Call(ctx, callee, receiver, count, vc(args));
    if (!JS_IsException(result)) {
        /* Publish the result before any consumed operand may finalize/reenter.
           Match successful apply:callee,receiver,then argument owners. */
        base[method] = result;
        JS_FreeValue(ctx, callee);
        if (method) {
            base[0] = JS_UNDEFINED;
            JS_FreeValue(ctx, receiver);
        }
    }
    for (i = 0; i < prefix; i++) {
        JSValue value = base[1 + method + i];
        base[1 + method + i] = JS_UNDEFINED;
        JS_FreeValue(ctx, value); /* Snapshot still owns each prefix. */
    }
    for (i = 0; i < count; i++) {
        JSValue value = args[i];
        args[i] = JS_UNDEFINED;
        JS_FreeValue(ctx, value);
    }
    if (JS_IsException(result)) {
        /* Original exception unwinding releases the builder arguments first,
           then receiver/callee. Consume exactly those owners here; the caller
           resumes its unchanged catch/finally loop at the committed PC/SP. */
        if (method) {
            base[0] = JS_UNDEFINED;
            JS_FreeValue(ctx, receiver);
        }
        base[method] = JS_UNDEFINED;
        JS_FreeValue(ctx, callee);
        sf->cur_sp = saved_cursor;
        return -(skip | (int)((prefix + 1 + method) << 8));
    }
    if (method) {
        base[0] = base[1];
        base[1] = JS_UNDEFINED;
    }
    sf->cur_sp = saved_cursor;
    return skip | (int)((prefix + method) << 8);
}
#undef CORE_SPREAD_CODE
