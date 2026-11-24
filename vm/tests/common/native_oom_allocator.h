/* Shared exact-allocation fault and leak ledger for public API fixtures. MIT. */
#ifndef QJS_TEST_OOM_ALLOCATOR_H
#define QJS_TEST_OOM_ALLOCATOR_H
typedef struct {
    size_t bytes, reserved;
} Header;
typedef struct {
    size_t live, bytes, peak, sequence, fail_at;
    size_t reallocs, requested, max_request;
    int observe, drain_probe;
    unsigned rejected;
} Allocator;
static int reject(Allocator *a)
{
    if (++a->sequence != a->fail_at)
        return 0;
    ++a->rejected;
    return 1;
}
static void *allocate(void *opaque, size_t n)
{
    Allocator *a = opaque;
    Header *h;
    if (a->drain_probe)
        return NULL;
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

typedef struct {
    void **blocks;
    size_t count, cap, saved_gc_threshold;
} AllocatorArenaDrain;
static inline void oom_drain_arenas(JSRuntime *rt, Allocator *a, AllocatorArenaDrain *d)
{
    static const uint16_t classes[31] = {16,  24,  32,  40,  48,  56,  64,  72,  80,  88,  96,
                                         104, 112, 120, 128, 144, 160, 176, 192, 208, 224, 240,
                                         256, 288, 320, 352, 384, 416, 448, 480, 512};
    size_t added = 0;
    d->blocks = NULL;
    d->count = 0;
    d->cap = 0;
    d->saved_gc_threshold = JS_GetGCThreshold(rt);
    a->drain_probe = 1;
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
    a->drain_probe = 0;
    if (d->saved_gc_threshold != (size_t)-1 && d->saved_gc_threshold <= SIZE_MAX - added)
        JS_SetGCThreshold(rt, d->saved_gc_threshold + added);
}
static inline void oom_undrain_arenas(JSRuntime *rt, AllocatorArenaDrain *d)
{
    while (d->count > 0)
        js_free_rt(rt, d->blocks[--d->count]);
    free(d->blocks);
    d->blocks = NULL;
    d->cap = 0;
    JS_SetGCThreshold(rt, d->saved_gc_threshold);
}

#endif
