/* Public serialization plus bounded allocation-failure ownership checks. */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include "quickjs.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef union Header {
    size_t size;
    long double alignment;
    unsigned char pad[16];
} Header;
typedef struct Memory {
    size_t attempts, fail_at, live, bytes;
    unsigned failed, drain_probe;
} Memory;
static Memory *armed;
static size_t offset;
static int reject(Memory *m)
{
    ++m->attempts;
    if (m->fail_at && m->attempts == m->fail_at) {
        ++m->failed;
        return 1;
    }
    return 0;
}
static void *allocate(void *opaque, size_t size)
{
    Memory *m = opaque;
    if (m->drain_probe)
        return NULL;
    if (reject(m) || size > SIZE_MAX - sizeof(Header))
        return NULL;
    Header *h = malloc(sizeof(*h) + size);
    if (!h)
        return NULL;
    h->size = size;
    ++m->live;
    m->bytes += size;
    return h + 1;
}
static void release(void *opaque, void *ptr)
{
    Memory *m = opaque;
    if (!ptr)
        return;
    Header *h = (Header *)ptr - 1;
    assert(m->live && m->bytes >= h->size);
    --m->live;
    m->bytes -= h->size;
    free(h);
}
static void *allocate_zero(void *opaque, size_t count, size_t size)
{
    if (size && count > SIZE_MAX / size)
        return NULL;
    void *p = allocate(opaque, count * size);
    if (p)
        memset(p, 0, count * size);
    return p;
}
static void *resize(void *opaque, void *ptr, size_t size)
{
    if (!ptr)
        return allocate(opaque, size);
    if (!size) {
        release(opaque, ptr);
        return NULL;
    }
    Memory *m = opaque;
    if (reject(m) || size > SIZE_MAX - sizeof(Header))
        return NULL;
    Header *h = (Header *)ptr - 1;
    size_t old = h->size;
    h = realloc(h, sizeof(*h) + size);
    if (!h)
        return NULL;
    h->size = size;
    m->bytes = m->bytes - old + size;
    return h + 1;
}
static size_t usable(const void *ptr)
{
    return ptr ? ((const Header *)ptr - 1)->size : 0;
}
typedef struct {
    void **blocks;
    size_t count, cap, saved_gc_threshold;
    int active;
} ConcatArenaDrain;
static ConcatArenaDrain armed_drain;
static void concat_drain_arenas(JSRuntime *rt, Memory *m, ConcatArenaDrain *d)
{
    static const uint16_t classes[31] = {16,  24,  32,  40,  48,  56,  64,  72,  80,  88,  96,
                                         104, 112, 120, 128, 144, 160, 176, 192, 208, 224, 240,
                                         256, 288, 320, 352, 384, 416, 448, 480, 512};
    size_t added = 0;
    d->blocks = NULL;
    d->count = 0;
    d->cap = 0;
    d->saved_gc_threshold = JS_GetGCThreshold(rt);
    d->active = 1;
    m->drain_probe = 1;
    for (unsigned i = 0; i < 31; ++i) {
        size_t req = (size_t)classes[i] - 8u;
        for (;;) {
            void *p = js_malloc_rt(rt, req);
            if (!p)
                break;
            if (d->count == d->cap) {
                size_t nc = d->cap ? d->cap * 2u : 256u;
                void **nb = (void **)realloc(d->blocks, nc * sizeof(*nb));
                assert(nb);
                d->blocks = nb;
                d->cap = nc;
            }
            d->blocks[d->count++] = p;
            added += classes[i];
        }
    }
    m->drain_probe = 0;
    if (d->saved_gc_threshold != (size_t)-1 && d->saved_gc_threshold <= SIZE_MAX - added)
        JS_SetGCThreshold(rt, d->saved_gc_threshold + added);
}
static void concat_undrain_arenas(JSRuntime *rt, ConcatArenaDrain *d)
{
    if (!d->active)
        return;
    while (d->count > 0)
        js_free_rt(rt, d->blocks[--d->count]);
    free(d->blocks);
    d->blocks = NULL;
    d->cap = 0;
    JS_SetGCThreshold(rt, d->saved_gc_threshold);
    d->active = 0;
}
static JSValue arm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    assert(armed);
    concat_drain_arenas(JS_GetRuntime(ctx), armed, &armed_drain);
    armed->fail_at = offset ? armed->attempts + offset : 0;
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *source)
{
    return JS_Eval(ctx, source, strlen(source), "string-concat-host.js", JS_EVAL_TYPE_GLOBAL);
}
static JSValue disarm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)self;
    (void)argc;
    (void)argv;
    assert(armed);
    armed->fail_at = 0;
    concat_undrain_arenas(JS_GetRuntime(ctx), &armed_drain);
    return JS_UNDEFINED;
}
static void local_failures(void)
{
    unsigned failed = 0, succeeded = 0;
    size_t normal_allocations = 0;
    JSMallocFunctions allocator = {allocate_zero, allocate, release, resize, usable};
    for (size_t n = 0; n <= 32; ++n) {
        Memory memory = {0};
        JSRuntime *rt = JS_NewRuntime2(&allocator, &memory);
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        JSValue global = JS_GetGlobalObject(ctx);
        assert(JS_SetPropertyStr(ctx, global, "arm", JS_NewCFunction(ctx, arm, "arm", 0)) > 0);
        assert(JS_SetPropertyStr(ctx, global, "disarm", JS_NewCFunction(ctx, disarm, "disarm", 0)) >
               0);
        JSValue setup = evaluate(
            ctx,
            "var localBase='x'.repeat(600),localPart=String.fromCharCode(937),inspect;"
            "function runLocal(){let s=localBase+'b';inspect=()=>s;arm();s=s+localPart;disarm();return s.length}");
        assert(!JS_IsException(setup));
        JS_FreeValue(ctx, setup);
        JSValue function = JS_GetPropertyStr(ctx, global, "runLocal");
        JS_FreeValue(ctx, global);
        armed = &memory;
        offset = n;
        size_t before = memory.attempts;
        JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 0, NULL);
        memory.fail_at = 0;
        armed = NULL;
        concat_undrain_arenas(rt, &armed_drain);
        if (!n)
            normal_allocations = memory.attempts - before;
        bool error = JS_IsException(result);
        if (error) {
            assert(memory.failed == 1);
            JSValue exception = JS_GetException(ctx);
            JS_FreeValue(ctx, exception);
            ++failed;
        } else
            ++succeeded;
        JS_FreeValue(ctx, result);
        JS_FreeValue(ctx, function);
        JSValue value = evaluate(ctx, "inspect()");
        assert(!JS_IsException(value));
        size_t length = 0;
        const char *text = JS_ToCStringLen(ctx, &length, value);
        assert(text);
        assert((length == 601 || length == 603) && text[0] == 'x' && text[599] == 'x' &&
               text[600] == 'b');
        if (!error)
            assert(length == 603);
        /* The first failed concat allocation must leave the captured local
           unchanged. Its closure holds the binding, not a second string value. */
        if (n == 1)
            assert(error && length == 601);
        JS_FreeCString(ctx, text);
        JS_FreeValue(ctx, value);
        JS_RunGC(rt);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        assert(memory.live == 0 && memory.bytes == 0);
    }
    assert(failed && succeeded);
    printf("local concat allocation failures=%u successes=%u whole-call-allocations=%zu\n", failed,
           succeeded, normal_allocations);
}
static void roundtrip(void)
{
    JSRuntime *rt = JS_NewRuntime();
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue original =
        evaluate(ctx, "(()=>{let a='x'.repeat(513),b=String.fromCharCode(937).repeat(513);"
                      "return [a+'y',b+'z',a+a+String.fromCharCode(0)+b]})()");
    assert(!JS_IsException(original));
    size_t size = 0;
    uint8_t *data = JS_WriteObject(ctx, &size, original, 0);
    assert(data && size);
    JSValue restored = JS_ReadObject(ctx, data, size, 0);
    assert(!JS_IsException(restored));
    js_free(ctx, data);
    JS_RunGC(rt);
    for (uint32_t i = 0; i < 3; ++i) {
        JSValue a = JS_GetPropertyUint32(ctx, original, i);
        JSValue b = JS_GetPropertyUint32(ctx, restored, i);
        assert(JS_IsStrictEqual(ctx, a, b) && JS_IsEqual(ctx, a, b) == 1);
        JS_FreeValue(ctx, a);
        JS_FreeValue(ctx, b);
    }
    JS_FreeValue(ctx, restored);
    JS_FreeValue(ctx, original);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
}
static void failures(void)
{
    JSMallocFunctions allocator = {allocate_zero, allocate, release, resize, usable};
    unsigned failed = 0, succeeded = 0;
    for (size_t n = 0; n <= 96; ++n) {
        Memory memory = {0};
        JSRuntime *rt = JS_NewRuntime2(&allocator, &memory);
        assert(rt);
        JSContext *ctx = JS_NewContext(rt);
        assert(ctx);
        JSValue global = JS_GetGlobalObject(ctx);
        assert(JS_SetPropertyStr(ctx, global, "arm", JS_NewCFunction(ctx, arm, "arm", 0)) > 0);
        JSValue setup =
            evaluate(ctx, "var a='x'.repeat(512),b=String.fromCharCode(937);"
                          "function run(){let s=a;arm();for(let i=0;i<6;++i)s+=b;return s}");
        assert(!JS_IsException(setup));
        JS_FreeValue(ctx, setup);
        JSValue function = JS_GetPropertyStr(ctx, global, "run");
        JS_FreeValue(ctx, global);
        armed = &memory;
        offset = n;
        JSValue result = JS_Call(ctx, function, JS_UNDEFINED, 0, NULL);
        memory.fail_at = 0;
        armed = NULL;
        concat_undrain_arenas(rt, &armed_drain);
        if (JS_IsException(result)) {
            assert(memory.failed == 1);
            JSValue error = JS_GetException(ctx);
            JS_FreeValue(ctx, error);
            ++failed;
        } else {
            const char *text = JS_ToCString(ctx, result);
            assert(text);
            assert(strlen(text) == 524 && text[0] == 'x' && text[511] == 'x');
            JS_FreeCString(ctx, text);
            ++succeeded;
        }
        JS_FreeValue(ctx, result);
        JS_FreeValue(ctx, function);
        JSValue intact = evaluate(ctx, "a==='x'.repeat(512)&&b===String.fromCharCode(937)");
        assert(!JS_IsException(intact) && JS_ToBool(ctx, intact) == 1);
        JS_FreeValue(ctx, intact);
        JS_RunGC(rt);
        JS_FreeContext(ctx);
        JS_FreeRuntime(rt);
        assert(memory.live == 0 && memory.bytes == 0);
    }
    assert(failed && succeeded);
    printf("bounded concat allocation failures=%u successes=%u\n", failed, succeeded);
}
int main(void)
{
    roundtrip();
    failures();
    local_failures();
    puts("string concat public roundtrip, roots and bounded OOM ownership passed");
    return 0;
}
