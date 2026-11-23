/* Public-API wire round trips, feature fallback, GC and OOM recovery. MIT. */
#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "WIRE line=%d: %s\n", __LINE__, #x);                                   \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

static void clear_exception(JSContext *ctx)
{
    JSValue error = JS_GetException(ctx);
    JS_FreeValue(ctx, error);
}

static void expect(JSContext *ctx, JSValue value, const char *expected)
{
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "WIRE exception: %s\n", message ? message : "<OOM>");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        exit(1);
    }
    const char *actual = JS_ToCString(ctx, value);
    CHECK(actual && strcmp(actual, expected) == 0);
    JS_FreeCString(ctx, actual);
    JS_FreeValue(ctx, value);
}

static void roundtrip(JSRuntime *rt, JSContext *ctx, const char *source, const char *check,
                      const char *expected, int version)
{
    JSValue original = JS_Eval(ctx, source, strlen(source), "wire.js",
                               JS_EVAL_TYPE_GLOBAL | (check ? 0 : JS_EVAL_FLAG_COMPILE_ONLY));
    CHECK(!JS_IsException(original));
    for (unsigned strip = 0; strip < 4; strip++) {
        if (getenv("FRAME_TEST_WIRE_VERBOSE")) {
            fprintf(stderr, "WIRE roundtrip version=%d strip=%u source=%s\n", version, strip,
                    source);
            fflush(stderr);
        }
        int flags = JS_WRITE_OBJ_BYTECODE | JS_WRITE_OBJ_REFERENCE;
        if (strip & 1)
            flags |= JS_WRITE_OBJ_STRIP_SOURCE;
        if (strip & 2)
            flags |= JS_WRITE_OBJ_STRIP_DEBUG;
        size_t size = 0;
        uint8_t *blob = JS_WriteObject(ctx, &size, original, flags);
        CHECK(blob && size > 5);
        if (strcmp(JS_GetVersion(), "0.17.0") == 0)
            CHECK(blob[0] == version);
        JS_RunGC(rt);
        /* The failed operations must leave no partial owner or pending error
           behind. Retry the same live input/blob after restoring the limit. */
        JS_SetMemoryLimit(rt, 1);
        size_t failed_size = 99;
        uint8_t *failed = JS_WriteObject(ctx, &failed_size, original, flags);
        CHECK(!failed && failed_size == 0);
        clear_exception(ctx);
        JSValue value =
            JS_ReadObject(ctx, blob, size, JS_READ_OBJ_BYTECODE | JS_READ_OBJ_REFERENCE);
        CHECK(JS_IsException(value));
        clear_exception(ctx);
        JS_SetMemoryLimit(rt, SIZE_MAX);
        JS_RunGC(rt);
        value = JS_ReadObject(ctx, blob, size, JS_READ_OBJ_BYTECODE | JS_READ_OBJ_REFERENCE);
        CHECK(!JS_IsException(value));
        if (check) {
            JSValue global = JS_GetGlobalObject(ctx);
            CHECK(JS_SetPropertyStr(ctx, global, "wire_input", value) >= 0);
            JS_FreeValue(ctx, global);
            value = JS_Eval(ctx, check, strlen(check), "wire-check.js", JS_EVAL_TYPE_GLOBAL);
        } else
            value = JS_EvalFunction(ctx, value);
        expect(ctx, value, expected);
        size_t again_size = 0;
        uint8_t *again = JS_WriteObject(ctx, &again_size, original, flags);
        CHECK(again && size == again_size && memcmp(blob, again, size) == 0);
        js_free(ctx, again);
        js_free(ctx, blob);
    }
    JS_FreeValue(ctx, original);
    JS_RunGC(rt);
}

int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    roundtrip(rt, ctx, "JSON.stringify(/ab+/g.exec('cabb'))", NULL, "[\"abb\"]", 29);
    roundtrip(
        rt, ctx,
        "(()=>{const m=/(?<x>a+)(b)\\k<x>/d.exec('zaabaa');return JSON.stringify([m[0],m.groups.x,m.indices[1]]);})()",
        NULL, "[\"aabaa\",\"aa\",[1,3]]", 29);
    roundtrip(rt, ctx, "JSON.stringify(/(?<=foo)(bar|baz){1,3}/i.exec('fooBARbaz'))", NULL,
              "[\"BARbaz\",\"baz\"]", 29);
    roundtrip(rt, ctx, "/a(b+)/g", "JSON.stringify(wire_input.exec('abbb'))", "[\"abbb\",\"bbb\"]",
              29);
    roundtrip(rt, ctx, "/\\p{Script=Unknown}/u.test(String.fromCharCode(0x378))", NULL, "true",
              29);
    roundtrip(rt, ctx, "new RegExp('(:?'.repeat(18)+'(?:a|)+'+'|)+'.repeat(18))",
              "String(wire_input.source === '(:?'.repeat(18)+'(?:a|)+'+'|)+'.repeat(18))", "true",
              29);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    puts("WIRE_PASS regexp literals/objects, captures, GC, OOM, versioned features");
    return 0;
}
