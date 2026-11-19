/* Public JSON family ownership, GC/reentry, source records and fault ledger. */
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error JSON family qualification needs assertions.
#endif
#include "../native_oom_allocator.h"
extern int JS_FrameCallbackScopeProbe(JSContext *, uintptr_t *);
typedef struct {
    unsigned calls, prepared, collections, reentries;
    int exercise;
    JSContext *other;
    JSValue nested;
} Observer;
static JSValue observe(JSContext *ctx, JSValueConst this_value, int argc, JSValueConst *argv)
{
    JSRuntime *rt = JS_GetRuntime(ctx);
    Observer *o = JS_GetRuntimeOpaque(rt);
    uintptr_t before[6], after[6];
    ++o->calls;
    if (JS_FrameCallbackScopeProbe(ctx, before)) {
        ++o->prepared;
        if (o->exercise && o->prepared % 7 == 0) {
            JS_RunGC(rt);
            ++o->collections;
            JSValue value = JS_Call(o->other, o->nested, JS_UNDEFINED, 0, NULL);
            int32_t nested = 0;
            assert(!JS_IsException(value) && JS_ToInt32(o->other, &nested, value) == 0 &&
                   nested == 42);
            JS_FreeValue(o->other, value);
            ++o->reentries;
            assert(JS_FrameCallbackScopeProbe(ctx, after) &&
                   !memcmp(before, after, sizeof(before)));
        }
    }
    return JS_UNDEFINED;
}
static void exception(JSContext *ctx)
{
    JSValue error = JS_GetException(ctx);
    const char *text = JS_ToCString(ctx, error);
    fprintf(stderr, "JSON_EXCEPTION %s\n", text ? text : "<OOM>");
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, error);
}
static JSValue evaluate(JSContext *ctx, const char *code)
{
    JSValue value = JS_Eval(ctx, code, strlen(code), "linux-json-family", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        exception(ctx);
        abort();
    }
    return value;
}
static void install(JSContext *ctx, Observer *o)
{
    JS_SetRuntimeOpaque(JS_GetRuntime(ctx), o);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "jsonProbe",
                             JS_NewCFunction(ctx, observe, "jsonProbe", 0)) >= 0);
    JS_FreeValue(ctx, global);
}
static void semantics(const char *path, const char *expect)
{
    FILE *file = fopen(path, "rb");
    assert(file);
    assert(!fseek(file, 0, SEEK_END));
    long size = ftell(file);
    assert(size > 0);
    rewind(file);
    char *code = malloc((size_t)size + 1);
    assert(code);
    assert(fread(code, 1, (size_t)size, file) == (size_t)size);
    fclose(file);
    code[size] = 0;
    Observer o = {0};
    o.exercise = 1;
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    o.other = JS_NewContext(rt);
    assert(o.other);
    o.nested = evaluate(o.other, "(function(){return JSON.parse('{\"other\":42}').other;})");
    install(ctx, &o);
    JSValue result = evaluate(ctx, code);
    free(code);
    JSValue passed = JS_GetPropertyStr(ctx, result, "passed");
    assert(JS_ToBool(ctx, passed) == 1);
    JS_FreeValue(ctx, passed);
    /* Golden values independently checked on stock NG and the prior product. */
    uint32_t checks = 0, digest = 0;
    JSValue field = JS_GetPropertyStr(ctx, result, "checks");
    assert(JS_ToUint32(ctx, &checks, field) == 0 && checks == 130);
    JS_FreeValue(ctx, field);
    field = JS_GetPropertyStr(ctx, result, "digest");
    assert(JS_ToUint32(ctx, &digest, field) == 0 && digest == UINT32_C(4216061805));
    JS_FreeValue(ctx, field);
    JSValue text = JS_JSONStringify(ctx, result, JS_UNDEFINED, JS_UNDEFINED);
    assert(!JS_IsException(text));
    const char *output = JS_ToCString(ctx, text);
    assert(output);
    printf("JSON_RESULT %s\n", output);
    JS_FreeCString(ctx, output);
    JS_FreeValue(ctx, text);
    assert(o.calls && !JS_FrameCallbackScopeProbe(ctx, NULL));
    if (expect) {
        assert(!strcmp(expect, "active") || !strcmp(expect, "idle"));
        if (!strcmp(expect, "active"))
            assert(o.prepared && o.collections && o.reentries == o.collections);
        else
            assert(!o.prepared && !o.collections && !o.reentries);
    }
    printf("LINUX_JSON_SEMANTICS_OK calls=%u prepared=%u gc=%u reentry=%u\n", o.calls, o.prepared,
           o.collections, o.reentries);
    JS_FreeValue(ctx, result);
    JS_FreeValue(o.other, o.nested);
    JS_RunGC(rt);
    JS_FreeContext(o.other);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
}
static const char *setup =
    "var payload='{'+Array.from({length:20},(_,i)=>'\"k'+i+'\":'+i).join(',')+',\"u\":\"é𠀀\"}';"
    "var data=JSON.parse(payload);"
    "var ascii=payload.replace(/é𠀀/g,'ascii');"
    "function source(k,v,c){jsonProbe();return v;}"
    "function value(k,v){jsonProbe();return v;}"
    "function replacer(k,v,missing){v=typeof v==='number'?v+1:v;jsonProbe();return v;}"
    "function runSource(){return JSON.parse(payload,source);}"
    "function runSourceASCII(){return JSON.parse(ascii,source);}"
    "function runParse(){return JSON.parse(payload);}"
    "function runValue(){return JSON.parse(payload,value);}"
    "function runWriteRO(){return JSON.stringify(data,value);}"
    "function runWrite(){return JSON.stringify(data,replacer);}"
    "source('',1,{});value('',1);replacer('',1);";
