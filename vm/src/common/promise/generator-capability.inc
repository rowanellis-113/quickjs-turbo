/* Private async-generator await and output Promise ownership. MIT, as quickjs.c. */
#ifdef _MSC_VER
extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);
extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);
#endif
static unsigned char js_generator_capability_mode;
static unsigned char js_generator_capability_get_mode(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode = JS_FrameCallMetaLoadByte(&js_generator_capability_mode);
#else
    mode = __atomic_load_n(&js_generator_capability_mode, __ATOMIC_RELAXED);
#endif
    if (unlikely(!mode)) {
        unsigned char desired = 16 | 32 | 7;
        if (getenv("QJS_DISABLE_GENERATOR_CAPABILITY"))
            desired = 128;
        else if (getenv("QJS_DISABLE_GENERATOR_CAPABILITY_FAST"))
            desired = 16;
        else {
            if (getenv("QJS_DISABLE_DIRECT_AWAIT"))
                desired &= ~1;
            if (getenv("QJS_DISABLE_SETTLED_AWAIT"))
                desired &= ~2;
            if (getenv("QJS_DISABLE_GENERATOR_CAPABILITY_OUTPUT"))
                desired &= ~4;
            if (getenv("QJS_DISABLE_GENERATOR_FAST_JOB"))
                desired &= ~32;
        }
#ifdef _MSC_VER
        mode = JS_FrameCallMetaInitByte(&js_generator_capability_mode, desired);
#else
        __atomic_compare_exchange_n(&js_generator_capability_mode, &mode, desired, false,
                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);
#endif
        if (!mode)
            mode = desired;
    }
    return mode;
}

/* A proof, not a cache: no allocation/callback/getter and no borrowed metadata
 * survives an allocation. Object/prototype changes are re-read at commit. */
static bool js_ready_await_non_thenable(JSValueConst value)
{
    JSObject *object;
    unsigned depth = 0;
    switch (JS_VALUE_GET_TAG(value)) {
    case JS_TAG_INT:
    case JS_TAG_BOOL:
    case JS_TAG_NULL:
    case JS_TAG_UNDEFINED:
    case JS_TAG_FLOAT64:
    case JS_TAG_STRING:
    case JS_TAG_SYMBOL:
    case JS_TAG_BIG_INT:
        return true;
    case JS_TAG_OBJECT:
        break;
    default:
        return false;
    }
    object = JS_VALUE_GET_OBJ(value);
    while (object) {
        JSProperty *property;
        JSShapeProperty *shape_property;
        if (++depth > 8 || object->class_id != JS_CLASS_OBJECT || object->is_exotic)
            return false;
        shape_property = find_own_property(&property, object, JS_ATOM_then);
        if (shape_property)
            return (shape_property->flags & JS_PROP_TMASK) == JS_PROP_NORMAL &&
                   JS_IsUndefined(property->u.value);
        object = object->shape->proto;
    }
    return true;
}

static JSValue js_ready_generator_resume_job(JSContext *ctx, int argc, JSValueConst *argv)
{
    JSAsyncGeneratorData *s;
    (void)argc;
    if (unlikely(js_poll_interrupts(ctx)))
        return JS_EXCEPTION;
    s = JS_GetOpaque(argv[0], JS_CLASS_ASYNC_GENERATOR);
    if (unlikely(!s))
        return JS_UNDEFINED;
    s->func_state.frame.cur_sp[-1] = js_dup(argv[1]);
    s->func_state.throw_flag = false;
    JS_GeneratorCapabilityResume(ctx, s);
    return JS_UNDEFINED;
}

static inline bool js_ready_gen_promise_ctor_std(JSContext *ctx)
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

/* 1 published,0 original path,-1 allocation error. The current caller owns
 * value/promise and generator while preparing the exact original job. */
