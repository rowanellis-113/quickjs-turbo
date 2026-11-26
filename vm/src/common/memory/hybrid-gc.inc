/* Hybrid Reference Counting + Generational Partial Mark-Sweep + Fast Synchronous RC. */
#define QJS_HYBRID_GC_OVERLAY 1
#include "src/common/internal/turbo-config.h"

_Static_assert(offsetof(JSObject, header) == 0 && offsetof(JSFunctionBytecode, header) == 0 &&
                   offsetof(JSShape, header) == 0 &&
                   (uint32_t)(JS_TAG_OBJECT - JS_TAG_FUNCTION_BYTECODE) == 1u,
               "inline child walker relies on contiguous GC tags and header at offset 0");

static void js_hybrid_gc_init(JSRuntime *rt, const JSMallocFunctions *mf)
{
    uint32_t mode = JS_HYBRID_MODE_PARTIAL | JS_HYBRID_MODE_FAST_RC;
    (void)mf;
    if (qjs_turbo_default_hybrid_gc_disabled())
        mode = 0;
    if (getenv("QJS_DISABLE_PARTIAL_CYCLE"))
        mode &= ~JS_HYBRID_MODE_PARTIAL;
    if (getenv("QJS_DISABLE_FAST_RC") || getenv("QJS_DISABLE_ZCT"))
        mode &= ~JS_HYBRID_MODE_FAST_RC;
    rt->hybrid_gc_mode = mode;
    rt->hybrid_gc_report = getenv("QJS_HYBRID_GC_REPORT") ? 1 : 0;
    rt->drc_ok = (mode & JS_HYBRID_MODE_FAST_RC) ? 1 : 0;
}

static void js_hybrid_unlink_boundary(JSRuntime *rt)
{
    if (rt->hybrid_gc_boundary_linked) {
        list_del(&rt->hybrid_gc_boundary.node.link);
        rt->hybrid_gc_boundary_linked = 0;
    }
}

static void js_hybrid_link_boundary_tail(JSRuntime *rt)
{
    if (!(rt->hybrid_gc_mode & JS_HYBRID_MODE_PARTIAL) || rt->in_free)
        return;
    js_hybrid_unlink_boundary(rt);
    memset(&rt->hybrid_gc_boundary, 0, sizeof(rt->hybrid_gc_boundary));
    JS_REF_COUNT(&rt->hybrid_gc_boundary.node) = 1;
    JS_GC_TYPE(&rt->hybrid_gc_boundary.node) = JS_GC_OBJ_TYPE_VAR_REF;
    JS_HYBRID_YOUNG(&rt->hybrid_gc_boundary.node) = 0;
    JS_GC_MARK(&rt->hybrid_gc_boundary.node) = 0;
    list_add_tail(&rt->hybrid_gc_boundary.node.link, &rt->gc_obj_list);
    rt->hybrid_gc_boundary_linked = 1;
}

static void js_hybrid_on_free_runtime(JSRuntime *rt)
{
    js_hybrid_unlink_boundary(rt);
    if (rt->hybrid_gc_report) {
        fprintf(stderr,
                "HYBRID_GC {\"mode\":%u,\"full\":%" PRIu64 ",\"minor\":%" PRIu64
                ",\"skipped\":%" PRIu64 ",\"fast_frees\":%" PRIu64 "}\n",
                rt->hybrid_gc_mode, rt->hybrid_gc_full_count, rt->hybrid_gc_minor_count,
                rt->hybrid_gc_skipped_count, rt->hybrid_gc_fast_frees);
    }
}

