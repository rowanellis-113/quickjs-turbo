/* Release call-leaf specialist supporting var_count>0 non-leaf caching, scope==2 callbacks,
 * LEAF_EXPR priority, and JS_FastTransitionResize. MIT. */
#include <stdatomic.h>
#include "src/common/internal/interpreter-env.h"
#include "src/common/call/interpreter-bytecode-metadata.inc"
#include "interpreter-aarch64-values.h"
#define LEAF_CODE                                                                                  \
    __attribute__((noipa, visibility("hidden"), section(".text.qjs_aarch64_call_leaf")))
enum {
    LEAF_PRIMITIVE = 1,
    LEAF_CHILD = 2,
    LEAF_GETTER = 4,
    LEAF_EXPR = 8,
    LEAF_CHAR = 16,
    LEAF_COMPOUND = 32
};
static _Atomic unsigned leaf_policy __attribute__((section(".bss.qjs_aarch64_leaf")));
#define LEAF_COUNT(n) ((void)0)
static unsigned leaf_modes(JSRuntime *rt)
{
    unsigned m = atomic_load_explicit(&leaf_policy, memory_order_acquire);
    if (!m) {
        unsigned expected = 0;
        const char *s;
        m = 0x80000000u;
        if (!getenv("QJS_DISABLE_FRAME_LEAF_ENTRY"))
            m |= LEAF_PRIMITIVE;
        if (!getenv("QJS_DISABLE_NATIVE_CHILD_LEAF"))
            m |= LEAF_CHILD;
        s = getenv("QJS_DISABLE_THIS_FIELD_LEAF");
        if (!s || *s == '0')
            m |= LEAF_GETTER;
        if (!getenv("QJS_DISABLE_NATIVE_INT_EXPRESSION_LEAF"))
            m |= LEAF_EXPR;
        if (!getenv("QJS_DISABLE_FRAME_CHARACTER_SET_LEAF"))
            m |= LEAF_CHAR;
        if (!getenv("QJS_DISABLE_FRAME_COMPOUND_LEAF"))
            m |= LEAF_COMPOUND;
        if (!atomic_compare_exchange_strong_explicit(&leaf_policy, &expected, m,
                                                     memory_order_acq_rel, memory_order_acquire))
            m = expected;
    }
    unsigned char *p = (unsigned char *)rt + offsetof(JSRuntime, module_loader_has_attr) + 1;
    if (!*p)
        *p = (m & LEAF_CHILD) ? 1 : 2;
    return *p == 1 ? m : m & ~LEAF_CHILD;
}
static int leaf_constant(const uint8_t **cursor, const uint8_t *end, int32_t *v)
{
    const uint8_t *p = *cursor;
    unsigned op, n;
    if (p == end)
        return 0;
    op = *p++;
    if (op >= OP_push_minus1 && op <= OP_push_7)
        *v = (int)op - OP_push_0;
    else {
        n = op == OP_push_i8 ? 1 : op == OP_push_i16 ? 2 : op == OP_push_i32 ? 4 : 0;
        if (!n || (size_t)(end - p) < n)
            return 0;
        *v = n == 1 ? (int8_t)*p : n == 2 ? (int16_t)get_u16(p) : (int32_t)get_u32(p);
        p += n;
    }
    *cursor = p;
    return 1;
}
static int leaf_operand(const uint8_t **cursor, const uint8_t *end, JSObject *f, int argc,
                        const JSValue *argv, int32_t *v)
{
    const uint8_t *p = *cursor;
    unsigned op, index;
    JSValue a;
    if (p == end)
        return 0;
    op = *p++;
    if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        index = op - OP_get_arg0;
        if (index >= (unsigned)argc)
            return 0;
        a = argv[index];
    } else {
        if (op >= OP_get_var_ref0 && op <= OP_get_var_ref3)
            index = op - OP_get_var_ref0;
        else if (op == OP_get_var_ref || op == OP_get_var_ref_check) {
            if (end - p < 2)
                return 0;
            index = get_u16(p);
            p += 2;
        } else
            return leaf_constant(cursor, end, v);
        if (index >= f->u.func.function_bytecode->closure_var_count)
            return 0;
        a = *f->u.func.var_refs[index]->pvalue;
    }
    if (JS_VALUE_GET_TAG(a) != JS_TAG_INT)
        return 0;
    *v = JS_VALUE_GET_INT(a);
    *cursor = p;
    return 1;
}
static int leaf_compare(unsigned op, int32_t a, int32_t b, int32_t *v)
{
    switch (op) {
    case OP_lt:
        *v = a < b;
        break;
    case OP_lte:
        *v = a <= b;
        break;
    case OP_gt:
        *v = a > b;
        break;
    case OP_gte:
        *v = a >= b;
        break;
    case OP_eq:
    case OP_strict_eq:
        *v = a == b;
        break;
    case OP_neq:
    case OP_strict_neq:
        *v = a != b;
        break;
    default:
        return 0;
    }
    return 1;
}
static int leaf_const_syntax_ok(const uint8_t **cursor, const uint8_t *end)
{
    const uint8_t *p = *cursor;
    unsigned op, n;
    if (p == end)
        return 0;
    op = *p++;
    if (op >= OP_push_minus1 && op <= OP_push_7)
        n = 0;
    else {
        n = op == OP_push_i8 ? 1 : op == OP_push_i16 ? 2 : op == OP_push_i32 ? 4 : 99;
        if (n > 4 || (size_t)(end - p) < n)
            return 0;
        p += n;
    }
    *cursor = p;
    return 1;
}
static int leaf_op_syntax_ok(const uint8_t **cursor, const uint8_t *end,
                             const JSFunctionBytecode *b)
{
    const uint8_t *p = *cursor;
    unsigned op, index;
    if (p == end)
        return 0;
    op = *p++;
    if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        *cursor = p;
        return 1;
    }
    if (op >= OP_get_var_ref0 && op <= OP_get_var_ref3)
        index = op - OP_get_var_ref0;
    else if (op == OP_get_var_ref || op == OP_get_var_ref_check) {
        if (end - p < 2)
            return 0;
        index = get_u16(p);
        p += 2;
    } else
        return leaf_const_syntax_ok(cursor, end);
    if (index >= b->closure_var_count)
        return 0;
    *cursor = p;
    return 1;
}
static int leaf_expr_syntax_ok(const JSFunctionBytecode *b)
{
    const uint8_t *p = b->byte_code_buf, *end = p + b->byte_code_len;
    unsigned op;
    int cmp_only = 0;
    if (b->byte_code_len < 4 || b->byte_code_len > 16 || b->var_count ||
        !leaf_op_syntax_ok(&p, end, b) || !leaf_op_syntax_ok(&p, end, b) || p == end)
        return 0;
    op = *p++;
    switch (op) {
    case OP_add:
    case OP_sub:
    case OP_mul:
    case OP_mod:
    case OP_and:
    case OP_or:
    case OP_xor:
    case OP_shl:
    case OP_sar:
    case OP_shr:
        break;
    case OP_lt:
    case OP_lte:
    case OP_gt:
    case OP_gte:
    case OP_eq:
    case OP_strict_eq:
    case OP_neq:
    case OP_strict_neq:
        cmp_only = 1;
        break;
    default:
        return 0;
    }
    if (!cmp_only) {
        if (p == end)
            return 0;
        if (*p == OP_lnot)
            p++;
        else if (*p != OP_return) {
            if (!leaf_const_syntax_ok(&p, end) || p == end)
                return 0;
            op = *p++;
            if (op != OP_lt && op != OP_lte && op != OP_gt && op != OP_gte && op != OP_eq &&
                op != OP_strict_eq && op != OP_neq && op != OP_strict_neq)
                return 0;
        }
    }
    return end - p == 1 && *p == OP_return;
}
static JSValue leaf_expression(JSObject *f, int argc, const JSValue *argv)
{
    JSFunctionBytecode *b = f->u.func.function_bytecode;
    const uint8_t *p = b->byte_code_buf, *end = p + b->byte_code_len;
    int32_t a, c, v;
    int tag = JS_TAG_INT;
    unsigned op, shift;
    int64_t wide;
    if (b->byte_code_len < 4 || b->byte_code_len > 16 || b->var_count ||
        !leaf_operand(&p, end, f, argc, argv, &a) || !leaf_operand(&p, end, f, argc, argv, &c) ||
        p == end)
        return JS_EXCEPTION;
    op = *p++;
    switch (op) {
    case OP_add:
        wide = (int64_t)a + c;
        goto bounded;
    case OP_sub:
        wide = (int64_t)a - c;
        goto bounded;
    case OP_mul:
        wide = (int64_t)a * c;
        if (wide == 0 && ((uint32_t)a ^ (uint32_t)c) >> 31)
            return JS_EXCEPTION;
    bounded:
        if (wide < INT32_MIN || wide > INT32_MAX)
            return JS_EXCEPTION;
        v = (int32_t)wide;
        break;
    case OP_mod:
        if (!c || a == INT32_MIN)
            return JS_EXCEPTION;
        v = a % c;
        if (!v && a < 0)
            return JS_EXCEPTION;
        break;
    case OP_and:
        v = a & c;
        break;
    case OP_or:
        v = a | c;
        break;
    case OP_xor:
        v = a ^ c;
        break;
    case OP_shl:
        shift = (uint32_t)c & 31;
        v = (int32_t)((uint32_t)a << shift);
        break;
    case OP_sar:
        shift = (uint32_t)c & 31;
        v = a >> shift;
        break;
    case OP_shr:
        shift = (uint32_t)c & 31;
        v = (int32_t)((uint32_t)a >> shift);
        if (v < 0)
            return JS_EXCEPTION;
        break;
    default:
        if (!leaf_compare(op, a, c, &v))
            return JS_EXCEPTION;
        tag = JS_TAG_BOOL;
        goto finish;
    }
    if (p == end)
        return JS_EXCEPTION;
    if (*p == OP_lnot) {
        p++;
        v = !v;
        tag = JS_TAG_BOOL;
    } else if (*p != OP_return) {
        if (!leaf_constant(&p, end, &c) || p == end || !leaf_compare(*p++, v, c, &v))
            return JS_EXCEPTION;
        tag = JS_TAG_BOOL;
    }
finish:
    if (end - p != 1 || *p != OP_return)
        return JS_EXCEPTION;
    return JS_MKVAL(tag, v);
}
static int leaf_own(JSValue object, JSAtom atom, JSValue *value)
{
    JSObject *o;
    JSShape *s;
    JSShapeProperty *p;
    uint32_t h;
    if (!JS_IsObject(object))
        return 0;
    o = JS_VALUE_GET_OBJ(object);
    s = o->shape;
    h = *(uint32_t *)((uint8_t *)s - 4 * ((atom & s->prop_hash_mask) + 1));
    while (h) {
        p = &s->prop[h - 1];
        if (p->atom == atom) {
            if (p->flags & JS_PROP_TMASK)
                return 0;
            *value = o->prop[h - 1].u.value;
            return 1;
        }
        h = p->hash_next;
    }
    return 0;
}
static int leaf_getter_shape(const JSFunctionBytecode *b)
{
    const uint8_t *p = b->byte_code_buf;
    if (b->var_count != 1 || b->var_ref_count || b->arg_count || p[0] != OP_push_this ||
        p[1] != OP_put_loc0 || p[2] != OP_get_loc0 || p[3] != OP_get_field)
        return 0;
    if (b->byte_code_len == 9 && b->stack_size == 1 && !b->closure_var_count && p[8] == OP_return)
        return 1;
    if (b->byte_code_len == 18 && b->stack_size == 2 && b->closure_var_count == 1 &&
        p[8] == OP_get_var_ref_check && get_u16(p + 9) == 0 && p[11] == OP_get_field &&
        (p[16] == OP_eq || p[16] == OP_strict_eq) && p[17] == OP_return)
        return 2;
    return 0;
}
static void leaf_cache(JSFunctionBytecode *b, unsigned kind)
{
    unsigned bytes = ARM_FRAME_HEADER_BYTES + 16u * (b->var_count + b->stack_size);
    if (bytes > 65535 || b->arg_count > 255 || b->var_count > 255)
        return;
    unsigned char *meta = (unsigned char *)b + FRAME_CALL_META_OFFSET;
    unsigned char *flags =
        (unsigned char *)b + QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE + 1;
    meta[0] = bytes;
    meta[1] = bytes >> 8;
    meta[2] = b->var_count;
    meta[3] = b->arg_count;
    if (kind) {
        *flags = (*flags & 0x8f) | (kind << 4);
        FRAME_KIND(b) &= ~16;
    } else
        FRAME_KIND(b) |= 16;
}
static unsigned leaf_primitive_kind(JSFunctionBytecode *b)
{
    const uint8_t *p = b->byte_code_buf;
    unsigned n = b->byte_code_len, op = p[0];
    if (b->var_count || b->var_ref_count || (FRAME_KIND(b) & 4))
        return 0;
    if (n == 1 && op == OP_return_undef)
        return 2;
    if (n == 2 && p[1] == OP_return) {
        if (op >= OP_push_minus1 && op <= OP_push_7)
            return 1;
        if (op >= OP_get_arg0 && op <= OP_get_arg3)
            return 3;
        if (op == OP_undefined)
            return 2;
        if (op == OP_null)
            return 6;
        if (op == OP_push_true || op == OP_push_false)
            return 7;
    }
    if (n == 4 && p[2] == OP_add && p[3] == OP_return && op >= OP_get_arg0 && op <= OP_get_arg3) {
        if (p[1] >= OP_push_minus1 && p[1] <= OP_push_7)
            return 4;
        if (p[1] >= OP_get_arg0 && p[1] <= OP_get_arg3)
            return 5;
    }
    return 0;
}
static int leaf_character(JSContext *ctx, JSFunctionBytecode *b, const JSValue *argv, int *polls)
{
    static const uint8_t offsets[] = {0, 1, 6, 7, 8, 10, 11, 12, 17, 18, 19, 21, 22, 23, 28, 29};
    static const uint8_t ops[] = {
        OP_get_arg0, OP_push_atom_value, OP_eq, OP_dup,   OP_if_true8, OP_drop,
        OP_get_arg0, OP_push_atom_value, OP_eq, OP_dup,   OP_if_true8, OP_drop,
        OP_get_arg0, OP_push_atom_value, OP_eq, OP_return};
    JSString *s, *atoms[3];
    const uint8_t *p = b->byte_code_buf;
    unsigned i;
    JSAtom atom;
    if (b->byte_code_len != 30 || b->arg_count != 1 || b->var_count || b->var_ref_count ||
        b->closure_var_count || b->stack_size != 2 || b->cpool_count || ctx->interrupt_counter <= 3)
        return -1;
    if (((((unsigned char *)b)[QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE + 1] >> 4) & 7) !=
        6)
        for (i = 0; i < sizeof(offsets); i++)
            if (p[offsets[i]] != ops[i])
                return -1;
    if (p[9] != 20 || p[20] != 9)
        return -1;
    for (i = 0; i < 3; i++) {
        atom = get_u32(p + (i == 0 ? 2 : i == 1 ? 13 : 24));
        if (atom & 0x80000000)
            return -1;
        atoms[i] = ctx->rt->atom_array[atom];
        if (atoms[i]->len != 1 || atoms[i]->kind != JS_STRING_KIND_NORMAL ||
            atoms[i]->is_wide_char || atoms[i]->atom_type != JS_ATOM_TYPE_STRING)
            return -1;
    }
    leaf_cache(b, 6);
    if (JS_VALUE_GET_TAG(argv[0]) != JS_TAG_STRING)
        return -1;
    s = JS_VALUE_GET_STRING(argv[0]);
    if (s->len != 1 || s->kind != JS_STRING_KIND_NORMAL || s->is_wide_char)
        return -1;
    *polls = 2;
    if (str8(s)[0] == str8(atoms[0])[0])
        return 1;
    *polls = 3;
    return str8(s)[0] == str8(atoms[1])[0] || str8(s)[0] == str8(atoms[2])[0];
}
#if defined(QJS_AARCH64_STRING_WORKERS) && defined(QJS_PROPERTY_IC)
extern uint64_t JS_FrameLocaleCompareCompound(JSContext *, JSFunctionBytecode *, const JSValue *,
                                              const JSValue *);
