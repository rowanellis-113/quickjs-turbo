/* Public embedding contract under many cached prototypes, GC and growth OOM.
 * Finalizers only count; they never execute JavaScript or reenter the VM. */
#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID probe_class;
static unsigned finalized;
static void probe_finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    ++finalized;
}
static const JSClassDef probe_definition = {"AdaptivePrototype", probe_finalizer};

static JSValue function(JSContext *ctx, const char *text)
{
    return JS_Eval(ctx, text, strlen(text), "adaptive-installed", JS_EVAL_TYPE_GLOBAL);
}
static int expect(JSContext *ctx, JSValue value, int expected)
{
    int32_t actual;
    if (JS_IsException(value))
        return -1;
    int code = JS_ToInt32(ctx, &actual, value) || actual != expected;
    JS_FreeValue(ctx, value);
    return code ? -1 : 0;
}

static int prototype_lifetimes(JSContext *ctx, JSRuntime *rt)
{
    JSValue fn = function(ctx, "(function(o){return o.value})");
    JSValue prototypes[16], receivers[16];
    unsigned i, round, count = 0;
    int code = -1;
    if (JS_IsException(fn))
        return -1;
    for (i = 0; i < 16; ++i)
        prototypes[i] = receivers[i] = JS_UNDEFINED;
    for (round = 0; round < 2; ++round) {
        for (i = 0; i < 16; ++i) {
            prototypes[i] = JS_NewObjectProtoClass(ctx, JS_NULL, probe_class);
            if (JS_IsException(prototypes[i]) ||
                JS_SetPropertyStr(ctx, prototypes[i], "value", JS_NewInt32(ctx, 83 + i)) < 0)
                goto end;
            receivers[i] = JS_NewObjectProto(ctx, prototypes[i]);
            if (JS_IsException(receivers[i]))
                goto end;
        }
        for (unsigned pass = 0; pass < 3; ++pass)
            for (i = 0; i < 16; ++i)
                if (expect(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 1, (JSValueConst *)&receivers[i]),
                           83 + i))
                    goto end;
        if (round) {
            /* Keep each receiver alive only through its own cycle. The
             * cached function stays rooted in the embedding throughout GC. */
            for (i = 0; i < 16; ++i)
                if (JS_SetPropertyStr(ctx, receivers[i], "self", JS_DupValue(ctx, receivers[i])) <
                    0)
                    goto end;
        }
        for (i = 0; i < 16; ++i) {
            JS_FreeValue(ctx, receivers[i]);
            receivers[i] = JS_UNDEFINED;
            JS_FreeValue(ctx, prototypes[i]);
            prototypes[i] = JS_UNDEFINED;
        }
        if (finalized != count + (round ? 0 : 16))
            goto end;
        JS_RunGC(rt);
        count += 16;
        if (finalized != count)
            goto end;
        printf("PROTOTYPES round=%u finalized=%u\n", round, finalized);
    }
    code = 0;
end:
    for (i = 0; i < 16; ++i) {
        JS_FreeValue(ctx, receivers[i]);
        JS_FreeValue(ctx, prototypes[i]);
    }
    JS_FreeValue(ctx, fn);
    return code;
}

static int ninth_shape_oom(JSContext *ctx, JSRuntime *rt)
{
    JSValue fn = function(ctx, "(function(o,v){o.value=v;return o.value})");
    JSValue objects[9], args[2];
    JSMemoryUsage usage;
    unsigned i;
    int code = -1;
    char name[32];
    if (JS_IsException(fn))
        return -1;
    for (i = 0; i < 9; ++i)
        objects[i] = JS_UNDEFINED;
    for (i = 0; i < 9; ++i) {
        objects[i] = JS_NewObject(ctx);
        snprintf(name, sizeof(name), "distinct%u", i);
        if (JS_IsException(objects[i]) ||
            JS_SetPropertyStr(ctx, objects[i], "value", JS_NewInt32(ctx, 0)) < 0 ||
            JS_SetPropertyStr(ctx, objects[i], name, JS_NewInt32(ctx, i)) < 0)
            goto end;
    }
    args[1] = JS_NewInt32(ctx, 99);
    for (unsigned pass = 0; pass < 2; ++pass)
        for (i = 0; i < 8; ++i) {
            args[0] = objects[i];
            if (expect(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 2, (JSValueConst *)args), 99))
                goto end;
        }
    JS_ComputeMemoryUsage(rt, &usage);
    JS_SetMemoryLimit(rt, (size_t)usage.malloc_size + 1);
    args[0] = objects[8];
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 2, (JSValueConst *)args);
    JS_SetMemoryLimit(rt, 0);
    if (expect(ctx, result, 99))
        goto end;
    for (unsigned pass = 0; pass < 2; ++pass)
        for (i = 0; i < 9; ++i) {
            args[0] = objects[i];
            if (expect(ctx, JS_Call(ctx, fn, JS_UNDEFINED, 2, (JSValueConst *)args), 99))
                goto end;
        }
    JS_RunGC(rt);
    for (i = 0; i < 9; ++i)
        if (expect(ctx, JS_GetPropertyStr(ctx, objects[i], "value"), 99))
            goto end;
    puts("NINTH_SHAPE_OOM preserved writes and subsequent GC/reuse");
    code = 0;
end:
    JS_SetMemoryLimit(rt, 0);
    for (i = 0; i < 9; ++i)
        JS_FreeValue(ctx, objects[i]);
    JS_FreeValue(ctx, fn);
    return code;
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    JSContext *ctx = rt ? JS_NewContext(rt) : NULL;
    int code = 1;
    if (!ctx) {
        if (rt)
            JS_FreeRuntime(rt);
        return 1;
    }
    JS_NewClassID(rt, &probe_class);
    if (JS_NewClass(rt, probe_class, &probe_definition) < 0)
        goto end;
    if (prototype_lifetimes(ctx, rt) || ninth_shape_oom(ctx, rt))
        goto end;
    puts("ADAPTIVE_INSTALLED_PUBLIC_CONTRACT_OK");
    code = 0;
end:
    if (code) {
        JSValue exception = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, exception);
        fprintf(stderr, "ADAPTIVE_INSTALLED_FAILURE finalized=%u exception=%s\n", finalized,
                text ? text : "unknown");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, exception);
    }
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    return code;
}
