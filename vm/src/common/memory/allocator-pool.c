/*
 * Independent 0.15.1 allocator experiment: 16-byte metadata, optional small
 * slabs, and original JSRuntime ownership/GC/accounting. No global freelist.
 * The original default/custom allocators are untouched. Header-only mode
 * separates usable-size-query savings from slab allocation savings.
 */
#include "allocator-pool.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define POOL_PAGE_BYTES 65536u
#define POOL_MAX_SMALL 512u
#define POOL_CLASSES (POOL_MAX_SMALL / 16u)
typedef struct FramePoolPage FramePoolPage;
typedef struct FramePoolHeader {
    FramePoolPage *page;
    size_t capacity;
} FramePoolHeader;
_Static_assert(sizeof(FramePoolHeader) == 16, "experiment targets 64-bit allocators");
_Static_assert(sizeof(size_t) == 8 && offsetof(FramePoolHeader, capacity) == 8,
               "native append reads capacity eight bytes before a proven pool block");
typedef struct FramePoolClass {
    FramePoolPage *available, *empty;
} FramePoolClass;
struct FramePoolPage {
    FramePool *owner;
    FramePoolPage *all_next, *all_prev, *available_next, *available_prev;
    void *free_head;
    unsigned live, slots, index;
};
struct FramePool {
    FramePoolClass classes[POOL_CLASSES];
    FramePoolPage *pages;
    size_t live_blocks;
    unsigned small_limit, flags, auto_destroy, observe;
    FramePoolStats stats;
};