static inline void js_hybrid_free_rt_fast(JSRuntime *rt, void *ptr)
{
    if (likely(ptr != NULL)) {
        JSMallocBlockHeader *b = container_of(ptr, JSMallocBlockHeader, user_data);
        if (likely(b->u.block_idx != JS_ARENA_FREE_NIL)) {
            unsigned int block_idx = b->u.block_idx;
            unsigned int block_size_idx = b->block_size_idx;
            unsigned int block_size = arena_block_sizes[block_size_idx];
            size_t free_size = (size_t)block_size - sizeof(JSMallocBlockHeader) + MALLOC_OVERHEAD;
            JSArena *ar =
                (JSArena *)((uint8_t *)b - (size_t)block_size * block_idx - sizeof(JSArena));
            JSMallocState *s = &rt->malloc_state;
            if (likely(free_size <= s->malloc_size && ar->n_used_blocks > 1)) {
                s->malloc_count--;
                s->malloc_size -= free_size;
                b->u.free_next = ar->first_free_block;
                ar->first_free_block = block_idx;
                if (unlikely(ar->n_used_blocks == ar->n_blocks))
                    list_add(&ar->free_link, &rt->arena_state.free_arena_list[block_size_idx]);
                ar->n_used_blocks--;
                return;
            }
        }
    }
    js_free_rt(rt, ptr);
}

static inline void js_hybrid_push_free(JSRuntime *rt, JSGCObjectHeader *ch)
{
    list_del(&ch->link);
    ch->link.next = (struct list_head *)rt->hybrid_free_stack;
    rt->hybrid_free_stack = ch;
}

static inline void js_hybrid_drop_val(JSRuntime *rt, JSValue v)
{
    if (JS_VALUE_HAS_REF_COUNT(v)) {
        void *r = JS_VALUE_GET_PTR(v);
        if (--JS_REF_COUNT(r) <= 0) {
            uint32_t tag = (uint32_t)JS_VALUE_GET_TAG(v);
            if (likely(tag == (uint32_t)JS_TAG_OBJECT)) {
                js_hybrid_push_free(rt, (JSGCObjectHeader *)r);
            } else if (tag == (uint32_t)JS_TAG_STRING) {
                js_free_string0(rt, (JSString *)r);
            } else {
                js_free_value_rt(rt, v);
            }
        }
    }
}

/* Fast leaf release for ref_count == 1 string/rope values without VM exit or reload. */
void js_hybrid_drop_string1(JSRuntime *rt, void *ptr, uint32_t is_rope)
{
    assert(JS_REF_COUNT(ptr) == 1);
    JS_REF_COUNT(ptr) = 0;
#ifdef ENABLE_DUMPS // JS_DUMP_FREE
    if (unlikely(check_dump_flag(rt, JS_DUMP_FREE))) {
        js_free_value_rt(rt, JS_MKPTR(is_rope ? JS_TAG_STRING_ROPE : JS_TAG_STRING, ptr));
        return;
    }
#endif
    if (likely(!is_rope)) {
        JSString *str = (JSString *)ptr;
#ifndef ENABLE_DUMPS // JS_DUMP_LEAKS
        if (likely(!str->atom_type)) {
            if (likely(str->kind == JS_STRING_KIND_NORMAL)) {
                js_hybrid_free_rt_fast(rt, str);
                return;
            }
            if (str->kind == JS_STRING_KIND_SLICE) {
                JSStringSlice *slice = (JSStringSlice *)&str[1];
                js_free_string(rt, slice->parent);
                js_hybrid_free_rt_fast(rt, str);
                return;
            }
        }
#endif
        js_free_string0(rt, str);
    } else {
        JSStringRope *p = (JSStringRope *)ptr;
        JS_FreeValueRT(rt, p->left);
        JS_FreeValueRT(rt, p->right);
        js_hybrid_free_rt_fast(rt, p);
    }
}

