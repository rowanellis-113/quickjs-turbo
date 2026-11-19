/* Public installed API host for unchanged strict property/prototype fixtures. */
#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned collections;
static JSValue host_gc(JSContext *ctx, JSValueConst value, int argc, JSValueConst *argv)
{
    (void)value;
    (void)argc;
    (void)argv;
    ++collections;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue host_print(JSContext *ctx, JSValueConst value, int argc, JSValueConst *argv)
{
    (void)value;
    for (int i = 0; i < argc; ++i) {
        const char *text = JS_ToCString(ctx, argv[i]);
        if (!text)
            return JS_EXCEPTION;
        if (i)
            putchar(' ');
        fputs(text, stdout);
        JS_FreeCString(ctx, text);
    }
    putchar('\n');
    return JS_UNDEFINED;
}
static int execute(JSRuntime *rt, const char *path)
{
    FILE *file = fopen(path, "rb");
    if (!file)
        return 1;
    if (fseek(file, 0, SEEK_END)) {
        fclose(file);
        return 2;
    }
    long length = ftell(file);
    if (length < 0 || fseek(file, 0, SEEK_SET)) {
        fclose(file);
        return 3;
    }
    char *source = malloc((size_t)length + 1);
    if (!source) {
        fclose(file);
        return 4;
    }
    size_t bytes = fread(source, 1, (size_t)length, file);
    fclose(file);
    if (bytes != (size_t)length) {
        free(source);
        return 5;
    }
    source[bytes] = 0;
    JSContext *ctx = JS_NewContext(rt);
    if (!ctx) {
        free(source);
        return 6;
    }
    JSValue global = JS_GetGlobalObject(ctx);
    int code = JS_SetPropertyStr(ctx, global, "gc", JS_NewCFunction(ctx, host_gc, "gc", 0));
    if (code >= 0)
        code =
            JS_SetPropertyStr(ctx, global, "print", JS_NewCFunction(ctx, host_print, "print", 1));
    JS_FreeValue(ctx, global);
    if (code >= 0) {
        JSValue result =
            JS_Eval(ctx, source, bytes, path, JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_STRICT);
        if (JS_IsException(result)) {
            JSValue error = JS_GetException(ctx);
            const char *text = JS_ToCString(ctx, error);
            fprintf(stderr, "%s: %s\n", path, text ? text : "exception");
            JS_FreeCString(ctx, text);
            JS_FreeValue(ctx, error);
            code = -1;
        }
        JS_FreeValue(ctx, result);
    }
    free(source);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    return code < 0 ? 7 : 0;
}
int main(int argc, char **argv)
{
    if (argc != 3)
        return 8;
    JSRuntime *rt = JS_NewRuntime();
    if (!rt)
        return 9;
    int code = execute(rt, argv[1]);
    if (!code)
        code = execute(rt, argv[2]);
    JS_FreeRuntime(rt);
    if (code)
        return code;
    if (!collections)
        return 10;
    printf("METHOD_PUBLIC_OK gc=%u\n", collections);
    return 0;
}
