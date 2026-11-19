/* Allocator contract tests: actual buffers, accounting, OOM and engine lifetime. */
#include "src/common/memory/allocator-pool.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#define CHECK(c)                                                                                   \
    do {                                                                                           \
        if (!(c)) {                                                                                \
            fprintf(stderr, "POOL_CHECK %s:%d %s\n", __FILE__, __LINE__, #c);                      \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)
static int64_t backing_budget = -1;
static size_t backing_live;
static int backing_allow(void)
{
    if (backing_budget < 0)
        return 1;
    if (!backing_budget)
        return 0;
    backing_budget--;
    return 1;
}
void *FramePoolTestMalloc(size_t n)
{
    void *p;
    if (!backing_allow())
        return NULL;
    p = malloc(n);
    if (p)
        backing_live++;
    return p;
}
void *FramePoolTestCalloc(size_t n, size_t s)
{
    void *p;
    if (!backing_allow())
        return NULL;
    p = calloc(n, s);
    if (p)
        backing_live++;
    return p;
}
void FramePoolTestFree(void *p)
{
    if (p) {
        CHECK(backing_live);
        backing_live--;
        free(p);
    }
}
void *FramePoolTestRealloc(void *p, size_t n)
{
    void *q;
    if (!backing_allow())
        return NULL;
    q = realloc(p, n);
    if (q && !p)
        backing_live++;
    return q;
}
static uint32_t random_state = 0x4719ac63;
static uint32_t next_random(void)
{
    uint32_t x = random_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return random_state = x;
}
static void filled(const void *p, size_t n, unsigned char value)
{
    const unsigned char *b = p;
    size_t i;
    for (i = 0; i < n; i++)
        CHECK(b[i] == value);
}
static void buffers(unsigned limit)
{
    struct Slot {
        void *ptr;
        size_t n;
        unsigned char value;
    } slots[1024] = {0};
    FramePool *p = FramePoolCreate(limit, FRAME_POOL_TRACK);
    FramePoolStats stats;
    const JSMallocFunctions *m = &FramePoolFunctions;
    size_t live = 0, bytes = 0;
    unsigned i;
    CHECK(p);
    for (i = 0; i < 50000; i++) {
        struct Slot *s = &slots[next_random() % 1024];
        size_t n = 1 + next_random() % ((next_random() % 4) ? 512 : 8192);
        if (s->ptr) {
            size_t old_capacity = m->js_malloc_usable_size(s->ptr);
            void *q;
            filled(s->ptr, s->n, s->value);
            if (next_random() % 3 == 0) {
                m->js_free(p, s->ptr);
                bytes -= old_capacity;
                live--;
                s->ptr = NULL;
                continue;
            }
            q = m->js_realloc(p, s->ptr, n);
            CHECK(q);
            filled(q, s->n < n ? s->n : n, s->value);
            bytes -= old_capacity;
            s->ptr = q;
        } else {
            if (next_random() & 1) {
                s->ptr = m->js_calloc(p, n, 1);
                CHECK(s->ptr);
                filled(s->ptr, n, 0);
            } else
                s->ptr = m->js_malloc(p, n);
            CHECK(s->ptr);
            live++;
        }
        CHECK(!((uintptr_t)s->ptr & 15));
        CHECK(m->js_malloc_usable_size(s->ptr) >= n);
        s->n = n;
        s->value = (unsigned char)next_random();
        memset(s->ptr, s->value, n);
        bytes += m->js_malloc_usable_size(s->ptr);
        if (i % 257 == 0) {
            FramePoolGetStats(p, &stats);
            CHECK(stats.live_blocks == live);
            CHECK(stats.live_capacity == bytes);
        }
    }
    for (i = 0; i < 1024; i++)
        if (slots[i].ptr) {
            filled(slots[i].ptr, slots[i].n, slots[i].value);
            m->js_free(p, slots[i].ptr);
        }
    FramePoolGetStats(p, &stats);
    CHECK(!stats.live_blocks && !stats.live_capacity);
    CHECK(stats.pages <= limit / 16);
    CHECK(!m->js_malloc(p, 0));
    CHECK(!m->js_malloc(p, SIZE_MAX));
    CHECK(!m->js_calloc(p, SIZE_MAX, 2));
    CHECK(!m->js_calloc(p, 0, 1));
    CHECK(!m->js_realloc(p, NULL, 0));
    m->js_free(p, NULL);
    {
        unsigned char *q = m->js_malloc(p, 73);
        size_t cap;
        CHECK(q);
        memset(q, 0x59, 73);
        cap = m->js_malloc_usable_size(q);
        CHECK(FramePoolDestroy(p) == -1);
        CHECK(!m->js_realloc(p, q, SIZE_MAX));
        filled(q, 73, 0x59);
        CHECK(m->js_malloc_usable_size(q) == cap);
        CHECK(!m->js_realloc(p, q, 0));
    }
    CHECK(FramePoolDestroy(p) == 0);
}
static void accounting(JSRuntime *rt, FramePool *p)
{
    JSMemoryUsage usage;
    FramePoolStats stats;
    JS_ComputeMemoryUsage(rt, &usage);
    FramePoolGetStats(p, &stats);
    CHECK(usage.malloc_count == (int64_t)stats.live_blocks);
    CHECK(usage.malloc_size == (int64_t)(stats.live_capacity + stats.live_blocks * 8));
}
static void runtime(unsigned limit)
{
    FramePool *p = FramePoolCreate(limit, FRAME_POOL_TRACK);
    JSRuntime *rt;
    JSContext *ctx;
    JSValue value;
    FramePoolStats stats;
    JSMemoryUsage usage;
    unsigned char *q;
    size_t cap;
    const char source[] =
        "(()=>{let sum=0;function f(o){return o.x+o.y;}"
        "for(let i=0;i<12000;i++){let o={x:i,y:3};sum+=f(o);"
        "if((i%17)===0){Object.setPrototypeOf(o,{get z(){return 7;}});if(o.z!==7)throw Error('proto');}"
        "let a=[i,2,3];let [x,...rest]=a;if(x!==i||rest[1]!==3)throw Error('iterator');"
        "let b=JSON.parse(JSON.stringify({i,a,unicode:'\\ud83d\\ude03'}));if(b.i!==i||b.a[0]!==i)throw Error('json');"
        "let r=/([a-z]+)([0-9]+)/.exec('abc123');if(r[2]!=='123')throw Error('regexp');"
        "if((BigInt(i)+17n)*3n!==BigInt(i*3+51))throw Error('bigint');}"
        "if(sum!==72030000)throw Error('sum '+sum);return 123;})()";
    CHECK(p);
    rt = JS_NewRuntime2(&FramePoolFunctions, p);
    CHECK(rt);
    ctx = JS_NewContext(rt);
    CHECK(ctx);
    accounting(rt, p);
    value = JS_Eval(ctx, source, sizeof(source) - 1, "pool-contract.js", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(value)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "POOL_JS %s\n", s ? s : "exception");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
    }
    CHECK(!JS_IsException(value));
    CHECK(JS_VALUE_GET_INT(value) == 123);
    JS_FreeValue(ctx, value);
    JS_RunGC(rt);
    accounting(rt, p);
    q = js_malloc_rt(rt, 73);
    CHECK(q);
    memset(q, 0x42, 73);
    cap = js_malloc_usable_size_rt(rt, q);
    JS_ComputeMemoryUsage(rt, &usage);
    JS_SetMemoryLimit(rt, (size_t)usage.malloc_size + 8);
    CHECK(!js_malloc_rt(rt, 4096));
    CHECK(!js_realloc_rt(rt, q, cap + 4096));
    filled(q, 73, 0x42);
    JS_SetMemoryLimit(rt, 0);
    js_free_rt(rt, q);
    accounting(rt, p);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    FramePoolGetStats(p, &stats);
    CHECK(!stats.live_blocks && !stats.live_capacity);
    CHECK(FramePoolDestroy(p) == 0);
}
typedef struct FailAllocator {
    FramePool *pool;
    int64_t budget;
} FailAllocator;
static int logical_allow(FailAllocator *p)
{
    if (p->budget < 0)
        return 1;
    if (!p->budget)
        return 0;
    p->budget--;
    return 1;
}
static void *fail_malloc(void *opaque, size_t n)
{
    FailAllocator *p = opaque;
    return logical_allow(p) ? FramePoolFunctions.js_malloc(p->pool, n) : NULL;
}
static void *fail_calloc(void *opaque, size_t n, size_t s)
{
    FailAllocator *p = opaque;
    return logical_allow(p) ? FramePoolFunctions.js_calloc(p->pool, n, s) : NULL;
}
static void *fail_realloc(void *opaque, void *ptr, size_t n)
{
    FailAllocator *p = opaque;
    return logical_allow(p) ? FramePoolFunctions.js_realloc(p->pool, ptr, n) : NULL;
}
static void fail_free(void *opaque, void *ptr)
{
    FailAllocator *p = opaque;
    FramePoolFunctions.js_free(p->pool, ptr);
}
static size_t fail_usable(const void *ptr)
{
    return FramePoolFunctions.js_malloc_usable_size(ptr);
}
static const JSMallocFunctions fail_functions = {fail_calloc, fail_malloc, fail_free, fail_realloc,
                                                 fail_usable};
static void oom(unsigned limit)
{
    unsigned i;
    for (i = 0; i < 700; i++) {
        FailAllocator a;
        JSRuntime *rt;
        JSContext *ctx = NULL;
        FramePoolStats stats;
        if (i % 100 == 0) {
            printf("POOL_OOM_PROGRESS %u\n", i);
            fflush(stdout);
        }
        a.pool = FramePoolCreate(limit, FRAME_POOL_TRACK);
        CHECK(a.pool);
        a.budget = i;
        rt = JS_NewRuntime2(&fail_functions, &a);
        if (rt) {
            ctx = JS_NewContext(rt);
            if (ctx)
                JS_FreeContext(ctx);
            JS_FreeRuntime(rt);
        }
        FramePoolGetStats(a.pool, &stats);
        CHECK(!stats.live_blocks && !stats.live_capacity);
        CHECK(FramePoolDestroy(a.pool) == 0);
    }
#ifdef FRAME_POOL_BACKING_FAULTS
    for (i = 0; i < 700; i++) {
        FramePool *p;
        JSRuntime *rt = NULL;
        JSContext *ctx = NULL;
        FramePoolStats stats;
        backing_budget = i;
        p = FramePoolCreate(limit, FRAME_POOL_TRACK);
        if (p) {
            rt = JS_NewRuntime2(&FramePoolFunctions, p);
            if (rt) {
                ctx = JS_NewContext(rt);
                if (ctx)
                    JS_FreeContext(ctx);
                JS_FreeRuntime(rt);
            }
            FramePoolGetStats(p, &stats);
            CHECK(!stats.live_blocks && !stats.live_capacity);
            CHECK(FramePoolDestroy(p) == 0);
        }
        backing_budget = -1;
        CHECK(!backing_live);
    }
#endif
}
int main(void)
{
    unsigned limits[] = {0, 128, 256, 512};
    unsigned i;
    for (i = 0; i < sizeof(limits) / sizeof(*limits); i++) {
        printf("POOL_STAGE buffers %u\n", limits[i]);
        fflush(stdout);
        buffers(limits[i]);
        printf("POOL_STAGE runtime %u\n", limits[i]);
        fflush(stdout);
        runtime(limits[i]);
        printf("POOL_STAGE oom %u\n", limits[i]);
        fflush(stdout);
        oom(limits[i]);
        CHECK(!backing_live);
        printf("POOL_CONTRACT_OK limit=%u\n", limits[i]);
        fflush(stdout);
    }
    return 0;
}
