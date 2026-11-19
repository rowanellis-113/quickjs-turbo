/* Common string kernel in the existing isolated native builtin TU.
 * Latin-1 is already NFC (Unicode UAX #15 section 1.3). Match NG's existing
 * normalized code-point order and exact -1/0/1 result, without ICU semantics.
 * Borrowed flat string inputs need no conversion, allocation or release.
 * Ropes, coercions, wide/mixed strings and OFF use the original builtin once.
 */
#ifdef _MSC_VER
extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);
extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);
#pragma section(".qjslfm", read, write)
__declspec(allocate(".qjslfm"))
#else
__attribute__((section(".qjslfm"), aligned(1)))
#endif
static unsigned char js_frame_locale_compare_control;

JSValue JS_FrameLocaleCompare(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    JSString *a, *b;
    unsigned char mode;
    int cmp;
    if (argc <= 0 || JS_VALUE_GET_TAG(this_val) != JS_TAG_STRING ||
        JS_VALUE_GET_TAG(argv[0]) != JS_TAG_STRING)
        goto original;
    a = JS_VALUE_GET_STRING(this_val);
    b = JS_VALUE_GET_STRING(argv[0]);
    if (a->is_wide_char || b->is_wide_char)
        goto original;
#ifdef _MSC_VER
    mode = JS_FrameCallMetaLoadByte(&js_frame_locale_compare_control);
#else
    mode = __atomic_load_n(&js_frame_locale_compare_control, __ATOMIC_RELAXED);
#endif
    if (unlikely(mode == 0)) {
        unsigned char desired = getenv("QJS_DISABLE_LOCALE_COMPARE_LATIN1") ? 2 : 1;
#ifdef _MSC_VER
        mode = JS_FrameCallMetaInitByte(&js_frame_locale_compare_control, desired);
#else
        __atomic_compare_exchange_n(&js_frame_locale_compare_control, &mode, desired, false,
                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);
#endif
        if (!mode)
            mode = desired;
    }
    if (mode != 1)
        goto original;
    /* str8() resolves normal, slice and indirect storage; explicit lengths
     * preserve embedded NULs. No Unicode unit exceeds 255 on this branch. */
    cmp = memcmp(str8(a), str8(b), min_int(a->len, b->len));
    cmp = cmp ? (cmp > 0) - (cmp < 0) : compare_u32(a->len, b->len);
    return js_int32(cmp);
original:
    return js_string_localeCompare(ctx, this_val, argc, argv);
}

/* Native compound interpreter entry. This does not call the general
 * locale builtin:mode0/2fall back BEFORE eliding any frame,so its original
 * first-use/OFF normalization allocation and all observable work stay rooted. */
#if defined(_WIN64) && (defined(__GNUC__) || defined(_MSC_VER)) && defined(QJS_PROPERTY_IC)
#ifdef _MSC_VER
#define CALL_LINK_INLINE __forceinline
#define COMPOUND_NOINLINE __declspec(noinline)
#else
#define CALL_LINK_INLINE inline __attribute__((always_inline))
#define COMPOUND_NOINLINE __attribute__((noipa))
#endif
/* Complete immutable JS wrapper / borrowed ordinary-data / pure builtin proof.
 * No allocation, observable callback, RC/store, poll, or exception. The
 * native compound entry borrows operands only while this proof remains live. */
extern JSValue JS_FrameLocaleCompare(JSContext *, JSValueConst, int, JSValueConst *);
static CALL_LINK_INLINE JSCFunction *compound_builtin(void)
{
    return JS_FrameLocaleCompare;
}
enum {
    COMPOUND_SHAPE = 1,
    COMPOUND_MODE = 2,
    COMPOUND_OBJECT = 3,
    COMPOUND_FIELDS = 4,
    COMPOUND_STRINGS = 5,
    COMPOUND_PROTO = 6,
    COMPOUND_BUILTIN = 7,
    COMPOUND_PIC = 8,
    COMPOUND_HASH = 9
};
_Static_assert(sizeof(JSFunctionBytecode) == 152 &&
                   offsetof(JSFunctionBytecode, property_ic) == 144 && sizeof(JSValue) == 16 &&
                   sizeof(JSPropertyICSite) == 64 && sizeof(JSPropertyICWay) == 40,
               "compound proof exact current private ABI");

static CALL_LINK_INLINE int compound_shape(const JSFunctionBytecode *b)
{
    const uint8_t *c = b->byte_code_buf;
    return b->byte_code_len == 22 && b->arg_count == 1 && b->var_count == 1 &&
           b->var_ref_count == 0 && b->closure_var_count == 0 && b->cpool_count == 0 &&
           b->stack_size == 3 && b->func_kind == 0 &&
           (((const unsigned char *)b)[offsetof(JSFunctionBytecode, byte_code_buf) - 1] & 1) &&
           c[0] == OP_push_this && c[1] == OP_put_loc0 && c[2] == OP_get_loc0 &&
           c[3] == OP_get_field && c[8] == OP_get_field2 && c[13] == OP_get_arg0 &&
           c[14] == OP_get_field && c[19] == OP_tail_call_method && get_u16(c + 20) == 1;
}

/* Equivalent to the pinned find_own_property's nonobserving shape hash walk.
 * Retain explicit plain-data proof;no prototype walk or exotic invocation. */
static CALL_LINK_INLINE JSValue *compound_hash_slot(JSObject *p, JSAtom atom)
{
    JSShape *sh = p->shape;
    uint32_t h = ((uint32_t *)(void *)sh)[-((intptr_t)((uintptr_t)atom & sh->prop_hash_mask)) - 1];
    while (h) {
        JSShapeProperty *pr = &sh->prop[h - 1];
        if (pr->atom == atom)
            return (pr->flags & JS_PROP_TMASK) ? NULL : &p->prop[h - 1].u.value;
        h = pr->hash_next;
    }
    return NULL;
}

