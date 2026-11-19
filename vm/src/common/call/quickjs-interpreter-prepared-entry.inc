/* Private CachedCall-style sort entry; original comparator/sort bodies below.
 * A scope strongly holds the method and validates immutable frame geometry.
 * The dedicated ASM entry repeats dynamic mode, TLS, runtime, owner, cursor,
 * idle-root, physical-stack and interrupt checks. Failure uses public JS_Call.
 * No new dispatch table or public/runtime/TLS field is introduced. MIT. */
extern JSValue JS_FramePreparedSortInvoke(JSFramePreparedSort *, JSValueConst *,
                                          JSFrameCachedHost *);
NATIVE_SORT_CODE JSValue JS_FramePreparedSortFallback(JSFramePreparedSort *call, JSValueConst *argv,
                                                      JSFrameCachedHost *host)
{
    (void)host;
    return JS_Call(call->cache.ctx, call->cache.callee, JS_UNDEFINED, 2, argv);
}
typedef struct ValueSlot {
    JSValue val;
    JSString *str;
    int64_t pos;
} ValueSlot;

struct frame_prepared_sort_context {
    JSContext *ctx;
    int exception;
    int has_method;
    JSValueConst method;
    JSFramePreparedSort *prepared;
    JSFrameCachedHost *host;
};

NATIVE_SORT_CODE int JS_FramePreparedSortCompare(const void *a, const void *b, void *opaque)
{
    struct frame_prepared_sort_context *psc = opaque;
    JSContext *ctx = psc->ctx;
    JSValueConst argv[2];
    JSValue res;
    ValueSlot *ap = (ValueSlot *)(void *)a;
    ValueSlot *bp = (ValueSlot *)(void *)b;
    int cmp;

    if (psc->exception)
        return 0;

    if (psc->has_method) {
        argv[0] = ap->val;
        argv[1] = bp->val;
        res = JS_FramePreparedSortInvoke(psc->prepared, argv, psc->host);
        if (JS_IsException(res))
            goto exception;
        if (JS_VALUE_GET_TAG(res) == JS_TAG_INT) {
            int val = JS_VALUE_GET_INT(res);
            cmp = (val > 0) - (val < 0);
        } else {
            double val;
            if (JS_ToFloat64Free(ctx, &val, res) < 0)
                goto exception;
            cmp = (val > 0) - (val < 0);
        }
    } else {
        /* Not supposed to bypass ToString even for identical objects as
         * tested in test262/test/built-ins/Array/prototype/sort/bug_596_1.js
         */
        if (!ap->str) {
            JSValue str = JS_ToString(ctx, ap->val);
            if (JS_IsException(str))
                goto exception;
            ap->str = JS_VALUE_GET_STRING(str);
        }
        if (!bp->str) {
            JSValue str = JS_ToString(ctx, bp->val);
            if (JS_IsException(str))
                goto exception;
            bp->str = JS_VALUE_GET_STRING(str);
        }
        cmp = js_string_compare(ap->str, bp->str);
    }
    if (cmp != 0)
        return cmp;
    /* make sort stable: compare array offsets */
    return (ap->pos > bp->pos) - (ap->pos < bp->pos);

exception:
    psc->exception = 1;
    return 0;
}

NATIVE_SORT_CODE JSValue JS_FramePreparedEntryArraySort(JSContext *ctx, JSValueConst this_val,
                                                        int argc, JSValueConst *argv,
                                                        JSFramePreparedSort *prepared,
                                                        JSFrameCachedHost *host)
{
    struct frame_prepared_sort_context asc = {ctx, 0, 0, argv[0], prepared, host};
    JSValue obj = JS_UNDEFINED;
    ValueSlot *array = NULL;
    size_t array_size = 0, pos = 0, n = 0;
    int64_t i, len, undefined_count = 0;
    int present;

    if (!JS_IsUndefined(asc.method)) {
        if (check_function(ctx, asc.method))
            goto exception;
        asc.has_method = 1;
    }
    obj = JS_ToObject(ctx, this_val);
    if (js_get_length64(ctx, &len, obj))
        goto exception;

    /* XXX: should special case fast arrays */
    for (i = 0; i < len; i++) {
        if (pos >= array_size) {
            size_t new_size;
            ValueSlot *new_array;
            new_size = (array_size + (array_size >> 1) + 31) & ~15;
            new_array = js_realloc(ctx, array, new_size * sizeof(*array));
            if (new_array == NULL)
                goto exception;
            array = new_array;
            array_size = new_size;
        }
        present = JS_TryGetPropertyInt64(ctx, obj, i, &array[pos].val);
        if (present < 0)
            goto exception;
        if (present == 0)
            continue;
        if (JS_IsUndefined(array[pos].val)) {
            undefined_count++;
            continue;
        }
        array[pos].str = NULL;
        array[pos].pos = i;
        pos++;
    }
    rqsort(array, pos, sizeof(*array), JS_FramePreparedSortCompare, &asc);
    if (asc.exception)
        goto exception;

    /* XXX: should special case fast arrays */
    while (n < pos) {
        if (array[n].str)
            JS_FreeValue(ctx, JS_MKPTR(JS_TAG_STRING, array[n].str));
        if (array[n].pos == n) {
            JS_FreeValue(ctx, array[n].val);
        } else {
            if (JS_SetPropertyInt64(ctx, obj, n, array[n].val) < 0) {
                n++;
                goto exception;
            }
        }
        n++;
    }
    js_free(ctx, array);
    for (i = n; undefined_count-- > 0; i++) {
        if (JS_SetPropertyInt64(ctx, obj, i, JS_UNDEFINED) < 0)
            goto fail;
    }
    for (; i < len; i++) {
        if (JS_DeletePropertyInt64(ctx, obj, i, JS_PROP_THROW) < 0)
            goto fail;
    }
    return obj;

exception:
    for (; n < pos; n++) {
        JS_FreeValue(ctx, array[n].val);
        if (array[n].str)
            JS_FreeValue(ctx, JS_MKPTR(JS_TAG_STRING, array[n].str));
    }
    js_free(ctx, array);
fail:
    JS_FreeValue(ctx, obj);
    return JS_EXCEPTION;
}
