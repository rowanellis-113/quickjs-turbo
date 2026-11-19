#include "quickjs.h"
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _MSC_VER
extern unsigned JS_FrameObjectProtoState(void);
extern unsigned JS_FrameObjectProtoHit(void);
#else
static unsigned JS_FrameObjectProtoState(void)
{
    return 0;
}
static unsigned JS_FrameObjectProtoHit(void)
{
    return 0;
}
#endif
typedef struct Block {
    size_t size;
    uint64_t magic;
} Block;
typedef struct Allocation {
    JSRuntime *rt;
    JSContext *ctx;
    JSClassID token_class;
    size_t live;
    unsigned gc, reentry, finalized, error;
} Allocation;
static void *allocate(void *opaque, size_t n)
{
    Allocation *a = opaque;
    Block *b = malloc(sizeof(*b) + n);
    if (!b)
        return NULL;
    b->size = n;
    b->magic = UINT64_C(0xdeaf4484);
    a->live++;
    return b + 1;
}
static void *allocate_zero(void *opaque, size_t n, size_t size)
{
    if (n && size > SIZE_MAX / n)
        return NULL;
    void *p = allocate(opaque, n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}
static void release(void *opaque, void *p)
{
    if (!p)
        return;
    Allocation *a = opaque;
    Block *b = (Block *)p - 1;
    if (b->magic != UINT64_C(0xdeaf4484) || !a->live)
        abort();
    a->live--;
    free(b);
}
static void *resize(void *opaque, void *p, size_t n)
{
    if (!p)
        return allocate(opaque, n);
    if (!n) {
        release(opaque, p);
        return NULL;
    }
    Block *b = realloc((Block *)p - 1, sizeof(*b) + n);
    if (!b)
        return NULL;
    b->size = n;
    return b + 1;
}
static size_t usable(const void *p)
{
    return p ? ((const Block *)p - 1)->size : 0;
}
static void finalizer(JSRuntime *rt, JSValue value)
{
    (void)value;
    ((Allocation *)JS_GetRuntimeOpaque(rt))->finalized++;
}
static int result_int(JSContext *ctx, JSValue v, int expected)
{
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *t = JS_ToCString(ctx, e);
        fprintf(stderr, "OBJECT_PROTO_EXCEPTION %s\n", t ? t : "?");
        JS_FreeCString(ctx, t);
        JS_FreeValue(ctx, e);
        return 1;
    }
    int32_t n = 0;
    int rc = JS_ToInt32(ctx, &n, v);
    JS_FreeValue(ctx, v);
    return rc || n != expected;
}
static int evaluate(JSContext *ctx, const char *code, int expected)
{
    return result_int(ctx, JS_Eval(ctx, code, strlen(code), "object-proto-native.js", 0), expected);
}
static JSValue global_property(JSContext *ctx, const char *name)
{
    JSValue g = JS_GetGlobalObject(ctx);
    JSValue v = JS_GetPropertyStr(ctx, g, name);
    JS_FreeValue(ctx, g);
    return v;
}
static JSValue native_probe(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv,
                            int magic, JSValue *data)
{
    (void)argc;
    (void)argv;
    (void)magic;
    Allocation *a = JS_GetContextOpaque(ctx);
    if (!JS_IsObject(receiver)) {
        a->error = 1;
        return JS_ThrowTypeError(ctx, "lost object receiver");
    }
    JSValue p = global_property(ctx, "objectProbeProto");
    JSAtom atom = JS_NewAtom(ctx, "run");
    int deleted = JS_DeleteProperty(ctx, p, atom, 0);
    JS_FreeAtom(ctx, atom);
    JS_FreeValue(ctx, p);
    if (deleted != 1) {
        a->error = 1;
        return JS_ThrowInternalError(ctx, "delete live method");
    }
    /* No prototype edge retains the callee/token cycle now. The acquired
       method and original native-call frame must keep both alive. */
    JS_RunGC(a->rt);
    a->gc++;
    JSValue x = JS_GetPropertyStr(ctx, data[0], "x");
    int32_t n = 0;
    if (JS_ToInt32(ctx, &n, x) || n != 91)
        a->error = 1;
    JS_FreeValue(ctx, x);
    if (evaluate(ctx,
                 "(()=>{let sum=0;for(let i=0;i<2;i++)sum+=reentryReceiver.go(90);return sum;})()",
                 182))
        a->error = 1;
    a->reentry++;
    return JS_DupValue(ctx, data[0]);
}
static JSValue install(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv)
{
    (void)receiver;
    (void)argc;
    (void)argv;
    Allocation *a = JS_GetContextOpaque(ctx);
    JSValue token = JS_NewObjectClass(ctx, a->token_class);
    if (JS_IsException(token))
        return token;
    if (JS_SetPropertyStr(ctx, token, "x", JS_NewInt32(ctx, 91)) < 0) {
        JS_FreeValue(ctx, token);
        return JS_EXCEPTION;
    }
    JSValue fn = JS_NewCFunctionData(ctx, native_probe, 0, 0, 1, &token);
    if (JS_IsException(fn)) {
        JS_FreeValue(ctx, token);
        return fn;
    }
    if (JS_SetPropertyStr(ctx, token, "fn", JS_DupValue(ctx, fn)) < 0) {
        JS_FreeValue(ctx, token);
        JS_FreeValue(ctx, fn);
        return JS_EXCEPTION;
    }
    JSValue p = global_property(ctx, "objectProbeProto");
    int rc = JS_SetPropertyStr(ctx, p, "run", fn);
    JS_FreeValue(ctx, p);
    JS_FreeValue(ctx, token);
    return rc < 0 ? JS_EXCEPTION : JS_UNDEFINED;
}
static DWORD WINAPI worker(void *opaque)
{
    unsigned *result = opaque;
    JSRuntime *rt = JS_NewRuntime();
    if (!rt) {
        *result = 1;
        return 0;
    }
    JSContext *ctx = JS_NewContext(rt);
    if (!ctx) {
        JS_FreeRuntime(rt);
        *result = 1;
        return 0;
    }
    *result = evaluate(
        ctx,
        "globalThis.threadReceiver=Object.create({go(x){return this.v+x;}});threadReceiver.v=3;(()=>{let n=0;for(let i=0;i<2000;i++)n+=threadReceiver.go(i);return n;})()",
        2005000);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return 0;
}
int main(void)
{
    HANDLE threads[4];
    unsigned errors[4] = {0};
    for (unsigned i = 0; i < 4; i++) {
        threads[i] = CreateThread(NULL, 0, worker, &errors[i], 0, NULL);
        if (!threads[i])
            return 2;
    }
    if (WaitForMultipleObjects(4, threads, TRUE, 60000) != WAIT_OBJECT_0)
        return 3;
    for (unsigned i = 0; i < 4; i++) {
        CloseHandle(threads[i]);
        if (errors[i])
            return 4;
    }
    unsigned warm = JS_FrameObjectProtoHit();
    Allocation a = {0};
    JSMallocFunctions mf = {allocate_zero, allocate, release, resize, usable};
    a.rt = JS_NewRuntime2(&mf, &a);
    if (!a.rt)
        return 5;
    JS_SetRuntimeOpaque(a.rt, &a);
    a.ctx = JS_NewContext(a.rt);
    if (!a.ctx)
        return 6;
    JS_SetContextOpaque(a.ctx, &a);
    JS_NewClassID(a.rt, &a.token_class);
    JSClassDef def = {0};
    def.class_name = "ObjectProtoToken";
    def.finalizer = finalizer;
    if (JS_NewClass(a.rt, a.token_class, &def))
        return 7;
    JSValue global = JS_GetGlobalObject(a.ctx);
    if (JS_SetPropertyStr(a.ctx, global, "installObjectProbe",
                          JS_NewCFunction(a.ctx, install, "installObjectProbe", 0)) < 0)
        return 8;
    JS_FreeValue(a.ctx, global);
    const char *stress =
        "globalThis.reentryReceiver=Object.create({go(x){return x+1;}});globalThis.objectProbeProto={};globalThis.objectProbe=Object.create(objectProbeProto);(()=>{let sum=0;for(let i=0;i<200;i++){installObjectProbe();let v=objectProbe.run();if(v.x!==91)throw Error('lost inherited method root');sum+=v.x;}return sum;})()";
    if (evaluate(a.ctx, stress, 18200) || a.error || a.gc != 200 || a.reentry != 200)
        return 9;
    unsigned hit = JS_FrameObjectProtoHit();
    int enabled = PROTO_HAS_LANE && !getenv("QJS_DISABLE_OBJECT_PROTO_DATA") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP");
    if (warm != (unsigned)(enabled && PROTO_DIAGNOSTIC) || hit != warm) {
        fprintf(stderr, "OBJECT_HIT warm=%u hit=%u mode=%u enabled=%d\n", warm, hit,
                JS_FrameObjectProtoState(), enabled);
        return 10;
    }
    JS_RunGC(a.rt);
    a.gc++;
    if (a.finalized != 200)
        return 11;
    JSContext *other = JS_NewContext(a.rt);
    if (!other)
        return 12;
    if (evaluate(a.ctx, "Object.prototype.__realmLane=function(){return 101;};0", 0) ||
        evaluate(other, "Object.prototype.__realmLane=function(){return 202;};0", 0))
        return 13;
    const char *code = "(function(){return ({}).__realmLane();})";
    JSValue fa = JS_Eval(a.ctx, code, strlen(code), "realm-a.js", 0),
            fb = JS_Eval(other, code, strlen(code), "realm-b.js", 0);
    if (JS_IsException(fa) || JS_IsException(fb))
        return 14;
    if (result_int(other, JS_Call(other, fa, JS_UNDEFINED, 0, NULL), 101) ||
        result_int(a.ctx, JS_Call(a.ctx, fb, JS_UNDEFINED, 0, NULL), 202))
        return 15;
    if (evaluate(
            a.ctx,
            "(()=>{let p={go(){return 303;}},o=Object.create(p);let f=()=>o.go();if(f()!==303)return 0;Object.setPrototypeOf(o,new Proxy({},{get(t,k,r){if(k==='go')return()=>404;return Reflect.get(t,k,r);}}));if(f()!==404)return 0;Object.setPrototypeOf(o,null);try{f();}catch(e){return e instanceof TypeError?1:0;}return 0;})()",
            1))
        return 16;
    JS_FreeValue(a.ctx, fa);
    JS_FreeValue(other, fb);
    JS_FreeContext(other);
    unsigned state = JS_FrameObjectProtoState();
    JS_FreeContext(a.ctx);
    JS_FreeRuntime(a.rt);
    if (a.live || a.error)
        return 17;
    printf(
        "OBJECT_PROTO_NATIVE_PASS diagnostic=%d lane=%d state=%u warm_hit=%u hit=%u threads=4 reentry=%u gc=%u finalized=%u live=%zu\n",
        PROTO_DIAGNOSTIC, PROTO_HAS_LANE, state, warm, hit, a.reentry, a.gc, a.finalized, a.live);
    return 0;
}