static CALL_LINK_INLINE JSValue *compound_own_slot(JSObject *p, JSAtom atom, JSPropertyICSite *site,
                                                   unsigned *pic)
{
    if (site && (uintptr_t)site > 3 && !site->megamorphic && (p->shape->is_hashed & 1)) {
        for (unsigned i = 0; i < site->count; i++) {
            JSPropertyICWay *w = i ? &site->secondary[i - 1] : &site->primary;
            if (w->shape == p->shape && w->kind == JS_IC_OWN && w->slot < p->shape->prop_count &&
                p->shape->prop[w->slot].atom == atom &&
                !(p->shape->prop[w->slot].flags & JS_PROP_TMASK)) {
                (*pic)++;
                return &p->prop[w->slot].u.value;
            }
        }
    }
    return compound_hash_slot(p, atom);
}

static CALL_LINK_INLINE unsigned compound_method(JSContext *ctx, JSFunctionBytecode *b)
{
    JSAtom name;
    JSObject *proto, *fn;
    JSValue *method;
    name = get_u32(b->byte_code_buf + 9);
    /* Primitive own index/length must never be replaced by a prototype slot. */
    if ((name & UINT32_C(0x80000000)) || name == JS_ATOM_length ||
        !JS_IsObject(ctx->class_proto[JS_CLASS_STRING]))
        return 0;
    proto = JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_STRING]);
    /* Same exact built-in-string / nonexotic ordinary-object protocol as the
     * existing StringProto native kernel. Arbitrary exotic objects fall back. */
    if (proto->class_id != JS_CLASS_STRING &&
        (proto->class_id != JS_CLASS_OBJECT || proto->is_exotic))
        return 0;
    method = compound_hash_slot(proto, name);
    if (!method || !JS_IsObject(*method))
        return 0;
    fn = JS_VALUE_GET_OBJ(*method);
    if (fn->class_id != JS_CLASS_C_FUNCTION || fn->u.cfunc.cproto != JS_CFUNC_generic ||
        fn->u.cfunc.length != 1 || fn->u.cfunc.realm != ctx ||
        fn->u.cfunc.c_function.generic != compound_builtin())
        return 0;
    return 1;
}

static CALL_LINK_INLINE unsigned compound_proof(JSContext *ctx, JSFunctionBytecode *b,
                                                const JSValue *thisp, const JSValue *args,
                                                JSString **ap, JSString **bp)
{
    JSObject *x, *y;
    JSValue *a, *v;
    JSPropertyICSite *s0 = NULL, *s1 = NULL;
    JSPropertyIC *ic;
    unsigned pic = 0;
    if (!compound_shape(b))
        return COMPOUND_SHAPE;
    if (ctx != b->realm || ctx->rt->property_ic_mode != 1)
        return COMPOUND_MODE;
    if (!args || !thisp || !JS_IsObject(*thisp) || !JS_IsObject(args[0]))
        return COMPOUND_OBJECT;
    x = JS_VALUE_GET_OBJ(*thisp);
    y = JS_VALUE_GET_OBJ(args[0]);
    if (x->is_exotic || y->is_exotic)
        return COMPOUND_OBJECT;
    ic = b->property_ic;
    if ((uintptr_t)ic > 1 && ic->map_count > 3) {
        s0 = ic->map[0];
        s1 = ic->map[3];
    }
    a = compound_own_slot(x, get_u32(b->byte_code_buf + 4), s0, &pic);
    v = compound_own_slot(y, get_u32(b->byte_code_buf + 15), s1, &pic);
    if (!a || !v)
        return COMPOUND_FIELDS;
    if (JS_VALUE_GET_TAG(*a) != JS_TAG_STRING || JS_VALUE_GET_TAG(*v) != JS_TAG_STRING ||
        JS_VALUE_GET_STRING(*a)->is_wide_char || JS_VALUE_GET_STRING(*v)->is_wide_char)
        return COMPOUND_STRINGS;
    if (!compound_method(ctx, b))
        return COMPOUND_BUILTIN;
    if (ap)
        *ap = JS_VALUE_GET_STRING(*a);
    if (bp)
        *bp = JS_VALUE_GET_STRING(*v);
    return pic == 2 ? COMPOUND_PIC : COMPOUND_HASH;
}

COMPOUND_NOINLINE uint64_t JS_FrameLocaleCompareCompound(JSContext *ctx, JSFunctionBytecode *b,
                                                         const JSValue *args, const JSValue *thisp)
{
    JSString *a, *v;
    int cmp;
    /* NULL/NULL is a cold,nonobserving admission request. It cannot make a
     * callback or inspect caller arguments;rejects acquire ordinary metadata. */
    if (!args && !thisp) {
        if (ctx != b->realm || ctx->rt->property_ic_mode != 1 || !compound_shape(b) ||
            !compound_method(ctx, b))
            return 0;
        return UINT64_C(1) << 33;
    }
#ifdef _MSC_VER
    if (JS_FrameCallMetaLoadByte(&js_frame_locale_compare_control) != 1 ||
#else
    if (__atomic_load_n(&js_frame_locale_compare_control, __ATOMIC_RELAXED) != 1 ||
#endif
        compound_proof(ctx, b, thisp, args, &a, &v) < COMPOUND_PIC)
        return 0;
    cmp = memcmp(str8(a), str8(v), min_int(a->len, v->len));
    cmp = cmp ? (cmp > 0) - (cmp < 0) : compare_u32(a->len, v->len);
    return (UINT64_C(1) << 32) | (uint32_t)cmp;
}
#undef CALL_LINK_INLINE
#undef COMPOUND_NOINLINE
#endif