/* Iterative O(1)-C-stack synchronous LIFO destruction using link.next after unlink. */
static no_inline void js_hybrid_free_object_root(JSRuntime *rt, JSGCObjectHeader *root)
{
    JSGCObjectHeader *cur;
    uint64_t fast_frees = 0;

    assert(rt->hybrid_free_stack == NULL);
    list_del(&root->link);
    root->link.next = NULL;
    rt->gc_phase = JS_GC_PHASE_DECREF;
    rt->hybrid_free_active = 1;
    cur = root;

    for (;;) {
        if (likely(JS_GC_TYPE(cur) == JS_GC_OBJ_TYPE_JS_OBJECT)) {
            JSObject *obj = (JSObject *)cur;
            uint16_t cid = obj->class_id;
            if (likely((uint16_t)(cid - JS_CLASS_OBJECT) <= (JS_CLASS_ARRAY - JS_CLASS_OBJECT) &&
                       !obj->first_weak_ref)) {
                JSShape *sh;
                JSShapeProperty *pr;
                JSProperty *prop;
                uint32_t i, prop_count;

#ifdef QJS_PROPERTY_IC
                if (unlikely(obj->is_prototype))
                    js_property_ic_prototype_free(rt, obj);
#endif
                obj->free_mark = 1;
                sh = obj->shape;
                pr = get_shape_prop(sh);
                prop = obj->prop;
                prop_count = (uint32_t)sh->prop_count;
                for (i = 0; i < prop_count; i++) {
                    if (unlikely(pr[i].flags & JS_PROP_TMASK)) {
                        free_property(rt, &prop[i], pr[i].flags);
                    } else {
                        js_hybrid_drop_val(rt, prop[i].u.value);
                    }
                }
#ifdef QJS_HYBRID_INLINE_PROPERTIES
                if (prop && !qjs_inline_property_current(obj))
                    js_hybrid_free_rt_fast(rt, prop);
#else
                if (prop)
                    js_hybrid_free_rt_fast(rt, prop);
#endif
                js_free_shape(rt, sh);

                if (cid == JS_CLASS_ARRAY) {
                    uint32_t j, acount = obj->u.array.count;
                    JSValue *vals = obj->u.array.u.values;
                    for (j = 0; j < acount; j++) {
                        js_hybrid_drop_val(rt, vals[j]);
                    }
                    if (vals)
                        js_hybrid_free_rt_fast(rt, vals);
                }

                js_hybrid_free_rt_fast(rt, obj);
                fast_frees++;
            } else {
                init_list_head(&cur->link);
                free_gc_object(rt, cur);
            }
        } else {
            init_list_head(&cur->link);
            free_gc_object(rt, cur);
        }

        cur = rt->hybrid_free_stack;
        if (!cur)
            break;
        rt->hybrid_free_stack = (JSGCObjectHeader *)cur->link.next;
    }

    rt->hybrid_free_stack = NULL;
    rt->hybrid_free_active = 0;
    rt->gc_phase = JS_GC_PHASE_NONE;
    if (unlikely(rt->hybrid_gc_report))
        rt->hybrid_gc_fast_frees += fast_frees;
}

#define JS_HYBRID_FULL_DECREF_HDR(rt_, hdr_)                                                       \
    do {                                                                                           \
        JSGCObjectHeader *_p = (hdr_);                                                             \
        assert(JS_REF_COUNT(_p) > 0);                                                              \
        JS_REF_COUNT(_p)--;                                                                        \
        if (JS_REF_COUNT(_p) == 0 && JS_GC_MARK(_p) == 1) {                                        \
            list_del(&_p->link);                                                                   \
            list_add_tail(&_p->link, &(rt_)->tmp_obj_list);                                        \
        }                                                                                          \
    } while (0)

#define JS_HYBRID_FULL_SCAN1_HDR(rt_, hdr_)                                                        \
    do {                                                                                           \
        JSGCObjectHeader *_p = (hdr_);                                                             \
        JS_REF_COUNT(_p)++;                                                                        \
        if (JS_REF_COUNT(_p) == 1) {                                                               \
            list_del(&_p->link);                                                                   \
            list_add_tail(&_p->link, &(rt_)->gc_obj_list);                                         \
            JS_GC_MARK(_p) = 0;                                                                    \
        }                                                                                          \
    } while (0)

