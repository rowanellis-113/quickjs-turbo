/* Frame-free borrowed root/leaf evaluator for short read-only JS callbacks. MIT. */
#include <stdatomic.h>

static _Atomic unsigned char js_fast_root_leaf_policy;

static SHARED_INLINE unsigned char js_fast_root_leaf_modes(void)
{
    unsigned char m = atomic_load_explicit(&js_fast_root_leaf_policy, memory_order_relaxed);
    if (unlikely(!m)) {
        unsigned char expected = 0;
        const char *g;
        m = 0x80u;
        if (getenv("QJS_DISABLE_FRAME_LEAF_ENTRY") == NULL &&
            getenv("QJS_DISABLE_NATIVE_CHILD_LEAF") == NULL)
            m |= 1u;
        g = getenv("QJS_DISABLE_THIS_FIELD_LEAF");
        if (!g || g[0] == '0')
            m |= 2u;
        if (!atomic_compare_exchange_strong_explicit(&js_fast_root_leaf_policy, &expected, m,
                                                     memory_order_relaxed, memory_order_relaxed))
            m = expected;
    }
    return m;
}

static SHARED_INLINE int js_fast_leaf_to_bool(JSValueConst v)
{
    int tag = JS_VALUE_GET_NORM_TAG(v);
    switch (tag) {
    case JS_TAG_INT:
        return JS_VALUE_GET_INT(v) != 0;
    case JS_TAG_BOOL:
        return JS_VALUE_GET_BOOL(v) != 0;
    case JS_TAG_NULL:
    case JS_TAG_UNDEFINED:
        return 0;
    case JS_TAG_FLOAT64: {
        double d = JS_VALUE_GET_FLOAT64(v);
        return !isnan(d) && d != 0.0;
    }
    case JS_TAG_STRING:
        return JS_VALUE_GET_STRING(v)->len != 0;
    case JS_TAG_STRING_ROPE:
        return JS_VALUE_GET_STRING_ROPE(v)->len != 0;
    case JS_TAG_OBJECT:
        return !JS_VALUE_GET_OBJ(v)->is_HTMLDDA;
    case JS_TAG_SYMBOL:
        return 1;
    default:
        return -1;
    }
}

