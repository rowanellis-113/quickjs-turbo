#include "quickjs.h"
#include "interpreter-private-abi-values.h"
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#if QJS_ABI_HAS_PREFIX_RC
int main(void)
{
    puts("inline-header allocation qualification does not apply to the arena allocator");
    return 77;
}
#else

extern JSValue JS_FrameNewNullObject(JSContext *, JSValueConst, JSClassID);

#define CHECK(condition)                                                                           \
    do {                                                                                           \
        if (!(condition)) {                                                                        \
            fprintf(stderr, "FAILED: %s at %d\n", #condition, __LINE__);                           \
            exit(1);                                                                               \
        }                                                                                          \
    } while (0)

typedef union Block {
    struct {
        size_t size;
    } info;
    long double alignment;
    void *padding[2];
} Block;
_Static_assert(sizeof(Block) == 16, "allocator preserves the engine's Win64 payload alignment");
typedef struct Allocator {
    JSRuntime *rt;
    JSContext *ctx;
    size_t calls, fail_at, live;
    int hook_at, in_hook, hooks;
} Allocator;

static void hook(Allocator *a)
{
    if (a->hook_at && !a->in_hook && a->ctx && --a->hook_at == 0) {
        a->in_hook = 1;
        JS_RunGC(a->rt);
        JSValue value = JS_NewObjectProto(a->ctx, JS_NULL);
        CHECK(!JS_IsException(value));
        JS_FreeValue(a->ctx, value);
        JS_RunGC(a->rt);
        a->hooks++;
        a->in_hook = 0;
    }
}

static void *allocate(void *opaque, size_t size)
{
    Allocator *a = opaque;
    if (a->fail_at && ++a->calls == a->fail_at)
        return NULL;
    hook(a);
    if (size > SIZE_MAX - sizeof(Block))
        return NULL;
    Block *block = malloc(sizeof(Block) + size);
    if (!block)
        return NULL;
    block->info.size = size;
    a->live++;
    return block + 1;
}

static void *allocate_zero(void *opaque, size_t count, size_t size)
{
    if (size && count > SIZE_MAX / size)
        return NULL;
    void *pointer = allocate(opaque, count * size);
    if (pointer)
        memset(pointer, 0, count * size);
    return pointer;
}

static void release(void *opaque, void *pointer)
{
    if (!pointer)
        return;
    Allocator *a = opaque;
    Block *block = (Block *)pointer - 1;
    a->live--;
    free(block);
}

static void *resize(void *opaque, void *pointer, size_t size)
{
    if (!pointer)
        return allocate(opaque, size);
    if (!size) {
        release(opaque, pointer);
        return NULL;
    }
    Allocator *a = opaque;
    if (a->fail_at && ++a->calls == a->fail_at)
        return NULL;
    hook(a);
    Block *block = (Block *)pointer - 1;
    if (size > SIZE_MAX - sizeof(Block))
        return NULL;
    block = realloc(block, sizeof(Block) + size);
    if (!block)
        return NULL;
    block->info.size = size;
    return block + 1;
}

static size_t usable(const void *pointer)
{
    return pointer ? ((const Block *)pointer - 1)->info.size : 0;
}

static int32_t shape_references(JSValueConst seed)
{
    void *shape;
    int32_t refs;
    memcpy(&shape, (const unsigned char *)JS_VALUE_GET_PTR(seed) + QJS_ABI_OFF_JSObject_shape,
           sizeof(shape));
    memcpy(&refs, (const unsigned char *)shape + QJS_ABI_REF_COUNT_OFFSET, sizeof(refs));
    return refs;
}

static void check_object(JSContext *ctx, JSValue value)
{
    CHECK(!JS_IsException(value) && JS_IsObject(value));
    JSValue proto = JS_GetPrototype(ctx, value);
    CHECK(JS_IsNull(proto));
    JS_FreeValue(ctx, proto);
    CHECK(JS_SetPropertyStr(ctx, value, "answer", JS_NewInt32(ctx, 42)) >= 0);
    JSValue answer = JS_GetPropertyStr(ctx, value, "answer");
    int32_t n = 0;
    CHECK(JS_ToInt32(ctx, &n, answer) == 0 && n == 42);
    JS_FreeValue(ctx, answer);
    JS_FreeValue(ctx, value);
}

static void benchmark(void)
{
    JSRuntime *rt = JS_NewRuntime();
    CHECK(rt);
    JSContext *ctx = JS_NewContext(rt);
    CHECK(ctx);
    JSValue seed = JS_NewObjectProto(ctx, JS_NULL);
    CHECK(!JS_IsException(seed));
    unsigned char *mode = (unsigned char *)rt + QJS_ABI_OFF_JSRuntime_module_loader_has_attr + 6;
    const int disabled[] = {1, 0, 0, 1, 0, 1, 1, 0};
    const unsigned iterations = 1000000;
    for (unsigned r = 0; r < 2; r++) {
        *mode = (unsigned char)r;
        for (unsigned i = 0; i < iterations; i++) {
            JSValue value = JS_FrameNewNullObject(ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT);
            CHECK(!JS_IsException(value));
            JS_FreeValue(ctx, value);
        }
    }
    for (unsigned r = 0; r < sizeof(disabled) / sizeof(disabled[0]); r++) {
        *mode = (unsigned char)disabled[r];
        clock_t start = clock();
        for (unsigned i = 0; i < iterations; i++) {
            JSValue value = JS_FrameNewNullObject(ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT);
            CHECK(!JS_IsException(value));
            JS_FreeValue(ctx, value);
        }
        double ns = (double)(clock() - start) * 1e9 / (CLOCKS_PER_SEC * (double)iterations);
        printf("null_alloc_sample disabled=%d ns_per_op=%.3f\n", disabled[r], ns);
    }
    JS_FreeValue(ctx, seed);
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
}

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--bench")) {
        benchmark();
        return 0;
    }
    static const JSMallocFunctions functions = {allocate_zero, allocate, release, resize, usable};
    Allocator a = {0};
    a.rt = JS_NewRuntime2(&functions, &a);
    CHECK(a.rt);
    a.ctx = JS_NewContext(a.rt);
    CHECK(a.ctx);
    JSValue seed = JS_NewObjectProto(a.ctx, JS_NULL);
    CHECK(!JS_IsException(seed));
    unsigned char *mode = (unsigned char *)a.rt + QJS_ABI_OFF_JSRuntime_module_loader_has_attr + 6;
    CHECK(*mode == 0);

    for (int disabled = 0; disabled < 2; disabled++) {
        *mode = (unsigned char)disabled;
        for (int i = 0; i < 100; i++)
            check_object(a.ctx,
                         JS_FrameNewNullObject(a.ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT));
        for (size_t fail = 1; fail <= 2; fail++) {
            int32_t before = shape_references(seed);
            a.calls = 0;
            a.fail_at = fail;
            JSValue value = JS_FrameNewNullObject(a.ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT);
            a.fail_at = 0;
            CHECK(JS_IsException(value));
            JSValue exception = JS_GetException(a.ctx);
            JS_FreeValue(a.ctx, exception);
            JS_FreeValue(a.ctx, value);
            JS_RunGC(a.rt);
            CHECK(shape_references(seed) == before);
        }
        {
            int32_t before = shape_references(seed);
            JS_SetMemoryLimit(a.rt, 1);
            JSValue value = JS_FrameNewNullObject(a.ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT);
            JS_SetMemoryLimit(a.rt, SIZE_MAX);
            CHECK(JS_IsException(value));
            JSValue exception = JS_GetException(a.ctx);
            JS_FreeValue(a.ctx, exception);
            JS_FreeValue(a.ctx, value);
            CHECK(shape_references(seed) == before);
        }
        for (int at = 1; at <= 2; at++) {
            int before = a.hooks;
            a.hook_at = at;
            check_object(a.ctx,
                         JS_FrameNewNullObject(a.ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT));
            CHECK(a.hooks == before + 1);
        }
        JS_SetGCThreshold(a.rt, 0);
        check_object(a.ctx, JS_FrameNewNullObject(a.ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_OBJECT));
    }
    *mode = 0;
    JSValue ordinary = JS_NewObject(a.ctx);
    JSValue derived = JS_FrameNewNullObject(a.ctx, ordinary, QJS_ABI_CONST_JS_CLASS_OBJECT);
    CHECK(!JS_IsException(derived));
    JSValue proto = JS_GetPrototype(a.ctx, derived);
    CHECK(JS_VALUE_GET_PTR(proto) == JS_VALUE_GET_PTR(ordinary));
    JS_FreeValue(a.ctx, proto);
    JS_FreeValue(a.ctx, derived);
    JS_FreeValue(a.ctx, ordinary);
    JSValue array = JS_FrameNewNullObject(a.ctx, JS_NULL, QJS_ABI_CONST_JS_CLASS_ARRAY);
    CHECK(!JS_IsException(array) && JS_IsArray(array));
    JS_FreeValue(a.ctx, array);
    JS_FreeValue(a.ctx, seed);
    JS_FreeContext(a.ctx);
    a.ctx = NULL;
    JS_FreeRuntime(a.rt);
    a.rt = NULL;
    CHECK(a.live == 0);
    puts(
        "null allocation: warm/fallback, both OOM points, shape ownership, GC, allocator reentry, prototype/class fallback and zero leaks passed");
    return 0;
}
#endif