#define JS_HYBRID_FULL_SCAN2_HDR(rt_, hdr_)                                                        \
    do {                                                                                           \
        (void)(rt_);                                                                               \
        JS_REF_COUNT((hdr_))++;                                                                    \
    } while (0)

#define JS_HYBRID_MINOR_DECREF_HDR(rt_, hdr_)                                                      \
    do {                                                                                           \
        JSGCObjectHeader *_p = (hdr_);                                                             \
        if (JS_HYBRID_YOUNG(_p)) {                                                                 \
            assert(JS_REF_COUNT(_p) > 0);                                                          \
            JS_REF_COUNT(_p)--;                                                                    \
            if (JS_REF_COUNT(_p) == 0 && JS_GC_MARK(_p) == 1) {                                    \
                list_del(&_p->link);                                                               \
                list_add_tail(&_p->link, &(rt_)->tmp_obj_list);                                    \
            }                                                                                      \
        }                                                                                          \
    } while (0)

#define JS_HYBRID_MINOR_SCAN1_HDR(rt_, hdr_)                                                       \
    do {                                                                                           \
        JSGCObjectHeader *_p = (hdr_);                                                             \
        if (JS_HYBRID_YOUNG(_p)) {                                                                 \
            JS_REF_COUNT(_p)++;                                                                    \
            if (JS_REF_COUNT(_p) == 1) {                                                           \
                list_del(&_p->link);                                                               \
                list_add_tail(&_p->link, &(rt_)->gc_obj_list);                                     \
                JS_GC_MARK(_p) = 0;                                                                \
            }                                                                                      \
        }                                                                                          \
    } while (0)

#define JS_HYBRID_MINOR_SCAN2_HDR(rt_, hdr_)                                                       \
    do {                                                                                           \
        JSGCObjectHeader *_p = (hdr_);                                                             \
        if (JS_HYBRID_YOUNG(_p))                                                                   \
            JS_REF_COUNT(_p)++;                                                                    \
    } while (0)

#ifdef QJS_PROPERTY_IC
#define JS_HYBRID_SHAPE_HAS_STRONG_PROTO(sh_)                                                      \
    ((sh_)->proto != NULL && !((sh_)->is_hashed & JS_IC_PROTO_WEAK))
#else
#define JS_HYBRID_SHAPE_HAS_STRONG_PROTO(sh_) ((sh_)->proto != NULL)
#endif

