#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static JSClassID owner_id;
static unsigned born, dead, probes, reentries;
static JSRuntime *runtime;
static void owner_finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    if (JS_GetOpaque(value, owner_id))
        dead++;
}
static JSValue make_owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    JSValue value = JS_NewObjectClass(ctx, owner_id);
    if (!JS_IsException(value)) {
        JS_SetOpaque(value, (void *)(uintptr_t)1);
        born++;
    }
    return value;
}
static JSValue call_global(JSContext *ctx, const char *name)
{
    JSValue global = JS_GetGlobalObject(ctx), fn = JS_GetPropertyStr(ctx, global, name);
    JS_FreeValue(ctx, global);
    if (JS_IsException(fn))
        return fn;
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 0, NULL);
    JS_FreeValue(ctx, fn);
    return result;
}
static JSValue probe(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    if (argc != 1 || !JS_GetOpaque(argv[0], owner_id))
        return JS_ThrowTypeError(ctx, "borrowed owner missing");
    probes++;
    JS_RunGC(runtime);
    JSValue result = call_global(ctx, "reenterConstruct");
    if (JS_IsException(result))
        return result;
    JSValue x = JS_GetPropertyStr(ctx, result, "x");
    int32_t n = 0;
    int failed = JS_ToInt32(ctx, &n, x);
    JS_FreeValue(ctx, x);
    JS_FreeValue(ctx, result);
    if (failed)
        return JS_EXCEPTION;
    if (n != 19 || !JS_GetOpaque(argv[0], owner_id))
        return JS_ThrowTypeError(ctx, "reentry damaged owner");
    reentries++;
    return JS_DupValue(ctx, argv[0]);
}
static JSValue fail_host(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_ThrowTypeError(ctx, "host-ctor-failure");
}
static JSValue arm_oom(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    JS_SetMemoryLimit(runtime, 1);
    return JS_UNDEFINED;
}
static void install(JSContext *ctx, const char *name, JSCFunction *function, int arity)
{
    JSValue global = JS_GetGlobalObject(ctx);
    if (JS_SetPropertyStr(ctx, global, name, JS_NewCFunction(ctx, function, name, arity)) < 0)
        abort();
    JS_FreeValue(ctx, global);
}
static void report_exception(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    const char *s = JS_ToCString(ctx, e);
    fprintf(stderr, "exception:%s\n", s ? s : "<oom>");
    JS_FreeCString(ctx, s);
    JS_FreeValue(ctx, e);
}
int main(void)
{
    runtime = JS_NewRuntime();
    if (!runtime)
        return 2;
    JSContext *ctx = JS_NewContext(runtime);
    if (!ctx)
        return 3;
    JS_NewClassID(runtime, &owner_id);
    JSClassDef cls = {0};
    cls.class_name = "ConstructHostOwner";
    cls.finalizer = owner_finalizer;
    if (JS_NewClass(runtime, owner_id, &cls) < 0)
        return 4;
    install(ctx, "makeOwner", make_owner, 0);
    install(ctx, "hostProbe", probe, 1);
    install(ctx, "failHost", fail_host, 0);
    install(ctx, "armOOM", arm_oom, 0);
    const char *script =
        "'use strict';class Inner{constructor(x){this.x=x;}}"
        "globalThis.reenterConstruct=function(){return new Inner(19)};"
        "class Box{constructor(owner){this.owner=owner;this.copy=hostProbe(owner);}}"
        "class Cycle{constructor(owner){this.owner=owner;this.self=this;hostProbe(owner);}}"
        "class Override{constructor(owner){this.owner=owner;hostProbe(owner);return {x:23};}}"
        "class Failing{constructor(owner){this.owner=owner;hostProbe(owner);failHost();}}"
        "class OOMBox{constructor(owner){this.owner=owner;armOOM();this.child=new Inner(1);}}"
        "globalThis.exercise=function(){for(let i=0;i<64;i++){"
        "let b=new Box(makeOwner());if(b.copy!==b.owner)throw Error('alias');"
        "new Cycle(makeOwner());if(new Override(makeOwner()).x!==23)throw Error('override');"
        "let caught=false;try{new Failing(makeOwner());}catch(e){caught=e.message==='host-ctor-failure'}"
        "if(!caught)throw Error('host throw');}};"
        "globalThis.triggerOOM=function(){new OOMBox(makeOwner());};";
    JSValue r = JS_Eval(ctx, script, strlen(script), "construct_host.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(r)) {
        report_exception(ctx);
        return 5;
    }
    JS_FreeValue(ctx, r);
    for (int round = 0; round < 3; round++) {
        r = call_global(ctx, "exercise");
        if (JS_IsException(r)) {
            report_exception(ctx);
            return 6;
        }
        JS_FreeValue(ctx, r);
        JS_RunGC(runtime);
        if (born != dead) {
            fprintf(stderr, "live owners:%u\n", born - dead);
            return 7;
        }
        r = call_global(ctx, "triggerOOM");
        JS_SetMemoryLimit(runtime, SIZE_MAX);
        if (!JS_IsException(r)) {
            JS_FreeValue(ctx, r);
            fprintf(stderr, "OOM did not throw\n");
            return 8;
        }
        JSValue e = JS_GetException(ctx);
        JS_FreeValue(ctx, e);
        JS_RunGC(runtime);
        if (born != dead) {
            fprintf(stderr, "OOM leaked owner:%u\n", born - dead);
            return 9;
        }
        r = call_global(ctx, "reenterConstruct");
        if (JS_IsException(r)) {
            report_exception(ctx);
            return 10;
        }
        JS_FreeValue(ctx, r);
    }
    JS_FreeContext(ctx);
    JS_FreeRuntime(runtime);
    if (born != dead || probes != 768 || reentries != 768)
        return 11;
    printf("CONSTRUCT_HOST_OK born=%u finalized=%u probes=%u reentries=%u oom=3\n", born, dead,
           probes, reentries);
    return 0;
}
