/* Default primitive-string sort. Collection, observable conversion, property
 * writes and cleanup remain in the pinned builtin. Never cache a borrowed
 * string in ValueSlot.str: the original cleanup owns every non-NULL cache. */
#ifdef _MSC_VER
extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);
extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);
#endif
static unsigned char js_default_string_sort_mode;

static bool js_default_string_sort_enabled(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode = JS_FrameCallMetaLoadByte(&js_default_string_sort_mode);
#else
    mode = __atomic_load_n(&js_default_string_sort_mode, __ATOMIC_RELAXED);
#endif
    if (unlikely(!mode)) {
        unsigned char desired = getenv("QJS_DISABLE_DEFAULT_STRING_RADIX") ? 2 : 1;
#ifdef _MSC_VER
        mode = JS_FrameCallMetaInitByte(&js_default_string_sort_mode, desired);
#else
        __atomic_compare_exchange_n(&js_default_string_sort_mode, &mode, desired, false,
                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);
#endif
        if (!mode)
            mode = desired;
    }
    return mode == 1;
}

typedef struct JSDefaultStringSortTask {
    uint32_t start, count, depth;
} JSDefaultStringSortTask;

static int js_default_string_index_compare(const ValueSlot *values, uint32_t a, uint32_t b,
                                           uint32_t depth)
{
    JSString *sa = JS_VALUE_GET_STRING(values[a].val);
    JSString *sb = JS_VALUE_GET_STRING(values[b].val);
    uint32_t la = sa->len, lb = sb->len, len = min_int(la, lb);
    int result = memcmp(str8(sa) + depth, str8(sb) + depth, len - depth);
    if (result)
        return result;
    if (la != lb)
        return (la > lb) - (la < lb);
    return (a > b) - (a < b);
}

static void js_default_string_index_insertion(const ValueSlot *values, uint32_t *order,
                                              uint32_t count, uint32_t depth)
{
    uint32_t i, j, value;
    for (i = 1; i < count; i++) {
        value = order[i];
        for (j = i; j && js_default_string_index_compare(values, order[j - 1], value, depth) > 0;
             j--)
            order[j] = order[j - 1];
        order[j] = value;
    }
}

static void js_default_string_index_sift(const ValueSlot *values, uint32_t *order, uint32_t root,
                                         uint32_t count, uint32_t depth)
{
    uint32_t value = order[root], child;
    while (root < count / 2) {
        child = root * 2 + 1;
        if (child + 1 < count &&
            js_default_string_index_compare(values, order[child], order[child + 1], depth) < 0)
            child++;
        if (js_default_string_index_compare(values, value, order[child], depth) >= 0)
            break;
        order[root] = order[child];
        root = child;
    }
    order[root] = value;
}

static void js_default_string_index_heap(const ValueSlot *values, uint32_t *order, uint32_t count,
                                         uint32_t depth)
{
    uint32_t i, temp;
    for (i = count / 2; i; i--)
        js_default_string_index_sift(values, order, i - 1, count, depth);
    for (i = count; i > 1; i--) {
        temp = order[0];
        order[0] = order[i - 1];
        order[i - 1] = temp;
        js_default_string_index_sift(values, order, 0, i - 1, depth);
    }
}

/* A bounded, nonrecursive native stack frame. No allocation, polling, callback
 * or refcount operation is allowed while indices or ValueSlots are moved. */
