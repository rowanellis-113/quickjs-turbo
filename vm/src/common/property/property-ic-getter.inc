/* Bounded frame-free getter invocation helpers shared across property IC overlays. */
#ifdef CONFIG_ATOMICS
static _Atomic unsigned char js_ic_inline_getter_mode;
static inline bool js_ic_inline_getter_enabled(void)
{
    unsigned char mode = atomic_load_explicit(&js_ic_inline_getter_mode, memory_order_relaxed);
    if (!mode) {
        mode = getenv("QJS_DISABLE_INLINE_GETTER") ? 2 : 1;
        atomic_store_explicit(&js_ic_inline_getter_mode, mode, memory_order_relaxed);
    }
    return mode == 1;
}
#else
static inline bool js_ic_inline_getter_enabled(void)
{
    return getenv("QJS_DISABLE_INLINE_GETTER") == NULL;
}
#endif

static JSValue js_ic_invoke_c_getter(JSContext *ctx, JSObject *getter, JSValueConst this_obj)
{
    int cproto = getter->u.cfunc.cproto;
    JSStackFrame sf_c;
    JSValue gf, res;
#ifdef ENABLE_DUMPS
    if (unlikely(ctx->rt->dump_flags != 0))
        goto fallback;
#endif
    if (unlikely(ctx->interrupt_counter <= 1 || js_check_stack_overflow(ctx->rt, 512)))
        goto fallback;
    ctx->interrupt_counter--;
    memset(&sf_c, 0, sizeof(sf_c));
    sf_c.prev_frame = ctx->rt->current_stack_frame;
    sf_c.cur_func = JS_MKPTR(JS_TAG_OBJECT, getter);
    ctx->rt->current_stack_frame = &sf_c;
    gf = js_dup(JS_MKPTR(JS_TAG_OBJECT, getter));
    if (cproto == JS_CFUNC_getter)
        res = getter->u.cfunc.c_function.getter(getter->u.cfunc.realm, this_obj);
    else
        res = getter->u.cfunc.c_function.getter_magic(getter->u.cfunc.realm, this_obj,
                                                      getter->u.cfunc.magic);
    ctx->rt->current_stack_frame = sf_c.prev_frame;
    JS_FreeValue(ctx, gf);
    return res;
fallback:
    return JS_CallFree(ctx, js_dup(JS_MKPTR(JS_TAG_OBJECT, getter)), this_obj, 0, NULL);
}