#define JS_HYBRID_DEFINE_WALKER(name_, action_, fallback_fn_)                                      \
    static inline void name_(JSRuntime *rt, JSGCObjectHeader *gp)                                  \
    {                                                                                              \
        if (likely(JS_GC_TYPE(gp) == JS_GC_OBJ_TYPE_JS_OBJECT)) {                                  \
            JSObject *p = (JSObject *)gp;                                                          \
            if (likely((uint16_t)(p->class_id - JS_CLASS_OBJECT) <=                                \
                           (JS_CLASS_ARRAY - JS_CLASS_OBJECT) &&                                   \
                       !p->first_weak_ref)) {                                                      \
                JSShape *sh = p->shape;                                                            \
                JSShapeProperty *prs = get_shape_prop(sh);                                         \
                JSProperty *props = p->prop;                                                       \
                int i, prop_count = sh->prop_count;                                                \
                action_(rt, &sh->header);                                                          \
                for (i = 0; i < prop_count; i++) {                                                 \
                    if (likely(prs[i].atom != JS_ATOM_NULL)) {                                     \
                        uint8_t flags = prs[i].flags;                                              \
                        if (unlikely(flags & JS_PROP_TMASK)) {                                     \
                            if ((flags & JS_PROP_TMASK) == JS_PROP_GETSET) {                       \
                                if (props[i].u.getset.getter)                                      \
                                    action_(rt, &props[i].u.getset.getter->header);                \
                                if (props[i].u.getset.setter)                                      \
                                    action_(rt, &props[i].u.getset.setter->header);                \
                            } else if ((flags & JS_PROP_TMASK) == JS_PROP_VARREF) {                \
                                if (props[i].u.var_ref->is_detached ||                             \
                                    props[i].u.var_ref->is_coro)                                   \
                                    action_(rt, &props[i].u.var_ref->header);                      \
                            } else if ((flags & JS_PROP_TMASK) == JS_PROP_AUTOINIT) {              \
                                js_autoinit_mark(rt, &props[i], (fallback_fn_));                   \
                            }                                                                      \
                        } else {                                                                   \
                            JSValue v = props[i].u.value;                                          \
                            if ((uint32_t)(JS_VALUE_GET_TAG(v) - JS_TAG_FUNCTION_BYTECODE) <=      \
                                1u) {                                                              \
                                action_(rt, (JSGCObjectHeader *)JS_VALUE_GET_PTR(v));              \
                            }                                                                      \
                        }                                                                          \
                    }                                                                              \
                }                                                                                  \
                if (p->class_id == JS_CLASS_ARRAY) {                                               \
                    uint32_t j, acount = p->u.array.count;                                         \
                    JSValue *vals = p->u.array.u.values;                                           \
                    for (j = 0; j < acount; j++) {                                                 \
                        JSValue v = vals[j];                                                       \
                        if ((uint32_t)(JS_VALUE_GET_TAG(v) - JS_TAG_FUNCTION_BYTECODE) <= 1u) {    \
                            action_(rt, (JSGCObjectHeader *)JS_VALUE_GET_PTR(v));                  \
                        }                                                                          \
                    }                                                                              \
                }                                                                                  \
                return;                                                                            \
            }                                                                                      \
        } else if (JS_GC_TYPE(gp) == JS_GC_OBJ_TYPE_SHAPE) {                                       \
            JSShape *sh = (JSShape *)gp;                                                           \
            if (JS_HYBRID_SHAPE_HAS_STRONG_PROTO(sh)) {                                            \
                action_(rt, &sh->proto->header);                                                   \
            }                                                                                      \
            return;                                                                                \
        }                                                                                          \
        mark_children(rt, gp, (fallback_fn_));                                                     \
    }

static void js_hybrid_minor_decref_child(JSRuntime *rt, JSGCObjectHeader *p)
{
    JS_HYBRID_MINOR_DECREF_HDR(rt, p);
}

static void js_hybrid_minor_scan_incref_child(JSRuntime *rt, JSGCObjectHeader *p)
{
    JS_HYBRID_MINOR_SCAN1_HDR(rt, p);
}

static void js_hybrid_minor_scan_incref_child2(JSRuntime *rt, JSGCObjectHeader *p)
{
    JS_HYBRID_MINOR_SCAN2_HDR(rt, p);
}

JS_HYBRID_DEFINE_WALKER(js_hybrid_walk_full_decref, JS_HYBRID_FULL_DECREF_HDR, gc_decref_child)
JS_HYBRID_DEFINE_WALKER(js_hybrid_walk_full_scan1, JS_HYBRID_FULL_SCAN1_HDR, gc_scan_incref_child)
JS_HYBRID_DEFINE_WALKER(js_hybrid_walk_full_scan2, JS_HYBRID_FULL_SCAN2_HDR, gc_scan_incref_child2)
JS_HYBRID_DEFINE_WALKER(js_hybrid_walk_minor_decref, JS_HYBRID_MINOR_DECREF_HDR,
                        js_hybrid_minor_decref_child)
JS_HYBRID_DEFINE_WALKER(js_hybrid_walk_minor_scan1, JS_HYBRID_MINOR_SCAN1_HDR,
                        js_hybrid_minor_scan_incref_child)
