#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID token_class;
static unsigned born, finalized, collections, reentries, interrupts;
static void token_finalizer(JSRuntime *rt, JSValue val)
{
    (void)rt;
    void *p = JS_GetOpaque(val, token_class);
    assert(p);
    free(p);
    finalized++;
}
static JSValue make_token(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue result = JS_NewObjectClass(ctx, token_class);
    if (JS_IsException(result))
        return result;
    unsigned *p = malloc(sizeof(*p));
    assert(p);
    *p = ++born;
    JS_SetOpaque(result, p);
    return result;
}
static JSValue alive(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1);
    unsigned *p = JS_GetOpaque2(ctx, argv[0], token_class);
    if (!p)
        return JS_EXCEPTION;
    assert(*p > 0 && *p <= born);
    return JS_NewBool(ctx, 1);
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    collections++;
    const char *source = "21+21";
    JSValue v = JS_Eval(ctx, source, strlen(source), "<nested-host>", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v))
        return v;
    int32_t result;
    assert(JS_ToInt32(ctx, &result, v) == 0 && result == 42);
    JS_FreeValue(ctx, v);
    reentries++;
    return JS_UNDEFINED;
}
static int interrupt(JSContext *ctx, void *opaque)
{
    (void)opaque;
    JS_RunGC(JS_GetRuntime(ctx));
    interrupts++;
    return interrupts == 3;
}
static void set(JSContext *ctx, const char *name, JSCFunction *fn, int argc)
{
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, name, JS_NewCFunction(ctx, fn, name, argc)) >= 0);
    JS_FreeValue(ctx, global);
}
static void execute(JSContext *ctx, const char *source)
{
    JSValue v = JS_Eval(ctx, source, strlen(source), "<stack-insert-host>", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "HOST JS exception: %s\n", s ? s : "<unprintable>");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
        abort();
    }
    JS_FreeValue(ctx, v);
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    assert(JS_NewClassID(rt, &token_class) != 0);
    JSClassDef def = {0};
    def.class_name = "InsertToken";
    def.finalizer = token_finalizer;
    assert(JS_NewClass(rt, token_class, &def) == 0);
    set(ctx, "make", make_token, 0);
    set(ctx, "alive", alive, 1);
    set(ctx, "collect", collect, 0);
    execute(ctx, "function check(v){if(!v)throw Error('owner');}"
                 "function put(a,k,v){return a[k]=v;}"
                 "for(let i=0;i<64;i++){let a=[],v=make(),r=put(a,3,v);"
                 "v=null;a.length=0;collect();check(alive(r));r=null;collect();}"
                 "for(let i=0;i<64;i++){let a={set x(v){collect();check(alive(v));}};"
                 "let r=put(a,'x',make());collect();check(alive(r));r=null;collect();}"
                 "for(let i=0;i<32;i++){let v=make();v.self=v;let a=[];"
                 "let r=put(a,2,v);v=null;a=null;collect();check(alive(r));r=null;collect();}"
                 "collect();");
    JS_RunGC(rt);
    assert(born == 160 && finalized == born);
    JS_SetInterruptHandler(rt, interrupt, NULL);
    const char *loop =
        "for(let i=0;i<10000000;i++){let a=[];let r=put(a,2,i);if(r!==i)throw Error('bad');}";
    JSValue v = JS_Eval(ctx, loop, strlen(loop), "<interrupt>", JS_EVAL_TYPE_GLOBAL);
    assert(JS_IsException(v) && interrupts == 3);
    JS_FreeValue(ctx, JS_GetException(ctx));
    JS_SetInterruptHandler(rt, NULL, NULL);
    execute(ctx, "check(put([],3,19)===19);collect();");
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(finalized == born && collections == reentries);
    printf("STACK_INSERT_HOST_OK born=%u finalized=%u collections=%u reentries=%u interrupts=%u\n",
           born, finalized, collections, reentries, interrupts);
    return 0;
}