#endif
LEAF_CODE JSValue JS_FrameAArch64CallLeaf(JSContext *ctx, JSValueConst function,
                                          JSValueConst receiver, int argc, const JSValue *argv,
                                          unsigned scope)
{
    JSRuntime *rt = ctx->rt;
    JSObject *f;
    JSFunctionBytecode *b;
    const uint8_t *p;
    unsigned modes, kind, shape, rawkind;
    int32_t a, c;
    int64_t wide;
    JSValue result = JS_EXCEPTION, v, r;
    int polls = 1;
    if ((unsigned)argc > 65535 || !JS_IsObject(function))
        return JS_EXCEPTION;
    f = JS_VALUE_GET_OBJ(function);
    if (f->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return JS_EXCEPTION;
    b = f->u.func.function_bytecode;
    p = b->byte_code_buf;
    if (!(FRAME_KIND(b) & 1) || b->var_ref_count || b->realm != ctx || argc < b->arg_count ||
        ctx->interrupt_counter <= 1 ||
        ((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 1] != 1 ||
        ((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 3] == 2 ||
        (rt->dump_flags & JS_DUMP_BYTECODE_STEP))
        return JS_EXCEPTION;
    if (scope != 1) {
        if ((FRAME_KIND(b) & 4) || (scope == 0 && b->stack_size > 2) ||
            js_check_stack_overflow(rt, (size_t)argc * 16 + 5280))
            return JS_EXCEPTION;
        if (!((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 3]) {
            ((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 3] =
                qjs_internal_interp_register_disabled() ? 2 : 1;
            if (((unsigned char *)rt)[offsetof(JSRuntime, current_stack_frame) - 3] != 1)
                return JS_EXCEPTION;
        }
    }
    modes = leaf_modes(rt);
    shape = (b->byte_code_len == 9 || b->byte_code_len == 18) ? leaf_getter_shape(b) : 0;
    if ((modes & (LEAF_CHILD | LEAF_GETTER)) == (LEAF_CHILD | LEAF_GETTER) && shape) {
        if (!leaf_own(receiver, get_u32(p + 4), &v))
            return JS_EXCEPTION;
        if (shape == 1) {
            if (JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v))
                return JS_EXCEPTION;
            result = JS_DupValue(ctx, v);
            LEAF_COUNT(3);
            goto success;
        }
        if (JS_VALUE_GET_TAG(v) != JS_TAG_SYMBOL ||
            !leaf_own(*f->u.func.var_refs[0]->pvalue, get_u32(p + 12), &r) ||
            JS_VALUE_GET_TAG(r) != JS_TAG_SYMBOL)
            return JS_EXCEPTION;
        result = JS_MKVAL(JS_TAG_BOOL, JS_VALUE_GET_PTR(v) == JS_VALUE_GET_PTR(r));
        LEAF_COUNT(4);
        goto success;
    }
#if defined(QJS_AARCH64_STRING_WORKERS) && defined(QJS_PROPERTY_IC)
    if (scope && (modes & (LEAF_PRIMITIVE | LEAF_COMPOUND)) == (LEAF_PRIMITIVE | LEAF_COMPOUND) &&
        b->byte_code_len == 22 && argc >= 1 && ctx->interrupt_counter > 2 &&
        ((((((unsigned char *)b)[QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE + 1] >> 4) &
           7) == 6) ||
         (JS_FrameLocaleCompareCompound(ctx, b, NULL, NULL) & (UINT64_C(1) << 33)))) {
        leaf_cache(b, 6);
        uint64_t packed = JS_FrameLocaleCompareCompound(ctx, b, argv, &receiver);
        if (packed & (UINT64_C(1) << 32)) {
            result = JS_MKVAL(JS_TAG_INT, (int32_t)packed);
            polls = 2;
            LEAF_COUNT(8);
            goto success;
        }
    }
#endif
    if (b->var_count) {
        if (!shape && b->byte_code_len != 19 && b->byte_code_len != 20 && b->byte_code_len != 21 &&
            b->byte_code_len != 22 && b->byte_code_len != 33 && b->byte_code_len != 35)
            leaf_cache(b, 0);
        return JS_EXCEPTION;
    }
    rawkind =
        (((unsigned char *)b)[QJS_ABI_BIT_JSFunctionBytecode_is_strict_mode_BYTE + 1] >> 4) & 7;
    kind = rawkind;
    if (kind == 6 && p[0] != OP_null)
        kind = 0;
    if ((modes & LEAF_PRIMITIVE) && !rawkind && !(FRAME_KIND(b) & 16)) {
        kind = leaf_primitive_kind(b);
        if (!kind)
            leaf_cache(b, 0);
    }
    if ((modes & LEAF_PRIMITIVE) && kind && scope) {
        leaf_cache(b, kind);
        switch (kind) {
        case 1:
            result = JS_MKVAL(JS_TAG_INT, (int)p[0] - OP_push_0);
            break;
        case 2:
            result = JS_UNDEFINED;
            break;
        case 6:
            result = JS_NULL;
            break;
        case 7:
            result = JS_MKVAL(JS_TAG_BOOL, p[0] == OP_push_true);
            break;
        default:
            a = p[0] - OP_get_arg0;
            if (a >= argc)
                return JS_EXCEPTION;
            v = argv[a];
            if (kind == 3) {
                if (JS_IsException(v))
                    return JS_EXCEPTION;
                result = JS_DupValue(ctx, v);
                break;
            }
            if (JS_VALUE_GET_TAG(v) != JS_TAG_INT)
                return JS_EXCEPTION;
            a = JS_VALUE_GET_INT(v);
            if (kind == 4)
                c = (int)p[1] - OP_push_0;
            else {
                c = p[1] - OP_get_arg0;
                if (c >= argc || JS_VALUE_GET_TAG(argv[c]) != JS_TAG_INT)
                    return JS_EXCEPTION;
                c = JS_VALUE_GET_INT(argv[c]);
            }
            wide = (int64_t)a + c;
            if (wide < INT32_MIN || wide > INT32_MAX)
                return JS_EXCEPTION;
            result = JS_MKVAL(JS_TAG_INT, (int32_t)wide);
        }
        LEAF_COUNT(5);
        goto success;
    }
    if (modes & LEAF_CHILD) {
        if (b->byte_code_len == 2 && p[1] == OP_return && p[0] >= OP_push_minus1 &&
            p[0] <= OP_push_7 && !scope) {
            result = JS_MKVAL(JS_TAG_INT, (int)p[0] - OP_push_0);
            goto simple;
        }
        if (b->byte_code_len == 4 && p[0] == OP_get_arg0 && p[1] >= OP_push_minus1 &&
            p[1] <= OP_push_7 && p[2] == OP_add && p[3] == OP_return && argc &&
            JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT) {
            wide = (int64_t)JS_VALUE_GET_INT(argv[0]) + (int)p[1] - OP_push_0;
            if (wide < INT32_MIN || wide > INT32_MAX)
                return JS_EXCEPTION;
            result = JS_MKVAL(JS_TAG_INT, (int32_t)wide);
            goto simple;
        }
        if (scope && b->byte_code_len == 8 && argc >= 2 && p[0] == OP_get_arg0 &&
            p[1] == OP_get_arg1 && p[2] == OP_add && p[3] >= OP_push_minus1 && p[3] <= OP_push_7 &&
            p[4] == OP_add && p[5] == OP_push_0 && p[6] == OP_or && p[7] == OP_return &&
            JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT && JS_VALUE_GET_TAG(argv[1]) == JS_TAG_INT) {
            a = (int32_t)((uint32_t)JS_VALUE_GET_INT(argv[0]) +
                          (uint32_t)JS_VALUE_GET_INT(argv[1]) + (uint32_t)((int)p[3] - OP_push_0));
            result = JS_MKVAL(JS_TAG_INT, a);
            LEAF_COUNT(1);
            goto success;
        }
        if (scope && b->byte_code_len == 14 && argc && b->closure_var_count == 1 &&
            b->stack_size == 2 && p[0] == OP_get_var_ref_check && get_u16(p + 1) == 0 &&
            p[3] == OP_get_arg0 && p[4] == OP_add && p[5] >= OP_push_minus1 && p[5] <= OP_push_7 &&
            p[6] == OP_add && p[7] == OP_push_0 && p[8] == OP_or && p[9] == OP_dup &&
            p[10] == OP_put_var_ref_check && get_u16(p + 11) == 0 && p[13] == OP_return_undef) {
            JSVarRef *ref = f->u.func.var_refs[0];
            if (ref->is_const || JS_VALUE_GET_TAG(*ref->pvalue) != JS_TAG_INT ||
                JS_VALUE_GET_TAG(argv[0]) != JS_TAG_INT)
                return JS_EXCEPTION;
            a = (int32_t)((uint32_t)JS_VALUE_GET_INT(*ref->pvalue) +
                          (uint32_t)JS_VALUE_GET_INT(argv[0]) + (uint32_t)((int)p[5] - OP_push_0));
            *ref->pvalue = JS_MKVAL(JS_TAG_INT, a);
            result = JS_UNDEFINED;
            LEAF_COUNT(2);
            goto success;
        }
    }
    if (modes & LEAF_EXPR) {
        result = leaf_expression(f, argc, argv);
        if (!JS_IsException(result)) {
            LEAF_COUNT(6);
            goto success;
        }
    }
    if (!scope)
        return JS_EXCEPTION;
    if ((modes & (LEAF_PRIMITIVE | LEAF_CHAR)) == (LEAF_PRIMITIVE | LEAF_CHAR) && argc &&
        (a = leaf_character(ctx, b, argv, &polls)) >= 0) {
        result = JS_MKVAL(JS_TAG_BOOL, a);
        LEAF_COUNT(7);
        goto success;
    }
    if (!shape && !kind && !leaf_expr_syntax_ok(b) &&
        !(b->byte_code_len == 8 && p[0] == OP_get_arg0 && p[1] == OP_get_arg1 && p[6] == OP_or) &&
        !(b->byte_code_len == 14 && b->closure_var_count == 1 && p[0] == OP_get_var_ref_check &&
          p[13] == OP_return_undef) &&
        b->byte_code_len != 8 && b->byte_code_len != 9 && b->byte_code_len != 22 &&
        b->byte_code_len != 30)
        leaf_cache(b, 0);
    return JS_EXCEPTION;
simple:
    LEAF_COUNT(0);
success:
    ctx->interrupt_counter -= polls;
    LEAF_COUNT(scope ? 10 : 9);
    return result;
}

_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue, "actual target JSValue");
_Static_assert(sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode,
               "actual target bytecode");
_Static_assert(offsetof(JSRuntime, module_loader_has_attr) + 2 <= offsetof(JSRuntime, u),
               "original runtime leaf byte remains padding");
_Static_assert(__builtin_types_compatible_p(__typeof__(&JS_FrameAArch64CallLeaf),
                                            JSValue (*)(JSContext *, JSValueConst, JSValueConst,
                                                        int, const JSValue *, unsigned)),
               "actual typed AAPCS64 call boundary");

#include "src/common/property/fast-transition-resize.inc"