static JSValue js_ic_invoke_getter(JSContext *ctx, JSObject *receiver, JSObject *getter,
                                   JSValueConst this_obj)
{
    bool allow = js_ic_inline_getter_enabled() && ctx->interrupt_counter > 2;
#ifdef ENABLE_DUMPS
    if (unlikely(ctx->rt->dump_flags != 0))
        allow = false;
#endif
    if (likely(allow)) {
        if (getter->class_id == JS_CLASS_C_FUNCTION) {
            int cproto = getter->u.cfunc.cproto;
            if (cproto == JS_CFUNC_getter || cproto == JS_CFUNC_getter_magic)
                return js_ic_invoke_c_getter(ctx, getter, this_obj);
        } else if (getter->class_id == JS_CLASS_BYTECODE_FUNCTION) {
            JSFunctionBytecode *gb = getter->u.func.function_bytecode;
            if (gb->func_kind == JS_FUNC_NORMAL && !gb->is_derived_class_constructor &&
                gb->arg_count == 0 && gb->var_ref_count == 0 && gb->closure_var_count == 0 &&
                gb->realm == ctx) {
                const uint8_t *code = gb->byte_code_buf;
                int len = gb->byte_code_len;
                if (gb->var_count == 1 && len == 9 && code[0] == OP_push_this &&
                    code[1] == OP_put_loc0 && code[2] == OP_get_loc0 && code[3] == OP_get_field &&
                    code[8] == OP_return && !receiver->is_exotic) {
                    JSProperty *pr2;
                    JSShapeProperty *prs2 = find_own_property(&pr2, receiver, get_u32(code + 4));
                    if (prs2 && !(prs2->flags & JS_PROP_TMASK) &&
                        !JS_IsUninitialized(pr2->u.value)) {
                        ctx->interrupt_counter--;
                        return js_dup(pr2->u.value);
                    }
                } else if (gb->var_count == 1 && len == 14 && code[0] == OP_push_this &&
                           code[1] == OP_put_loc0 && code[2] == OP_get_loc0 &&
                           code[3] == OP_get_field && code[8] == OP_get_field &&
                           code[13] == OP_return && !receiver->is_exotic) {
                    JSProperty *pr2;
                    JSShapeProperty *prs2 = find_own_property(&pr2, receiver, get_u32(code + 4));
                    if (prs2 && !(prs2->flags & JS_PROP_TMASK) &&
                        JS_VALUE_GET_TAG(pr2->u.value) == JS_TAG_OBJECT) {
                        JSObject *inner = JS_VALUE_GET_OBJ(pr2->u.value);
                        JSAtom atom2 = get_u32(code + 9);
                        if (inner->class_id == JS_CLASS_ARRAY && inner->fast_array &&
                            atom2 == JS_ATOM_length && inner->shape->prop_count >= 1) {
                            JSShapeProperty *lprop = &get_shape_prop(inner->shape)[0];
                            if (lprop->atom == JS_ATOM_length && !(lprop->flags & JS_PROP_TMASK)) {
                                ctx->interrupt_counter--;
                                return js_dup(inner->prop[0].u.value);
                            }
                        } else if (!inner->is_exotic) {
                            JSObject *ip = inner;
                            for (unsigned d = 0; d <= 8 && ip; d++, ip = ip->shape->proto) {
                                if (ip->is_exotic)
                                    break;
                                JSProperty *pr3;
                                JSShapeProperty *prs3 = find_own_property(&pr3, ip, atom2);
                                if (prs3) {
                                    uint32_t tm = prs3->flags & JS_PROP_TMASK;
                                    if (!tm && !JS_IsUninitialized(pr3->u.value)) {
                                        ctx->interrupt_counter--;
                                        return js_dup(pr3->u.value);
                                    }
                                    if (tm == JS_PROP_GETSET && pr3->u.getset.getter &&
                                        pr3->u.getset.getter->class_id == JS_CLASS_C_FUNCTION &&
                                        (pr3->u.getset.getter->u.cfunc.cproto == JS_CFUNC_getter ||
                                         pr3->u.getset.getter->u.cfunc.cproto ==
                                             JS_CFUNC_getter_magic)) {
                                        JSStackFrame sf_outer;
                                        JSValue ogf = js_dup(JS_MKPTR(JS_TAG_OBJECT, getter));
                                        JSValue iv = js_dup(pr2->u.value);
                                        JSValue r;
                                        memset(&sf_outer, 0, sizeof(sf_outer));
                                        sf_outer.prev_frame = ctx->rt->current_stack_frame;
                                        sf_outer.cur_func = ogf;
                                        sf_outer.cur_pc = gb->byte_code_buf + 13;
                                        ctx->rt->current_stack_frame = &sf_outer;
                                        ctx->interrupt_counter--;
                                        r = js_ic_invoke_c_getter(ctx, pr3->u.getset.getter, iv);
                                        ctx->rt->current_stack_frame = sf_outer.prev_frame;
                                        JS_FreeValue(ctx, iv);
                                        JS_FreeValue(ctx, ogf);
                                        return r;
                                    }
                                    break;
                                }
                            }
                        }
                    }
                } else {
                    int off = -1;
                    if (gb->var_count == 1 && len >= 3 && code[0] == OP_push_this &&
                        code[1] == OP_put_loc0)
                        off = 2;
                    else if (gb->var_count == 0)
                        off = 0;
                    if (off >= 0) {
                        int rem = len - off;
                        if (rem == 1 && code[off] == OP_return_undef) {
                            ctx->interrupt_counter--;
                            return JS_UNDEFINED;
                        }
                        if (rem == 2 && code[off + 1] == OP_return) {
                            uint8_t op = code[off];
                            if (op == OP_undefined) {
                                ctx->interrupt_counter--;
                                return JS_UNDEFINED;
                            }
                            if (op == OP_null) {
                                ctx->interrupt_counter--;
                                return JS_NULL;
                            }
                            if (op == OP_push_true || op == OP_push_false) {
                                ctx->interrupt_counter--;
                                return JS_NewBool(ctx, op == OP_push_true);
                            }
                            if (op >= OP_push_minus1 && op <= OP_push_7) {
                                ctx->interrupt_counter--;
                                return js_int32((int)op - OP_push_0);
                            }
                        } else if (rem == 3 && code[off] == OP_push_i8 &&
                                   code[off + 2] == OP_return) {
                            ctx->interrupt_counter--;
                            return js_int32((int8_t)code[off + 1]);
                        } else if (rem == 4 && code[off] == OP_push_i16 &&
                                   code[off + 3] == OP_return) {
                            ctx->interrupt_counter--;
                            return js_int32((int16_t)get_u16(code + off + 1));
                        } else if (rem == 6 && code[off] == OP_push_i32 &&
                                   code[off + 5] == OP_return) {
                            ctx->interrupt_counter--;
                            return js_int32((int32_t)get_u32(code + off + 1));
                        }
                    }
                }
            }
        }
    }
    return JS_CallFree(ctx, js_dup(JS_MKPTR(JS_TAG_OBJECT, getter)), this_obj, 0, NULL);
}