static no_inline int js_ready_generator_enqueue(JSContext *ctx, JSAsyncGeneratorData *s,
                                                JSValueConst value, JSPromiseData *promise_data,
                                                bool direct)
{
    JSValue generator = JS_MKPTR(JS_TAG_OBJECT, s->generator);
    JSJobEntry *job;
    if (ctx->rt->promise_hook || js_check_stack_overflow(ctx->rt, 4096))
        return 0;
    if (direct && (!JS_IsObject(ctx->promise_ctor) || ctx->interrupt_counter <= 1 ||
                   !js_ready_await_non_thenable(value)))
        return 0;
    if (!direct && (!promise_data || promise_data->promise_state != JS_PROMISE_FULFILLED))
        return 0;
    if (unlikely(!(js_generator_capability_get_mode() & 32))) {
        JSValue handler =
            JS_NewCFunctionData(ctx, js_async_generator_resolve_function, 1, 0, 1, &generator);
        if (JS_IsException(handler))
            return -1;
        job = js_malloc(ctx, sizeof(*job) + 5 * sizeof(JSValue));
        if (!job) {
            JS_FreeValue(ctx, handler);
            return -1;
        }
        if (ctx->rt->promise_hook ||
            (direct && (ctx->interrupt_counter <= 1 || js_check_stack_overflow(ctx->rt, 4096) ||
                        !js_ready_await_non_thenable(value))) ||
            (!direct && promise_data->promise_state != JS_PROMISE_FULFILLED)) {
            js_free(ctx, job);
            JS_FreeValue(ctx, handler);
            return 0;
        }
        assert(!ctx->rt->in_free);
        if (direct)
            --ctx->interrupt_counter;
        job->ctx = ctx;
        job->job_func = promise_reaction_job;
        job->argc = 5;
        job->argv[0] = JS_UNDEFINED;
        job->argv[1] = JS_UNDEFINED;
        job->argv[2] = handler;
        job->argv[3] = JS_FALSE;
        job->argv[4] = js_dup(value);
        list_add_tail(&job->link, &ctx->rt->job_list);
        if (promise_data)
            promise_data->is_handled = true;
        return 1;
    }
    job = js_malloc(ctx, sizeof(*job) + 2 * sizeof(JSValue));
    if (!job)
        return -1;
    if (ctx->rt->promise_hook ||
        (direct && (ctx->interrupt_counter <= 1 || js_check_stack_overflow(ctx->rt, 4096) ||
                    !js_ready_await_non_thenable(value))) ||
        (!direct && promise_data->promise_state != JS_PROMISE_FULFILLED)) {
        js_free(ctx, job);
        return 0;
    }
    assert(!ctx->rt->in_free);
    if (direct)
        --ctx->interrupt_counter; /* one omitted private resolver JS_Call */
    job->ctx = ctx;               /* exact borrowed-context ownership of JS_EnqueueJob */
    job->job_func = js_ready_generator_resume_job;
    job->argc = 2;
    job->argv[0] = js_dup(generator);
    job->argv[1] = js_dup(value);
    list_add_tail(&job->link, &ctx->rt->job_list);
    if (promise_data)
        promise_data->is_handled = true;
    return 1;
}

static int js_ready_generator_direct_try(JSContext *ctx, JSAsyncGeneratorData *s,
                                         JSValueConst value)
{
    if (JS_IsObject(value)) {
        JSObject *po = JS_VALUE_GET_OBJ(value);
        if (po->class_id == JS_CLASS_PROMISE) {
            JSPromiseData *data = po->u.promise_data;
            if (data && data->promise_state == JS_PROMISE_FULFILLED && !po->is_exotic &&
                po->shape->prop_count == 0 &&
                po->shape->proto == JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_PROMISE]) &&
                js_ready_gen_promise_ctor_std(ctx))
                return js_ready_generator_enqueue(ctx, s, data->promise_result, data, false);
            return 0;
        }
    }
    return js_ready_generator_enqueue(ctx, s, value, NULL, true);
}
static int js_ready_generator_await_try(JSContext *ctx, JSAsyncGeneratorData *s,
                                        JSValueConst promise)
{
    JSPromiseData *data = JS_GetOpaque(promise, JS_CLASS_PROMISE);
    if (!data || data->promise_state != JS_PROMISE_FULFILLED)
        return 0;
    return js_ready_generator_enqueue(ctx, s, data->promise_result, data, false);
}

extern void qjs_generator_capability_original(JSContext *, JSAsyncGeneratorData *);
extern JSValue qjs_generator_capability_original_next(JSContext *, JSValueConst, int,
                                                      JSValueConst *, int);
void JS_GeneratorCapabilityResume(JSContext *, JSAsyncGeneratorData *);

/* The request, removed exactly once from its generator queue, owns the public
 * Promise directly. No resolver escapes, and no new layout or state flag is
 * needed. Preserve the original omitted JS_Call poll and Resolve algorithm. */
static JSValue js_generator_capability_settle(JSContext *ctx, JSValueConst promise,
                                              JSValueConst resolution, bool is_reject)
{
    JSValue then;
    JSValueConst args[3];
    JSPromiseData *data;
    if (js_poll_interrupts(ctx))
        return JS_EXCEPTION;
    data = JS_GetOpaque(promise, JS_CLASS_PROMISE);
    if (!data || data->promise_state != JS_PROMISE_PENDING)
        return JS_UNDEFINED;
    if (is_reject || !JS_IsObject(resolution))
        goto done;
    if (js_same_value(ctx, resolution, promise)) {
        JS_ThrowTypeError(ctx, "promise self resolution");
        goto fail_reject;
    }
    if (js_ready_await_non_thenable(resolution))
        goto done;
    then = JS_GetProperty(ctx, resolution, JS_ATOM_then);
    if (JS_IsException(then)) {
        JSValue error;
    fail_reject:
        error = JS_GetException(ctx);
        fulfill_or_reject_promise(ctx, promise, error, true);
        JS_FreeValue(ctx, error);
    } else if (!JS_IsFunction(ctx, then)) {
        JS_FreeValue(ctx, then);
    done:
        fulfill_or_reject_promise(ctx, promise, resolution, is_reject);
    } else {
        args[0] = promise;
        args[1] = resolution;
        args[2] = then;
        JS_EnqueueJob(ctx, js_promise_resolve_thenable_job, 3, args);
        JS_FreeValue(ctx, then);
    }
    return JS_UNDEFINED;
}
