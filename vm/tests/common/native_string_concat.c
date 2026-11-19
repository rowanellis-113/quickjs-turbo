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
#ifdef FRAME_TEST_STRING_POOL
#include "allocator-pool.h"
#endif

typedef union Header {
    size_t size;
    long double alignment;
    unsigned char pad[16];
} Header;
typedef struct Memory {
    size_t attempts, fail_at, live, bytes;
    unsigned failed;
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
static JSValue arm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    assert(armed);
    armed->fail_at = offset ? armed->attempts + offset : 0;
    return JS_UNDEFINED;
}
static JSValue evaluate(JSContext *ctx, const char *source)
{
    return JS_Eval(ctx, source, strlen(source), "string-concat-host.js", JS_EVAL_TYPE_GLOBAL);
}
static JSValue disarm(JSContext *ctx, JSValueConst self, int argc, JSValueConst *argv)
{
    (void)ctx;
    (void)self;
    (void)argc;
    (void)argv;
    assert(armed);
    armed->fail_at = 0;
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
#ifdef FRAME_TEST_STRING_POOL
static size_t pool_free_calls;
static void pool_count_free(void *opaque, void *ptr)
{
    ++pool_free_calls;
    FramePoolFunctions.js_free(opaque, ptr);
}
static void pool_capacity(bool wide, bool wrapped)
{
    FramePool *pool = FramePoolCreate(256, FRAME_POOL_TRACK);
    assert(pool);
    JSMallocFunctions functions = FramePoolFunctions;
    if (wrapped)
        functions.js_free = pool_count_free;
    JSRuntime *rt = JS_NewRuntime2(&functions, pool);
    assert(rt);
    JSContext *ctx = JS_NewContext(rt);
    assert(ctx);
    JSValue global = JS_GetGlobalObject(ctx);
    assert(JS_SetPropertyStr(ctx, global, "poolWide", JS_NewBool(ctx, wide)) > 0);
    JSValue value = evaluate(
        ctx,
        "var poolSeed='x'.repeat(600);"
        "function poolLoop(){var s=poolSeed+String.fromCharCode(poolWide?1000:97);for(var i=0;i<200;++i)s=s+String.fromCharCode((poolWide?1001:97)+i%26);return s.length}"
        "function poolDriver(){return poolLoop()+0}");
    assert(!JS_IsException(value));
    JS_FreeValue(ctx, value);
    JSValue function = JS_GetPropertyStr(ctx, global, "poolDriver");
    JS_FreeValue(ctx, global);
    for (unsigned warm = 0; warm < 3; ++warm) {
        value = JS_Call(ctx, function, JS_UNDEFINED, 0, NULL);
        assert(!JS_IsException(value));
        JS_FreeValue(ctx, value);
    }
    FramePoolStats before, after;
    FramePoolGetStats(pool, &before);
    value = JS_Call(ctx, function, JS_UNDEFINED, 0, NULL);
    assert(!JS_IsException(value));
    int32_t length = 0;
    assert(JS_ToInt32(ctx, &length, value) == 0 && length == 801);
    FramePoolGetStats(pool, &after);
    size_t allocations = after.allocations - before.allocations;
    bool enabled = false;
#ifdef FRAME_TEST_STRING_POOL_NATIVE
    enabled = !getenv("QJS_DISABLE_LOCAL_ROPE_APPEND") && !getenv("QJS_DISABLE_LOCAL_ROPE_SPARE") &&
              !getenv("QJS_DISABLE_CONCAT_ROPE") && !getenv("QJS_DISABLE_INTERP_FRAME") &&
              !getenv("QJS_DISABLE_INTERNAL_INTERP") && !getenv("QJS_DISABLE_REGISTER_INTERP");
#endif
    if (enabled && (!wide || !wrapped))
        assert(allocations < (wide ? 300 : 80));
    else
        assert(allocations >= (wide ? 400 : 200));
    printf("pool capacity allocations=%zu enabled=%d wide=%d wrapped-free=%d\n", allocations,
           enabled, wide, wrapped);
    JS_FreeValue(ctx, value);
    JS_FreeValue(ctx, function);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    FramePoolGetStats(pool, &after);
    assert(after.live_blocks == 0);
    assert(FramePoolDestroy(pool) == 0);
}
#endif
int main(void)
{
    roundtrip();
    failures();
    local_failures();
#ifdef FRAME_TEST_STRING_POOL
    pool_capacity(false, false);
    pool_capacity(true, false);
    pool_capacity(false, true);
    pool_capacity(true, true);
    assert(pool_free_calls > 0);
#endif
    puts("string concat public roundtrip, roots and bounded OOM ownership passed");
    return 0;
}