static bool js_ic_classify_getter(JSContext *ctx, JSFunctionBytecode *b, JSObject *receiver,
                                  JSObject *holder, JSObject *getter, uint32_t holder_slot,
                                  JSPropertyICWay *fresh)
{
    if (receiver->is_exotic || !ctx->rt->property_ic_epoch)
        return false;
    if (holder != receiver && receiver != JS_VALUE_GET_OBJ(ctx->global_obj) && b->realm == ctx &&
        js_ic_inline_getter_enabled() && getter->class_id == JS_CLASS_BYTECODE_FUNCTION) {
        JSFunctionBytecode *gb = getter->u.func.function_bytecode;
        if (gb->func_kind == JS_FUNC_NORMAL && !gb->is_derived_class_constructor &&
            gb->arg_count == 0 && gb->var_ref_count == 0 && gb->closure_var_count == 0 &&
            gb->realm == ctx) {
            const uint8_t *code = gb->byte_code_buf;
            int len = gb->byte_code_len;
            if (gb->var_count == 1 && len == 9 && code[0] == OP_push_this &&
                code[1] == OP_put_loc0 && code[2] == OP_get_loc0 && code[3] == OP_get_field &&
                code[8] == OP_return) {
                JSProperty *pr2;
                JSShapeProperty *prs2 = find_own_property(&pr2, receiver, get_u32(code + 4));
                if (prs2 && !(prs2->flags & JS_PROP_TMASK) && !JS_IsUninitialized(pr2->u.value)) {
                    fresh->shape = receiver->shape;
                    fresh->slot = (uint32_t)(pr2 - receiver->prop);
                    fresh->kind = JS_IC_GETTER_FIELD;
                    fresh->holder = holder;
                    fresh->epoch = ctx->rt->property_ic_epoch;
                    return true;
                }
            } else {
                int off = -1;
                if (gb->var_count == 1 && len == 5 && code[0] == OP_push_this &&
                    code[1] == OP_put_loc0)
                    off = 2;
                else if (gb->var_count == 0 && len == 2)
                    off = 0;
                if (off >= 0 && (code[off] == OP_push_true || code[off] == OP_push_false) &&
                    code[off + 1] == OP_return) {
                    fresh->shape = receiver->shape;
                    fresh->slot = (code[off] == OP_push_true) ? 1u : 0u;
                    fresh->kind = JS_IC_GETTER_BOOL;
                    fresh->holder = holder;
                    fresh->epoch = ctx->rt->property_ic_epoch;
                    return true;
                }
            }
        }
    }
    fresh->shape = receiver->shape;
    fresh->slot = holder_slot;
    fresh->kind = JS_IC_GETTER;
    fresh->holder = holder == receiver ? NULL : holder;
    fresh->epoch = ctx->rt->property_ic_epoch;
    return true;
}
