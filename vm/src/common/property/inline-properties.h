/* Co-allocated inline property storage helper for ordinary small objects. */
#ifdef QJS_VM_INSTRUMENT
#define qjs_inline_property_plan(sh, tail_bytes, min_cap) ((size_t)0)
#define qjs_inline_property_initialize(p, sh, tail_bytes, bytes) ((JSProperty *)NULL)
#define qjs_inline_property_realloc(ctx, p, bytes) js_realloc((ctx), (p)->prop, (bytes))
#define qjs_inline_property_current(p) 0
#define qjs_inline_property_account(s, p) ((void)0)
#else
typedef struct QJSInlinePropertyHeader {
    uint32_t allocation_bytes;
    uint32_t property_capacity;
} QJSInlinePropertyHeader;
_Static_assert(sizeof(QJSInlinePropertyHeader) == 8, "owned property header8");

static inline size_t qjs_inline_property_offset(size_t tail_bytes)
{
    return (sizeof(JSObject) + tail_bytes + sizeof(QJSInlinePropertyHeader) + 15u) & ~(size_t)15u;
}

static inline size_t qjs_inline_property_plan(JSShape *sh, size_t tail_bytes, uint32_t min_cap)
{
    size_t offset;
    uint32_t cap;
    if (tail_bytes > 256u - sizeof(JSObject) - sizeof(QJSInlinePropertyHeader))
        return 0;
    offset = qjs_inline_property_offset(tail_bytes);
    if (offset > 256u || (!sh->prop_size && !min_cap))
        return 0;
    cap = (uint32_t)sh->prop_size < min_cap ? min_cap : (uint32_t)sh->prop_size;
    if (cap > (256u - offset) / sizeof(JSProperty))
        return 0;
    return offset + (size_t)cap * sizeof(JSProperty);
}

static inline JSProperty *qjs_inline_property_initialize(JSObject *p, JSShape *sh,
                                                         size_t tail_bytes, size_t bytes)
{
    size_t offset = qjs_inline_property_offset(tail_bytes);
    QJSInlinePropertyHeader *header =
        (QJSInlinePropertyHeader *)((uint8_t *)p + offset - sizeof(*header));
    header->allocation_bytes = bytes;
    header->property_capacity = (uint32_t)((bytes - offset) / sizeof(JSProperty));
    p->turbo_obj_flags |= 32;
    return (JSProperty *)((uint8_t *)p + offset);
}

static inline size_t qjs_inline_property_tail_bytes(const JSObject *p)
{
    if ((p->class_id == JS_CLASS_BYTECODE_FUNCTION || p->class_id == JS_CLASS_ASYNC_FUNCTION) &&
        (p->turbo_obj_flags & 64)) {
        assert(p->u.func.function_bytecode);
        return (size_t)p->u.func.function_bytecode->closure_var_count * sizeof(JSVarRef *);
    }
    return 0;
}

static inline QJSInlinePropertyHeader *qjs_inline_property_header(const JSObject *p)
{
    size_t offset = qjs_inline_property_offset(qjs_inline_property_tail_bytes(p));
    return (QJSInlinePropertyHeader *)((uint8_t *)p + offset - sizeof(QJSInlinePropertyHeader));
}

static inline int qjs_inline_property_current(const JSObject *p)
{
    if (!(p->turbo_obj_flags & 32))
        return 0;
    return (uint8_t *)p->prop ==
           (uint8_t *)qjs_inline_property_header(p) + sizeof(QJSInlinePropertyHeader);
}

#if defined(_MSC_VER)
#define QJS_INLINE_PROP_NOIPA __declspec(noinline)
#else
#define QJS_INLINE_PROP_NOIPA __attribute__((noipa))
#endif

static QJS_INLINE_PROP_NOIPA JSProperty *qjs_inline_property_realloc(JSContext *ctx, JSObject *p,
                                                                     size_t bytes)
{
    QJSInlinePropertyHeader *header;
    JSProperty *prop;
    if (!qjs_inline_property_current(p))
        return js_realloc(ctx, p->prop, bytes);
    header = qjs_inline_property_header(p);
    if (bytes <= (size_t)header->property_capacity * sizeof(JSProperty))
        return p->prop;
    prop = js_malloc(ctx, bytes);
    if (!prop)
        return NULL;
    memcpy(prop, p->prop, (size_t)header->property_capacity * sizeof(JSProperty));
    return prop;
}

#ifdef QJS_INLINE_PROPERTY_DEFINE_REALLOC_RT
__attribute__((visibility("hidden"), section(".text.qjs_frame"), noipa))
JSProperty *qjs_inline_property_realloc_rt(JSRuntime *rt, JSObject *p, size_t bytes)
{
    QJSInlinePropertyHeader *header;
    JSProperty *prop;
    if (!qjs_inline_property_current(p))
        return js_realloc_rt(rt, p->prop, bytes);
    header = qjs_inline_property_header(p);
    if (bytes <= (size_t)header->property_capacity * sizeof(JSProperty))
        return p->prop;
    prop = js_malloc_rt(rt, bytes);
    if (!prop)
        return NULL;
    memcpy(prop, p->prop, (size_t)header->property_capacity * sizeof(JSProperty));
    return prop;
}
#endif

static inline void qjs_inline_property_account(JSMemoryUsage *s, const JSObject *p)
{
    size_t extra;
    if (!(p->turbo_obj_flags & 32))
        return;
    extra = qjs_inline_property_header(p)->allocation_bytes - sizeof(JSObject) -
            qjs_inline_property_tail_bytes(p);
    if (qjs_inline_property_current(p)) {
        s->memory_used_count--;
        extra -= (size_t)p->shape->prop_size * sizeof(JSProperty);
    }
    s->obj_size += extra;
}
#endif
