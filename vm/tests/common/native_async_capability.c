/* Public async Promise ownership, hook, GC, OOM and realm checks.
 * This is a correctness/observer host, never a speed workload. */
#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x)                                                                                   \
    do {                                                                                           \
        ++checks;                                                                                  \
        if (!(x)) {                                                                                \
            fprintf(stderr, "CHECK line=%d n=%u\n", __LINE__, checks);                             \
            exit(2);                                                                               \
        }                                                                                          \
    } while (0)
typedef struct Block {
    size_t size;
    uint64_t magic;
} Block;
typedef struct State {
    size_t blocks, bytes, peak, attempts, fail_after, armed_alloc, fired;
    unsigned hooks[4], reentries, interrupts, stop_after;
    JSRuntime *rt;
    JSContext *other;
    JSValue nested;
} State;
static const uint64_t magic = UINT64_C(0x50524f4d49534531);
static unsigned checks;
static void hook(JSContext *ctx, JSPromiseHookType type, JSValueConst promise, JSValueConst parent,
                 void *opaque)
{
    State *s = opaque;
    (void)ctx;
    (void)parent;
    CHECK(type >= 0 && type < 4 && JS_IsPromise(promise));
    s->hooks[type]++;
}
static void *allocate(void *opaque, size_t size)
{
    State *s = opaque;
    Block *b;
    s->attempts++;
    if (s->fail_after && --s->fail_after == 0)
        return NULL;
    if (s->armed_alloc && --s->armed_alloc == 0) {
        JSValue v;
        s->fired++;
        JS_SetPromiseHook(s->rt, hook, s);
        JS_RunGC(s->rt);
        v = JS_Call(s->other, s->nested, JS_UNDEFINED, 0, NULL);
        CHECK(!JS_IsException(v));
        JS_FreeValue(s->other, v);
        s->reentries++;
    }
    if (size > SIZE_MAX - sizeof(*b))
        return NULL;
    b = malloc(sizeof(*b) + size);
    if (!b)
        return NULL;
    b->size = size;
    b->magic = magic;
    s->blocks++;
    s->bytes += size;
    if (s->bytes > s->peak)
        s->peak = s->bytes;
    return b + 1;
}
static void deallocate(void *opaque, void *ptr)
{
    State *s = opaque;
    Block *b;
    if (!ptr)
        return;
    b = (Block *)ptr - 1;
    CHECK(b->magic == magic && s->blocks && s->bytes >= b->size);
    s->blocks--;
    s->bytes -= b->size;
    b->magic = 0;
    free(b);
}
static void *resize(void *opaque, void *ptr, size_t size)
{
    size_t old;
    void *out;
    if (!ptr)
        return allocate(opaque, size);
    if (!size) {
        deallocate(opaque, ptr);
        return NULL;
    }
    old = ((Block *)ptr - 1)->size;
    out = allocate(opaque, size);
    if (!out)
        return NULL;
    memcpy(out, ptr, old < size ? old : size);
    deallocate(opaque, ptr);
    return out;
}
static void *zero_allocate(void *opaque, size_t count, size_t size)
{
    void *ptr;
    if (count && size > SIZE_MAX / count)
        return NULL;
    ptr = allocate(opaque, count * size);
    if (ptr)
        memset(ptr, 0, count * size);
    return ptr;
}
static size_t usable(const void *ptr)
{
    const Block *b = (const Block *)ptr - 1;
    CHECK(b->magic == magic);
    return b->size;
}
static const JSMallocFunctions mf = {zero_allocate, allocate, deallocate, resize, usable};
static const char *generator_body =
    "(async function(n){let sum=0;const g=(async function*(){for(let i=0;i<n;i++)yield {i:i&7};})();for await(const v of g)sum+=v.i;return sum;})";
static const char *ordinary_body =
    "(function(){async function get(x){return x;}return async function(n){let sum=0;for(let i=0;i<n;i++)sum+=await get(i&7);return sum;};})()";
static const char *reentry_generator_body =
    "(async function(n){let sum=0;const g=(async function*(){for(let i=0;i<n;i++)yield {i:i&7,pad:new Array(80).fill(i)};})();for await(const v of g)sum+=v.i;return sum;})";
static const char *reentry_ordinary_body =
    "(function(){async function get(x){return {v:x,pad:new Array(80).fill(x)};}return async function(n){let sum=0;for(let i=0;i<n;i++)sum+=(await get(i&7)).v;return sum;};})()";
