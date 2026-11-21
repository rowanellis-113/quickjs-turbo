/* A capability-free ordinary async invocation owns exactly one reference to
 * its public Promise. The second slot distinguishes it from a resolver pair.
 * Await reactions still use the original two recovery functions and job. */
static JSValue js_promise_settle(JSContext *, JSValueConst, JSValueConst, bool);
static JSValue js_promise_new(JSContext *, JSValueConst, JSValue *);

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
    result = js_promise_settle(ctx, promise, value, reject);
    JS_FreeValue(ctx, promise);
    return result;
}
