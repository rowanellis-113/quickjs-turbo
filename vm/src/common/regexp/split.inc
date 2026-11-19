#include "src/common/regexp/flag-atoms.inc"

/* Direct @@split search for an unchanged intrinsic RegExp. MIT.
 * All guards are live descriptor reads without user-code execution. The
 * original algorithm remains the fallback for observable hooks and reentry.
 * This fragment is shared by native and portable private-source workers.
 */
/* The pinned core's private header has the old public RegExp declarations. */
int lre_get_alloc_count(const uint8_t *bc_buf);

static JSShapeProperty *js_regexp_split_property(JSProperty **property, JSObject *object,
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

static bool js_regexp_split_data(JSContext *ctx, JSObject *object, JSAtom atom,
                                 JSValueConst expected)
{
    JSProperty *property;
    JSShapeProperty *shape = js_regexp_split_property(&property, object, atom);
    return shape && (shape->flags & JS_PROP_TMASK) == JS_PROP_NORMAL &&
           js_same_value(ctx, property->u.value, expected);
}

static bool js_regexp_split_guard(JSContext *ctx, JSValueConst receiver, JSValueConst input,
                                  JSValueConst limit)
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
    JSObject *object, *prototype, *getter;
    JSProperty *property;
    JSShapeProperty *shape;
    unsigned i;

    /* A registered interrupt hook can reenter JS and replace these properties
     * while matching. Its complete original call/getter ordering is retained.
     * Ropes retain the original ToString/linearization and ownership path.
     */
    if (JS_VALUE_GET_TAG(receiver) != JS_TAG_OBJECT || JS_VALUE_GET_TAG(input) != JS_TAG_STRING ||
        (!JS_IsUndefined(limit) && !JS_IsNumber(limit)) || ctx->rt->interrupt_handler ||
        js_check_stack_overflow(ctx->rt, 4096) || getenv("QJS_DISABLE_REGEXP_SPLIT"))
        return false;
    object = JS_VALUE_GET_OBJ(receiver);
    prototype = JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_REGEXP]);
    if (object->class_id != JS_CLASS_REGEXP || object->is_exotic ||
        object->shape->proto != prototype ||
        (lre_get_flags(str8(object->u.regexp.bytecode)) & LRE_FLAG_STICKY))
        return false;
    if (!js_regexp_split_data(ctx, object, JS_ATOM_constructor, ctx->regexp_ctor) ||
        !js_regexp_split_data(ctx, JS_VALUE_GET_OBJ(ctx->regexp_ctor), JS_ATOM_prototype,
                              ctx->class_proto[JS_CLASS_REGEXP]))
        return false;
    /* RegExp construction performs IsRegExp, including this observable get,
     * even for a receiver with actual RegExp internal slots. A data value's
     * ToBoolean cannot call user code; an accessor must use the fallback.
     */
    shape = js_regexp_split_property(&property, object, JS_ATOM_Symbol_match);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
        return false;
    shape = js_regexp_split_property(&property, JS_VALUE_GET_OBJ(ctx->regexp_ctor),
                                     JS_ATOM_Symbol_species);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_GETSET ||
        !(getter = property->u.getset.getter) || getter->class_id != JS_CLASS_C_FUNCTION ||
        getter->u.cfunc.cproto != JS_CFUNC_getter ||
        getter->u.cfunc.c_function.getter != js_get_this || getter->u.cfunc.realm != ctx)
        return false;
    shape = js_regexp_split_property(&property, object, JS_ATOM_exec);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
        !JS_IsCFunction(ctx, property->u.value,
#ifdef QJS_REGEXP_SPLIT_NATIVE
                        JS_FrameRegExpExec,
#else
                        js_regexp_exec,
#endif
                        0) ||
        JS_VALUE_GET_OBJ(property->u.value)->u.cfunc.realm != ctx)
        return false;
    shape = js_regexp_split_property(&property, object, JS_ATOM_flags);
    if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_GETSET ||
        !(getter = property->u.getset.getter) || getter->class_id != JS_CLASS_C_FUNCTION ||
        getter->u.cfunc.cproto != JS_CFUNC_getter || getter->u.cfunc.realm != ctx)
        return false;
    if (getter->u.cfunc.c_function.getter != js_regexp_get_flags
#ifdef QJS_REGEXP_SPLIT_NATIVE
        && getter->u.cfunc.c_function.getter != JS_RegExpOwnedFlags
#endif
    )
        return false;
    for (i = 0; i < countof(flags); i++) {
        JSAtom atom =
            js_regexp_borrow_flag_atom(ctx->rt, flags[i].name, flags[i].length, flags[i].hash);
        if (atom == JS_ATOM_NULL)
            return false;
        shape = js_regexp_split_property(&property, object, atom);
        if (!shape || (shape->flags & JS_PROP_TMASK) != JS_PROP_GETSET ||
            !(getter = property->u.getset.getter) || getter->class_id != JS_CLASS_C_FUNCTION ||
            getter->u.cfunc.cproto != JS_CFUNC_getter_magic || getter->u.cfunc.realm != ctx ||
            getter->u.cfunc.c_function.getter_magic != js_regexp_get_flag ||
            getter->u.cfunc.magic != flags[i].mask)
            return false;
    }
    return true;
}

