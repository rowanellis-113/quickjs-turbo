/* A capability-free ordinary async invocation owns exactly one reference to
 * its public Promise. The second slot distinguishes it from a resolver pair.
 * Fast ready-await skips intermediate Promise and dual-resolver allocations
 * while preserving exact microtask order, interrupt polls, and GC ownership. */
static JSValue js_promise_settle(JSContext *, JSValueConst, JSValueConst, bool);
static JSValue js_promise_new(JSContext *, JSValueConst, JSValue *);
static bool js_async_function_resume(JSContext *, JSAsyncFunctionData *);
static void fulfill_or_reject_promise(JSContext *, JSValueConst, JSValueConst, bool);
static int js_async_promise_try_fulfilled(JSContext *, JSValueConst, JSValueConst *);
static void js_async_promise_mark_handled(JSValueConst);

static inline bool js_async_value_non_thenable(JSContext *ctx, JSValueConst value)
{
    JSObject *obj;
    unsigned depth = 0;
    if (!JS_IsObject(value))
        return true;
    obj = JS_VALUE_GET_OBJ(value);
    if (obj->class_id == JS_CLASS_OBJECT && !obj->is_exotic) {
        JSShape *sh = obj->shape;
        if (sh->prop_count == 2) {
            JSShapeProperty *prs = get_shape_prop(sh);
            if (prs[0].atom == JS_ATOM_value && prs[1].atom == JS_ATOM_done) {
                obj = sh->proto;
                depth = 1;
            }
        }
    } else if ((obj->class_id == JS_CLASS_DATAVIEW || obj->class_id == JS_CLASS_ARRAY_BUFFER ||
                obj->class_id == JS_CLASS_MAP || obj->class_id == JS_CLASS_SET) &&
               !obj->is_exotic) {
        /* non-exotic built-in container; check own + prototype chain */
    } else if ((obj->class_id == JS_CLASS_ARRAY || is_typed_array(obj->class_id)) &&
               obj->fast_array) {
        /* JS_ATOM_then is never a numeric index; fast_array exotic does not intercept it */
    } else {
        return false;
    }
    while (obj) {
        JSProperty *prop;
        JSShapeProperty *sp;
        if (++depth > 8)
            return false;
        if (depth > 1 && !((obj->class_id == JS_CLASS_OBJECT && !obj->is_exotic) ||
                           (obj->class_id == JS_CLASS_ARRAY && obj->fast_array)))
            return false;
        sp = find_own_property(&prop, obj, JS_ATOM_then);
        if (sp)
            return (sp->flags & JS_PROP_TMASK) == JS_PROP_NORMAL && JS_IsUndefined(prop->u.value);
        obj = obj->shape->proto;
    }
    (void)ctx;
    return true;
}

static inline bool js_async_promise_proto_ctor_std(JSContext *ctx)
{
    JSObject *proto;
    JSProperty *prop;
    JSShapeProperty *sp;
    if (unlikely(!JS_IsObject(ctx->class_proto[JS_CLASS_PROMISE]) ||
                 !JS_IsObject(ctx->promise_ctor)))
        return false;
    proto = JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_PROMISE]);
    if (unlikely(proto->is_exotic))
        return false;
    sp = find_own_property(&prop, proto, JS_ATOM_constructor);
    return sp && (sp->flags & JS_PROP_TMASK) == JS_PROP_NORMAL &&
           js_same_value(ctx, prop->u.value, ctx->promise_ctor);
}

static JSValue js_async_func_fast_resume_job(JSContext *ctx, int argc, JSValueConst *argv)
{
    JSAsyncFunctionData *s = JS_VALUE_GET_PTR(argv[0]);
    bool ok;
    (void)argc;
    if (unlikely(js_poll_interrupts(ctx))) {
        js_async_function_free(ctx->rt, s);
        return JS_EXCEPTION;
    }
    s->func_state.throw_flag = false;
    s->func_state.frame.cur_sp[-1] = js_dup(argv[1]);
    ok = js_async_function_resume(ctx, s);
    js_async_function_free(ctx->rt, s);
    return ok ? JS_UNDEFINED : JS_EXCEPTION;
}

/* 1=enqueued fast, 0=use original await path, -1=allocation error. */
static int js_async_function_await_fast(JSContext *ctx, JSAsyncFunctionData *s, JSValueConst value)
{
    JSValueConst resolved_val = value;
    JSJobEntry *job;
    bool direct = true;
    if (unlikely(ctx->rt->promise_hook || js_check_stack_overflow(ctx->rt, 4096) ||
                 !JS_IsObject(ctx->promise_ctor)))
        return 0;
    if (JS_IsObject(value)) {
        JSObject *po = JS_VALUE_GET_OBJ(value);
        if (po->class_id == JS_CLASS_PROMISE) {
            if (!js_async_promise_try_fulfilled(ctx, value, &resolved_val))
                return 0;
            direct = false;
        } else if (ctx->interrupt_counter <= 1 || !js_async_value_non_thenable(ctx, value)) {
            return 0;
        }
    } else if (ctx->interrupt_counter <= 1) {
        return 0;
    }
    job = qjs_job2_alloc_fast(ctx);
    if (unlikely(!job))
        return -1;
    if (unlikely(
            ctx->rt->promise_hook ||
            (direct && (ctx->interrupt_counter <= 1 || js_check_stack_overflow(ctx->rt, 4096) ||
                        !js_async_value_non_thenable(ctx, value))) ||
            (!direct && !js_async_promise_try_fulfilled(ctx, value, &resolved_val)))) {
        js_free(ctx, job);
        return 0;
    }
    assert(!ctx->rt->in_free);
    if (direct)
        --ctx->interrupt_counter;
    else
        js_async_promise_mark_handled(value);
    JS_REF_COUNT(s)++;
    job->ctx = ctx;
    job->job_func = js_async_func_fast_resume_job;
    job->argc = 2;
    job->argv[0] =
        JS_MKPTR(JS_TAG_INT, s); /* direct refcount ownership; freed on job run/teardown */
    job->argv[1] = js_dup(resolved_val);
    list_add_tail(&job->link, &ctx->rt->job_list);
    return 1;
}

static JSValue js_async_output_settle(JSContext *ctx, JSAsyncFunctionData *s, JSValueConst value,
                                      bool reject)
{
    JSValue promise, result;
    if (!JS_IsUndefined(s->resolving_funcs[1]))
        return JS_Call(ctx, s->resolving_funcs[reject], JS_UNDEFINED, 1, &value);
    /* Match the poll in the omitted JS_Call, including late interrupt hooks. */
    if (js_poll_interrupts(ctx))
        return JS_EXCEPTION;
    promise = s->resolving_funcs[0];
    s->resolving_funcs[0] = JS_UNDEFINED;
    if (JS_IsUndefined(promise))
        return JS_UNDEFINED;
    if (reject || !JS_IsObject(value) ||
        (!js_same_value(ctx, value, promise) && js_async_value_non_thenable(ctx, value))) {
        fulfill_or_reject_promise(ctx, promise, value, reject);
        JS_FreeValue(ctx, promise);
        return JS_UNDEFINED;
    }
    result = js_promise_settle(ctx, promise, value, reject);
    JS_FreeValue(ctx, promise);
    return result;
}