JS_HYBRID_DEFINE_WALKER(js_hybrid_walk_minor_scan2, JS_HYBRID_MINOR_SCAN2_HDR,
                        js_hybrid_minor_scan_incref_child2)

static no_inline void js_hybrid_full_decref(JSRuntime *rt)
{
    struct list_head *el, *el1;
    JSGCObjectHeader *p;

    init_list_head(&rt->tmp_obj_list);
    list_for_each_safe(el, el1, &rt->gc_obj_list)
    {
        p = list_entry(el, JSGCObjectHeader, link);
        assert(JS_GC_MARK(p) == 0);
        js_hybrid_walk_full_decref(rt, p);
        JS_GC_MARK(p) = 1;
        if (JS_REF_COUNT(p) == 0) {
            list_del(&p->link);
            list_add_tail(&p->link, &rt->tmp_obj_list);
        }
    }
}

static no_inline void js_hybrid_full_scan(JSRuntime *rt)
{
    struct list_head *el;
#ifdef QJS_PROPERTY_IC
    struct list_head *ic_cursor;
#endif
    JSGCObjectHeader *p;

#ifdef QJS_PROPERTY_IC
    rt->property_ic_gc_mode |= JS_IC_GC_SCAN;
#endif
    list_for_each(el, &rt->gc_obj_list)
    {
        p = list_entry(el, JSGCObjectHeader, link);
        assert(JS_REF_COUNT(p) > 0);
        JS_GC_MARK(p) = 0;
        js_hybrid_walk_full_scan1(rt, p);
    }
#ifdef QJS_PROPERTY_IC
    ic_cursor = rt->gc_obj_list.prev;
    while (js_property_ic_gc_propagate(rt, gc_scan_incref_child)) {
        while (ic_cursor->next != &rt->gc_obj_list) {
            ic_cursor = ic_cursor->next;
            p = list_entry(ic_cursor, JSGCObjectHeader, link);
            js_hybrid_walk_full_scan1(rt, p);
        }
    }
    js_property_ic_gc_restore(rt);
    rt->property_ic_gc_mode &= ~JS_IC_GC_SCAN;
#endif
    list_for_each(el, &rt->tmp_obj_list)
    {
        p = list_entry(el, JSGCObjectHeader, link);
        js_hybrid_walk_full_scan2(rt, p);
    }
#ifdef QJS_PROPERTY_IC
    rt->gc_phase = JS_GC_PHASE_REMOVE_CYCLES;
    js_property_ic_gc_prune(rt);
    rt->gc_phase = JS_GC_PHASE_NONE;
#endif
}

#ifdef QJS_PROPERTY_IC
static bool js_hybrid_ic_minor_propagate(JSRuntime *rt, JS_MarkFunc *mark)
{
    JSPropertyIC *ic;
    bool changed = false;
    uint32_t i, j;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        if (!JS_HYBRID_YOUNG(ic->owner) || JS_GC_MARK(ic->owner))
            continue;
        for (i = 0; i < ic->site_count; i++) {
            JSPropertyICSite *site = &ic->sites[i];
            for (j = 0; j < site->count; j++) {
                JSPropertyICWay *way = j ? &site->secondary[j - 1] : &site->primary;
                if (!way->transition || !rt->property_ic_epoch ||
                    way->epoch != rt->property_ic_epoch)
                    continue;
                if (!JS_GC_MARK(way->shape) && JS_GC_MARK(way->transition)) {
                    mark(rt, &way->transition->header);
                    way->kind |= 0x200u;
                    changed = true;
                } else if (JS_GC_MARK(way->shape) && !JS_GC_MARK(way->transition)) {
                    mark(rt, &way->shape->header);
                    way->kind |= 0x100u;
                    changed = true;
                }
            }
        }
    }
    return changed;
}

