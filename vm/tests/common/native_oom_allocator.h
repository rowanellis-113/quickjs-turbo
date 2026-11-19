/* Shared exact-allocation fault and leak ledger for public API fixtures. MIT. */
#ifndef QJS_TEST_OOM_ALLOCATOR_H
#define QJS_TEST_OOM_ALLOCATOR_H
typedef struct {
    size_t bytes, reserved;
} Header;
typedef struct {
    size_t live, bytes, peak, sequence, fail_at;
    size_t reallocs, requested, max_request;
    int observe;
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

#endif
