/* Public calls plus the existing private observation hook. No VM field access.
 * Exercise arena reuse, GC in the child, independent runtime/thread TLS and OFF. */
#include "quickjs.h"
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int JS_FrameSharedProbe(JSRuntime *, uintptr_t *);
typedef struct State {
    int hits, failures, disabled;
} State;

static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    State *state = JS_GetContextOpaque(ctx);
    uintptr_t words[6] = {0};
    int shared = JS_FrameSharedProbe(JS_GetRuntime(ctx), words);
    (void)self;
    (void)argc;
    (void)argv;
    if (shared != !state->disabled || (shared && (words[1] != words[4] || words[0] <= words[3]))) {
        state->failures++;
        return JS_ThrowInternalError(ctx, "Linux shared arena/TLS mismatch");
    }
    state->hits += shared;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}

static JSValue bounce(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    if (argc != 2)
        return JS_ThrowInternalError(ctx, "Linux shared fixture arity");
    return JS_Call(ctx, argv[0], JS_UNDEFINED, 1, argv + 1);
}

static void *worker(void *opaque)
{
    State *state = opaque;
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = rt ? JS_NewContext(rt) : NULL;
    JSValue global, root, value, arg;
    static const char source[] =
        "function linuxSharedChild(x){linuxSharedProbe();return x+2}"
        "function linuxSharedRoot(x){return linuxSharedBounce(linuxSharedChild,x)}";
    if (!ctx) {
        state->failures++;
        if (rt)
            JS_FreeRuntime(rt);
        return NULL;
    }
    JS_SetContextOpaque(ctx, state);
    global = JS_GetGlobalObject(ctx);
    JS_SetPropertyStr(ctx, global, "linuxSharedProbe", JS_NewCFunction(ctx, probe, "probe", 0));
    JS_SetPropertyStr(ctx, global, "linuxSharedBounce", JS_NewCFunction(ctx, bounce, "bounce", 2));
    value = JS_Eval(ctx, source, sizeof(source) - 1, "linux-shared-tls", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value))
        state->failures++;
    JS_FreeValue(ctx, value);
    root = JS_GetPropertyStr(ctx, global, "linuxSharedRoot");
    arg = JS_NewInt32(ctx, 40);
    for (int i = 0; i < 64 && !state->failures; ++i) {
        int32_t result;
        value = JS_Call(ctx, root, JS_UNDEFINED, 1, &arg);
        if (JS_IsException(value) || JS_ToInt32(ctx, &result, value) < 0 || result != 42)
            state->failures++;
        JS_FreeValue(ctx, value);
    }
    if (state->failures) {
        value = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, value);
        fprintf(stderr, "Linux TLS failure: %s\n", message ? message : "unknown");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, value);
    }
    JS_FreeValue(ctx, arg);
    JS_FreeValue(ctx, root);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return NULL;
}

int main(void)
{
    int disabled = getenv("QJS_DISABLE_SHARED_ENTRY") != NULL;
    State states[2] = {{0, 0, disabled}, {0, 0, disabled}};
    pthread_t threads[2];
    if (pthread_create(&threads[0], NULL, worker, &states[0]))
        return 1;
    if (pthread_create(&threads[1], NULL, worker, &states[1])) {
        pthread_join(threads[0], NULL);
        return 1;
    }
    pthread_join(threads[0], NULL);
    pthread_join(threads[1], NULL);
    if (states[0].failures || states[1].failures || states[0].hits != (disabled ? 0 : 64) ||
        states[1].hits != (disabled ? 0 : 64))
        return 1;
    printf("LINUX_SHARED_TLS_OK hits=%d,%d disabled=%d\n", states[0].hits, states[1].hits,
           disabled);
    return 0;
}
