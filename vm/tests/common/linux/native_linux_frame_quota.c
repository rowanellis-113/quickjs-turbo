/* Public-API regression for the Linux development frame foundation. */
#include "quickjs.h"
#include <stdio.h>
#include <string.h>

static int interrupted(JSContext *ctx, void *opaque)
{
    (void)ctx;
    int *count = opaque;
    return ++*count > 2;
}

static JSValue reenter(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    (void)this_value;
    if (argc != 1 || !JS_IsFunction(ctx, argv[0]))
        return JS_ThrowTypeError(ctx, "function required");
    JS_SetMaxStackSize(JS_GetRuntime(ctx), 128 * 1024);
    JS_RunGC(JS_GetRuntime(ctx));
    JSValue value = JS_Call(ctx, argv[0], JS_UNDEFINED, 0, NULL);
    JS_SetMaxStackSize(JS_GetRuntime(ctx), 64 * 1024);
    return value;
}

static JSValue eval(JSContext *ctx, const char *source)
{
    return JS_Eval(ctx, source, strlen(source), "linux-frame-quota", JS_EVAL_TYPE_GLOBAL);
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    if (!rt)
        return 1;
    JSContext *ctx = JS_NewContext(rt);
    if (!ctx)
        return 2;
    JS_SetMaxStackSize(rt, 64 * 1024);
    JSValue value = eval(ctx, "function depth(n) { return n ? depth(n-1)+1 : 1; } depth(100000);");
    if (!JS_IsException(value)) {
        fprintf(stderr, "deep recursion failed to enforce the runtime stack quota\n");
        return 3;
    }
    JSValue error = JS_GetException(ctx);
    if (!JS_IsError(error))
        return 4;
    JS_FreeValue(ctx, error);
    JS_FreeValue(ctx, value);
    value = eval(ctx, "depth(10);");
    int32_t answer = 0;
    if (JS_ToInt32(ctx, &answer, value) || answer != 11)
        return 5;
    JS_FreeValue(ctx, value);
    JSValue global = JS_GetGlobalObject(ctx);
    if (JS_SetPropertyStr(ctx, global, "nativeReenter",
                          JS_NewCFunction(ctx, reenter, "nativeReenter", 1)) < 0)
        return 6;
    JS_FreeValue(ctx, global);
    value = eval(ctx, "function outer() { return nativeReenter(() => 42); } outer();");
    if (JS_ToInt32(ctx, &answer, value) || answer != 42)
        return 7;
    JS_FreeValue(ctx, value);
    value = eval(ctx, "depth(10);");
    if (JS_ToInt32(ctx, &answer, value) || answer != 11)
        return 8;
    JS_FreeValue(ctx, value);
    int count = 0;
    JS_SetInterruptHandler(rt, interrupted, &count);
    value = eval(ctx, "function spin() { let n=0; while(true) n++; } spin();");
    JS_SetInterruptHandler(rt, NULL, NULL);
    if (!JS_IsException(value) || count <= 2)
        return 9;
    error = JS_GetException(ctx);
    JS_FreeValue(ctx, error);
    JS_FreeValue(ctx, value);
    value = eval(ctx, "21+21;");
    if (JS_ToInt32(ctx, &answer, value) || answer != 42)
        return 10;
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("LINUX_FRAME_QUOTA_REENTRY_INTERRUPT_OK");
    return 0;
}
