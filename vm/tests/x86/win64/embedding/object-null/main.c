/* Public API finalizers/HTMLDDA; native counters only assert route coverage. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef OBJECT_NULL_NATIVE_COUNTERS
extern uint64_t JS_FrameLooseEqStats[];
#endif
static JSClassID class_id;
static unsigned finalized;
static void finalize(JSRuntime *rt, JSValue value)
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
    return JS_NewObjectClass(ctx, class_id);
}
static JSValue count(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewUint32(ctx, finalized);
}
int main(int argc, char **argv)
{
    assert(argc == 2);
    const int expect_hits = atoi(argv[1]);
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JS_NewClassID(rt, &class_id);
    JSClassDef def = {0};
    def.class_name = "NullFinalizer";
    def.finalizer = finalize;
    assert(JS_NewClass(rt, class_id, &def) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "make", JS_NewCFunction(ctx, make, "make", 0)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "count", JS_NewCFunction(ctx, count, "count", 0)) >= 0);
    JSValue dda = JS_NewObject(ctx);
    assert(!JS_IsException(dda));
    JS_SetIsHTMLDDA(ctx, dda);
    assert(JS_SetPropertyStr(ctx, global, "dda", dda) >= 0);
    const char *source =
        "function eq(a,b){return a==b} function ne(a,b){return a!=b}"
        "const ordinary={};let conversion=0;"
        "const poison={[Symbol.toPrimitive](){conversion++;throw Error('conversion')}};"
        "for(let i=0;i<5000;i++){"
        "if(eq(ordinary,null)||eq(null,ordinary)||eq(ordinary,undefined)||eq(undefined,ordinary))throw Error('ordinary eq');"
        "if(!ne(ordinary,null)||!ne(null,ordinary)||!ne(ordinary,undefined)||!ne(undefined,ordinary))throw Error('ordinary ne');"
        "if(!eq(dda,null)||!eq(null,dda)||!eq(dda,undefined)||!eq(undefined,dda))throw Error('HTMLDDA eq');"
        "if(ne(dda,null)||ne(null,dda)||ne(dda,undefined)||ne(undefined,dda))throw Error('HTMLDDA ne');"
        "if(eq(poison,null)||!ne(undefined,poison)||conversion)throw Error('coercion');}"
        "for(let i=0;i<256;i++){let before=count();"
        "if(make()==null||count()!==before+1)throw Error('last-reference eq/finalizer');"
        "if(!(null!=make())||count()!==before+2)throw Error('last-reference ne/finalizer');}"
        "if(count()!==512)throw Error('count');";
    JSValue result =
        JS_Eval(ctx, source, strlen(source), "object-null-public-host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", s ? s : "exception");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, error);
        abort();
    }
    JS_FreeValue(ctx, result);
    /* MinGW has clean+dirty banks; MSVC only the clean bank. */
    uint64_t hits = 0;
#ifdef OBJECT_NULL_NATIVE_COUNTERS
    hits = JS_FrameLooseEqStats[7];
#ifdef OBJECT_NULL_MINGW
    hits += JS_FrameLooseEqStats[15];
#endif
    assert(expect_hits ? (hits > 0) : (hits == 0));
#else
    (void)expect_hits;
#endif
    assert(finalized == 512);
    JS_RunGC(rt);
    assert(finalized == 512);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("OBJECT_NULL_PUBLIC_HOST_OK finalized=%u object_hits=%llu\n", finalized,
           (unsigned long long)hits);
    return 0;
}