static void pool_available_remove(FramePool *p, FramePoolPage *page)
{
    FramePoolClass *c = &p->classes[page->index];
    if (page->available_prev)
        page->available_prev->available_next = page->available_next;
    else {
        assert(c->available == page);
        c->available = page->available_next;
    }
    if (page->available_next)
        page->available_next->available_prev = page->available_prev;
    page->available_prev = page->available_next = NULL;
}
static void pool_available_add(FramePool *p, FramePoolPage *page)
{
    FramePoolClass *c = &p->classes[page->index];
    page->available_prev = NULL;
    page->available_next = c->available;
    if (c->available)
        c->available->available_prev = page;
    c->available = page;
}
static void pool_page_release(FramePool *p, FramePoolPage *page)
{
    FramePoolClass *c = &p->classes[page->index];
    assert(page->live == 0);
    pool_available_remove(p, page);
    if (c->empty == page)
        c->empty = NULL;
    if (page->all_prev)
        page->all_prev->all_next = page->all_next;
    else
        p->pages = page->all_next;
    if (page->all_next)
        page->all_next->all_prev = page->all_prev;
    p->stats.pages--;
    p->stats.retained_bytes -= POOL_PAGE_BYTES;
    free(page);
}
static FramePoolPage *pool_page_new(FramePool *p, unsigned index, size_t capacity)
{
    const size_t start = (sizeof(FramePoolPage) + 15u) & ~(size_t)15u;
    const size_t stride = sizeof(FramePoolHeader) + capacity;
    FramePoolPage *page = malloc(POOL_PAGE_BYTES);
    unsigned i;
    if (!page)
        return NULL;
    memset(page, 0, sizeof(*page));
    page->owner = p;
    page->index = index;
    page->slots = (unsigned)((POOL_PAGE_BYTES - start) / stride);
    assert(page->slots != 0 && ((uintptr_t)page & 15u) == 0);
    for (i = page->slots; i != 0; --i) {
        FramePoolHeader *h = (FramePoolHeader *)((unsigned char *)page + start + (i - 1) * stride);
        void *ptr = h + 1;
        h->page = page;
        h->capacity = capacity;
        memcpy(ptr, &page->free_head, sizeof(page->free_head));
        page->free_head = ptr;
    }
    page->all_next = p->pages;
    if (p->pages)
        p->pages->all_prev = page;
    p->pages = page;
    pool_available_add(p, page);
    p->stats.pages++;
    p->stats.backing_allocations++;
    p->stats.retained_bytes += POOL_PAGE_BYTES;
    if (p->stats.retained_bytes > p->stats.peak_retained_bytes)
        p->stats.peak_retained_bytes = p->stats.retained_bytes;
    return page;
}
FramePool *FramePoolCreate(unsigned small_limit, unsigned flags)
{
    FramePool *p;
    if (small_limit > POOL_MAX_SMALL || small_limit % 16u)
        return NULL;
    p = calloc(1, sizeof(*p));
    if (p) {
        p->small_limit = small_limit;
        p->flags = flags;
    }
    return p;
}
void FramePoolGetStats(const FramePool *p, FramePoolStats *stats)
{
    *stats = p->stats;
    stats->live_blocks = p->live_blocks;
}
int FramePoolDestroy(FramePool *p)
{
    FramePoolPage *page, *next;
    if (!p)
        return 0;
    if (p->live_blocks != 0)
        return -1;
    if (p->observe) {
        fprintf(
            stderr,
            "FRAME_POOL {\"limit\":%u,\"live\":%zu,\"allocations\":%zu,\"backing\":%zu,\"peak_live_capacity\":%zu,\"peak_slab_bytes\":%zu}\n",
            p->small_limit, p->live_blocks, p->stats.allocations, p->stats.backing_allocations,
            p->stats.peak_live_capacity, p->stats.peak_retained_bytes);
    }
    for (page = p->pages; page; page = next) {
        next = page->all_next;
        assert(page->live == 0);
        free(page);
    }
    free(p);
    return 0;
}
static void pool_record_alloc(FramePool *p, size_t capacity)
{
    p->live_blocks++;
    if (p->flags & FRAME_POOL_TRACK) {
        p->stats.allocations++;
        p->stats.live_capacity += capacity;
        if (p->stats.live_capacity > p->stats.peak_live_capacity)
            p->stats.peak_live_capacity = p->stats.live_capacity;
    }
}
static void *pool_malloc(void *opaque, size_t size)
{
    FramePool *p = opaque;
    FramePoolHeader *h;
    size_t capacity;
    if (!size || size > SIZE_MAX - 15u)
        return NULL;
    capacity = (size + 15u) & ~(size_t)15u;
    if (capacity <= p->small_limit) {
        unsigned index = (unsigned)(capacity / 16u - 1u);
        FramePoolClass *c = &p->classes[index];
        FramePoolPage *page = c->available;
        void *ptr;
        if (!page && !(page = pool_page_new(p, index, capacity)))
            return NULL;
        assert(page->owner == p && page->free_head && page->live < page->slots);
        if (!page->live)
            c->empty = NULL;
        ptr = page->free_head;
        memcpy(&page->free_head, ptr, sizeof(page->free_head));
        if (++page->live == page->slots)
            pool_available_remove(p, page);
        pool_record_alloc(p, capacity);
        return ptr;
    }
    if (capacity > SIZE_MAX - sizeof(*h))
        return NULL;
    h = malloc(sizeof(*h) + capacity);
    if (!h)
        return NULL;
    h->page = NULL;
    h->capacity = capacity;
    p->stats.backing_allocations++;
    pool_record_alloc(p, capacity);
    return h + 1;
}
static void pool_free(void *opaque, void *ptr)
{
    FramePool *p = opaque;
    FramePoolHeader *h;
    FramePoolPage *page;
    if (!ptr)
        return;
    h = (FramePoolHeader *)ptr - 1;
    page = h->page;
    assert(p->live_blocks != 0);
    if (p->flags & FRAME_POOL_TRACK) {
        assert(p->stats.live_capacity >= h->capacity);
        p->stats.live_capacity -= h->capacity;
    }
    if (page) {
        FramePoolClass *c;
        assert(page->owner == p && page->live != 0);
        c = &p->classes[page->index];
        if (page->live-- == page->slots)
            pool_available_add(p, page);
        memcpy(ptr, &page->free_head, sizeof(page->free_head));
        page->free_head = ptr;
        if (!page->live) {
            if (c->empty) {
                assert(c->empty != page);
                pool_page_release(p, page);
            } else
                c->empty = page;
        }
    } else
        free(h);
    if (--p->live_blocks == 0 && p->auto_destroy) {
        if (FramePoolDestroy(p) != 0)
            abort();
    }
}
static size_t pool_usable(const void *ptr)
{
    return ptr ? ((const FramePoolHeader *)ptr - 1)->capacity : 0;
}
static void *pool_calloc(void *opaque, size_t count, size_t size)
{
    void *ptr;
    if (!count || !size || count > SIZE_MAX / size)
        return NULL;
    ptr = pool_malloc(opaque, count * size);
    if (ptr)
        memset(ptr, 0, count * size);
    return ptr;
}
static void *pool_realloc(void *opaque, void *ptr, size_t size)
{
    FramePool *p = opaque;
    FramePoolHeader *h, *next;
    size_t capacity, old;
    void *result;
    if (!ptr)
        return pool_malloc(opaque, size);
    if (!size) {
        pool_free(opaque, ptr);
        return NULL;
    }
    h = (FramePoolHeader *)ptr - 1;
    old = h->capacity;
    if (h->page && size <= old)
        return ptr;
    if (size > SIZE_MAX - 15u)
        return NULL;
    capacity = (size + 15u) & ~(size_t)15u;
    if (!h->page && capacity > p->small_limit) {
        if (capacity > SIZE_MAX - sizeof(*h))
            return NULL;
        next = realloc(h, sizeof(*h) + capacity);
        if (!next)
            return NULL;
        next->page = NULL;
        next->capacity = capacity;
        if (p->flags & FRAME_POOL_TRACK) {
            p->stats.live_capacity = p->stats.live_capacity - old + capacity;
            if (p->stats.live_capacity > p->stats.peak_live_capacity)
                p->stats.peak_live_capacity = p->stats.live_capacity;
        }
        return next + 1;
    }
    result = pool_malloc(opaque, size);
    if (!result)
        return NULL;
    memcpy(result, ptr, old < size ? old : size);
    pool_free(opaque, ptr);
    return result;
}
const JSMallocFunctions FramePoolFunctions = {pool_calloc, pool_malloc, pool_free, pool_realloc,
                                              pool_usable};

