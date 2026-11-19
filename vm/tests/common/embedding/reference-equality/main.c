/* Public API ownership check. No JS execution in the finalizer. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static JSClassID resource_class;
static unsigned finalized;
static void finish(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    finalized++;
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewObjectClass(ctx, resource_class);
}
static JSValue count(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewUint32(ctx, finalized);
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_NewClassID(rt, &resource_class);
    JSClassDef def = {0};
    def.class_name = "StrictResource";
    def.finalizer = finish;
    assert(JS_NewClass(rt, resource_class, &def) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "make", JS_NewCFunction(ctx, make, "make", 0)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "count", JS_NewCFunction(ctx, count, "count", 0)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "collect", JS_NewCFunction(ctx, collect, "collect", 0)) >=
           0);
    const char *source =
        "function check(v,m){if(!v)throw Error(m)}"
        "function eq(a,b){return a===b}function ne(a,b){return a!==b}"
        "function differentLast(){return make()===make()}"
        "function differentNe(){return make()!==make()}"
        "function localSame(){let x=make();return x===x}"
        "let shared;function takeAndClear(){let x=shared;shared=undefined;return x}"
        "function exactlyTwo(){shared=make();return shared===takeAndClear()}"
        "function mixedLast(o){return make()===o}"
        "for(let i=0;i<128;i++){let b=count();"
        "check(differentLast()===false,'distinct last eq');check(count()===b+2,'two immediate releases');"
        "check(differentNe()===true,'distinct last ne');check(count()===b+4,'ne immediate releases');"
        "check(localSame()===true,'nonlast alias');check(count()===b+5,'local final release');"
        "check(exactlyTwo()===true,'exact two aliases');check(count()===b+6,'alias last release');"
        "let a=make(),z=make();check(eq(a,a)&&!ne(a,a),'held same');"
        "check(!eq(a,z)&&ne(a,z),'held distinct');check(count()===b+6,'no premature release');"
        "check(mixedLast(a)===false,'mixed ownership');check(count()===b+7,'mixed immediate release');"
        "collect();check(eq(a,a)&&eq(z,z),'roots after GC');"
        "a=z=undefined;check(count()===b+9,'held final releases');}"
        "check(count()===1152,'total');";
    JSValue result = JS_Eval(ctx, source, strlen(source), "strict-reference-public-host.js",
                             JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *text = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", text ? text : "exception");
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, error);
        abort();
    }
    JS_FreeValue(ctx, result);
    assert(finalized == 1152);
    JS_RunGC(rt);
    assert(finalized == 1152);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("REFERENCE_PUBLIC_HOST_OK finalized=%u\n", finalized);
    return 0;
}
