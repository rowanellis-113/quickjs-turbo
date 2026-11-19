/* Public host/JS ownership checks. Finalizers only count; they do not run JS. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static JSClassID resource_class;
static unsigned released;
static void finalize(JSRuntime *rt, JSValue value)
{
    (void)rt;
    (void)value;
    released++;
}
static JSValue count(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewInt32(ctx, released);
}
static JSValue resource(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    return JS_NewObjectProtoClass(ctx, JS_NULL, resource_class);
}
static JSValue self_resource(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    JSValue value = resource(ctx, self, argc, argv);
    if (JS_IsException(value))
        return value;
    if (JS_SetPropertyStr(ctx, value, "value", JS_DupValue(ctx, value)) < 0) {
        JS_FreeValue(ctx, value);
        return JS_EXCEPTION;
    }
    return value;
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
    JSClassDef definition = {"PropertyStoreResource", finalize, NULL, NULL, NULL};
    JS_NewClassID(rt, &resource_class);
    assert(JS_NewClass(rt, resource_class, &definition) == 0);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "resource",
                             JS_NewCFunction(ctx, resource, "resource", 0)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "selfResource",
                             JS_NewCFunction(ctx, self_resource, "selfResource", 0)) >= 0);
    assert(JS_SetPropertyStr(ctx, global, "released", JS_NewCFunction(ctx, count, "released", 0)) >=
           0);
    JS_FreeValue(ctx, global);
    const char *code =
        "function check(v,m){if(!v)throw Error(m)}"
        "function put(o,v){o.value=v}"
        /* Native clean/dirty frames warm up at the same real assignment site. */
        "var a={value:{}},b={};for(var i=0;i<1000;i++)put(a,b);"
        "a=null;b=null;"
        /* One old reference: finalizer runs before the next JS observation. */
        "var n=released(),o={value:resource()};put(o,0);check(released()===n+1,'last old');o=null;"
        /* Two combined releases of a self-receiver: must fall back before mutation. */
        "function clearSelf(){selfResource().value=0;return released()}"
        "n=released();for(var i=1;i<=64;i++)check(clearSelf()===n+i,'combined self finalizer');"
        /* Safe self-alias has a third reference and must not be freed early. */
        "n=released();o=selfResource();put(o,17);check(released()===n,'live self');o=null;"
        "check(released()===n+1,'release safe self');"
        /* Old and new value equal: transfer a reference, no leak or premature free. */
        "n=released();var old=resource();o={value:old};for(var i=0;i<1000;i++)put(o,old);"
        "check(released()===n,'same old/new');put(o,0);check(released()===n,'shared old');"
        "old=null;check(released()===n+1,'shared final release');o=null;"
        /* New value aliases receiver; old referenced value stays rooted outside. */
        "n=released();old=resource();o={value:old};put(o,o);check(o.value===o,'new receiver');"
        "check(released()===n,'old still owned');old=null;check(released()===n+1,'old final');"
        "put(o,0);o=null;"
        /* Referenced strings/symbols/BigInts and a mutable shape at the same site. */
        "var values=['long '+Array(50).join('abc'),Symbol('old'),1234567890123456789012345n,{},()=>42];"
        "o={value:values[0]};for(var i=0;i<3000;i++){put(o,values[i%5]);check(o.value===values[i%5],'tags')}"
        "delete o.value;put(o,values[1]);Object.defineProperty(o,'value',{writable:false});"
        "put(o,0);check(o.value===values[1],'sloppy readonly');"
        "function strictPut(o,v){'use strict';o.value=v}"
        "var threw=false;try{strictPut(o,0)}catch(e){threw=e instanceof TypeError}check(threw,'strict readonly');"
        /* Setter/proxy reentry includes GC with live frame roots. */
        "var seen=0,live={answer:42},p={set value(v){gc();seen=v.answer}};"
        "put(p,live);check(seen===42&&live.answer===42,'setter roots');"
        "var proxy=new Proxy({value:0},{set(t,k,v,r){gc();seen=v.answer;return Reflect.set(t,k,v,r)}});"
        "put(proxy,live);check(seen===42&&proxy.value===live,'proxy roots');"
        "globalThis.storeResult=1;";
    /* A legal C host callback to force GC from ordinary JS, not a finalizer. */
    global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "gc", JS_NewCFunction(ctx, collect, "gc", 0)) >= 0);
    JS_FreeValue(ctx, global);
    JSValue result = JS_Eval(ctx, code, strlen(code), "property-store-host", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(result)) {
        JSValue error = JS_GetException(ctx);
        const char *message = JS_ToCString(ctx, error);
        fprintf(stderr, "%s\n", message ? message : "exception");
        JS_FreeCString(ctx, message);
        JS_FreeValue(ctx, error);
        return 1;
    }
    JS_FreeValue(ctx, result);
    JS_RunGC(rt);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    printf("PROPERTY STORE PASS immediate-finalizers=%u\n", released);
    return 0;
}
