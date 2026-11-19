/* Actual generic/magic C ABI, padding, live callee changes, realm, owning
 * results, exceptions, GC reentry and stack-limit refresh. No VM field reads. */
#include "quickjs.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

typedef struct InvokeTest {
    JSContext *caller, *realm;
    JSValue nested;
    int actual, formal, magic, method, result_kind, failures, calls;
} InvokeTest;

static JSValue invoke_checked(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv,
                              int magic)
{
    InvokeTest *test = JS_GetContextOpaque(ctx);
    JSValue value;
    int32_t n;
    if (ctx != test->realm || argc != test->actual || magic != test->magic)
        goto fail;
    for (int i = 0; i < argc || i < test->formal; ++i) {
        if (i >= argc) {
            if (!JS_IsUndefined(argv[i]))
                goto fail;
        } else if (JS_ToInt32(ctx, &n, argv[i]) < 0 || n != i - 13) {
            goto fail;
        }
    }
    if (test->method) {
        value = JS_GetPropertyStr(ctx, self, "marker");
        if (JS_IsException(value))
            return value;
        int valid = JS_ToInt32(ctx, &n, value) == 0 && n == 42;
        JS_FreeValue(ctx, value);
        if (!valid)
            goto fail;
    } else if (!JS_IsUndefined(self)) {
        goto fail;
    }
    ++test->calls;
    JS_RunGC(JS_GetRuntime(ctx));
    value = JS_Call(test->caller, test->nested, JS_UNDEFINED, 0, NULL);
    if (JS_IsException(value))
        return value;
    int valid = JS_ToInt32(ctx, &n, value) == 0 && n == 31;
    JS_FreeValue(ctx, value);
    if (!valid)
        goto fail;
    switch (test->result_kind) {
    case 1:
        return JS_NewFloat64(ctx, -1234.75);
    case 2:
        return JS_NewString(ctx, "native result");
    case 3:
        return JS_ThrowRangeError(ctx, "native expected exception");
    case 4:
        JS_SetMaxStackSize(JS_GetRuntime(ctx), 0);
        return JS_NewInt32(ctx, 17);
    case 5:
        JS_SetMaxStackSize(JS_GetRuntime(ctx), 1024 * 1024);
        return JS_NewInt32(ctx, 17);
    default:
        return JS_NewInt32(ctx, 17);
    }
fail:
    ++test->failures;
    return JS_ThrowInternalError(ctx, "Linux C ABI argc=%d formal=%d magic=%d", argc, test->formal,
                                 magic);
}

static JSValue native_generic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    return invoke_checked(ctx, self, argc, argv, 0);
}
static JSValue native_magic(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv,
                            int magic)
{
    return invoke_checked(ctx, self, argc, argv, magic);
}

static int run_case(InvokeTest *test, JSValue global, int formal, int actual, int magic, int method)
{
    JSContext *ctx = test->caller;
    JSValue fn, box, root, result;
    char code[4096];
    size_t used;
    test->formal = formal;
    test->actual = actual;
    test->magic = magic;
    test->method = method;
    fn = magic ? JS_NewCFunctionMagic(test->realm, native_magic, "foreignMagic", formal,
                                      JS_CFUNC_generic_magic, magic)
               : JS_NewCFunction(test->realm, native_generic, "foreignGeneric", formal);
    if (JS_IsException(fn))
        return -1;
    if (JS_SetPropertyStr(ctx, global, "nativeTarget", JS_DupValue(ctx, fn)) < 0) {
        JS_FreeValue(ctx, fn);
        return -1;
    }
    box = JS_NewObject(ctx);
    if (JS_IsException(box)) {
        JS_FreeValue(ctx, fn);
        return -1;
    }
    JS_SetPropertyStr(ctx, box, "marker", JS_NewInt32(ctx, 42));
    JS_SetPropertyStr(ctx, box, "fn", fn);
    if (JS_SetPropertyStr(ctx, global, "nativeBox", box) < 0)
        return -1;
    used = (size_t)snprintf(code, sizeof(code), "(function(){return %s(",
                            method ? "nativeBox.fn" : "nativeTarget");
    for (int i = 0; i < actual; ++i)
        used += (size_t)snprintf(code + used, sizeof(code) - used, "%s%d", i ? "," : "", i - 13);
    used += (size_t)snprintf(code + used, sizeof(code) - used, ")})");
    root = JS_Eval(ctx, code, used, "linux-c-invoke", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(root))
        return -1;
    for (int kind = 0; kind < 6; ++kind) {
        int valid = 0;
        int32_t integer;
        double number;
        test->result_kind = kind;
        result = JS_Call(ctx, root, JS_UNDEFINED, 0, NULL);
        if (kind == 3) {
            valid = JS_IsException(result);
            result = JS_GetException(ctx);
        } else if (!JS_IsException(result)) {
            if (kind == 1)
                valid = JS_ToFloat64(ctx, &number, result) == 0 && number == -1234.75;
            else if (kind == 2) {
                const char *text = JS_ToCString(ctx, result);
                valid = text && !strcmp(text, "native result");
                JS_FreeCString(ctx, text);
            } else
                valid = JS_ToInt32(ctx, &integer, result) == 0 && integer == 17;
        }
        JS_FreeValue(ctx, result);
        if (!valid) {
            JS_FreeValue(ctx, root);
            return -1;
        }
    }
    JS_FreeValue(ctx, root);
    return 0;
}

int main(void)
{
    const int formals[] = {0, 1, 2, 7, 255};
    const int actuals[] = {0, 1, 2, 7, 255, 256};
    JSRuntime *rt = JS_NewRuntime();
    JSContext *caller = rt ? JS_NewContext(rt) : NULL;
    JSContext *realm = caller ? JS_NewContext(rt) : NULL;
    JSValue global = JS_UNDEFINED;
    InvokeTest test = {.caller = caller, .realm = realm, .nested = JS_UNDEFINED};
    int status = 1;
    if (!realm)
        goto done;
    JS_SetMaxStackSize(rt, 1024 * 1024);
    JS_SetContextOpaque(caller, &test);
    JS_SetContextOpaque(realm, &test);
    const char *nested = "(function(){return 31})";
    test.nested = JS_Eval(caller, nested, strlen(nested), "nested", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(test.nested))
        goto done;
    global = JS_GetGlobalObject(caller);
    for (unsigned f = 0; f < sizeof(formals) / sizeof(formals[0]); ++f)
        for (unsigned a = 0; a < sizeof(actuals) / sizeof(actuals[0]); ++a)
            for (int method = 0; method < 2; ++method)
                for (int magic = 0; magic < 2; ++magic)
                    if (run_case(&test, global, formals[f], actuals[a], magic ? -1234 : 0, method))
                        goto done;
    if (test.failures || test.calls != 720)
        goto done;
    printf("LINUX_C_INVOKE_ABI_OK calls=%d\n", test.calls);
    status = 0;
done:
    if (status && caller) {
        JSValue error = JS_GetException(caller);
        const char *message = JS_ToCString(caller, error);
        fprintf(stderr, "C invoke failure calls=%d: %s\n", test.calls,
                message ? message : "unknown");
        JS_FreeCString(caller, message);
        JS_FreeValue(caller, error);
    }
    if (caller) {
        JS_FreeValue(caller, test.nested);
        JS_FreeValue(caller, global);
    }
    if (realm)
        JS_FreeContext(realm);
    if (caller)
        JS_FreeContext(caller);
    if (rt)
        JS_FreeRuntime(rt);
    return status;
}
