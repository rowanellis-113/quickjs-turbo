/* Closure structure reuse with co-allocated inline property storage.
   The original closure binding, lazy prototype and public property semantics
   remain in force. Context GC owns each retained hashed shape explicitly. */
static bool js_closure_template_recipe(JSContext *ctx, JSObject *p, JSFunctionBytecode *b)
{
    JSShape *sh = p->shape;
    JSValue proto = ctx->class_proto[p->class_id];
    int count = b->has_prototype ? 3 : 2;
    if (!(sh->is_hashed & 1) || sh->prop_count != count || sh->deleted_prop_count ||
        (JS_VALUE_GET_TAG(proto) != JS_TAG_OBJECT && !JS_IsNull(proto)) ||
        sh->proto != (JS_IsNull(proto) ? NULL : JS_VALUE_GET_OBJ(proto)))
        return false;
    if (get_shape_prop(sh)[0].atom != JS_ATOM_length ||
        get_shape_prop(sh)[0].flags != JS_PROP_CONFIGURABLE ||
        get_shape_prop(sh)[1].atom != JS_ATOM_name ||
        get_shape_prop(sh)[1].flags != JS_PROP_CONFIGURABLE)
        return false;
    if (count == 3 && (get_shape_prop(sh)[2].atom != JS_ATOM_prototype ||
                       get_shape_prop(sh)[2].flags != (JS_PROP_WRITABLE | JS_PROP_AUTOINIT)))
        return false;
    return true;
}

static no_inline JSValue js_closure_tail_object(JSContext *ctx, JSShape *sh, JSClassID class_id,
                                                JSProperty *props, size_t tail_bytes)
{
    JSObject *p;
    int i;
    assert(tail_bytes && sizeof(JSObject) + tail_bytes <= 256);
    assert(class_id == JS_CLASS_BYTECODE_FUNCTION || class_id == JS_CLASS_ASYNC_FUNCTION);
    js_trigger_gc(ctx->rt, sizeof(JSObject) + tail_bytes);
    size_t inline_bytes = qjs_inline_property_plan(sh, tail_bytes, 0u);
    p = js_malloc(ctx, inline_bytes ? inline_bytes : sizeof(JSObject) + tail_bytes);
    if (!p)
        goto fail;
    p->class_id = class_id;
    p->extensible = true;
    p->free_mark = 0;
    p->is_exotic = ctx->rt->class_array[class_id].exotic != NULL;
    p->fast_array = 0;
    p->is_constructor = 0;
    p->is_uncatchable_error = 0;
    p->tmp_mark = 0;
    p->is_HTMLDDA = 0;
    p->is_prototype = 0;
    p->turbo_obj_flags = 64; /* explicit owned-tail flag, preserved by GC bitfields */
    p->first_weak_ref = NULL;
    p->u.func.function_bytecode = NULL;
    p->u.func.home_object = NULL;
    p->u.func.var_refs = (JSVarRef **)(p + 1);
    memset(p + 1, 0, tail_bytes);
    p->shape = sh;
    p->prop = inline_bytes ? qjs_inline_property_initialize(p, sh, tail_bytes, inline_bytes)
                           : js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);
    if (!p->prop) {
        js_free(ctx, p);
    fail:
        for (i = 0; i < sh->prop_count; i++)
            free_property(ctx->rt, &props[i], get_shape_prop(sh)[i].flags);
        js_free_shape(ctx->rt, sh);
        return JS_EXCEPTION;
    }
    JS_REF_COUNT(p) = 1;
    add_gc_object(ctx->rt, &p->header, JS_GC_OBJ_TYPE_JS_OBJECT);
    for (i = 0; i < sh->prop_count; i++)
        p->prop[i] = props[i];
    return JS_MKPTR(JS_TAG_OBJECT, p);
}

static no_inline JSValue js_closure_tail_bind(JSContext *ctx, JSValue obj, JSFunctionBytecode *b,
                                              JSVarRef **cur_var_refs, JSStackFrame *sf)
{
    JSObject *p = JS_VALUE_GET_OBJ(obj);
    JSVarRef **var_refs = p->u.func.var_refs;
    p->u.func.function_bytecode = b;
    assert(var_refs == (JSVarRef **)(p + 1));
    for (int i = 0; i < b->closure_var_count; i++) {
        JSClosureVar *cv = &b->closure_var[i];
        JSVarRef *var_ref;
        switch (cv->closure_type) {
        case JS_CLOSURE_LOCAL:
            var_ref = get_var_ref(ctx, sf, cv->var_idx, false);
            break;
        case JS_CLOSURE_ARG:
            var_ref = get_var_ref(ctx, sf, cv->var_idx, true);
            break;
        case JS_CLOSURE_REF:
        case JS_CLOSURE_GLOBAL_REF:
            var_ref = cur_var_refs[cv->var_idx];
            JS_REF_COUNT(var_ref)++;
            break;
        default:
            abort();
        }
        if (!var_ref) {
            JS_FreeValue(ctx, obj);
            return JS_EXCEPTION;
        }
        var_refs[i] = var_ref;
    }
    return obj;
}