static SHARED_INLINE bool js_try_fast_borrowed_leaf(JSContext *ctx, JSValueConst func,
                                                    JSValueConst this_value, int argc,
                                                    JSValueConst *argv, JSValue *out)
{
    JSRuntime *rt = ctx->rt;
    unsigned char modes;
    JSObject *f;
    JSFunctionBytecode *b;
    const uint8_t *code;
    int len;

    if (unlikely((unsigned)argc > 65535u || JS_VALUE_GET_TAG(func) != JS_TAG_OBJECT))
        return false;
    f = JS_VALUE_GET_OBJ(func);
    if (f->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return false;
    modes = js_fast_root_leaf_modes();
    if (unlikely(!(modes & 1u)))
        return false;
    if (unlikely(!FRAME_STATE(rt))) {
        FRAME_STATE(rt) =
            !qjs_internal_interp_frame_disabled() && getenv("QJS_DISABLE_MIN_CALL_FRAME") == NULL
                ? 1
                : 2;
    }
    if (FRAME_STATE(rt) != 1 || FRAME_REGISTER_STATE(rt) == 2)
        return false;
#ifdef ENABLE_DUMPS
    if (unlikely(check_dump_flag(rt, JS_DUMP_BYTECODE_STEP)))
        return false;
#endif
    b = js_frame_target(func);
    if (!b || (FRAME_KIND(b) & 4) || b->var_ref_count != 0 || b->realm != ctx ||
        ctx->interrupt_counter <= 2)
        return false;
    if (unlikely(js_check_stack_overflow(rt, (size_t)argc * sizeof(JSValue) + 5280)))
        return false;

    code = b->byte_code_buf;
    len = b->byte_code_len;

    /* Fast path 1: exact 9-byte `this.<atom>` getter without frame setup. */
    if (b->var_count == 1) {
        if ((modes & 2u) && len == 9 && b->arg_count == 0 && b->closure_var_count == 0 &&
            b->stack_size == 1 && code[0] == OP_push_this && code[1] == OP_put_loc0 &&
            code[2] == OP_get_loc0 && code[3] == OP_get_field && code[8] == OP_return &&
            JS_VALUE_GET_TAG(this_value) == JS_TAG_OBJECT) {
            JSObject *ro = JS_VALUE_GET_OBJ(this_value);
            if (!ro->is_exotic) {
#ifdef QJS_PROPERTY_IC
                if (rt->property_ic_mode == 1 &&
                    b->property_ic != (struct JSPropertyIC *)(uintptr_t)1) {
                    JSPropertyIC *ic = b->property_ic;
                    JSPropertyICSite *s;
                    if (!js_property_ic_is_ptr(ic) || 0u >= ic->map_count || !ic->map[0])
                        return false;
                    s = ic->map[0];
                    if (!s->megamorphic) {
                        JSValue pv;
                        if (s->primary.shape != ro->shape || s->primary.kind != JS_IC_OWN)
                            return false;
                        pv = ro->prop[s->primary.slot].u.value;
                        if (unlikely(JS_IsUninitialized(pv) || JS_IsException(pv)))
                            return false;
                        ctx->interrupt_counter--;
                        *out = js_dup(pv);
                        return true;
                    }
                }
#endif
                JSProperty *pr;
                JSShapeProperty *prs = find_own_property(&pr, ro, get_u32(code + 4));
                if (prs && !(prs->flags & JS_PROP_TMASK) && !JS_IsUninitialized(pr->u.value) &&
                    !JS_IsException(pr->u.value)) {
                    ctx->interrupt_counter--;
                    *out = js_dup(pr->u.value);
                    return true;
                }
            }
        }
        return false;
    }

    /* Fast path 2: bounded zero-local read-only evaluator (up to 48 bytes, 24 steps). */
    if (b->var_count != 0 || len <= 0 || len > 48 || b->stack_size > 8)
        return false;

    JSValue eval_sp[8];
    int top = 0, pos = 0, steps = 0, polls = 1;

    while (pos < len && steps++ < 24) {
        uint8_t op = code[pos];
        switch (op) {
        case OP_return_undef:
            if (unlikely(polls >= ctx->interrupt_counter))
                return false;
            ctx->interrupt_counter -= polls;
            *out = JS_UNDEFINED;
            return true;
        case OP_return:
            if (unlikely(top < 1 || polls >= ctx->interrupt_counter))
                return false;
            ctx->interrupt_counter -= polls;
            *out = js_dup(eval_sp[top - 1]);
            return true;
        case OP_undefined:
            if (top >= 8)
                return false;
            eval_sp[top++] = JS_UNDEFINED;
            pos += 1;
            break;
        case OP_null:
            if (top >= 8)
                return false;
            eval_sp[top++] = JS_NULL;
            pos += 1;
            break;
        case OP_push_true:
        case OP_push_false:
            if (top >= 8)
                return false;
            eval_sp[top++] = JS_NewBool(ctx, op == OP_push_true);
            pos += 1;
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
            if (top >= 8)
                return false;
            eval_sp[top++] = js_int32((int)op - OP_push_0);
            pos += 1;
            break;
        case OP_push_i8:
            if (top >= 8 || pos + 2 > len)
                return false;
            eval_sp[top++] = js_int32((int8_t)code[pos + 1]);
            pos += 2;
            break;
        case OP_push_i16:
            if (top >= 8 || pos + 3 > len)
                return false;
            eval_sp[top++] = js_int32((int16_t)get_u16(code + pos + 1));
            pos += 3;
            break;
        case OP_push_i32:
            if (top >= 8 || pos + 5 > len)
                return false;
            eval_sp[top++] = js_int32((int32_t)get_u32(code + pos + 1));
            pos += 5;
            break;
        case OP_push_const8:
        case OP_push_const: {
            uint32_t idx;
            JSValue cv;
            if (op == OP_push_const8) {
                if (pos + 2 > len)
                    return false;
                idx = code[pos + 1];
                pos += 2;
            } else {
                if (pos + 5 > len)
                    return false;
                idx = get_u32(code + pos + 1);
                pos += 5;
            }
            if (top >= 8 || idx >= (uint32_t)b->cpool_count)
                return false;
            cv = b->cpool[idx];
            if (JS_VALUE_GET_TAG(cv) == JS_TAG_FUNCTION_BYTECODE || JS_IsException(cv))
                return false;
            eval_sp[top++] = cv;
            break;
        }
        case OP_get_arg0:
        case OP_get_arg1:
        case OP_get_arg2:
        case OP_get_arg3:
        case OP_get_arg: {
            uint32_t idx;
            JSValue av;
            if (op == OP_get_arg) {
                if (pos + 3 > len)
                    return false;
                idx = get_u16(code + pos + 1);
                pos += 3;
            } else {
                idx = (uint32_t)(op - OP_get_arg0);
                pos += 1;
            }
            if (top >= 8)
                return false;
            av = idx < (uint32_t)argc ? argv[idx] : JS_UNDEFINED;
            if (unlikely(JS_IsException(av)))
                return false;
            eval_sp[top++] = av;
            break;
        }
        case OP_get_var_ref0:
        case OP_get_var_ref1:
        case OP_get_var_ref2:
        case OP_get_var_ref3:
        case OP_get_var_ref:
        case OP_get_var_ref_check: {
            uint32_t idx;
            JSValue rv;
            if (op >= OP_get_var_ref0 && op <= OP_get_var_ref3) {
                idx = (uint32_t)(op - OP_get_var_ref0);
                pos += 1;
            } else {
                if (pos + 3 > len)
                    return false;
                idx = get_u16(code + pos + 1);
                pos += 3;
            }
            if (top >= 8 || idx >= (uint32_t)b->closure_var_count)
                return false;
            rv = *f->u.func.var_refs[idx]->pvalue;
            if (unlikely(JS_IsUninitialized(rv) || JS_IsException(rv)))
                return false;
            eval_sp[top++] = rv;
            break;
        }
        case OP_dup:
            if (top < 1 || top >= 8)
                return false;
            eval_sp[top] = eval_sp[top - 1];
            top++;
            pos += 1;
            break;
        case OP_drop:
            if (top < 1)
                return false;
            top--;
            pos += 1;
            break;
        case OP_typeof_is_undefined:
        case OP_typeof_is_function:
            if (top < 1)
                return false;
            {
                JSAtom ta = js_operator_typeof(ctx, eval_sp[top - 1]);
                JSAtom want = op == OP_typeof_is_function ? JS_ATOM_function : JS_ATOM_undefined;
                eval_sp[top - 1] = JS_NewBool(ctx, ta == want);
            }
            pos += 1;
            break;
        case OP_typeof:
            if (top < 1 || pos + 7 > len || code[pos + 1] != OP_push_atom_value ||
                (code[pos + 6] != OP_strict_eq && code[pos + 6] != OP_strict_neq))
                return false;
            {
                JSAtom ta = js_operator_typeof(ctx, eval_sp[top - 1]);
                bool eq = (ta == (JSAtom)get_u32(code + pos + 2));
                if (code[pos + 6] == OP_strict_neq)
                    eq = !eq;
                eval_sp[top - 1] = JS_NewBool(ctx, eq);
            }
            pos += 7;
            break;
        case OP_is_undefined:
            if (top < 1)
                return false;
            eval_sp[top - 1] =
                JS_NewBool(ctx, JS_VALUE_GET_TAG(eval_sp[top - 1]) == JS_TAG_UNDEFINED);
            pos += 1;
            break;
        case OP_is_null:
            if (top < 1)
                return false;
            eval_sp[top - 1] = JS_NewBool(ctx, JS_VALUE_GET_TAG(eval_sp[top - 1]) == JS_TAG_NULL);
            pos += 1;
            break;
        case OP_is_undefined_or_null:
            if (top < 1)
                return false;
            {
                int t = JS_VALUE_GET_TAG(eval_sp[top - 1]);
                eval_sp[top - 1] = JS_NewBool(ctx, t == JS_TAG_UNDEFINED || t == JS_TAG_NULL);
            }
            pos += 1;
            break;
        case OP_lnot:
            if (top < 1)
                return false;
            {
                int truthy = js_fast_leaf_to_bool(eval_sp[top - 1]);
                if (truthy < 0)
                    return false;
                eval_sp[top - 1] = JS_NewBool(ctx, !truthy);
            }
            pos += 1;
            break;
        case OP_neg:
            if (top < 1)
                return false;
            {
                JSValue v = eval_sp[top - 1];
                int tag = JS_VALUE_GET_NORM_TAG(v);
                if (tag == JS_TAG_INT) {
                    int32_t iv = JS_VALUE_GET_INT(v);
                    if (iv == 0 || iv == INT32_MIN)
                        return false;
                    eval_sp[top - 1] = js_int32(-iv);
                } else if (tag == JS_TAG_FLOAT64) {
                    eval_sp[top - 1] = js_float64(-JS_VALUE_GET_FLOAT64(v));
                } else {
                    return false;
                }
            }
            pos += 1;
            break;
        case OP_not:
            if (top < 1)
                return false;
            {
                JSValue v = eval_sp[top - 1];
                if (JS_VALUE_GET_TAG(v) != JS_TAG_INT)
                    return false;
                eval_sp[top - 1] = js_int32(~JS_VALUE_GET_INT(v));
            }
            pos += 1;
            break;
        case OP_add:
        case OP_sub:
        case OP_mul:
        case OP_div: {
            JSValue v1, v2;
            int t1, t2;
            if (top < 2)
                return false;
            v1 = eval_sp[top - 2];
            v2 = eval_sp[top - 1];
            t1 = JS_VALUE_GET_NORM_TAG(v1);
            t2 = JS_VALUE_GET_NORM_TAG(v2);
            if (t1 == JS_TAG_INT && t2 == JS_TAG_INT) {
                int32_t a = JS_VALUE_GET_INT(v1), c = JS_VALUE_GET_INT(v2);
                JSValue r;
                if (op == OP_add) {
                    int64_t w = (int64_t)a + c;
                    r = (w >= INT32_MIN && w <= INT32_MAX) ? js_int32((int32_t)w)
                                                           : js_float64((double)w);
                } else if (op == OP_sub) {
                    int64_t w = (int64_t)a - c;
                    r = (w >= INT32_MIN && w <= INT32_MAX) ? js_int32((int32_t)w)
                                                           : js_float64((double)w);
                } else if (op == OP_mul) {
                    int64_t w = (int64_t)a * c;
                    if (w == 0 && (((uint32_t)a ^ (uint32_t)c) >> 31))
                        r = js_float64(-0.0);
                    else
                        r = (w >= INT32_MIN && w <= INT32_MAX) ? js_int32((int32_t)w)
                                                               : js_float64((double)w);
                } else {
                    r = js_number((double)a / (double)c);
                }
                eval_sp[top - 2] = r;
            } else if ((t1 == JS_TAG_INT || t1 == JS_TAG_FLOAT64) &&
                       (t2 == JS_TAG_INT || t2 == JS_TAG_FLOAT64)) {
                double d1 =
                    t1 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v1) : JS_VALUE_GET_FLOAT64(v1);
                double d2 =
                    t2 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v2) : JS_VALUE_GET_FLOAT64(v2);
                double dr = op == OP_add   ? d1 + d2
                            : op == OP_sub ? d1 - d2
                            : op == OP_mul ? d1 * d2
                                           : d1 / d2;
                eval_sp[top - 2] = (op == OP_div) ? js_number(dr) : js_float64(dr);
            } else {
                return false;
            }
            top--;
            pos += 1;
            break;
        }
        case OP_mod: {
            JSValue v1, v2;
            int t1, t2;
            if (top < 2)
                return false;
            v1 = eval_sp[top - 2];
            v2 = eval_sp[top - 1];
            t1 = JS_VALUE_GET_NORM_TAG(v1);
            t2 = JS_VALUE_GET_NORM_TAG(v2);
            if (t1 == JS_TAG_INT && t2 == JS_TAG_INT) {
                int32_t a = JS_VALUE_GET_INT(v1), c = JS_VALUE_GET_INT(v2), r;
                if (!c || a == INT32_MIN)
                    return false;
                r = a % c;
                eval_sp[top - 2] = (r == 0 && a < 0) ? js_float64(-0.0) : js_int32(r);
            } else if ((t1 == JS_TAG_INT || t1 == JS_TAG_FLOAT64) &&
                       (t2 == JS_TAG_INT || t2 == JS_TAG_FLOAT64)) {
                double d1 =
                    t1 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v1) : JS_VALUE_GET_FLOAT64(v1);
                double d2 =
                    t2 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v2) : JS_VALUE_GET_FLOAT64(v2);
                eval_sp[top - 2] = js_float64(fmod(d1, d2));
            } else {
                return false;
            }
            top--;
            pos += 1;
            break;
        }
        case OP_and:
        case OP_or:
        case OP_xor:
        case OP_shl:
        case OP_sar:
        case OP_shr: {
            JSValue v1, v2;
            int32_t a, c;
            if (top < 2)
                return false;
            v1 = eval_sp[top - 2];
            v2 = eval_sp[top - 1];
            if (JS_VALUE_GET_TAG(v1) != JS_TAG_INT || JS_VALUE_GET_TAG(v2) != JS_TAG_INT)
                return false;
            a = JS_VALUE_GET_INT(v1);
            c = JS_VALUE_GET_INT(v2);
            if (op == OP_and)
                eval_sp[top - 2] = js_int32(a & c);
            else if (op == OP_or)
                eval_sp[top - 2] = js_int32(a | c);
            else if (op == OP_xor)
                eval_sp[top - 2] = js_int32(a ^ c);
            else if (op == OP_shl)
                eval_sp[top - 2] = js_int32((int32_t)((uint32_t)a << ((uint32_t)c & 31u)));
            else if (op == OP_sar)
                eval_sp[top - 2] = js_int32(a >> ((uint32_t)c & 31u));
            else {
                uint32_t u = (uint32_t)a >> ((uint32_t)c & 31u);
                eval_sp[top - 2] = u <= INT32_MAX ? js_int32((int32_t)u) : js_float64((double)u);
            }
            top--;
            pos += 1;
            break;
        }
        case OP_lt:
        case OP_lte:
        case OP_gt:
        case OP_gte: {
            JSValue v1, v2;
            int t1, t2;
            bool cmp;
            if (top < 2)
                return false;
            v1 = eval_sp[top - 2];
            v2 = eval_sp[top - 1];
            t1 = JS_VALUE_GET_NORM_TAG(v1);
            t2 = JS_VALUE_GET_NORM_TAG(v2);
            if (t1 == JS_TAG_INT && t2 == JS_TAG_INT) {
                int32_t a = JS_VALUE_GET_INT(v1), c = JS_VALUE_GET_INT(v2);
                cmp = op == OP_lt    ? (a < c)
                      : op == OP_lte ? (a <= c)
                      : op == OP_gt  ? (a > c)
                                     : (a >= c);
            } else if ((t1 == JS_TAG_INT || t1 == JS_TAG_FLOAT64) &&
                       (t2 == JS_TAG_INT || t2 == JS_TAG_FLOAT64)) {
                double d1 =
                    t1 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v1) : JS_VALUE_GET_FLOAT64(v1);
                double d2 =
                    t2 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v2) : JS_VALUE_GET_FLOAT64(v2);
                cmp = op == OP_lt    ? (d1 < d2)
                      : op == OP_lte ? (d1 <= d2)
                      : op == OP_gt  ? (d1 > d2)
                                     : (d1 >= d2);
            } else {
                return false;
            }
            eval_sp[top - 2] = JS_NewBool(ctx, cmp);
            top--;
            pos += 1;
            break;
        }
        case OP_strict_eq:
        case OP_strict_neq: {
            JSValue v1, v2;
            int t1, t2;
            bool eq;
            if (top < 2)
                return false;
            v1 = eval_sp[top - 2];
            v2 = eval_sp[top - 1];
            t1 = JS_VALUE_GET_NORM_TAG(v1);
            t2 = JS_VALUE_GET_NORM_TAG(v2);
            if ((t1 == JS_TAG_INT || t1 == JS_TAG_FLOAT64) &&
                (t2 == JS_TAG_INT || t2 == JS_TAG_FLOAT64)) {
                if (t1 == JS_TAG_INT && t2 == JS_TAG_INT) {
                    eq = (JS_VALUE_GET_INT(v1) == JS_VALUE_GET_INT(v2));
                } else {
                    double d1 =
                        t1 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v1) : JS_VALUE_GET_FLOAT64(v1);
                    double d2 =
                        t2 == JS_TAG_INT ? (double)JS_VALUE_GET_INT(v2) : JS_VALUE_GET_FLOAT64(v2);
                    eq = (d1 == d2);
                }
            } else if (t1 != t2) {
                if ((t1 == JS_TAG_STRING || t1 == JS_TAG_STRING_ROPE) &&
                    (t2 == JS_TAG_STRING || t2 == JS_TAG_STRING_ROPE))
                    return false;
                eq = false;
            } else if (t1 == JS_TAG_UNDEFINED || t1 == JS_TAG_NULL) {
                eq = true;
            } else if (t1 == JS_TAG_BOOL) {
                eq = (JS_VALUE_GET_BOOL(v1) == JS_VALUE_GET_BOOL(v2));
            } else if (t1 == JS_TAG_OBJECT || t1 == JS_TAG_SYMBOL) {
                eq = (JS_VALUE_GET_PTR(v1) == JS_VALUE_GET_PTR(v2));
            } else {
                return false;
            }
            if (op == OP_strict_neq)
                eq = !eq;
            eval_sp[top - 2] = JS_NewBool(ctx, eq);
            top--;
            pos += 1;
            break;
        }
        case OP_eq:
        case OP_neq: {
            JSValue v1, v2;
            int t1, t2;
            bool eq;
            if (top < 2)
                return false;
            v1 = eval_sp[top - 2];
            v2 = eval_sp[top - 1];
            t1 = JS_VALUE_GET_NORM_TAG(v1);
            t2 = JS_VALUE_GET_NORM_TAG(v2);
            if (t1 == JS_TAG_INT && t2 == JS_TAG_INT) {
                eq = (JS_VALUE_GET_INT(v1) == JS_VALUE_GET_INT(v2));
            } else if (t1 == JS_TAG_BOOL && t2 == JS_TAG_BOOL) {
                eq = (JS_VALUE_GET_BOOL(v1) == JS_VALUE_GET_BOOL(v2));
            } else if ((t1 == JS_TAG_NULL || t1 == JS_TAG_UNDEFINED) &&
                       (t2 == JS_TAG_NULL || t2 == JS_TAG_UNDEFINED)) {
                eq = true;
            } else if (t1 == JS_TAG_NULL || t1 == JS_TAG_UNDEFINED) {
                if (t2 == JS_TAG_OBJECT)
                    return false;
                eq = false;
            } else if (t2 == JS_TAG_NULL || t2 == JS_TAG_UNDEFINED) {
                if (t1 == JS_TAG_OBJECT)
                    return false;
                eq = false;
            } else {
                return false;
            }
            if (op == OP_neq)
                eq = !eq;
            eval_sp[top - 2] = JS_NewBool(ctx, eq);
            top--;
            pos += 1;
            break;
        }
        case OP_get_field: {
            JSValue obj, out_val = JS_UNDEFINED;
            JSObject *o;
            JSAtom atom;
            JSProperty *pr;
            JSShapeProperty *prs;
            bool resolved = false;
            if (top < 1 || pos + 5 > len)
                return false;
            obj = eval_sp[top - 1];
            if (JS_VALUE_GET_TAG(obj) != JS_TAG_OBJECT)
                return false;
            o = JS_VALUE_GET_OBJ(obj);
            if (o->is_exotic)
                return false;
            atom = get_u32(code + pos + 1);
#ifdef QJS_PROPERTY_IC
            if (rt->property_ic_mode == 1 &&
                b->property_ic != (struct JSPropertyIC *)(uintptr_t)1) {
                JSPropertyIC *ic = b->property_ic;
                uint32_t mpos = (uint32_t)pos >> 2;
                JSPropertyICSite *s;
                if (!js_property_ic_is_ptr(ic) || mpos >= ic->map_count || !ic->map[mpos])
                    return false;
                s = ic->map[mpos];
                if (!s->megamorphic) {
                    if (s->primary.shape != o->shape)
                        return false;
                    uint32_t pk = s->primary.kind;
                    if (pk == JS_IC_OWN) {
                        JSValue pv = o->prop[s->primary.slot].u.value;
                        if (unlikely(JS_IsUninitialized(pv) || JS_IsException(pv)))
                            return false;
                        out_val = pv;
                        resolved = true;
                    } else if ((pk == JS_IC_PROTO || pk == JS_IC_UNSET) && rt->property_ic_epoch &&
                               s->primary.epoch == rt->property_ic_epoch) {
                        if (pk == JS_IC_UNSET) {
                            out_val = JS_UNDEFINED;
                            resolved = true;
                        } else {
                            JSValue pv = s->primary.holder->prop[s->primary.slot].u.value;
                            if (unlikely(JS_IsUninitialized(pv) || JS_IsException(pv)))
                                return false;
                            out_val = pv;
                            resolved = true;
                        }
                    } else {
                        return false;
                    }
                }
            }
#endif
            if (!resolved) {
                prs = find_own_property(&pr, o, atom);
                if (!prs || (prs->flags & JS_PROP_TMASK) || JS_IsUninitialized(pr->u.value) ||
                    JS_IsException(pr->u.value))
                    return false;
                out_val = pr->u.value;
            }
            eval_sp[top - 1] = out_val;
            pos += 5;
            break;
        }
        case OP_get_length: {
            JSValue v;
            int tag;
            if (top < 1)
                return false;
            v = eval_sp[top - 1];
            tag = JS_VALUE_GET_TAG(v);
            if (tag == JS_TAG_STRING) {
                eval_sp[top - 1] = js_int32(JS_VALUE_GET_STRING(v)->len);
            } else if (tag == JS_TAG_STRING_ROPE) {
                eval_sp[top - 1] = js_int32(JS_VALUE_GET_STRING_ROPE(v)->len);
            } else if (tag == JS_TAG_OBJECT) {
                JSObject *o = JS_VALUE_GET_OBJ(v);
                if (o->class_id != JS_CLASS_ARRAY || !o->fast_array || o->shape->prop_count < 1)
                    return false;
                JSShapeProperty *lp = &get_shape_prop(o->shape)[0];
                if (lp->atom != JS_ATOM_length || (lp->flags & JS_PROP_TMASK) ||
                    !(lp->flags & JS_PROP_LENGTH))
                    return false;
                eval_sp[top - 1] = o->prop[0].u.value;
            } else {
                return false;
            }
            pos += 1;
            break;
        }
        case OP_get_array_el: {
            JSValue obj, idxv;
            JSObject *o;
            int32_t idx;
            if (top < 2)
                return false;
            obj = eval_sp[top - 2];
            idxv = eval_sp[top - 1];
            if (JS_VALUE_GET_TAG(obj) != JS_TAG_OBJECT || JS_VALUE_GET_TAG(idxv) != JS_TAG_INT)
                return false;
            o = JS_VALUE_GET_OBJ(obj);
            idx = JS_VALUE_GET_INT(idxv);
            if (o->class_id != JS_CLASS_ARRAY || !o->fast_array || idx < 0 ||
                (uint32_t)idx >= o->u.array.count)
                return false;
            {
                JSValue ev = o->u.array.u.values[idx];
                if (unlikely(JS_IsException(ev)))
                    return false;
                eval_sp[top - 2] = ev;
            }
            top--;
            pos += 1;
            break;
        }
        case OP_if_false8:
        case OP_if_true8:
        case OP_goto8: {
            int8_t rel;
            int target;
            bool take = true;
            if (pos + 2 > len)
                return false;
            rel = (int8_t)code[pos + 1];
            if (rel < 1)
                return false;
            target = pos + 1 + rel;
            if (target >= len)
                return false;
            if (op != OP_goto8) {
                int truthy;
                if (top < 1)
                    return false;
                truthy = js_fast_leaf_to_bool(eval_sp[--top]);
                if (truthy < 0)
                    return false;
                take = (op == OP_if_true8) ? (truthy != 0) : (truthy == 0);
            }
            if (++polls >= ctx->interrupt_counter)
                return false;
            pos = take ? target : pos + 2;
            break;
        }
        default:
            return false;
        }
    }
    return false;
}
