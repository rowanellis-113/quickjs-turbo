#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static JSClassID token_class;
static JSContext *active_context;
static JSValue reader;
static unsigned born, finalized, reentries;

static void finish(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    finalized++;
    if (!JS_IsUndefined(reader)) {
        JSValue result = JS_Call(active_context, reader, JS_UNDEFINED, 0, NULL);
        int32_t number;
        assert(!JS_IsException(result));
        assert(JS_ToInt32(active_context, &number, result) == 0 && number == 43);
        JS_FreeValue(active_context, result);
        reentries++;
    }
}
static JSValue make(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue value = JS_NewObjectClass(ctx, token_class);
    if (!JS_IsException(value))
        born++;
    return value;
}
static JSValue watch(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    assert(argc == 1 && JS_IsFunction(ctx, argv[0]));
    JSValue next = JS_DupValue(ctx, argv[0]);
    JS_FreeValue(ctx, reader);
    reader = next;
    return JS_UNDEFINED;
}
static JSValue collect(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue value =
        JS_Eval(ctx, source, strlen(source), "reference-slot-public-host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "exception");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        assert(0);
    }
    return value;
}
int main(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    active_context = ctx;
    reader = JS_UNDEFINED;
    JS_NewClassID(rt, &token_class);
    JSClassDef def = {0};
    def.class_name = "ReferenceSlotToken";
    def.finalizer = finish;
    assert(JS_NewClass(rt, token_class, &def) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "make", JS_NewCFunction(ctx, make, "make", 0)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "watch", JS_NewCFunction(ctx, watch, "watch", 1)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "collect", JS_NewCFunction(ctx, collect, "collect", 0)) >=
           0);
    JS_FreeValue(ctx, global);
    const char *sources[] = {
        "(function localPut(){let v=make();v=43;collect();return v;})",
        "(function localSet(){let v=make();let r=(v=43);collect();return r;})",
        "(function capturedPut(){let v=make();watch(function read(){return v;});v=43;collect();return v;})",
        "(function capturedSet(){let v=make();watch(function read(){return v;});let r=(v=43);collect();return r;})"};
    for (unsigned k = 0; k < sizeof(sources) / sizeof(sources[0]); k++) {
        JSValue fn = evaluate(ctx, sources[k]);
        for (unsigned i = 0; i < 64; i++) {
            JSValue value = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
            int32_t number;
            assert(!JS_IsException(value));
            assert(JS_ToInt32(ctx, &number, value) == 0 && number == 43);
            JS_FreeValue(ctx, value);
            assert(born == finalized);
        }
        JS_FreeValue(ctx, fn);
        JS_FreeValue(ctx, reader);
        reader = JS_UNDEFINED;
    }
    assert(born == 256 && finalized == 256 && reentries == 128);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("REFERENCE_SLOT_HOST_OK born=%u finalized=%u reentries=%u\n", born, finalized,
           reentries);
    return 0;
}