static unsigned failures, injected;
static size_t trial(const char *name, size_t fault)
{
    Allocator memory = {0};
    Observer o = {0};
    JSRuntime *rt = JS_NewRuntime2(&functions, &memory);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    install(ctx, &o);
    JSValue value = evaluate(ctx, setup);
    JS_FreeValue(ctx, value);
    JSValue global = JS_GetGlobalObject(ctx), fn = JS_GetPropertyStr(ctx, global, name);
    JS_FreeValue(ctx, global);
    assert(JS_IsFunction(ctx, fn));
    for (int i = 0; i < 2; ++i) {
        value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        if (JS_IsException(value)) {
            exception(ctx);
            abort();
        }
        JS_FreeValue(ctx, value);
    }
    size_t before = memory.sequence;
    memory.fail_at = fault ? before + fault : 0;
    value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    memory.fail_at = 0;
    size_t count = memory.sequence - before;
    injected += memory.rejected;
    if (JS_IsException(value)) {
        ++failures;
        value = JS_GetException(ctx);
    }
    JS_FreeValue(ctx, value);
    assert(!JS_FrameCallbackScopeProbe(ctx, NULL));
    value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    if (JS_IsException(value)) {
        exception(ctx);
        abort();
    }
    assert(!strncmp(name, "runWrite", 8) ? JS_IsString(value) : JS_IsObject(value));
    JS_FreeValue(ctx, value);
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    if (memory.live || memory.bytes)
        fprintf(stderr, "JSON_OOM_LEAK case=%s fault=%zu live=%zu bytes=%zu\n", name, fault,
                memory.live, memory.bytes);
    assert(memory.live == 0 && memory.bytes == 0);
    return count;
}
int main(int argc, char **argv)
{
    assert(argc > 1);
    if (argc == 4 && !strcmp(argv[1], "fault")) {
        trial(argv[2], (size_t)strtoull(argv[3], NULL, 10));
        return 0;
    }
    if (strcmp(argv[1], "sweep"))
        semantics(argv[1], argc == 3 ? argv[2] : NULL);
    else {
        const char *cases[] = {"runParse",  "runValue",   "runSourceASCII",
                               "runSource", "runWriteRO", "runWrite"};
        for (unsigned i = 0; i < sizeof(cases) / sizeof(*cases); ++i) {
            size_t count = trial(cases[i], 0);
            unsigned initial_failures = failures;
            for (size_t fault = 1; fault <= count + 1; ++fault)
                trial(cases[i], fault);
            assert(failures > initial_failures);
            printf("JSON_OOM_CASE %s allocations=%zu failures=%u\n", cases[i], count,
                   failures - initial_failures);
        }
        assert(injected && failures);
        printf("LINUX_JSON_OOM_OK failures=%u injected=%u\n", failures, injected);
    }
    return 0;
}
