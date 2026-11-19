#include "quickjs.h"
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef union Allocation Allocation;
union Allocation {
    long double align;
    unsigned char padding[32];
    struct {
        size_t size;
        Allocation *next;
    } h;
};
typedef struct Host {
    JSRuntime *rt;
    JSContext *ctx;
    JSClassID owner, function_class;
    JSValue replacement, maker;
    size_t live, moves;
    Allocation *retired;
    unsigned born, freed, gc, reentries, failed;
    int blocked, busy, armed, allocation;
} Host;
static void require(int ok, const char *why)
{
    if (!ok) {
        fprintf(stderr, "CLOSURE_HOST_FAIL %s\n", why);
        exit(40);
    }
}
static void on_allocation(Host *s);
static void *moving_malloc(void *opaque, size_t n)
{
    Host *s = opaque;
    if (s->blocked) {
        s->failed++;
        return NULL;
    }
    if (n > SIZE_MAX - sizeof(Allocation))
        return NULL;
    Allocation *p = malloc(sizeof(*p) + (n ? n : 1));
    if (!p)
        return NULL;
    p->h.size = n ? n : 1;
    p->h.next = NULL;
    s->live++;
    on_allocation(s);
    return p + 1;
}
static void moving_free(void *opaque, void *ptr)
{
    if (!ptr)
        return;
    Host *s = opaque;
    require(s->live > 0, "allocation balance");
    s->live--;
    free((Allocation *)ptr - 1);
}
static void *moving_calloc(void *opaque, size_t count, size_t n)
{
    if (count && n > SIZE_MAX / count)
        return NULL;
    void *p = moving_malloc(opaque, count * n);
    if (p)
        memset(p, 0, count * n);
    return p;
}
static size_t moving_size(const void *ptr)
{
    return ptr ? ((const Allocation *)ptr - 1)->h.size : 0;
}
static void *moving_realloc(void *opaque, void *ptr, size_t n)
{
    Host *s = opaque;
    if (!ptr)
        return moving_malloc(opaque, n);
    if (!n) {
        moving_free(opaque, ptr);
        return NULL;
    }
    Allocation *old = (Allocation *)ptr - 1;
    size_t before = old->h.size;
    void *p = moving_malloc(opaque, n);
    if (!p)
        return NULL;
    memcpy(p, ptr, n < before ? n : before);
    memset(ptr, 0, before);
    old->h.next = s->retired;
    s->retired = old;
    s->live--;
    s->moves++;
    return p;
}
static void finalizer(JSRuntime *rt, JSValue value)
{
    Host *s = JS_GetRuntimeOpaque(rt);
    if (JS_GetOpaque(value, s->owner))
        s->freed++;
}
static JSValue owner(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    Host *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    JSValue v = JS_NewObjectClass(ctx, s->owner);
    if (!JS_IsException(v))
        JS_SetOpaque(v, (void *)(uintptr_t)++s->born);
    return v;
}
static JSValue gc(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    Host *s = JS_GetRuntimeOpaque(JS_GetRuntime(ctx));
    s->gc++;
    JS_RunGC(s->rt);
    return JS_UNDEFINED;
}
static JSValue eval(JSContext *ctx, const char *text)
{
    JSValue v = JS_Eval(ctx, text, strlen(text), "closure_public.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *t = JS_ToCString(ctx, e);
        fprintf(stderr, "exception:%s\n", t ? t : "<oom>");
        JS_FreeCString(ctx, t);
        JS_FreeValue(ctx, e);
        require(0, "eval");
    }
    return v;
}
static int number(JSContext *ctx, JSValue value)
{
    int32_t n = 0;
    require(!JS_IsException(value) && JS_ToInt32(ctx, &n, value) == 0, "integer result");
    JS_FreeValue(ctx, value);
    return n;
}
static JSValue make_inner(JSContext *ctx, JSValue maker, int value)
{
    JSValue arg = JS_NewInt32(ctx, value), result = JS_Call(ctx, maker, JS_UNDEFINED, 1, &arg);
    require(!JS_IsException(result), "closure creation");
    return result;
}
static void check_inner(JSContext *ctx, JSValue f, int value)
{
    JSValue arg = JS_NewInt32(ctx, 1);
    require(number(ctx, JS_Call(ctx, f, JS_UNDEFINED, 1, &arg)) == value + 1,
            "capture survives reentry and GC");
    require(number(ctx, JS_GetPropertyStr(ctx, f, "length")) == 1, "function length");
    JSValue name = JS_GetPropertyStr(ctx, f, "name");
    const char *n = JS_ToCString(ctx, name);
    require(n && strcmp(n, "inner") == 0, "function name");
    JS_FreeCString(ctx, n);
    JS_FreeValue(ctx, name);
}
static void on_allocation(Host *s)
{
    if (!s->armed || s->busy || !s->ctx || !s->rt)
        return;
    if (++s->allocation != s->armed)
        return;
    s->armed = 0;
    s->busy = 1;
    JS_SetClassProto(s->ctx, s->function_class, JS_DupValue(s->ctx, s->replacement));
    JSValue nested = make_inner(s->ctx, s->maker, 41);
    check_inner(s->ctx, nested, 41);
    JSValue proto = JS_GetPrototype(s->ctx, nested);
    require(JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(s->replacement),
            "reentrant closure sees new class prototype");
    JS_FreeValue(s->ctx, proto);
    JS_FreeValue(s->ctx, nested);
    s->gc++;
    JS_RunGC(s->rt);
    s->reentries++;
    s->busy = 0;
}
static void exercise(int moving)
{
    Host s = {0};
    s.replacement = s.maker = JS_UNDEFINED;
    JSMallocFunctions functions = {moving_calloc, moving_malloc, moving_free, moving_realloc,
                                   moving_size};
    JSRuntime *rt = moving ? JS_NewRuntime2(&functions, &s) : JS_NewRuntime();
    require(rt != NULL, "runtime");
    s.rt = rt;
    JS_SetRuntimeOpaque(rt, &s);
    JS_NewClassID(rt, &s.owner);
    JSClassDef def = {"ClosureOwner", .finalizer = finalizer};
    require(JS_NewClass(rt, s.owner, &def) == 0, "owner class");
    JSContext *a = JS_NewContext(rt), *b = JS_NewContext(rt);
    require(a && b, "two realms");
    JSContext *contexts[2] = {a, b};
    for (int i = 0; i < 2; i++) {
        JSValue global = JS_GetGlobalObject(contexts[i]);
        require(JS_SetPropertyStr(contexts[i], global, "makeOwner",
                                  JS_NewCFunction(contexts[i], owner, "makeOwner", 0)) == 1,
                "owner export");
        require(JS_SetPropertyStr(contexts[i], global, "hostGC",
                                  JS_NewCFunction(contexts[i], gc, "hostGC", 0)) == 1,
                "GC export");
        JS_FreeValue(contexts[i], global);
        JS_FreeValue(
            contexts[i],
            eval(
                contexts[i],
                "(()=>{let list=[];for(let n=0;n<24;n++){let value=makeOwner();let f=function retained(a){return value;};f.prototype.back=f;list.push(f);hostGC();if(f(0)!==value)throw Error('owner');}list=null;hostGC();})()"));
    }
    s.maker = eval(a, "(function maker(value){return function inner(a){return value+a;};})");
    JSValue warm = make_inner(a, s.maker, 20);
    s.function_class = JS_GetClassID(warm);
    check_inner(a, warm, 20);
    JSValue original = JS_GetClassProto(a, s.function_class);
    JS_FreeValue(a, warm);
    JSValue foreign = make_inner(b, s.maker, 22), proto = JS_GetPrototype(b, foreign);
    require(JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(original),
            "foreign caller retains function realm");
    check_inner(b, foreign, 22);
    JS_FreeValue(b, proto);
    JS_FreeValue(b, foreign);
    s.replacement = owner(a, JS_UNDEFINED, 0, NULL);
    require(!JS_IsException(s.replacement), "replacement owner");
    JS_SetClassProto(a, s.function_class, JS_DupValue(a, s.replacement));
    JSValue replaced = make_inner(a, s.maker, 24);
    proto = JS_GetPrototype(a, replaced);
    require(JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(s.replacement),
            "class prototype replacement invalidates template");
    JS_FreeValue(a, proto);
    check_inner(a, replaced, 24);
    JS_FreeValue(a, replaced);
    JS_SetClassProto(a, s.function_class, JS_DupValue(a, original));
    if (moving) {
        s.ctx = a;
        for (int n = 1; n <= 16; n++) {
            JS_SetClassProto(a, s.function_class, JS_DupValue(a, original));
            for (int k = 0; k < 3; k++) {
                JSValue v = make_inner(a, s.maker, k);
                JS_FreeValue(a, v);
            }
            s.allocation = 0;
            s.armed = n;
            JSValue f = make_inner(a, s.maker, 100 + n);
            s.armed = 0;
            check_inner(a, f, 100 + n);
            proto = JS_GetPrototype(a, f);
            require(JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(original) ||
                        JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(s.replacement),
                    "inflight object holds a valid old or new prototype");
            JS_FreeValue(a, proto);
            JS_FreeValue(a, f);
        }
        require(s.reentries > 0, "actual allocator reentry");
        JS_SetClassProto(a, s.function_class, JS_DupValue(a, original));
        s.blocked = 1;
        JSValue value = JS_Call(a, s.maker, JS_UNDEFINED, 0, NULL);
        s.blocked = 0;
        require(JS_IsException(value), "real allocation failure");
        JS_FreeValue(a, JS_GetException(a));
        s.ctx = NULL;
    }
    JS_FreeValue(a, s.replacement);
    s.replacement = JS_UNDEFINED;
    JS_FreeValue(a, s.maker);
    s.maker = JS_UNDEFINED;
    JS_FreeValue(a, original);
    s.gc++;
    JS_RunGC(rt);
    require(s.born == s.freed, "all custom owners released before context teardown");
    JS_FreeContext(a);
    JS_FreeContext(b);
    s.gc++;
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(s.born == 49 && s.freed == 49, "realm owner balance");
    if (moving) {
        require(s.live == 0 && s.moves > 0 && s.failed > 0, "moving/OOM allocator balance");
        while (s.retired) {
            Allocation *p = s.retired;
            s.retired = p->h.next;
            free(p);
        }
    }
    printf(
        "CLOSURE_HOST_OK moving=%d born=%u finalized=%u gc=%u reentries=%u moves=%zu failed=%u\n",
        moving, s.born, s.freed, s.gc, s.reentries, s.moves, s.failed);
}
int main(void)
{
    exercise(0);
    exercise(1);
    return 0;
}
