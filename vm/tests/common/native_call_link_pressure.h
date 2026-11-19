/* Qualification only: exhaust the actual metadata size class without editing
 * the shipping allocator or callback code. Hold raw runtime allocations until
 * after the observed miss, then release every block and the C-side vector. */
typedef struct ArenaPressure {
    void **held;
    size_t count, capacity;
} ArenaPressure;
static int arena_pressure_push(ArenaPressure *p, void *block)
{
    if (p->count == p->capacity) {
        size_t cap = p->capacity ? p->capacity * 2 : 64;
        if (cap > 65536)
            return 1;
        void **v = realloc(p->held, cap * sizeof(*v));
        if (!v)
            return 1;
        p->held = v;
        p->capacity = cap;
    }
    p->held[p->count++] = block;
    return 0;
}
static int arena_pressure_begin(JSRuntime *rt, size_t requested, ArenaPressure *p)
{
    if (p->count || p->held)
        return 1;
#if QJS_ABI_HAS_PREFIX_RC
    void *first = js_malloc_rt(rt, requested);
    if (!first)
        return 1;
    JSMallocBlockHeader *b =
        (JSMallocBlockHeader *)((unsigned char *)first - sizeof(JSMallocBlockHeader));
    if (b->u.block_idx == JS_ARENA_FREE_NIL) {
        js_free_rt(rt, first);
        return 0;
    }
    unsigned index = b->block_size_idx;
    if (index >= JS_ARENA_BLOCK_SIZE_COUNT) {
        js_free_rt(rt, first);
        return 1;
    }
    if (arena_pressure_push(p, first)) {
        js_free_rt(rt, first);
        return 1;
    }
    struct list_head *head = &rt->arena_state.free_arena_list[index];
    while (head->next != head) {
        void *block = js_malloc_rt(rt, requested);
        if (!block)
            return 1;
        if (arena_pressure_push(p, block)) {
            js_free_rt(rt, block);
            return 1;
        }
    }
#else
    /* The inline-header core calls the host allocator for every metadata block.
    Its forced-OOM/reentry hooks need no size-class exhaustion beforehand. */
    (void)rt;
    (void)requested;
#endif
    return 0;
}
static void arena_pressure_end(JSRuntime *rt, ArenaPressure *p)
{
    while (p->count)
        js_free_rt(rt, p->held[--p->count]);
    free(p->held);
    p->held = NULL;
    p->capacity = 0;
}