static no_inline void js_default_string_sort_kernel(ValueSlot *values, uint32_t n, uint32_t *order,
                                                    uint32_t *scratch,
                                                    JSDefaultStringSortTask *tasks,
                                                    uint32_t capacity)
{
    uint32_t counts[257], cursor[257], top = 1, i, j, bucket, begin, end;
    JSDefaultStringSortTask task;
    tasks[0] = (JSDefaultStringSortTask){0, n, 0};
    for (i = 0; i < n; i++)
        order[i] = i;
    while (top) {
        task = tasks[--top];
        if (task.depth > 32) {
            js_default_string_index_heap(values, order + task.start, task.count, task.depth);
            continue;
        }
        memset(counts, 0, sizeof(counts));
        end = task.start + task.count;
        for (i = task.start; i < end; i++) {
            JSString *s = JS_VALUE_GET_STRING(values[order[i]].val);
            bucket = task.depth < s->len ? (uint32_t)str8(s)[task.depth] + 1 : 0;
            counts[bucket]++;
        }
        begin = task.start;
        for (bucket = 0; bucket < 257; bucket++) {
            cursor[bucket] = begin;
            begin += counts[bucket];
        }
        for (i = task.start; i < end; i++) {
            JSString *s = JS_VALUE_GET_STRING(values[order[i]].val);
            bucket = task.depth < s->len ? (uint32_t)str8(s)[task.depth] + 1 : 0;
            scratch[cursor[bucket]++] = order[i];
        }
        memcpy(order + task.start, scratch + task.start, task.count * sizeof(*order));
        begin = task.start + counts[0]; /* Already-ended equal strings stay stable. */
        for (bucket = 1; bucket < 257; bucket++) {
            uint32_t count = counts[bucket];
            if (count > 1) {
                if (count < 32)
                    js_default_string_index_insertion(values, order + begin, count, task.depth + 1);
                else if (top < capacity)
                    tasks[top++] = (JSDefaultStringSortTask){begin, count, task.depth + 1};
                else
                    js_default_string_index_heap(values, order + begin, count, task.depth + 1);
            }
            begin += count;
        }
    }
    /* order maps each destination to its original source. Move complete owned
     * slots along each cycle, retaining exactly one owner in a local temp. */
    for (i = 0; i < n; i++) {
        ValueSlot temp;
        if (order[i] == i)
            continue;
        temp = values[i];
        j = i;
        while ((begin = order[j]) != i) {
            values[j] = values[begin];
            order[j] = j;
            j = begin;
        }
        values[j] = temp;
        order[j] = j;
    }
}

static bool js_default_string_sort_try(ValueSlot *values, size_t n, struct array_sort_context *asc)
{
    uint32_t i, capacity;
    size_t bytes;
    uint32_t *workspace;
    if (n < 64 || n > 1048576 || asc->has_method || asc->exception ||
        !js_default_string_sort_enabled() || js_check_stack_overflow(asc->ctx->rt, 4096))
        return false;
    for (i = 0; i < n; i++) {
        if (JS_VALUE_GET_TAG(values[i].val) != JS_TAG_STRING || values[i].str ||
            JS_VALUE_GET_STRING(values[i].val)->is_wide_char)
            return false;
    }
    capacity = (uint32_t)n / 32 + 1;
    bytes = 2 * n * sizeof(*workspace) + capacity * sizeof(JSDefaultStringSortTask);
    /* RT allocation is optional and does not install an exception. Failure
     * leaves every slot untouched for the exact original sorter. */
    workspace = js_malloc_rt(asc->ctx->rt, bytes);
    if (!workspace)
        return false;
    js_default_string_sort_kernel(values, (uint32_t)n, workspace, workspace + n,
                                  (JSDefaultStringSortTask *)(workspace + 2 * n), capacity);
    js_free_rt(asc->ctx->rt, workspace);
    return true;
}

#ifdef _MSC_VER
extern void qjs_default_string_sort_original(void *, size_t, size_t, cmp_f, void *);
void JS_ArrayDefaultStringSortDispatch(void *base, size_t count, size_t size, cmp_f cmp,
                                       void *opaque)
{
    if (size != sizeof(ValueSlot) || !js_default_string_sort_try(base, count, opaque))
        qjs_default_string_sort_original(base, count, size, cmp, opaque);
}
#else
/* This is the audited GCC clone ABI, not the five-argument source rqsort ABI.
 * Its private identity and both original call sites are bound by the generator. */
extern void qjs_default_string_sort_original(ValueSlot *, size_t, struct array_sort_context *);
void JS_ArrayDefaultStringSortDispatch(ValueSlot *base, size_t count,
                                       struct array_sort_context *asc)
{
    if (!js_default_string_sort_try(base, count, asc))
        qjs_default_string_sort_original(base, count, asc);
}
#endif
