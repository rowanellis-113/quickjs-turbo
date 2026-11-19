#include "src/common/regexp/flag-atoms.inc"

/* MIT. Intrinsic empty-string @@replace, common native/portable C.
 * Live descriptors prove that skipped gets/conversions cannot execute JS.
 * Observable hooks, reentry, ropes and sticky expressions keep the fallback.
 */
int lre_get_alloc_count(const uint8_t *bc_buf);

/* This private ablation switch is a process-start configuration. Cache its
 * first observation with the core's atomic abstraction; object/property/realm
 * guards below are still live on every call. Toolchains without core atomics
 * retain the uncached lookup and the same JavaScript semantics.
 */
static inline bool js_regexp_empty_enabled(void)
{
#ifdef CONFIG_ATOMICS
    static _Atomic unsigned char control;
    unsigned char mode = atomic_load(&control);
    if (!mode) {
        unsigned char desired = getenv("QJS_DISABLE_REGEXP_REPLACE_EMPTY") ? 2 : 1;
        if (atomic_compare_exchange_strong(&control, &mode, desired))
            mode = desired;
    }
    return mode == 1;
#else
    return !getenv("QJS_DISABLE_REGEXP_REPLACE_EMPTY");
#endif
}

static JSShapeProperty *js_regexp_empty_property(JSProperty **property, JSObject *object,
                                                 JSAtom atom)
{
    while (object && !object->is_exotic) {
        JSShapeProperty *shape = find_own_property(property, object, atom);
        if (shape)
            return shape;
        object = object->shape->proto;
    }
    return NULL;
}

static bool js_regexp_empty_guard(JSContext *ctx, JSValueConst receiver, JSValueConst input,
                                  JSValueConst replacement, int *regexp_flags,
                                  JSProperty **last_index)
{
    static const struct {
        char name[12];
        uint8_t length;
        uint16_t mask;
        uint32_t hash;
    } flags[] = {
        /* hash_string8(name, length, JS_ATOM_TYPE_STRING), masked. */
        {"hasIndices", 10, LRE_FLAG_INDICES, 0x004861b6u},
        {"global", 6, LRE_FLAG_GLOBAL, 0x0e4f2c3cu},
        {"ignoreCase", 10, LRE_FLAG_IGNORECASE, 0x00ed3b3bu},
        {"multiline", 9, LRE_FLAG_MULTILINE, 0x0c389e2cu},
        {"dotAll", 6, LRE_FLAG_DOTALL, 0x045b0519u},
        {"unicode", 7, LRE_FLAG_UNICODE, 0x03d69fccu},
        {"unicodeSets", 11, LRE_FLAG_UNICODE_SETS, 0x0f0c3175u},
        {"sticky", 6, LRE_FLAG_STICKY, 0x0c27c592u},
    };
    JSObject *object, *getter;
    JSProperty *property;
    JSShapeProperty *shape;
    int bits;

    if (JS_VALUE_GET_TAG(receiver) != JS_TAG_OBJECT || JS_VALUE_GET_TAG(input) != JS_TAG_STRING ||
        JS_VALUE_GET_TAG(replacement) != JS_TAG_STRING || JS_VALUE_GET_STRING(replacement)->len ||
        !JS_IsObject(ctx->class_proto[JS_CLASS_REGEXP]) || !JS_IsObject(ctx->regexp_ctor) ||
        ctx->rt->interrupt_handler || js_check_stack_overflow(ctx->rt, 4096) ||
        !js_regexp_empty_enabled())
        return false;
    object = JS_VALUE_GET_OBJ(receiver);
    if (object->class_id != JS_CLASS_REGEXP || object->is_exotic ||
        object->shape->proto != JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_REGEXP]) ||
        !object->u.regexp.bytecode)
        return false;
    bits = lre_get_flags(str8(object->u.regexp.bytecode));
    if (bits & LRE_FLAG_STICKY)
        return false;

    /* Even nonglobal native exec performs ToLength(lastIndex) before ignoring
     * it. Admit only an own integer data value; coercible objects must run JS.
     * A global reset must be writable and must not release an object value.
     */
    shape = find_own_property(last_index, object, JS_ATOM_lastIndex);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
        JS_VALUE_GET_TAG((*last_index)->u.value) != JS_TAG_INT ||
        ((bits & LRE_FLAG_GLOBAL) && !(shape->flags & JS_PROP_WRITABLE)))
        return false;
    /* The inherited global-empty path also reads constructor. Preserve its
     * fallback behavior when that read can be observable or changes identity.
     */
    shape = js_regexp_empty_property(&property, object, JS_ATOM_constructor);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
        !js_same_value(ctx, property->u.value, ctx->regexp_ctor))
        return false;
    shape = js_regexp_empty_property(&property, object, JS_ATOM_exec);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
        !JS_IsCFunction(ctx, property->u.value,
#ifdef QJS_REGEXP_EMPTY_NATIVE
                        JS_FrameRegExpExec,
#else
                        js_regexp_exec,
#endif
                        0) ||
        JS_VALUE_GET_OBJ(property->u.value)->u.cfunc.realm != ctx)
        return false;
    shape = js_regexp_empty_property(&property, object, JS_ATOM_flags);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_GETSET ||
        !(getter = property->u.getset.getter) || getter->class_id != JS_CLASS_C_FUNCTION ||
        getter->u.cfunc.cproto != JS_CFUNC_getter || getter->u.cfunc.realm != ctx)
        return false;
    if (getter->u.cfunc.c_function.getter != js_regexp_get_flags
#ifdef QJS_REGEXP_EMPTY_NATIVE
        && getter->u.cfunc.c_function.getter != JS_RegExpOwnedFlags
#endif
    )
        return false;
    for (unsigned i = 0; i < countof(flags); i++) {
        JSAtom atom =
            js_regexp_borrow_flag_atom(ctx->rt, flags[i].name, flags[i].length, flags[i].hash);
        if (atom == JS_ATOM_NULL)
            return false;
        shape = js_regexp_empty_property(&property, object, atom);
        if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_GETSET ||
            !(getter = property->u.getset.getter) || getter->class_id != JS_CLASS_C_FUNCTION ||
            getter->u.cfunc.cproto != JS_CFUNC_getter_magic || getter->u.cfunc.realm != ctx ||
            getter->u.cfunc.c_function.getter_magic != js_regexp_get_flag ||
            getter->u.cfunc.magic != flags[i].mask)
            return false;
    }
    *regexp_flags = bits;
    return true;
}