static no_inline JSValue js_closure_template_create(JSContext *ctx, JSValue bfunc,
                                                    JSVarRef **cur_var_refs, JSStackFrame *sf,
                                                    JSShape *shape)
{
    JSFunctionBytecode *b = JS_VALUE_GET_PTR(bfunc);
    JSProperty props[3];
    JSValue obj;
    JSObject *p;
    JSAtom name = b->func_name ? b->func_name : JS_ATOM_empty_string;
    size_t tail_bytes = (size_t)b->closure_var_count * sizeof(JSVarRef *);
    bool tail =
        (ctx->closure_template_mode & 4) && tail_bytes && tail_bytes <= 256 - sizeof(JSObject);
    props[0].u.value = js_int32(b->defined_arg_count);
    props[1].u.value = JS_UNDEFINED;
    if (b->has_prototype) {
        props[2].u.init.realm_and_id = (uintptr_t)JS_DupContext(ctx) | JS_AUTOINIT_ID_PROTOTYPE;
        props[2].u.init.opaque = NULL;
    }
    shape = js_dup_shape(shape);
    obj = tail ? js_closure_tail_object(ctx, shape, func_kind_to_class_id[b->func_kind], props,
                                        tail_bytes)
               : JS_NewObjectFromShape(ctx, shape, func_kind_to_class_id[b->func_kind], props);
    if (JS_IsException(obj)) {
        JS_FreeValue(ctx, bfunc);
        return obj;
    }
    obj = tail ? js_closure_tail_bind(ctx, obj, b, cur_var_refs, sf)
               : js_closure2(ctx, obj, b, cur_var_refs, sf);
    if (JS_IsException(obj))
        return obj;
    p = JS_VALUE_GET_OBJ(obj);
    p->prop[1].u.value = JS_AtomToString(ctx, name);
    if (b->has_prototype)
        JS_SetConstructorBit(ctx, obj, true);
    return obj;
}

static JSValue js_closure(JSContext *ctx, JSValue bfunc, JSVarRef **cur_var_refs, JSStackFrame *sf)
{
    JSFunctionBytecode *b = JS_VALUE_GET_PTR(bfunc);
    JSValue result;
    JSAtom name = b->func_name ? b->func_name : JS_ATOM_empty_string;
    unsigned mode = ctx->closure_template_mode;
    int index = -1;
    if (!mode) {
        mode = getenv("QJS_DISABLE_CLOSURE_SHAPE_TEMPLATE") ? 2 : 1;
        if (mode == 1 && !getenv("QJS_DISABLE_CLOSURE_INLINE_REFS"))
            mode |= 4;
        ctx->closure_template_mode = mode;
    }
    if ((mode & 1) && (b->func_kind == JS_FUNC_NORMAL || b->func_kind == JS_FUNC_ASYNC) &&
        !__JS_AtomIsTaggedInt(name) &&
        ctx->rt->atom_array[name]->atom_type == JS_ATOM_TYPE_STRING) {
        JSShape *shape;
        JSValue proto;
        index = (b->func_kind == JS_FUNC_ASYNC ? 2 : 0) + b->has_prototype;
        shape = ctx->closure_template_shapes[index];
        proto = ctx->class_proto[func_kind_to_class_id[b->func_kind]];
        if (shape && (JS_VALUE_GET_TAG(proto) == JS_TAG_OBJECT || JS_IsNull(proto)) &&
            shape->proto == (JS_IsNull(proto) ? NULL : JS_VALUE_GET_OBJ(proto)))
            return js_closure_template_create(ctx, bfunc, cur_var_refs, sf, shape);
    }
    result = js_closure_template_original(ctx, bfunc, cur_var_refs, sf);
    if (index >= 0 && !JS_IsException(result) && (ctx->closure_template_mode & 1)) {
        JSObject *p = JS_VALUE_GET_OBJ(result);
        if (js_closure_template_recipe(ctx, p, b)) {
            JSShape *old = ctx->closure_template_shapes[index];
            ctx->closure_template_shapes[index] = js_dup_shape(p->shape);
            js_free_shape_null(ctx->rt, old);
        }
    }
    return result;
}
