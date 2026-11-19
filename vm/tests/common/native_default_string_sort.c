#include "quickjs.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define N 512
#define SCRATCH_SIZE (8 * N + 12 * (N / 32 + 1))
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
typedef struct Alloc {
    size_t bytes, peak, blocks, attempts, scratch_attempts, fail_after;
    unsigned arm, fired, callbacks;
    JSRuntime *rt;
    JSContext *other;
    JSValue nested;
} Alloc;
static unsigned checks;
static Alloc state;
static const char *prefix = "";
static unsigned embedded_nul;
static const uint64_t magic = UINT64_C(0x534f52544f574e52);

static void scratch_callback(Alloc *s)
{
    unsigned action = s->arm;
    s->arm = 0;
    s->fired++;
    if (action == 2) {
        JSValue v;
        s->callbacks++;
        JS_RunGC(s->rt);
        v = JS_Call(s->other, s->nested, JS_UNDEFINED, 0, NULL);
        CHECK(!JS_IsException(v));
        JS_FreeValue(s->other, v);
    }
}
static void *allocate(void *opaque, size_t size)
{
    Alloc *s = opaque;
    Block *b;
    s->attempts++;
    if (s->fail_after && --s->fail_after == 0)
        return NULL;
    if (size == SCRATCH_SIZE) {
        s->scratch_attempts++;
        if (s->arm) {
            unsigned action = s->arm;
            scratch_callback(s);
            if (action == 1)
                return NULL;
        }
    }
    if (size > SIZE_MAX - sizeof(*b))
        return NULL;
    b = malloc(sizeof(*b) + size);
    if (!b)
        return NULL;
    b->size = size;
    b->magic = magic;
    s->bytes += size;
    s->blocks++;
    if (s->bytes > s->peak)
        s->peak = s->bytes;
    return b + 1;
}
static void deallocate(void *opaque, void *ptr)
{
    Alloc *s = opaque;
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
    void *out;
    size_t old;
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
static JSValue evaluate(JSContext *ctx, const char *source)
{
    JSValue v = JS_Eval(ctx, source, strlen(source), "sort-host", JS_EVAL_TYPE_GLOBAL);
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(ctx);
        const char *s = JS_ToCString(ctx, e);
        fprintf(stderr, "eval: %s\n", s ? s : "?");
        JS_FreeCString(ctx, s);
        JS_FreeValue(ctx, e);
    }
    CHECK(!JS_IsException(v));
    return v;
}
static void trial(JSContext *ctx, JSContext *callctx, JSValueConst sort, unsigned action,
                  unsigned sparse, unsigned lowstack, unsigned oom)
{
    JSValue arr = JS_NewArray(ctx), v;
    void *identities[N];
    char keys[N][128];
    unsigned indices[N], lengths[N], i, j, t;
    size_t before, first_scratch = state.scratch_attempts;
    unsigned first_fired = state.fired, success = 0;
    CHECK(!JS_IsException(arr));
    for (i = 0; i < N; i++) {
        lengths[i] = (unsigned)snprintf(keys[i], sizeof(keys[i]), "%skey-%03u-equal-content",
                                        prefix, (N - i) % 17);
        CHECK(lengths[i] < sizeof(keys[i]));
        if (embedded_nul)
            keys[i][12] = 0;
        v = JS_NewStringLen(ctx, keys[i], lengths[i]);
        CHECK(!JS_IsException(v));
        identities[i] = JS_VALUE_GET_PTR(v);
        indices[i] = i;
        if (i >= 17)
            CHECK(identities[i] != identities[i - 17]);
        CHECK(JS_SetPropertyUint32(ctx, arr, i * (sparse ? 2 : 1), v) > 0);
    }
    for (i = 1; i < N; i++) {
        t = indices[i];
        j = i;
        while (j && memcmp(keys[indices[j - 1]], keys[t], lengths[t]) > 0) {
            indices[j] = indices[j - 1];
            j--;
        }
        indices[j] = t;
    }
    state.arm = action;
    state.fail_after = oom;
    before = state.bytes;
    state.peak = before;
    if (lowstack) {
        JS_UpdateStackTop(state.rt);
        JS_SetMaxStackSize(state.rt, lowstack);
    }
    v = JS_Call(callctx, sort, arr, 0, NULL);
    state.arm = 0;
    state.fail_after = 0;
    if (lowstack) {
        JS_SetMaxStackSize(state.rt, 2 * 1024 * 1024);
        JS_UpdateStackTop(state.rt);
    }
    if (JS_IsException(v)) {
        JSValue e = JS_GetException(callctx);
        CHECK(oom || lowstack);
        JS_FreeValue(callctx, e);
    } else {
        success = 1;
        CHECK(JS_IsSameValue(callctx, v, arr));
        for (i = 0; i < N; i++) {
            JSValue s = JS_GetPropertyUint32(ctx, arr, i);
            CHECK(JS_VALUE_GET_TAG(s) == JS_TAG_STRING &&
                  JS_VALUE_GET_PTR(s) == identities[indices[i]]);
            JS_FreeValue(ctx, s);
        }
    }
    JS_FreeValue(callctx, v);
    JS_FreeValue(ctx, arr);
    JS_RunGC(state.rt);
    printf(
        "TRIAL action=%u sparse=%u stack=%u oom=%u scratch=%zu fired=%u extra_peak=%zu success=%u\n",
        action, sparse, lowstack, oom, state.scratch_attempts - first_scratch,
        state.fired - first_fired, state.peak - before, success);
}
int main(void)
{
    JSMallocFunctions mf = {zero_allocate, allocate, deallocate, resize, usable};
    JSRuntime *rt = JS_NewRuntime2(&mf, &state);
    JSContext *a, *b;
    JSValue sort;
    unsigned i;
    CHECK(rt);
    state.rt = rt;
    JS_SetMaxStackSize(rt, 2 * 1024 * 1024);
    a = JS_NewContext(rt);
    b = JS_NewContext(rt);
    CHECK(a && b);
    state.other = b;
    state.nested = evaluate(
        b,
        "(function(){let a=Array.from({length:96},(_,i)=>String(95-i));a.sort();if(a[0]!=='0')throw Error('nested');return a.length;})");
    sort = evaluate(a, "Array.prototype.sort");
    trial(a, b, sort, 0, 0, 0, 0);
    trial(a, b, sort, 0, 1, 0, 0);
    prefix = "same-common-prefix-for-more-than-thirty-two-code-units-";
    trial(a, b, sort, 0, 0, 0, 0);
    embedded_nul = 1;
    trial(a, b, sort, 0, 0, 0, 0);
    embedded_nul = 0;
    prefix = "";
    trial(a, b, sort, 1, 0, 0, 0);
    trial(a, b, sort, 2, 0, 0, 0);
    for (i = 1024; i <= 65536; i *= 2)
        trial(a, b, sort, 0, 0, i, 0);
    for (i = 1; i <= 20; i++)
        trial(a, b, sort, 0, 0, 0, i);
    JS_FreeValue(a, sort);
    JS_FreeValue(b, state.nested);
    JS_FreeContext(b);
    JS_FreeContext(a);
    JS_RunGC(rt);
    JS_FreeRuntime(rt);
    CHECK(state.bytes == 0 && state.blocks == 0);
    printf("SORT_HOST_PASS checks=%u callbacks=%u scratch=%zu peak=%zu\n", checks, state.callbacks,
           state.scratch_attempts, state.peak);
    return 0;
}