static JSValue js_regexp_empty_search(JSContext *ctx, JSValueConst receiver, JSValueConst input,
                                      int flags, JSProperty *last_index)
{
    uint8_t *small_capture[64], **capture = small_capture;
    JSString *string = JS_VALUE_GET_STRING(input);
    const uint8_t *bytecode = str8(JS_VALUE_GET_OBJ(receiver)->u.regexp.bytecode);
    int slots = lre_get_alloc_count(bytecode), shift = string->is_wide_char;
    uint32_t size = string->len, search = 0, next = 0;
    bool global = (flags & LRE_FLAG_GLOBAL) != 0;
    bool unicode = (flags & (LRE_FLAG_UNICODE | LRE_FLAG_UNICODE_SETS)) != 0;
    bool matched = false;
    StringBuffer buffer, *b = &buffer;
    JSValue result;

    string_buffer_init(ctx, b, 0);
    /* Guarded own integer: no reference release, setter, allocation or reentry.
     * It remains zero throughout the intrinsic global-empty deletion loop.
     */
    if (global)
        last_index->u.value = js_int32(0);
    if (slots > countof(small_capture)) {
        capture = js_malloc(ctx, (size_t)slots * sizeof(*capture));
        if (!capture)
            goto exception;
    }
    do {
        int status = lre_exec(capture, bytecode, str8(string), search, size, shift, ctx);
        uint32_t start, end;
        if (status < 0) {
            if (status == LRE_RET_TIMEOUT)
                JS_ThrowInterrupted(ctx);
            else if (status == LRE_RET_BYTECODE_ERROR)
                JS_ThrowInternalError(ctx, "corrupted bytecode in regexp execution");
            else
                JS_ThrowInternalError(ctx, "out of memory in regexp execution");
            goto exception;
        }
        if (status != 1)
            break;
        start = (uint32_t)((capture[0] - str8(string)) >> shift);
        end = (uint32_t)((capture[1] - str8(string)) >> shift);
        /* An empty match removes nothing. Keep scanning globally without
         * copying the subject one unchanged fragment at a time.
         */
        if (start == end) {
            if (!global)
                break;
            search = string_advance_index(string, end, unicode);
            continue;
        }
        matched = true;
        if (next < start && string_buffer_concat(b, string, next, start))
            goto exception;
        next = end;
        if (!global)
            break;
        search = end == start ? string_advance_index(string, end, unicode) : end;
    } while (search <= size);
    if (!matched) {
        string_buffer_free(b);
        result = JS_DupValue(ctx, input);
    } else {
        if (string_buffer_concat(b, string, next, size))
            goto exception;
        result = string_buffer_end(b);
    }
    goto done;
exception:
    string_buffer_free(b);
    result = JS_EXCEPTION;
done:
    if (capture != small_capture)
        js_free(ctx, capture);
    return result;
}
