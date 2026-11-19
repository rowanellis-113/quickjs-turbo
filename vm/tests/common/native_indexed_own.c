/* Public API lifetime checks. Finalizers only increment a counter. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static JSClassID resource_class;
static unsigned finalized;
static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    finalized++;
}
static JSValue resource(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewObjectClass(ctx, resource_class);
}
static JSValue temporary(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue a = JS_NewArray(ctx);
    assert(!JS_IsException(a));
    assert(JS_DefinePropertyValueUint32(ctx, a, 0, JS_NewInt32(ctx, 42),
                                        JS_PROP_CONFIGURABLE | JS_PROP_WRITABLE) > 0);
    assert(JS_SetPropertyUint32(ctx, a, 1, JS_NewObjectClass(ctx, resource_class)) > 0);
    return a;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *s)
{
    JSValue v = JS_Eval(ctx, s, strlen(s), "indexed-own-host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, e);
        fprintf(stderr, "indexed own exception: %s\n", message ? message : "?");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, e);
        assert(0);
    }
    return v;
}
static void run_numbers(JSContext *ctx, const char *source, unsigned releases)
{
    JSValue fn = evaluate(ctx, source);
    for (unsigned i = 0; i < 32; i++) {
        unsigned before = finalized;
        JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        int n;
        assert(!JS_IsException(v));
        assert(JS_ToInt32(ctx, &n, v) == 0 && n == 42);
        assert(finalized == before + releases);
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, fn);
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_NewClassID(rt, &resource_class);
    JSClassDef def = {0};
    def.class_name = "IndexedResource";
    def.finalizer = finalize;
    assert(JS_NewClass(rt, resource_class, &def) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "indexedResource",
                             JS_NewCFunction(ctx, resource, "indexedResource", 0)) > 0);
    assert(JS_SetPropertyStr(ctx, global, "indexedTemporary",
                             JS_NewCFunction(ctx, temporary, "indexedTemporary", 0)) > 0);
    assert(JS_SetPropertyStr(ctx, global, "indexedGC",
                             JS_NewCFunction(ctx, collect, "indexedGC", 0)) > 0);
    JS_FreeValue(ctx, global);
    run_numbers(ctx, "(function indexedLastRead(){return indexedTemporary()[0]})", 1);
    run_numbers(ctx, "(function indexedLastWrite(){indexedTemporary()[0]=21;return 42})", 1);
    run_numbers(
        ctx,
        "(function indexedOldResource(){let a=[];Object.defineProperty(a,0,{value:indexedResource(),writable:true,configurable:true});a[0]=42;return a[0]})",
        1);
    run_numbers(
        ctx,
        "(function indexedAliasRelease(){function make(){let a=[];Object.defineProperty(a,0,{value:0,writable:true,configurable:true});a[0]=a;a[1]=indexedResource();return a}make()[0]=42;return 42})",
        1);
    run_numbers(
        ctx,
        "(function indexedGetterGC(){let live={n:42};live.self=live;let a=[];Object.defineProperty(a,0,{get(){indexedGC();return live}});return a[0].n})",
        0);
    JSValue fn = evaluate(
        ctx,
        "(function indexedReturnedResource(){let a=[];Object.defineProperty(a,0,{value:indexedResource(),writable:true,configurable:true});return a[0]})");
    for (unsigned i = 0; i < 32; i++) {
        unsigned before = finalized;
        JSValue v = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(v) && JS_IsObject(v));
        assert(finalized == before);
        JS_FreeValue(ctx, v);
        assert(finalized == before + 1);
    }
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(finalized == 160);
    printf("INDEXED OWN HOST PASS finalized=%u getter_gc=32\n", finalized);
    return 0;
}
