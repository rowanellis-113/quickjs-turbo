#include "quickjs.h"
#include <stdint.h>
#include <stddef.h>
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
typedef struct Allocator {
    size_t live, moves, retired, failed, old_size, new_size, fail_size, first_fail_size;
    int arm, blocked;
    Allocation *old;
} Allocator;
static unsigned born, finalized, reentries, recovered;
static JSClassID owner_id;
static void require(int ok, const char *why)
{
    if (!ok) {
        fprintf(stderr, "BINDING_HOST_FAIL %s\n", why);
        exit(40);
    }
}
static void *moving_malloc(void *opaque, size_t n)
{
    Allocator *s = opaque;
    if (s->blocked) {
        if (!s->failed)
            s->first_fail_size = n;
        ++s->failed;
        s->fail_size = n;
        return NULL;
    }
    if (n > SIZE_MAX - sizeof(Allocation))
        return NULL;
    Allocation *p = malloc(sizeof(*p) + (n ? n : 1));
    if (!p)
        return NULL;
    p->h.size = n ? n : 1;
    p->h.next = NULL;
    ++s->live;
    return p + 1;
}
static void moving_free(void *opaque, void *ptr)
{
    if (!ptr)
        return;
    Allocator *s = opaque;
    require(s->live > 0, "allocator live underflow");
    --s->live;
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
    Allocator *s = opaque;
    if (!ptr)
        return moving_malloc(opaque, n);
    if (!n) {
        moving_free(opaque, ptr);
        return NULL;
    }
    Allocation *old = (Allocation *)ptr - 1;
    size_t previous = old->h.size;
    void *result = moving_malloc(opaque, n);
    if (!result)
        return NULL;
    memcpy(result, ptr, previous < n ? previous : n);
    /* Keep retired storage zeroed and unavailable for reuse until runtime end.
     * A stale value-cell pointer deterministically observes the wrong value. */
    memset(ptr, 0, previous);
    old->h.next = s->old;
    s->old = old;
    --s->live;
    ++s->retired;
    ++s->moves;
    if (s->arm && previous >= 256 && previous % 16 == 0 && n == (previous / 16 * 3 / 2) * 16) {
        s->arm = 0;
        s->blocked = 1;
        s->old_size = previous;
        s->new_size = n;
    }
    return result;
}
static void retire_cleanup(Allocator *s)
{
    while (s->old) {
        Allocation *next = s->old->h.next;
        free(s->old);
        s->old = next;
    }
}
static void exception_report(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    const char *text = JS_ToCString(ctx, e);
    fprintf(stderr, "exception:%s\n", text ? text : "<oom>");
    JS_FreeCString(ctx, text);
    JS_FreeValue(ctx, e);
}
static JSValue evaluate(JSContext *ctx, const char *source, int flags)
{
    JSValue v = JS_Eval(ctx, source, strlen(source), "binding_cell_host.js", flags);
    if (JS_IsException(v)) {
        exception_report(ctx);
        require(0, "eval");
    }
    return v;
}
static void run(JSContext *ctx, const char *source)
{
    JSValue v = evaluate(ctx, source, JS_EVAL_TYPE_GLOBAL);
    JS_FreeValue(ctx, v);
}
static void integer(JSContext *ctx, JSValue value, int expected, const char *why)
{
    int32_t n = 0;
    require(!JS_IsException(value), why);
    require(JS_IsNumber(value), why);
    require(JS_ToInt32(ctx, &n, value) == 0 && n == expected, why);
    JS_FreeValue(ctx, value);
}
static JSValue call(JSContext *ctx, JSValue fn, JSValue anchor)
{
    JSValue result = JS_Call(ctx, fn, JS_UNDEFINED, 1, &anchor);
    if (JS_IsException(result)) {
        exception_report(ctx);
        require(0, "reader call");
    }
    return result;
}
static JSValue reader(JSContext *ctx, const char *name)
{
    char code[200];
    snprintf(code, sizeof(code), "(function(receiver){const keep=receiver.keep;return %s;})", name);
    return evaluate(ctx, code, JS_EVAL_TYPE_GLOBAL);
}
static void own_finalizer(JSRuntime *rt, JSValue value)
{
    (void)rt;
    if (JS_GetOpaque(value, owner_id))
        ++finalized;
}
static JSValue new_owner(JSContext *ctx)
{
    JSValue v = JS_NewObjectClass(ctx, owner_id);
    require(!JS_IsException(v), "new owner");
    JS_SetOpaque(v, (void *)(uintptr_t)1);
    ++born;
    return v;
}
static JSValue host_reenter(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    ++reentries;
    run(ctx, "for(let i=0;i<96;i++)globalThis['__callbackGrow'+i]=i;__cellLexical=29;");
    JS_RunGC(JS_GetRuntime(ctx));
    return JS_UNDEFINED;
}
static void seed(JSRuntime *rt, JSContext *ctx, JSValue global)
{
    owner_id = 0;
    JS_NewClassID(rt, &owner_id);
    JSClassDef cls = {0};
    cls.class_name = "BindingCellOwner";
    cls.finalizer = own_finalizer;
    require(JS_NewClass(rt, owner_id, &cls) == 0, "register owner");
    require(JS_SetPropertyStr(ctx, global, "hostReenter",
                              JS_NewCFunction(ctx, host_reenter, "hostReenter", 0)) == 1,
            "host install");
    run(ctx,
        "let __cellLexical=7;globalThis.__hostRun=function(receiver){const keep=receiver.keep;hostReenter();return __cellLexical;};");
}
static void basic(JSRuntime *rt, JSContext *ctx, JSValue global, JSValue anchor)
{
    unsigned before = finalized;
    require(JS_SetPropertyStr(ctx, global, "__cellData", new_owner(ctx)) == 1,
            "data owner install");
    JSValue fn = reader(ctx, "__cellData");
    for (int i = 0; i < 32; ++i) {
        JSValue v = call(ctx, fn, anchor);
        require(JS_GetOpaque(v, owner_id) != NULL, "owner identity");
        JS_FreeValue(ctx, v);
    }
    require(finalized == before, "cache must not prematurely finalize");
    require(JS_SetPropertyStr(ctx, global, "__cellData", JS_NULL) == 1, "replace owner");
    require(finalized == before + 1, "cache must not retain old owner until GC");
    JS_FreeValue(ctx, fn);
    require(JS_SetPropertyStr(ctx, global, "__cellUninitialized", JS_UNINITIALIZED) == 1,
            "host uninitialized install");
    fn = reader(ctx, "__cellUninitialized");
    for (int i = 0; i < 12; ++i) {
        JSValue v = call(ctx, fn, anchor);
        require(JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED,
                "global data must not acquire lexical TDZ");
        JS_FreeValue(ctx, v);
    }
    JS_FreeValue(ctx, fn);
    fn = JS_GetPropertyStr(ctx, global, "__hostRun");
    for (int i = 0; i < 16; ++i)
        integer(ctx, call(ctx, fn, anchor), 29, "host GC/reentry");
    JS_FreeValue(ctx, fn);
    JS_RunGC(rt);
}
static void foreign_realm(JSRuntime *rt, JSContext *caller, JSValue anchor)
{
    JSContext *other = JS_NewContext(rt);
    require(other != NULL, "foreign context");
    JSValue global = JS_GetGlobalObject(other);
    unsigned before = finalized;
    require(JS_SetPropertyStr(other, global, "__ctxSentinel", new_owner(other)) == 1,
            "realm sentinel");
    run(other, "globalThis.__foreignData=17;");
    JSValue fn = reader(other, "__foreignData");
    for (int i = 0; i < 16; ++i)
        integer(caller, call(caller, fn, anchor), 17, "realm selection");
    JS_FreeContext(other); /* The retained function owns its original realm. */
    require(finalized == before, "function keeps realm alive");
    for (int i = 0; i < 1024; ++i) {
        char key[64];
        snprintf(key, sizeof(key), "__foreignGrow%d", i);
        require(JS_SetPropertyStr(caller, global, key, JS_NewInt32(caller, i)) == 1,
                "foreign global resize");
    }
    require(JS_SetPropertyStr(caller, global, "__foreignData", JS_NewInt32(caller, 37)) == 1,
            "foreign update");
    JS_RunGC(rt);
    integer(caller, call(caller, fn, anchor), 37, "foreign invalidation after context release");
    JS_FreeValue(caller, fn);
    JS_FreeValue(caller, global);
    JS_RunGC(rt);
    JS_RunGC(rt);
    require(finalized == before + 1, "borrowed realm must not keep dead cycle");
}
static void moving_oom(JSRuntime *rt, JSContext *ctx, JSValue anchor, Allocator *s)
{
    for (int i = 0; i < 80; ++i) {
        char declaration[96];
        snprintf(declaration, sizeof(declaration), "let __oomLexical%d=0;", i);
        JSValue compiled =
            evaluate(ctx, declaration, JS_EVAL_TYPE_GLOBAL | JS_EVAL_FLAG_COMPILE_ONLY);
        JSValue fn = reader(ctx, "__cellLexical");
        for (int warm = 0; warm < 8; ++warm)
            integer(ctx, call(ctx, fn, anchor), 29, "warm cell before OOM move");
        size_t failed = s->failed;
        s->arm = 1;
        JSValue result = JS_EvalFunction(ctx, compiled);
        s->arm = 0;
        s->blocked = 0;
        if (s->failed != failed) {
            require(JS_IsException(result), "post-move injected OOM must throw");
            JSValue e = JS_GetException(ctx);
            JS_FreeValue(ctx, e);
            JS_RunGC(rt);
            integer(ctx, call(ctx, fn, anchor), 29, "post-move OOM must invalidate retired cell");
            JS_FreeValue(ctx, fn);
            ++recovered;
            printf(
                "MOVE_OOM old=%zu new=%zu first_failed_size=%zu failed_size=%zu attempts=%zu step=%d\n",
                s->old_size, s->new_size, s->first_fail_size, s->fail_size, s->failed - failed, i);
            return;
        }
        require(!JS_IsException(result), "ordinary declaration");
        JS_FreeValue(ctx, result);
        JS_FreeValue(ctx, fn);
    }
    require(0, "no forced post-move OOM observed");
}
static void exercise(int moving)
{
    Allocator stats = {0};
    JSMallocFunctions f = {moving_calloc, moving_malloc, moving_free, moving_realloc, moving_size};
    JSRuntime *rt = moving ? JS_NewRuntime2(&f, &stats) : JS_NewRuntime();
    require(rt != NULL, "runtime");
    JSContext *ctx = JS_NewContext(rt);
    require(ctx != NULL, "context");
    JSValue global = JS_GetGlobalObject(ctx);
    JSValue anchor = JS_NewObject(ctx);
    require(JS_SetPropertyStr(ctx, anchor, "keep", JS_NewInt32(ctx, 1)) == 1, "anchor");
    seed(rt, ctx, global);
    basic(rt, ctx, global, anchor);
    foreign_realm(rt, ctx, anchor);
    if (moving)
        moving_oom(rt, ctx, anchor, &stats);
    JS_FreeValue(ctx, anchor);
    JS_FreeValue(ctx, global);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    require(born == finalized, "host resource leak");
    if (moving) {
        require(stats.live == 0, "moving allocator logical leak");
        require(stats.moves > 0, "no actual relocation");
        retire_cleanup(&stats);
    }
    printf("HOST_RUNTIME_OK moving=%d moves=%zu retired=%zu born=%u finalized=%u\n", moving,
           stats.moves, stats.retired, born, finalized);
}
int main(void)
{
    exercise(0);
    exercise(1);
    require(reentries == 32 && recovered == 1, "host coverage counters");
    printf("BINDING_CELL_HOST_OK born=%u finalized=%u reentries=%u oom=%u\n", born, finalized,
           reentries, recovered);
    return 0;
}
