#include "quickjs.h"
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _MSC_VER
extern unsigned JS_FrameStringProtoState(void);
extern uint64_t JS_FrameStringProtoCount(void);
#else
static unsigned JS_FrameStringProtoState(void)
{
    return 0;
}
static uint64_t JS_FrameStringProtoCount(void)
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
    b->magic = UINT64_C(0xdeaf4462);
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
    if (b->magic != UINT64_C(0xdeaf4462) || !a->live)
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
static void token_finalizer(JSRuntime *rt, JSValue v)
{
    (void)v;
    Allocation *a = JS_GetRuntimeOpaque(rt);
    a->finalized++;
}
static int error(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    const char *s = JS_ToCString(ctx, e);
    fprintf(stderr, "STRING_PROTO_EXCEPTION %s\n", s ? s : "?");
    JS_FreeCString(ctx, s);
    JS_FreeValue(ctx, e);
    return 1;
}
static int evaluate(JSContext *ctx, const char *code, int expected)
{
    JSValue v = JS_Eval(ctx, code, strlen(code), "string-proto-native.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v))
        return error(ctx);
    int32_t n = 0;
    int rc = JS_ToInt32(ctx, &n, v);
    JS_FreeValue(ctx, v);
    return rc || n != expected;
}
static int result_int(JSContext *ctx, JSValue v, int expected)
{
    if (JS_IsException(v))
        return error(ctx);
    int32_t n = 0;
    int rc = JS_ToInt32(ctx, &n, v);
    JS_FreeValue(ctx, v);
    return rc || n != expected;
}
static JSValue native_probe(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv,
                            int magic, JSValue *data)
{
    (void)argc;
    (void)argv;
    (void)magic;
    Allocation *a = JS_GetContextOpaque(ctx);
    if (!JS_IsString(receiver)) {
        a->error = 1;
        return JS_ThrowTypeError(ctx, "lost primitive receiver");
    }
    JSValue proto = JS_GetClassProto(ctx, 5);
    JSAtom atom = JS_NewAtom(ctx, "__native_string_probe");
    int deleted = JS_DeleteProperty(ctx, proto, atom, 0);
    JS_FreeAtom(ctx, atom);
    JS_FreeValue(ctx, proto);
    if (deleted != 1) {
        a->error = 1;
        return JS_ThrowInternalError(ctx, "delete live method");
    }
    // The callee and its token now form an otherwise unreachable cycle. The
    // current method value/native C frame must keep both live across GC/JS.
    JS_RunGC(a->rt);
    a->gc++;
    JSValue x = JS_GetPropertyStr(ctx, data[0], "x");
    int32_t n = 0;
    if (JS_ToInt32(ctx, &n, x) || n != 91)
        a->error = 1;
    JS_FreeValue(ctx, x);
    const char *code = "(()=>{let x='abcd'.slice(1);return x==='bcd' && 9n*9n+10n===91n;})()";
    JSValue r = JS_Eval(ctx, code, strlen(code), "string-proto-reentry.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(r) || JS_ToBool(ctx, r) != 1)
        a->error = 1;
    JS_FreeValue(ctx, r);
    a->reentry++;
    return JS_DupValue(ctx, data[0]);
}
static JSValue install_probe(JSContext *ctx, JSValueConst receiver, int argc, JSValueConst *argv)
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
    JSValue proto = JS_GetClassProto(ctx, 5);
    int rc = JS_SetPropertyStr(ctx, proto, "__native_string_probe", fn);
    JS_FreeValue(ctx, proto);
    JS_FreeValue(ctx, token);
    return rc < 0 ? JS_EXCEPTION : JS_UNDEFINED;
}
static DWORD WINAPI cold_worker(void *opaque)
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
    const char *code =
        "String.prototype.__thread_string_probe=function(x){'use strict';return this.length+x;};(()=>{let n=0;for(let i=0;i<2000;i++)n+='abc'.__thread_string_probe(i);return n;})()";
    *result = evaluate(ctx, code, 2005000);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    return 0;
}
int main(void)
{
    // Four independent runtimes race the first process-wide control init.
    HANDLE threads[4];
    unsigned workers[4] = {0};
    for (unsigned i = 0; i < 4; i++) {
        threads[i] = CreateThread(NULL, 0, cold_worker, &workers[i], 0, NULL);
        if (!threads[i])
            return 2;
    }
    if (WaitForMultipleObjects(4, threads, TRUE, 60000) != WAIT_OBJECT_0)
        return 3;
    for (unsigned i = 0; i < 4; i++) {
        CloseHandle(threads[i]);
        if (workers[i])
            return 4;
    }
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
    def.class_name = "StringProtoToken";
    def.finalizer = token_finalizer;
    if (JS_NewClass(a.rt, a.token_class, &def))
        return 7;
    JSValue global = JS_GetGlobalObject(a.ctx);
    if (JS_SetPropertyStr(a.ctx, global, "installNativeStringProbe",
                          JS_NewCFunction(a.ctx, install_probe, "installNativeStringProbe", 0)) < 0)
        return 8;
    JS_FreeValue(a.ctx, global);
    uint64_t warm = JS_FrameStringProtoCount();
    const char *stress =
        "(()=>{let total=0;for(let i=0;i<200;i++){installNativeStringProbe();let v='abc'.__native_string_probe();if(v.x!==91)throw Error('lost method token root');total+=v.x;}return total;})()";
    if (evaluate(a.ctx, stress, 18200) || a.error || a.gc != 200 || a.reentry != 200)
        return 9;
    uint64_t hits = JS_FrameStringProtoCount();
    int enabled = PROTO_HAS_LANE && !getenv("QJS_DISABLE_STRING_PROTO_DATA") &&
                  !getenv("QJS_DISABLE_REGISTER_INTERP");
    if ((PROTO_DIAGNOSTIC && enabled) ? (warm < 8000 || hits < warm + 200) : hits != 0) {
        fprintf(stderr, "PROTO_HITS warm=%llu hits=%llu enabled=%d\n", (unsigned long long)warm,
                (unsigned long long)hits, enabled);
        return 10;
    }
    JS_RunGC(a.rt);
    a.gc++;
    if (a.finalized != 200) {
        fprintf(stderr, "PROTO_FINALIZED %u\n", a.finalized);
        return 11;
    }
    // Functions invoked through another C context still use their own realm.
    JSContext *other = JS_NewContext(a.rt);
    if (!other)
        return 12;
    if (evaluate(a.ctx, "String.prototype.__realmLane=function(){return 101;};0", 0) ||
        evaluate(other, "String.prototype.__realmLane=function(){return 202;};0", 0))
        return 13;
    const char *function = "(function(){return 'abc'.__realmLane();})";
    JSValue fa = JS_Eval(a.ctx, function, strlen(function), "realm-a.js", 0),
            fb = JS_Eval(other, function, strlen(function), "realm-b.js", 0);
    if (JS_IsException(fa) || JS_IsException(fb))
        return 14;
    if (result_int(other, JS_Call(other, fa, JS_UNDEFINED, 0, NULL), 101) ||
        result_int(a.ctx, JS_Call(a.ctx, fb, JS_UNDEFINED, 0, NULL), 202))
        return 15;
    JSValue saved = JS_GetClassProto(a.ctx, 5), alternate = JS_NewObject(a.ctx);
    const char *fn = "(function(){return 303;})";
    JSValue value = JS_Eval(a.ctx, fn, strlen(fn), "alternate.js", 0);
    if (JS_SetPropertyStr(a.ctx, alternate, "__realmLane", value) < 0)
        return 16;
    JS_SetClassProto(a.ctx, 5, alternate);
    if (result_int(a.ctx, JS_Call(a.ctx, fa, JS_UNDEFINED, 0, NULL), 303))
        return 17;
    const char *proxy =
        "new Proxy({},{get(o,k,r){if(k==='__realmLane')return function(){return 404;};return Reflect.get(o,k,r);}})";
    alternate = JS_Eval(a.ctx, proxy, strlen(proxy), "proxy-prototype.js", 0);
    if (JS_IsException(alternate))
        return 18;
    uint64_t before = JS_FrameStringProtoCount();
    JS_SetClassProto(a.ctx, 5, alternate);
    if (result_int(a.ctx, JS_Call(a.ctx, fa, JS_UNDEFINED, 0, NULL), 404) ||
        JS_FrameStringProtoCount() != before)
        return 19;
    JS_SetClassProto(a.ctx, 5, JS_NULL);
    if (evaluate(
            a.ctx,
            "(()=>{try{'a'.__realmLane();}catch(e){return e instanceof TypeError?1:0;}return 0;})()",
            1))
        return 20;
    JS_SetClassProto(a.ctx, 5, saved);
    if (result_int(a.ctx, JS_Call(a.ctx, fa, JS_UNDEFINED, 0, NULL), 101))
        return 21;
    JS_FreeValue(a.ctx, fa);
    JS_FreeValue(other, fb);
    JS_FreeContext(other);
    unsigned state = JS_FrameStringProtoState();
    JS_FreeContext(a.ctx);
    a.ctx = NULL;
    JS_FreeRuntime(a.rt);
    if (a.live || a.error)
        return 22;
    printf(
        "STRING_PROTO_NATIVE_PASS diagnostic=%d lane=%d state=%u warm_hits=%llu hits=%llu threads=4 reentry=%u gc=%u finalized=%u live=%zu\n",
        PROTO_DIAGNOSTIC, PROTO_HAS_LANE, state, (unsigned long long)warm, (unsigned long long)hits,
        a.reentry, a.gc, a.finalized, a.live);
    return 0;
}
