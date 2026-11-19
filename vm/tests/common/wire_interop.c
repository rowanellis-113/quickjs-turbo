/* Public bytecode exchange between separately built engines and LP64 ISAs. */
#include "quickjs.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char source[] = "(()=>{const make=x=>y=>x+y;const f=make(40);"
                             "const r=/ab+/g.exec('cabb')[0];"
                             "return [f(2),r,12345678901234567890n.toString(),"
                             "JSON.parse('{\"v\":7}').v,new Uint8Array([1,2,3])[2]].join(':')})()";
static const char expected[] = "42:abb:12345678901234567890:7:3";

int main(int argc, char **argv)
{
    JSRuntime *rt = NULL;
    JSContext *ctx = NULL;
    JSValue value = JS_UNDEFINED;
    FILE *file = NULL;
    uint8_t *data = NULL;
    size_t size = 0;
    int status = 1;
    if (argc != 3 || (strcmp(argv[1], "write") && strcmp(argv[1], "read"))) {
        fprintf(stderr, "Usage: wire_interop write|read file\n");
        return 2;
    }
    rt = JS_NewRuntime();
    if (!rt || !(ctx = JS_NewContext(rt)))
        goto done;
    if (!strcmp(argv[1], "write")) {
        value = JS_Eval(ctx, source, sizeof(source) - 1, "wire-interop.js",
                        JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
        if (JS_IsException(value))
            goto done;
        data = JS_WriteObject(ctx, &size, value, JS_WRITE_OBJ_BYTECODE);
        if (!data || !(file = fopen(argv[2], "wb")) || fwrite(data, 1, size, file) != size)
            goto done;
        status = fclose(file);
        file = NULL;
    } else {
        long length;
        if (!(file = fopen(argv[2], "rb")) || fseek(file, 0, SEEK_END) ||
            (length = ftell(file)) <= 0 || length > 16 * 1024 * 1024 || fseek(file, 0, SEEK_SET))
            goto done;
        size = (size_t)length;
        if (!(data = js_malloc(ctx, size)) || fread(data, 1, size, file) != size)
            goto done;
        value = JS_ReadObject(ctx, data, size, JS_READ_OBJ_BYTECODE);
        if (JS_IsException(value))
            goto done;
        value = JS_EvalFunction(ctx, value);
        if (!JS_IsException(value)) {
            const char *text = JS_ToCString(ctx, value);
            if (text && !strcmp(text, expected))
                status = 0;
            JS_FreeCString(ctx, text);
        }
    }
done:
    if (ctx) {
        if (status) {
            JSValue error = JS_GetException(ctx);
            const char *text = JS_ToCString(ctx, error);
            fprintf(stderr, "WIRE_INTEROP_FAILED: %s\n", text ? text : "I/O or allocation");
            JS_FreeCString(ctx, text);
            JS_FreeValue(ctx, error);
        }
        JS_FreeValue(ctx, value);
        js_free(ctx, data);
        JS_FreeContext(ctx);
    }
    if (file)
        fclose(file);
    if (rt)
        JS_FreeRuntime(rt);
    if (!status)
        printf("WIRE_INTEROP_OK %s\n", argv[1]);
    return status;
}
