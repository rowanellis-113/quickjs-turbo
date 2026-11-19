/* Live builtin flag-getter recognition; no shape/realm/object cache. MIT. */
#ifdef _MSC_VER
extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);
extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);
#pragma section(".qjsrfm", read, write)
__declspec(allocate(".qjsrfm"))
#else
__attribute__((section(".qjsrfm")))
#endif
static unsigned char js_frame_regexp_flags_control;

static inline unsigned char js_frame_regexp_flags_mode(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode = JS_FrameCallMetaLoadByte(&js_frame_regexp_flags_control);
#else
    mode = __atomic_load_n(&js_frame_regexp_flags_control, __ATOMIC_RELAXED);
#endif
    if (!mode) {
        unsigned char desired = getenv("QJS_DISABLE_REGEXP_FLAGS_LEAF") ? 2 : 1;
        if (getenv("QJS_DISABLE_REGEXP_FLAGS_BATCH"))
            desired |= 4;
#ifdef _MSC_VER
        mode = JS_FrameCallMetaInitByte(&js_frame_regexp_flags_control, desired);
#else
        __atomic_compare_exchange_n(&js_frame_regexp_flags_control, &mode, desired, false,
                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);
#endif
        if (!mode)
            mode = desired;
    }
    return mode;
}

static JSValue js_frame_regexp_flag_property(JSContext *ctx, JSValueConst obj, JSAtom atom)
{
    JSObject *receiver = JS_VALUE_GET_OBJ(obj), *object = receiver;
    JSProperty *property;
    JSShapeProperty *shape;
    JSObject *getter;

    /* The public getter admits a real RegExp before calling this helper.
     * Inspect each property anew, in specification order. No lookup may cross
     * an exotic object: its get trap is an observable operation. */
    while (object && !object->is_exotic) {
        shape = find_own_property(&property, object, atom);
        if (shape) {
            if ((shape->flags & JS_PROP_TMASK) != JS_PROP_GETSET ||
                !(getter = property->u.getset.getter) || getter->class_id != JS_CLASS_C_FUNCTION ||
                getter->u.cfunc.length != 0 || getter->u.cfunc.cproto != JS_CFUNC_getter_magic ||
                getter->u.cfunc.c_function.getter_magic != js_regexp_get_flag)
                break;
            /* Polling can reenter JS and mutate this property. The original
             * lookup/call path owns its chosen getter across that boundary.
             * Use that entire path when a poll or stack check is due. */
            if (ctx->interrupt_counter <= 1 || js_check_stack_overflow(ctx->rt, 1024))
                break;
            --ctx->interrupt_counter;
            return js_bool(lre_get_flags(str8(receiver->u.regexp.bytecode)) &
                           getter->u.cfunc.magic);
        }
        object = object->shape->proto;
    }
    return JS_GetProperty(ctx, obj, atom);
}

static JSValue js_frame_regexp_flag_property_str(JSContext *ctx, JSValueConst obj, const char *name)
{
    JSAtom atom = JS_NewAtom(ctx, name);
    JSValue value;
    if (atom == JS_ATOM_NULL)
        return JS_EXCEPTION;
    value = js_frame_regexp_flag_property(ctx, obj, atom);
    JS_FreeAtom(ctx, atom);
    return value;
}

/* Verified live intrinsic descriptors, without shape/object/realm caches. MIT. */
static inline bool js_frame_regexp_flag_atom_name(JSContext *ctx, JSAtom atom, const char *name,
                                                  size_t len)
{
    /* A Symbol description can have the same text as a string key. */
    JSAtomStruct *s;
    if (!atom || (atom & JS_ATOM_TAG_INT))
        return false;
    s = ctx->rt->atom_array[atom];
    return s && s->atom_type == JS_ATOM_TYPE_STRING && s->len == len && !s->is_wide_char &&
           !memcmp(str8(s), name, len);
}

static bool js_frame_regexp_flags_batch(JSContext *ctx, JSValueConst value, int *flags)
{
    JSObject *receiver = JS_VALUE_GET_OBJ(value), *proto;
    JSShapeProperty *shape;
    JSProperty *property;
    JSObject *getter;
    /* The caller has checked the actual RegExp class. The existing canonical
     * shape owns just lastIndex and its original immediate prototype. This
     * equality excludes own overrides without keeping any weak shape hint. */
    if (receiver->is_exotic || receiver->shape != ctx->regexp_shape ||
        ctx->interrupt_counter <= 8 || js_check_stack_overflow(ctx->rt, 1024))
        return false;
    proto = receiver->shape->proto;
    if (!proto || proto->is_exotic || proto->shape->prop_count < 10)
        return false;
    shape = proto->shape->prop + 2;
    property = proto->prop + 2;
    /* The generator pins the initializer order. Recheck every atom,
     * descriptor kind, function identity, ABI and magic on every call.
     * No getter, proxy trap, poll or allocation runs during this proof. */
#define QJS_FLAG_BUILTIN(index, mask)                                                              \
    do {                                                                                           \
        if ((shape[index].flags & JS_PROP_TMASK) != JS_PROP_GETSET ||                              \
            !(getter = property[index].u.getset.getter) ||                                         \
            getter->class_id != JS_CLASS_C_FUNCTION || getter->u.cfunc.length != 0 ||              \
            getter->u.cfunc.cproto != JS_CFUNC_getter_magic ||                                     \
            getter->u.cfunc.c_function.getter_magic != js_regexp_get_flag ||                       \
            getter->u.cfunc.magic != (mask))                                                       \
            return false;                                                                          \
    } while (0)
#define QJS_FLAG_NAMED(index, name, mask)                                                          \
    do {                                                                                           \
        if (!js_frame_regexp_flag_atom_name(ctx, shape[index].atom, name, sizeof(name) - 1))       \
            return false;                                                                          \
        QJS_FLAG_BUILTIN(index, mask);                                                             \
    } while (0)
    if (shape[0].atom != JS_ATOM_global || shape[4].atom != JS_ATOM_unicode)
        return false;
    QJS_FLAG_BUILTIN(0, LRE_FLAG_GLOBAL);
    QJS_FLAG_NAMED(1, "ignoreCase", LRE_FLAG_IGNORECASE);
    QJS_FLAG_NAMED(2, "multiline", LRE_FLAG_MULTILINE);
    QJS_FLAG_NAMED(3, "dotAll", LRE_FLAG_DOTALL);
    QJS_FLAG_BUILTIN(4, LRE_FLAG_UNICODE);
    QJS_FLAG_NAMED(5, "unicodeSets", LRE_FLAG_UNICODE_SETS);
    QJS_FLAG_NAMED(6, "sticky", LRE_FLAG_STICKY);
    QJS_FLAG_NAMED(7, "hasIndices", LRE_FLAG_INDICES);
#undef QJS_FLAG_NAMED
#undef QJS_FLAG_BUILTIN
    /* No poll can be due in these eight intrinsic reads. When one is due,
     * the complete existing per-property path retains getter selection and
     * permits the interrupt callback to mutate subsequent properties. */
    ctx->interrupt_counter -= 8;
    *flags = lre_get_flags(str8(receiver->u.regexp.bytecode));
    return true;
}
