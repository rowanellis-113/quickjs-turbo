/* MIT. Partial Promise capability ownership and async-entry OOM regression.
 * Every trial uses a fresh runtime and one failed allocation, with leak and
 * duplicate-release checks. These allocator observations are not timings. */
#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(x)                                                                                   \
    do {                                                                                           \
        if (!(x)) {                                                                                \
            fprintf(stderr, "PROMISE_OOM_CHECK line=%d case=%u offset=%zu hooks=%u\n", __LINE__,   \
                    current_case, current_offset, current_hooks);                                  \
            exit(2);                                                                               \
        }                                                                                          \
    } while (0)

typedef struct {
    size_t bytes;
    uint64_t magic;
} Block;
typedef struct {
    size_t live, bytes, requests, fail_at;
    unsigned observing, rejected, hook_calls;
} Allocator;
static const uint64_t block_magic = UINT64_C(0x50524f4d4f4f4d31);
static unsigned current_case, current_hooks;
static size_t current_offset;

static void *allocate(void *opaque, size_t n)
{
    Allocator *a = opaque;
    Block *b;
    if (a->observing && ++a->requests == a->fail_at) {
        ++a->rejected;
        return NULL;
    }
    if (n > SIZE_MAX - sizeof(*b))
        return NULL;
    b = malloc(sizeof(*b) + n);
    if (!b)
        return NULL;
    b->bytes = n;
    b->magic = block_magic;
    ++a->live;
    a->bytes += n;
    return b + 1;
}

static void release(void *opaque, void *p)
{
    Allocator *a = opaque;
    Block *b;
    if (!p)
        return;
    b = (Block *)p - 1;
    CHECK(b->magic == block_magic && a->live && a->bytes >= b->bytes);
    --a->live;
    a->bytes -= b->bytes;
    b->magic = 0;
    free(b);
}

static void *resize(void *opaque, void *p, size_t n)
{
    void *out;
    size_t old;
    if (!p)
        return allocate(opaque, n);
    if (!n) {
        release(opaque, p);
        return NULL;
    }
    old = ((Block *)p - 1)->bytes;
    out = allocate(opaque, n);
    if (out) {
        memcpy(out, p, old < n ? old : n);
        release(opaque, p);
    }
    return out;
}

static void *allocate_zero(void *opaque, size_t n, size_t size)
{
    void *p;
    if (size && n > SIZE_MAX / size)
        return NULL;
    p = allocate(opaque, n * size);
    if (p)
        memset(p, 0, n * size);
    return p;
}

static size_t usable(const void *p)
{
    const Block *b;
    if (!p)
        return 0;
    b = (const Block *)p - 1;
    CHECK(b->magic == block_magic);
    return b->bytes;
}

static const JSMallocFunctions functions = {allocate_zero, allocate, release, resize, usable};

static void hook(JSContext *ctx, JSPromiseHookType type, JSValueConst promise, JSValueConst parent,
                 void *opaque)
{
    Allocator *a = opaque;
    (void)ctx;
    (void)parent;
    CHECK(type >= 0 && type < 4 && JS_IsPromise(promise));
    ++a->hook_calls;
}

static void clear_exception(JSContext *ctx)
{
    JSValue e = JS_GetException(ctx);
    JS_FreeValue(ctx, e);
}

static const char *scripts[] = {
    NULL, /* Public C capability API, with initially empty output slots. */
    "(async function(n){await 0;return n;})", "(async function(n){return n;})",
    "(function(n){let g=(async function*(){yield n;})();"
    "return g.next().then(v=>v.value);})",
    "(function(n){return new Promise(resolve=>resolve(n)).then(v=>v);})"};