static void js_hybrid_ic_minor_restore(JSRuntime *rt)
{
    JSPropertyIC *ic;
    uint32_t i, j;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        if (!JS_HYBRID_YOUNG(ic->owner) || JS_GC_MARK(ic->owner))
            continue;
        for (i = 0; i < ic->site_count; i++) {
            JSPropertyICSite *site = &ic->sites[i];
            for (j = 0; j < site->count; j++) {
                JSPropertyICWay *way = j ? &site->secondary[j - 1] : &site->primary;
                if (way->shape && JS_HYBRID_YOUNG(way->shape) && !(way->kind & 0x100u))
                    JS_REF_COUNT(way->shape)++;
                if (way->transition && JS_HYBRID_YOUNG(way->transition) && !(way->kind & 0x200u))
                    JS_REF_COUNT(way->transition)++;
                way->kind &= 0xffu;
            }
        }
    }
}
#endif

static no_inline void js_hybrid_gc_minor(JSRuntime *rt)
{
    struct list_head *boundary = &rt->hybrid_gc_boundary.node.link;
    struct list_head *el, *el1;
    JSGCObjectHeader *p;
    size_t young_count = 0;
#ifdef QJS_PROPERTY_IC
    struct list_head *ic_cursor;
#endif

    for (el = boundary->next; el != &rt->gc_obj_list; el = el->next) {
        p = list_entry(el, JSGCObjectHeader, link);
        assert(JS_GC_MARK(p) == 0);
        JS_HYBRID_YOUNG(p) = 1;
        young_count++;
    }
    if (!young_count) {
        rt->hybrid_gc_skipped_count++;
        rt->hybrid_gc_minor_since_full++;
        return;
    }

    init_list_head(&rt->tmp_obj_list);

    for (el = boundary->next; el != &rt->gc_obj_list; el = el1) {
        el1 = el->next;
        p = list_entry(el, JSGCObjectHeader, link);
        assert(JS_GC_MARK(p) == 0);
        js_hybrid_walk_minor_decref(rt, p);
        JS_GC_MARK(p) = 1;
        if (JS_REF_COUNT(p) == 0) {
            list_del(&p->link);
            list_add_tail(&p->link, &rt->tmp_obj_list);
        }
    }

#ifdef QJS_PROPERTY_IC
    rt->property_ic_gc_mode |= JS_IC_GC_SCAN;
#endif
    for (el = boundary->next; el != &rt->gc_obj_list; el = el->next) {
        p = list_entry(el, JSGCObjectHeader, link);
        assert(JS_REF_COUNT(p) > 0);
        JS_GC_MARK(p) = 0;
        js_hybrid_walk_minor_scan1(rt, p);
    }
#ifdef QJS_PROPERTY_IC
    ic_cursor = rt->gc_obj_list.prev;
    while (js_hybrid_ic_minor_propagate(rt, js_hybrid_minor_scan_incref_child)) {
        while (ic_cursor->next != &rt->gc_obj_list) {
            ic_cursor = ic_cursor->next;
            p = list_entry(ic_cursor, JSGCObjectHeader, link);
            JS_GC_MARK(p) = 0;
            js_hybrid_walk_minor_scan1(rt, p);
        }
    }
    js_hybrid_ic_minor_restore(rt);
    rt->property_ic_gc_mode &= ~JS_IC_GC_SCAN;
#endif

    list_for_each(el, &rt->tmp_obj_list)
    {
        p = list_entry(el, JSGCObjectHeader, link);
        js_hybrid_walk_minor_scan2(rt, p);
    }

    for (el = boundary->next; el != &rt->gc_obj_list; el = el->next) {
        p = list_entry(el, JSGCObjectHeader, link);
        JS_HYBRID_YOUNG(p) = 0;
    }
    list_for_each(el, &rt->tmp_obj_list)
    {
        p = list_entry(el, JSGCObjectHeader, link);
        JS_HYBRID_YOUNG(p) = 0;
    }

    if (!list_empty(&rt->tmp_obj_list)) {
#ifdef QJS_PROPERTY_IC
        rt->gc_phase = JS_GC_PHASE_REMOVE_CYCLES;
        js_property_ic_gc_prune(rt);
        rt->gc_phase = JS_GC_PHASE_NONE;
#endif
        gc_free_cycles(rt);
    }
    rt->hybrid_gc_minor_count++;
    rt->hybrid_gc_minor_since_full++;
    js_hybrid_link_boundary_tail(rt);
}

