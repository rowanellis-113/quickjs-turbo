/* Reuse only the initial length/name shape of unnamed internal functions.
 * Function data, callbacks, promise state and scheduling keep their original
 * allocation, ownership and publication order. No callable values are cached. */
static bool js_internal_function_class(JSClassID id)
{
    return id == JS_CLASS_C_FUNCTION_DATA || id == JS_CLASS_PROMISE_RESOLVE_FUNCTION ||
           id == JS_CLASS_PROMISE_REJECT_FUNCTION;
}

static JSValue js_internal_function_object(JSContext *ctx, JSValueConst proto, JSClassID id,
                                           bool unnamed)
{
    JSShape *shape;
    JSProperty props[2];
    unsigned mode = ctx->internal_function_mode;
    if (!mode) {
        mode = getenv("QJS_DISABLE_INTERNAL_FUNCTION_TEMPLATE") ? 2 : 1;
        ctx->internal_function_mode = mode;
    }
    shape = ctx->internal_function_shape;
    if (unnamed && (mode & 1) && shape && js_internal_function_class(id) &&
        (JS_IsObject(proto) || JS_IsNull(proto)) &&
        shape->proto == (JS_IsNull(proto) ? NULL : JS_VALUE_GET_OBJ(proto))) {
        /* Every property is a valid owner before allocation may collect or
         * reenter. This constructor consumes both shape and property owners
         * on failure. The original caller attaches its opaque data later. */
        props[0].u.value = JS_UNDEFINED;
        props[1].u.value = JS_UNDEFINED;
        return JS_NewObjectFromShape(ctx, js_dup_shape(shape), id, props);
    }
    return JS_NewObjectProtoClass(ctx, proto, id);
}

static void js_internal_function_finish_properties(JSContext *ctx, JSValue obj, JSAtom name,
                                                   int length)
{
    JSObject *p = JS_VALUE_GET_OBJ(obj);
    JSShape *shape = p->shape;
    if (name == JS_ATOM_empty_string && shape == ctx->internal_function_shape &&
        (ctx->internal_function_mode & 1) && js_internal_function_class(p->class_id)) {
        /* Empty atom conversion only duplicates its string reference. Named
         * functions retain the original atom conversion and OOM behavior. */
        set_value(ctx, &p->prop[0].u.value, js_int32(length));
        set_value(ctx, &p->prop[1].u.value, JS_AtomToString(ctx, name));
        return;
    }
    js_function_set_properties(ctx, obj, name, length);
    shape = p->shape;
    if (name == JS_ATOM_empty_string && (ctx->internal_function_mode & 1) &&
        js_internal_function_class(p->class_id) && (shape->is_hashed & 1) &&
        shape->prop_count == 2 && !shape->deleted_prop_count &&
        (JS_IsObject(ctx->function_proto) || JS_IsNull(ctx->function_proto)) &&
        shape->proto ==
            (JS_IsNull(ctx->function_proto) ? NULL : JS_VALUE_GET_OBJ(ctx->function_proto)) &&
        get_shape_prop(shape)[0].atom == JS_ATOM_length &&
        get_shape_prop(shape)[0].flags == JS_PROP_CONFIGURABLE &&
        get_shape_prop(shape)[1].atom == JS_ATOM_name &&
        get_shape_prop(shape)[1].flags == JS_PROP_CONFIGURABLE) {
        JSShape *old = ctx->internal_function_shape;
        ctx->internal_function_shape = js_dup_shape(shape);
        js_free_shape_null(ctx->rt, old);
    }
}