static int trial(unsigned which, size_t fail_request, size_t limit_delta, unsigned hooks,
                 size_t *out_requests)
{
    Allocator a = {0};
    JSRuntime *rt;
    JSContext *ctx, *job_ctx;
    JSValue fn = JS_UNDEFINED, promise, value;
    JSValue resolve[2] = {JS_UNDEFINED, JS_UNDEFINED};
    JSValue arg;
    size_t requests;
    unsigned jobs = 0;
    int rc, answer = -1;
    int had_oom = 0;

    current_case = which;
    current_offset = fail_request ? fail_request : limit_delta;
    current_hooks = hooks;
    rt = JS_NewRuntime2(&functions, &a);
    CHECK(rt);
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    ctx = JS_NewContext(rt);
    CHECK(ctx);
    if (scripts[which]) {
        fn = JS_Eval(ctx, scripts[which], strlen(scripts[which]), "promise-oom",
                     JS_EVAL_TYPE_GLOBAL);
        CHECK(!JS_IsException(fn));
    }
    if (hooks)
        JS_SetPromiseHook(rt, hook, &a);
    if (limit_delta > 0) {
        JSMemoryUsage usage;
        JS_ComputeMemoryUsage(rt, &usage);
        JS_SetMemoryLimit(rt, (size_t)usage.malloc_size + limit_delta);
    }
    a.observing = 1;
    a.fail_at = fail_request;
    arg = JS_NewInt32(ctx, 4);
    promise = scripts[which] ? JS_Call(ctx, fn, JS_UNDEFINED, 1, &arg)
                             : JS_NewPromiseCapability(ctx, resolve);
    if (JS_IsException(promise)) {
        had_oom = 1;
        if (fail_request)
            CHECK(a.rejected == 1);
        clear_exception(ctx);
        if (!scripts[which]) {
            /* Released partial outputs must not retain a stale owner. */
            CHECK(JS_IsUndefined(resolve[0]) && JS_IsUndefined(resolve[1]));
        }
    } else {
        CHECK(JS_IsPromise(promise));
        if (!scripts[which]) {
            value = JS_Call(ctx, resolve[0], JS_UNDEFINED, 1, &arg);
            if (JS_IsException(value)) {
                had_oom = 1;
                if (fail_request)
                    CHECK(a.rejected == 1);
                clear_exception(ctx);
            }
            JS_FreeValue(ctx, value);
        }
    }
    while ((rc = JS_ExecutePendingJob(rt, &job_ctx)) != 0) {
        CHECK(++jobs < 4096);
        if (rc < 0) {
            had_oom = 1;
            if (fail_request)
                CHECK(a.rejected == 1);
            clear_exception(job_ctx);
        }
    }
    if (!JS_IsException(promise) && JS_PromiseState(ctx, promise) != JS_PROMISE_FULFILLED)
        had_oom = 1;
    if (fail_request && a.rejected)
        had_oom = 1;
    JS_SetMemoryLimit(rt, 0);
    a.observing = 0;
    requests = a.requests;
    if (out_requests)
        *out_requests = requests;
    if (fail_request)
        CHECK(a.rejected == (fail_request <= a.requests));
    if (!had_oom) {
        CHECK(!JS_IsException(promise));
        CHECK(JS_PromiseState(ctx, promise) == JS_PROMISE_FULFILLED);
        value = JS_PromiseResult(ctx, promise);
        CHECK(JS_ToInt32(ctx, &answer, value) == 0 && answer == 4);
        JS_FreeValue(ctx, value);
        if (hooks)
            CHECK(a.hook_calls > 0);
    }
    if (!JS_IsException(promise)) {
        JS_FreeValue(ctx, promise);
        JS_FreeValue(ctx, resolve[0]);
        JS_FreeValue(ctx, resolve[1]);
    }
    JS_SetPromiseHook(rt, NULL, NULL);
    JS_FreeValue(ctx, fn);
    JS_FreeContext(ctx);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    CHECK(a.live == 0 && a.bytes == 0);
    return (had_oom || (fail_request && a.rejected)) ? 0 : 1;
}

int main(void)
{
    unsigned which, hooks, trials = 0;
    size_t offset, requests = 0;
    setvbuf(stdout, NULL, _IONBF, 0);
    for (hooks = 0; hooks < 2; ++hooks) {
        for (which = 0; which < sizeof(scripts) / sizeof(scripts[0]); ++which) {
            CHECK(trial(which, 0, 0, hooks, &requests) == 1);
            CHECK(requests < 256);
            ++trials;
            for (offset = 1; offset <= requests; ++offset) {
                CHECK(trial(which, offset, 0, hooks, NULL) == 0);
                ++trials;
            }
            CHECK(trial(which, 0, 1, hooks, NULL) == 0);
            ++trials;
            unsigned consecutive_ok = 0;
            for (size_t delta = 16; delta <= 32768; delta += 16) {
                int ok = trial(which, 0, delta, hooks, NULL);
                ++trials;
                if (ok) {
                    if (++consecutive_ok >= 4)
                        break;
                } else {
                    consecutive_ok = 0;
                }
            }
            CHECK(consecutive_ok >= 4);
            printf("PROMISE_OOM_CASE case=%u hooks=%u requests=%zu\n", which, hooks, requests);
        }
    }
    printf("PROMISE_OOM_OK trials=%u live=0\n", trials);
    return 0;
}