static JSValue js_regexp_split_search(JSContext *ctx, JSValueConst receiver, JSValueConst input,
                                      JSValueConst limit)
{
    uint8_t *small_capture[64], **capture = small_capture;
    JSString *string = JS_VALUE_GET_STRING(input);
    const uint8_t *bytecode = str8(JS_VALUE_GET_OBJ(receiver)->u.regexp.bytecode);
    uint32_t size = string->len, p = 0, q = 0, length = 0, lim = UINT32_MAX;
    int flags = lre_get_flags(bytecode), count = lre_get_capture_count(bytecode);
    int slots = lre_get_alloc_count(bytecode), shift = string->is_wide_char;
    bool unicode = (flags & (LRE_FLAG_UNICODE | LRE_FLAG_UNICODE_SETS)) != 0;
    JSValue array = JS_UNDEFINED, part;

    if (!JS_IsUndefined(limit) && JS_ToUint32(ctx, &lim, limit))
        return JS_EXCEPTION;
    array = JS_NewArray(ctx);
    if (JS_IsException(array) || !lim)
        return array;
    if (slots > countof(small_capture)) {
        capture = js_malloc(ctx, (size_t)slots * sizeof(*capture));
        if (!capture)
            goto exception;
    }
    do {
        int result = lre_exec(capture, bytecode, str8(string), q, size, shift, ctx);
        uint32_t start, end;
        if (result < 0) {
            if (result == LRE_RET_TIMEOUT)
                JS_ThrowInterrupted(ctx);
            else if (result == LRE_RET_BYTECODE_ERROR)
                JS_ThrowInternalError(ctx, "corrupted bytecode in regexp execution");
            else
                JS_ThrowInternalError(ctx, "out of memory in regexp execution");
            goto exception;
        }
        if (!size) {
            if (result == 1)
                goto done;
            break;
        }
        if (result != 1)
            break;
        start = (uint32_t)((capture[0] - str8(string)) >> shift);
        end = (uint32_t)((capture[1] - str8(string)) >> shift);
        if (start == size)
            break;
        if (end == p) {
            q = string_advance_index(string, start, unicode);
            continue;
        }
        part = js_sub_string(ctx, string, p, start);
        if (JS_IsException(part) || JS_DefinePropertyValueUint32(ctx, array, length++, part,
                                                                 JS_PROP_C_W_E | JS_PROP_THROW) < 0)
            goto exception;
        if (length == lim)
            goto done;
        p = end;
        for (int i = 1; i < count; i++) {
            part = capture[2 * i]
                       ? js_sub_string(ctx, string, (capture[2 * i] - str8(string)) >> shift,
                                       (capture[2 * i + 1] - str8(string)) >> shift)
                       : JS_UNDEFINED;
            if (JS_IsException(part) ||
                JS_DefinePropertyValueUint32(ctx, array, length++, part,
                                             JS_PROP_C_W_E | JS_PROP_THROW) < 0)
                goto exception;
            if (length == lim)
                goto done;
        }
        q = p;
    } while (q < size);
    part = js_sub_string(ctx, string, p, size);
    if (JS_IsException(part) ||
        JS_DefinePropertyValueUint32(ctx, array, length, part, JS_PROP_C_W_E | JS_PROP_THROW) < 0)
        goto exception;
    goto done;
exception:
    JS_FreeValue(ctx, array);
    array = JS_EXCEPTION;
done:
    if (capture != small_capture)
        js_free(ctx, capture);
    return array;
}
