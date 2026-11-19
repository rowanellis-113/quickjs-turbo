/* A native caller pauses in the C opcode step while legacy generator frames
 * invoke ordinary JS callbacks. Verify arena reuse, GC roots, realm/exception
 * restoration and independent TLS owners through the actual linked archive. */
#include "quickjs.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int JS_FrameSharedProbe(JSRuntime *, uintptr_t *);

typedef struct SlowHostTest {
    JSContext *foreign;
    JSValue callback;
    int calls, hits, failures, disabled;
} SlowHostTest;

static JSValue observe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    SlowHostTest *test = JS_GetContextOpaque(ctx);
    JSRuntime *rt = JS_GetRuntime(ctx);
    uintptr_t before[6] = {0}, after[6] = {0};
    JSValue result;
    int32_t input, output;
    int shared;
    (void)self;
    if (argc != 2 || JS_ToInt32(ctx, &input, argv[0]) < 0 || !JS_IsObject(argv[1]))
        return JS_ThrowInternalError(ctx, "slow host fixture arguments");
    ++test->calls;
    shared = JS_FrameSharedProbe(rt, before);
    if (shared != !test->disabled || (shared && (before[1] != before[4] || before[0] <= before[3])))
        goto fail;
    test->hits += shared;
    JS_RunGC(rt);
    result = JS_Call(test->foreign, test->callback, JS_UNDEFINED, 1, argv);
    if (input == 3) {
        if (!JS_IsException(result)) {
            JS_FreeValue(test->foreign, result);
            goto fail;
        }
        result = JS_GetException(test->foreign);
    } else if (JS_IsException(result) || JS_ToInt32(test->foreign, &output, result) < 0 ||
               output != input + 7) {
        JS_FreeValue(test->foreign, result);
        goto fail;
    }
    JS_FreeValue(test->foreign, result);
    JS_RunGC(rt);
    if (JS_FrameSharedProbe(rt, after) != shared || memcmp(before, after, sizeof(before)))
        goto fail;
    return JS_UNDEFINED;
fail:
    ++test->failures;
    return JS_ThrowInternalError(ctx, "slow host arena/realm/exception restoration");
}

static void *worker(void *opaque)
{
    SlowHostTest *test = opaque;
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = rt ? JS_NewContext(rt) : NULL;
    JSValue global = JS_UNDEFINED, root = JS_UNDEFINED, value;
    static const char source[] =
        "function child(x){let box={x:x};slowObserve(x,box);return box.x+1}"
        "function* values(n){for(let i=0;i<n;i++)yield child(i)}"
        "function legacy(n){if(n<0)throw new Error('legacy boundary');"
        "let a=0;for(const x of values(n))a+=x;return a}"
        "function root(n){return legacy(n)}";
    static const char foreign[] =
        "(function(x){if(x===3)throw new Error('foreign callback');return x+7})";
    test->callback = JS_UNDEFINED;
    if (!ctx || !(test->foreign = JS_NewContext(rt))) {
        ++test->failures;
        goto done;
    }
    JS_SetContextOpaque(ctx, test);
    test->callback =
        JS_Eval(test->foreign, foreign, sizeof(foreign) - 1, "foreign", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(test->callback))
        goto fail;
    global = JS_GetGlobalObject(ctx);
    if (JS_SetPropertyStr(ctx, global, "slowObserve",
                          JS_NewCFunction(ctx, observe, "slowObserve", 2)) < 0)
        goto fail;
    value = JS_Eval(ctx, source, sizeof(source) - 1, "linux-slow-host", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value))
        goto fail;
    JS_FreeValue(ctx, value);
    root = JS_GetPropertyStr(ctx, global, "root");
    for (int i = 0; i < 10; ++i) {
        int32_t output = 0;
        JSValue arg = JS_NewInt32(ctx, i == 8 ? -1 : 8);
        value = JS_Call(ctx, root, JS_UNDEFINED, 1, &arg);
        JS_FreeValue(ctx, arg);
        if (i == 8) {
            if (!JS_IsException(value)) {
                JS_FreeValue(ctx, value);
                goto fail;
            }
            value = JS_GetException(ctx);
        } else if (JS_IsException(value) || JS_ToInt32(ctx, &output, value) < 0 || output != 36) {
            JS_FreeValue(ctx, value);
            goto fail;
        }
        JS_FreeValue(ctx, value);
    }
    if (test->calls != 72 || test->hits != (test->disabled ? 0 : 72))
        goto fail;
    goto done;
fail:
    ++test->failures;
    value = JS_GetException(ctx);
    const char *message = JS_ToCString(ctx, value);
    fprintf(stderr, "Linux slow host failure: %s calls=%d hits=%d\n", message ? message : "unknown",
            test->calls, test->hits);
    JS_FreeCString(ctx, message);
    JS_FreeValue(ctx, value);
done:
    if (test->foreign) {
        JS_FreeValue(test->foreign, test->callback);
        JS_FreeContext(test->foreign);
    }
    if (ctx) {
        JS_FreeValue(ctx, root);
        JS_FreeValue(ctx, global);
        JS_FreeContext(ctx);
    }
    if (rt)
        JS_FreeRuntime(rt);
    return NULL;
}

int main(void)
{
    int disabled = getenv("QJS_DISABLE_SLOW_HOST_SHARE") || getenv("QJS_DISABLE_SHARED_ENTRY");
    SlowHostTest tests[2] = {{.disabled = disabled}, {.disabled = disabled}};
    pthread_t threads[2];
    if (pthread_create(&threads[0], NULL, worker, &tests[0]))
        return 1;
    if (pthread_create(&threads[1], NULL, worker, &tests[1])) {
        pthread_join(threads[0], NULL);
        return 1;
    }
    pthread_join(threads[0], NULL);
    pthread_join(threads[1], NULL);
    if (tests[0].failures || tests[1].failures)
        return 1;
    printf("LINUX_SLOW_HOST_OK shared=%d,%d disabled=%d\n", tests[0].hits, tests[1].hits, disabled);
    return 0;
}