static void js_hybrid_run_full_gc(JSRuntime *rt)
{
    js_hybrid_unlink_boundary(rt);
    if (!(rt->hybrid_gc_mode & JS_HYBRID_MODE_PARTIAL)) {
        gc_decref(rt);
        gc_scan(rt);
        gc_free_cycles(rt);
    } else {
        js_hybrid_full_decref(rt);
        js_hybrid_full_scan(rt);
        gc_free_cycles(rt);
    }
    rt->hybrid_gc_full_count++;
    rt->hybrid_gc_minor_since_full = 0;
    rt->hybrid_gc_full_malloc = rt->malloc_state.malloc_size;
    js_hybrid_link_boundary_tail(rt);
}

static no_inline void js_hybrid_trigger_gc_slow(JSRuntime *rt)
{
    if (unlikely(rt->gc_phase != JS_GC_PHASE_NONE || rt->in_free))
        return;
#ifdef ENABLE_DUMPS // JS_DUMP_GC
    if (check_dump_flag(rt, JS_DUMP_GC)) {
        printf("GC: size=%zd\n", rt->malloc_state.malloc_size);
    }
#endif
#ifdef FORCE_GC_AT_MALLOC
    JS_RunGC(rt);
    rt->malloc_gc_threshold = rt->malloc_state.malloc_size + (rt->malloc_state.malloc_size >> 1);
#else
    if (!(rt->hybrid_gc_mode & JS_HYBRID_MODE_PARTIAL) || !rt->hybrid_gc_boundary_linked) {
        JS_RunGC(rt);
        rt->malloc_gc_threshold =
            rt->malloc_state.malloc_size + (rt->malloc_state.malloc_size >> 1);
    } else {
        size_t before = rt->malloc_state.malloc_size;
        size_t lim = rt->malloc_state.malloc_limit;
        size_t base = rt->hybrid_gc_full_malloc;
        if (base < (256u * 1024u))
            base = 256u * 1024u;
        size_t full_cap = base + (base >> 1) + (base >> 2);
        bool near_limit = (lim != 0 && before + (before >> 2) > lim);
        if (rt->hybrid_gc_minor_since_full >= 8 || near_limit || before > full_cap) {
            JS_RunGC(rt);
#ifdef _WIN32
            /* Bound heap growth after a low-yield full collection on Windows. */
            rt->malloc_gc_threshold =
                rt->malloc_state.malloc_size + (rt->malloc_state.malloc_size >> 1);
#else
            size_t after = rt->malloc_state.malloc_size;
            if (!near_limit && before >= (1024u * 1024u) && after >= before - (before >> 4)) {
                rt->malloc_gc_threshold = after + after;
                rt->hybrid_gc_full_malloc = after + (after >> 2);
            } else {
                rt->malloc_gc_threshold = after + (after >> 1);
            }
#endif
        } else {
            size_t after;
            js_hybrid_gc_minor(rt);
            after = rt->malloc_state.malloc_size;
            if (after <= base + (base >> 3)) {
                rt->malloc_gc_threshold = after + (after >> 1);
            } else {
                size_t next_thresh = after + (after >> 2);
                size_t cap_thresh = full_cap + (base >> 3);
                size_t min_thresh = after + (after >> 3);
                if (next_thresh > cap_thresh)
                    next_thresh = cap_thresh;
                if (next_thresh < min_thresh)
                    next_thresh = min_thresh;
                rt->malloc_gc_threshold = next_thresh;
            }
        }
    }
#endif
}
