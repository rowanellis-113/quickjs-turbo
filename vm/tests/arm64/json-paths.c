/* Public builtin/API JSON roundtrip and passive native vector path evidence. MIT. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef QJS_AARCH64_VM_INSTRUMENT
#include "src/arm64/linux/interpreter-observe.h"
#endif
int main(int argc, char **argv)
{
    assert(argc == 2);
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
#ifdef QJS_AARCH64_VM_INSTRUMENT
    uint64_t before[2], after[2];
    qjs_aarch64_json_vector_counts(before);
#endif
    const char *code =
        "(function(){const seeds=['a','é','€','😀','\\ud800','\\\\','\\u0000','\\\"'];"
        "const lengths=[0,1,7,8,15,16,17,31,32,33,63,64,65,127,128,129];const result=[];"
        "for(const seed of seeds)for(const n of lengths){const text=seed.repeat(n);"
        "const encoded=JSON.stringify(text);if(JSON.parse(encoded)!==text)throw Error('builtin roundtrip');"
        "result.push({text,encoded});}return result;})()";
    JSValue value = JS_Eval(ctx, code, strlen(code), "arm-json-public-paths", JS_EVAL_TYPE_GLOBAL);
    assert(!JS_IsException(value));
    JSValue encoded = JS_JSONStringify(ctx, value, JS_UNDEFINED, JS_UNDEFINED);
    assert(!JS_IsException(encoded));
    size_t length;
    const char *text = JS_ToCStringLen(ctx, &length, encoded);
    assert(text);
    JSValue parsed = JS_ParseJSON(ctx, text, length, "arm-json-public-api");
    assert(!JS_IsException(parsed));
    JSValue again = JS_JSONStringify(ctx, parsed, JS_UNDEFINED, JS_UNDEFINED);
    assert(!JS_IsException(again));
    size_t other_length;
    const char *other = JS_ToCStringLen(ctx, &other_length, again);
    assert(other);
    assert(length == other_length && !memcmp(text, other, length));
    uint32_t digest = 2166136261u;
    for (size_t i = 0; i < length; ++i)
        digest = (digest ^ (uint8_t)text[i]) * 16777619u;
#ifdef QJS_AARCH64_VM_INSTRUMENT
    qjs_aarch64_json_vector_counts(after);
    if (!strcmp(argv[1], "active"))
        assert(after[0] > before[0] && after[1] > before[1]);
    else {
        assert(!strcmp(argv[1], "idle"));
        assert(after[0] == before[0] && after[1] == before[1]);
    }
    printf("AARCH64_JSON_NATIVE_VECTORS loads=%llu stores=%llu\n",
           (unsigned long long)(after[0] - before[0]), (unsigned long long)(after[1] - before[1]));
#else
    (void)argv;
#endif
    JS_FreeCString(ctx, other);
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, again);
    JS_FreeValue(ctx, parsed);
    JS_FreeValue(ctx, encoded);
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("AARCH64_JSON_PATHS_OK cases=128 bytes=%zu digest=%u\n", length, digest);
    return 0;
}