static JSRuntime *pool_new_runtime(const char *mode)
{
    const char *observe = getenv("QJS_EXPERIMENT_ALLOCATOR_REPORT");
    FramePool *p;
    JSRuntime *rt;
    unsigned limit;
    if (!strcmp(mode, "header"))
        limit = 0;
    else if (!strcmp(mode, "128"))
        limit = 128;
    else if (!strcmp(mode, "256"))
        limit = 256;
    else if (!strcmp(mode, "512"))
        limit = 512;
    else {
        fprintf(stderr, "invalid QJS_EXPERIMENT_ALLOCATOR\n");
        return NULL;
    }
    p = FramePoolCreate(limit, observe && !strcmp(observe, "1") ? FRAME_POOL_TRACK : 0);
    if (!p)
        return NULL;
    p->observe = (p->flags & FRAME_POOL_TRACK) != 0;
    rt = JS_NewRuntime2(&FramePoolFunctions, p);
    if (!rt) {
        if (FramePoolDestroy(p) != 0)
            abort();
        return NULL;
    }
    p->auto_destroy = 1;
    return rt;
}
static const char *pool_selected_mode(void)
{
    const char *mode = getenv("QJS_EXPERIMENT_ALLOCATOR");
#ifdef QJS_DEFAULT_EXPERIMENT_ALLOCATOR
    if (!mode)
        mode = QJS_DEFAULT_EXPERIMENT_ALLOCATOR;
#endif
    return mode;
}
JSRuntime *FrameExperiment_NewRuntime(void)
{
    const char *mode = pool_selected_mode();
    if (!mode || !*mode || !strcmp(mode, "off") || !strcmp(mode, "0"))
        return JS_NewRuntime();
    return pool_new_runtime(mode);
}
JSRuntime *FramePool_NewRuntime(const JSMallocFunctions *fallback, void *opaque)
{
    const char *mode = pool_selected_mode();
    if (!mode || !*mode || !strcmp(mode, "off") || !strcmp(mode, "0"))
        return JS_NewRuntime2(fallback, opaque);
    return pool_new_runtime(mode);
}
