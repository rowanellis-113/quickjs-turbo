#include "quickjs.h"
#include "quickjs-libc.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef NDEBUG
#error File-loader verification requires assertions
#endif

typedef struct {
    size_t bytes, reserved;
} Header;
typedef struct {
    size_t live, bytes, peak, sequence, fail_at;
    size_t reallocs, requested, max_request;
    int observe;
} Allocator;
static int reject(Allocator *a)
{
    return ++a->sequence == a->fail_at;
}
static void *allocate(void *opaque, size_t n)
{
    Allocator *a = opaque;
    Header *h;
    if (n > SIZE_MAX - sizeof(*h) || reject(a))
        return NULL;
    h = malloc(sizeof(*h) + n);
    if (!h)
        return NULL;
    h->bytes = n;
    ++a->live;
    a->bytes += n;
    if (a->bytes > a->peak)
        a->peak = a->bytes;
    return h + 1;
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
static void release(void *opaque, void *ptr)
{
    Allocator *a = opaque;
    Header *h;
    if (!ptr)
        return;
    h = (Header *)ptr - 1;
    assert(a->live && a->bytes >= h->bytes);
    --a->live;
    a->bytes -= h->bytes;
    free(h);
}
static void *resize(void *opaque, void *ptr, size_t n)
{
    Allocator *a = opaque;
    Header *h, *p;
    size_t old;
    if (a->observe) {
        ++a->reallocs;
        a->requested += n;
        if (n > a->max_request)
            a->max_request = n;
    }
    if (!ptr)
        return allocate(opaque, n);
    if (!n) {
        release(opaque, ptr);
        return NULL;
    }
    if (n > SIZE_MAX - sizeof(*h) || reject(a))
        return NULL;
    h = (Header *)ptr - 1;
    old = h->bytes;
    p = realloc(h, sizeof(*h) + n);
    if (!p)
        return NULL;
    p->bytes = n;
    a->bytes = a->bytes - old + n;
    if (a->bytes > a->peak)
        a->peak = a->bytes;
    return p + 1;
}
static size_t usable(const void *ptr)
{
    return ptr ? ((const Header *)ptr - 1)->bytes : 0;
}
static const JSMallocFunctions functions = {allocate_zero, allocate, release, resize, usable};
static size_t checks;
static void verify_bytes(const uint8_t *buf, size_t length, size_t expected)
{
    size_t i;
    assert(buf && length == expected && buf[length] == 0);
    for (i = 0; i < length; i++)
        assert(buf[i] == (uint8_t)(i * 37 + 11));
    ++checks;
}
static void verify_file(JSContext *ctx, const char *folder, size_t n)
{
    char path[2048];
    size_t length = SIZE_MAX;
    uint8_t *buf;
    assert(snprintf(path, sizeof(path), "%s/%zu.bin", folder, n) > 0);
    buf = js_load_file(ctx, &length, path);
    verify_bytes(buf, length, n);
    if (ctx)
        js_free(ctx, buf);
    else
        free(buf);
}
static void close_context(JSRuntime *rt, JSContext *ctx, Allocator *a)
{
    JS_FreeContext(ctx);
    JS_FreeRuntime(rt);
    assert(a->live == 0 && a->bytes == 0);
    ++checks;
}
int main(int argc, char **argv)
{
    const size_t sizes[] = {0, 1, 8191, 8192, 8193, 16383, 16384, 16385, 65537, 1048577};
    Allocator a = {0};
    JSRuntime *rt;
    JSContext *ctx;
    uint8_t *buf;
    char path[2048];
    size_t i, n, sequence, length, oom_points, reallocs, requested, max_request;
    if (argc == 3 && (!strcmp(argv[1], "--stream") || !strcmp(argv[1], "--stream-ctx"))) {
        const int with_context = !strcmp(argv[1], "--stream-ctx");
        rt = NULL;
        ctx = NULL;
        if (with_context) {
            rt = JS_NewRuntime2(&functions, &a);
            assert(rt);
            ctx = JS_NewContext(rt);
            assert(ctx);
        }
        length = SIZE_MAX;
        buf = js_load_file(ctx, &length, argv[2]);
        verify_bytes(buf, length, 16385);
        if (ctx) {
            js_free(ctx, buf);
            close_context(rt, ctx, &a);
        } else
            free(buf);
        puts("FILE_LOAD_STREAM passed");
        return 0;
    }
    assert(argc == 2);
    /* Each CTest mode owns a build-local fixture directory. */
    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++) {
        FILE *f;
        uint8_t bytes[8192];
        size_t j, offset = 0, chunk;
        assert(snprintf(path, sizeof(path), "%s/%zu.bin", argv[1], sizes[i]) > 0);
        f = fopen(path, "wb");
        assert(f);
        while (offset < sizes[i]) {
            chunk = sizes[i] - offset;
            if (chunk > sizeof(bytes))
                chunk = sizeof(bytes);
            for (j = 0; j < chunk; j++)
                bytes[j] = (uint8_t)((offset + j) * 37 + 11);
            assert(fwrite(bytes, 1, chunk, f) == chunk);
            offset += chunk;
        }
        assert(fclose(f) == 0);
    }
    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++)
        verify_file(NULL, argv[1], sizes[i]);
    rt = JS_NewRuntime2(&functions, &a);
    assert(rt);
    ctx = JS_NewContext(rt);
    assert(ctx);
    for (i = 0; i < sizeof(sizes) / sizeof(sizes[0]); i++)
        verify_file(ctx, argv[1], sizes[i]);
    a.observe = 1;
    a.reallocs = a.requested = a.max_request = 0;
    verify_file(ctx, argv[1], 1048577);
    a.observe = 0;
    reallocs = a.reallocs;
    requested = a.requested;
    max_request = a.max_request;
    sequence = a.sequence;
    verify_file(ctx, argv[1], 65537);
    oom_points = a.sequence - sequence;
    assert(oom_points > 0 && oom_points < 64);
    close_context(rt, ctx, &a);
    for (n = 1; n <= oom_points; n++) {
        Allocator trial = {0};
        rt = JS_NewRuntime2(&functions, &trial);
        assert(rt);
        ctx = JS_NewContext(rt);
        assert(ctx);
        trial.fail_at = trial.sequence + n;
        assert(snprintf(path, sizeof(path), "%s/65537.bin", argv[1]) > 0);
        length = SIZE_MAX;
        buf = js_load_file(ctx, &length, path);
        assert(!buf && length == SIZE_MAX);
        JS_FreeValue(ctx, JS_GetException(ctx));
        trial.fail_at = 0;
        verify_file(ctx, argv[1], 8193);
        close_context(rt, ctx, &trial);
    }
    printf(
        "FILE_LOAD_NATIVE checks=%zu oom_points=%zu reallocs=%zu requested=%zu max_request=%zu\n",
        checks, oom_points, reallocs, requested, max_request);
    return 0;
}