static const char *body;
static const char *reentry_body;
static JSValue eval(JSContext *ctx, const char *source)
{
    JSValue v =
        JS_Eval(ctx, source, strlen(source), "ready-await-public-host", JS_EVAL_TYPE_GLOBAL);
    CHECK(!JS_IsException(v));
    return v;
}
static void clear_exception(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    JS_FreeValue(ctx, e);
}
static unsigned drain(JSRuntime *rt, int errors_allowed)
{
    JSContext *ctx;
    int rc;
    unsigned jobs = 0;
    while ((rc = JS_ExecutePendingJob(rt, &ctx)) != 0) {
        CHECK(++jobs < 2000000);
        if (rc < 0) {
            CHECK(errors_allowed);
            clear_exception(ctx);
        }
    }
    return jobs;
}
static int execute(JSContext *ctx, JSRuntime *rt, JSValueConst fn, int n, int errors_allowed)
{
    JSValue arg = JS_NewInt32(ctx, n), p = JS_Call(ctx, fn, JS_UNDEFINED, 1, &arg), value;
    int state;
    if (JS_IsException(p)) {
        CHECK(errors_allowed);
        clear_exception(ctx);
        drain(rt, errors_allowed);
        return -1;
    }
    CHECK(JS_IsPromise(p));
    drain(rt, errors_allowed);
    state = JS_PromiseState(ctx, p);
    if (!errors_allowed) {
        int64_t answer;
        CHECK(state == JS_PROMISE_FULFILLED);
        value = JS_PromiseResult(ctx, p);
        CHECK(JS_ToInt64(ctx, &answer, value) == 0 &&
              answer == (n / 8) * 28 + ((n % 8) * (n % 8 - 1)) / 2);
        JS_FreeValue(ctx, value);
    }
    JS_FreeValue(ctx, p);
    return state;
}
static void setup(State *s, JSContext **ctx, JSValue *fn)
{
    memset(s, 0, sizeof(*s));
    s->rt = JS_NewRuntime2(&mf, s);
    CHECK(s->rt);
    JS_SetMaxStackSize(s->rt, 2 * 1024 * 1024);
    *ctx = JS_NewContext(s->rt);
    CHECK(*ctx);
    *fn = eval(*ctx, body);
}
static void teardown(State *s, JSContext *ctx, JSValue fn)
{
    s->fail_after = 0;
    s->armed_alloc = 0;
    JS_SetPromiseHook(s->rt, NULL, NULL);
    JS_SetInterruptHandler(s->rt, NULL, NULL);
    if (s->other) {
        JS_FreeValue(s->other, s->nested);
        JS_FreeContext(s->other);
    }
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_RunGC(s->rt);
    JS_FreeRuntime(s->rt);
    CHECK(s->blocks == 0 && s->bytes == 0);
}
static int interrupt(JSContext *ctx, void *opaque)
{
    State *s = opaque;
    (void)ctx;
    return ++s->interrupts > s->stop_after;
}
int main(int argc, char **argv)
{
    State s;
    JSContext *ctx;
    JSValue fn;
    unsigned i;
    size_t before;
    const char *kind = argc > 1 ? argv[1] : "generator";
    CHECK(!strcmp(kind, "generator") || !strcmp(kind, "ordinary"));
    CHECK(argc <= 3 && (argc < 3 || !strcmp(argv[2], "sweep")));
    body = !strcmp(kind, "ordinary") ? ordinary_body : generator_body;
    reentry_body = !strcmp(kind, "ordinary") ? reentry_ordinary_body : reentry_generator_body;
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 3) {
        for (i = 1; i <= 340; i++) {
            int result;
            setup(&s, &ctx, &fn);
            s.fail_after = i;
            result = execute(ctx, s.rt, fn, 4, 1);
            s.fail_after = 0;
            CHECK(result >= -1 && result <= JS_PROMISE_REJECTED);
            teardown(&s, ctx, fn);
        }
        printf("ASYNC_CAPABILITY_OK kind=%s trials=340 live=0 checks=%u\n", kind, checks);
        return 0;
    }
    setup(&s, &ctx, &fn);
    execute(ctx, s.rt, fn, 128, 0);
    for (i = 0; i < 3; i++) {
        before = s.attempts;
        execute(ctx, s.rt, fn, 128, 0);
        printf("ALLOC trial=%u n=128 attempts=%zu live=%zu bytes=%zu\n", i, s.attempts - before,
               s.blocks, s.bytes);
    }
    JS_SetPromiseHook(s.rt, hook, &s);
    execute(ctx, s.rt, fn, 32, 0);
    CHECK(s.hooks[JS_PROMISE_HOOK_INIT] > 0 && s.hooks[JS_PROMISE_HOOK_RESOLVE] > 0);
    printf("HOOK init=%u before=%u after=%u resolve=%u\n", s.hooks[0], s.hooks[1], s.hooks[2],
           s.hooks[3]);
    JS_SetPromiseHook(s.rt, NULL, NULL);
    s.other = JS_NewContext(s.rt);
    CHECK(s.other);
    s.nested = eval(s.other, "(function(){return {nested:17};})");
    {
        JSValue reentry_fn = eval(ctx, reentry_body);
        for (i = 1; sizeof(void *) == 8 && sizeof(JSValue) == 16 && i <= 6; i++) {
            unsigned initial = (unsigned)s.fired;
            s.armed_alloc = i;
            execute(ctx, s.rt, reentry_fn, 16, 0);
            CHECK(s.fired == initial + 1 && s.reentries == s.fired);
            JS_SetPromiseHook(s.rt, NULL, NULL);
            s.armed_alloc = 0;
        }
        JS_FreeValue(ctx, reentry_fn);
    }
    {
        JSValue other_fn = eval(s.other, body);
        execute(ctx, s.rt, other_fn, 64, 0);
        JS_FreeValue(s.other, other_fn);
    }
    printf("REENTRY fired=%zu callbacks=%u crossrealm=1\n", s.fired, s.reentries);
    teardown(&s, ctx, fn);
    setup(&s, &ctx, &fn);
    s.stop_after = 3;
    JS_SetInterruptHandler(s.rt, interrupt, &s);
    execute(ctx, s.rt, fn, 100000, 1);
    CHECK(s.interrupts >= 4);
    printf("INTERRUPT calls=%u\n", s.interrupts);
    teardown(&s, ctx, fn);
    printf("ASYNC_CAPABILITY_OK kind=%s checks=%u\n", kind, checks);
    return 0;
}
