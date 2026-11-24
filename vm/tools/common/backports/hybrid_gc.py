"""Hybrid RC + Generational Partial Mark-Sweep + Fast Synchronous RC overlay.

Preserves every upstream core byte on disk and preserves logical source line numbers.
Original JSRuntime/JSGCObjectHeader field offsets are preserved.
"""

import re


def replace_exact_lines(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Hybrid GC source anchor changed: " + old[:120])
    diff = old.count("\n") - new.count("\n")
    if diff < 0:
        raise ValueError("Hybrid GC replacement expanded line count: " + old[:120])
    if diff > 0:
        new += "\n" * diff
    return text.replace(old, new, 1)


def core_overlay(text):
    before_lines = text.count("\n")

    # 1. Split gc_obj_type : 7 in JSMallocBlockHeader into 6 + 1 (hybrid_young),
    #    add JS_HYBRID_YOUNG accessor macro, reorder JSGCObjectTypeEnum +
    #    JSGCObjectHeader before JSRuntime, and embed ISO C11 JSHybridGCBoundary
    #    without nesting a flexible-array struct inside another struct.
    text = replace_exact_lines(
        text,
        "    uint8_t  gc_obj_type : 7; /* JSGCObjectTypeEnum for GC objects */\n"
        "    uint8_t  mark : 1;        /* used by the cycle collector */",
        "    uint8_t  gc_obj_type : 6; /* JSGCObjectTypeEnum for GC objects */\n"
        "    uint8_t  hybrid_young : 1; uint8_t mark : 1; /* cycle collector */",
    )
    text = replace_exact_lines(
        text,
        "#define JS_GC_MARK(p)   (js_rc(p)->mark)\n\n/* bigint */",
        "#define JS_GC_MARK(p)   (js_rc(p)->mark)\n#define JS_HYBRID_YOUNG(p) (js_rc(p)->hybrid_young)\n/* bigint */",
    )

    rt_start = text.index("\nstruct JSRuntime {\n")
    varref_start = text.index("\ntypedef struct JSVarRef {\n", rt_start)
    block = text[rt_start:varref_start]
    gc_enum_anchor = "\ntypedef enum {\n    JS_GC_OBJ_TYPE_JS_OBJECT,"
    gc_enum_idx = block.index(gc_enum_anchor)
    rt_part = block[:gc_enum_idx]
    gc_part = block[gc_enum_idx:]

    rt_final_re = re.compile(r"(    JSRuntimeFinalizerState \*finalizers;[^\n]*)\n(\};)")
    if not rt_final_re.search(rt_part):
        raise ValueError("JSRuntime finalizers anchor missing")
    rt_fields = (
        " JSHybridGCBoundary hybrid_gc_boundary;"
        " JSGCObjectHeader *hybrid_free_stack;"
        " size_t hybrid_gc_full_malloc;"
        " uint64_t hybrid_gc_full_count, hybrid_gc_minor_count, hybrid_gc_skipped_count, hybrid_gc_fast_frees;"
        " uint32_t hybrid_gc_mode, hybrid_gc_minor_since_full;"
        " uint8_t hybrid_gc_boundary_linked, hybrid_gc_report, drc_ok, hybrid_free_active;"
    )
    rt_part = rt_final_re.sub(r"\1" + rt_fields + r"\n\2", rt_part, count=1)

    boundary_decl = (
        "typedef struct JSHybridGCBoundary {"
        " _Alignas(JS_ARENA_ALIGN) uint8_t prefix[offsetof(JSMallocBlockHeader, user_data)];"
        " JSGCObjectHeader node;"
        " } JSHybridGCBoundary; struct JSRuntime {"
    )
    assert rt_part.startswith("\nstruct JSRuntime {\n")
    rt_part = "\n" + boundary_decl + rt_part[len("\nstruct JSRuntime {") :]

    new_block = gc_part + rt_part
    if new_block.count("\n") != block.count("\n"):
        raise ValueError("Header reorder changed line count")
    text = text[:rt_start] + new_block + text[varref_start:]

    # Propagate hybrid_young across block realloc and shape resize/compaction.
    text = replace_exact_lines(
        text,
        "            nb->gc_obj_type = b->gc_obj_type;\n            nb->mark = b->mark;",
        "            nb->gc_obj_type = b->gc_obj_type; nb->hybrid_young = b->hybrid_young;\n"
        "            nb->mark = b->mark;",
    )
    text = replace_exact_lines(
        text,
        "        JS_REF_COUNT(sh) = JS_REF_COUNT(old_sh);\n"
        "        JS_GC_TYPE(sh) = JS_GC_TYPE(old_sh);\n"
        "        JS_GC_MARK(sh) = JS_GC_MARK(old_sh);",
        "        JS_REF_COUNT(sh) = JS_REF_COUNT(old_sh);\n"
        "        JS_GC_TYPE(sh) = JS_GC_TYPE(old_sh); JS_HYBRID_YOUNG(sh) = JS_HYBRID_YOUNG(old_sh);\n"
        "        JS_GC_MARK(sh) = JS_GC_MARK(old_sh);",
    )
    text = replace_exact_lines(
        text,
        "    JS_REF_COUNT(sh) = JS_REF_COUNT(old_sh);\n"
        "    JS_GC_TYPE(sh) = JS_GC_TYPE(old_sh);\n"
        "    JS_GC_MARK(sh) = JS_GC_MARK(old_sh);",
        "    JS_REF_COUNT(sh) = JS_REF_COUNT(old_sh);\n"
        "    JS_GC_TYPE(sh) = JS_GC_TYPE(old_sh); JS_HYBRID_YOUNG(sh) = JS_HYBRID_YOUNG(old_sh);\n"
        "    JS_GC_MARK(sh) = JS_GC_MARK(old_sh);",
    )

    text = replace_exact_lines(
        text,
        """static int arena_get_size_index(size_t size)
{
    if (size <= 16)
        return 0;
    else if (size <= 128)
        return (size + 7) / 8 - 2;
    else if (size <= 256)
        return (size + 15) / 16 + 6;
    else if (size <= 512)
        return (size + 31) / 32 + 14;
    else
        return JS_ARENA_BLOCK_SIZE_COUNT;
}""",
        """static inline int arena_get_size_index(size_t size)
{
    static const uint8_t lut[65] = {
        0,0,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,
        15,15,16,16,17,17,18,18,19,19,20,20,21,21,22,22,
        23,23,23,23,24,24,24,24,25,25,25,25,26,26,26,26,
        27,27,27,27,28,28,28,28,29,29,29,29,30,30,30,30,
    };
    return size <= 512 ? lut[(size + 7) >> 3] : JS_ARENA_BLOCK_SIZE_COUNT;
}""",
    )
    text = replace_exact_lines(
        text,
        """static void *js_arena_malloc(JSRuntime *rt, size_t size)
{
    size_t total_size;

    if (unlikely(size == 0))
        return arena_zero_block(rt)->user_data;
    total_size = ((size + JS_ARENA_ALIGN - 1) & ~(size_t)(JS_ARENA_ALIGN - 1)) +
        sizeof(JSMallocBlockHeader);
    if (!JS_ARENA_LARGE_BLOCKS_ONLY && total_size <= JS_ARENA_MAX_SMALL_SIZE) {
        int block_size_idx;
        unsigned int block_idx, block_size;
        JSMallocBlockHeader *b;
        JSArena *ar;
        struct list_head *el, *head;

        block_size_idx = arena_get_size_index(total_size);
        block_size = arena_block_sizes[block_size_idx];
        head = &rt->arena_state.free_arena_list[block_size_idx];
        el = head->next;
        if (unlikely(el == head)) {
            ar = arena_new(rt, block_size_idx);
            if (!ar)
                return NULL;
        } else {
            ar = list_entry(el, JSArena, free_link);
        }
        block_idx = ar->first_free_block;
        b = arena_get_block(ar, block_idx, block_size);
        ar->first_free_block = b->u.free_next;
        b->u.block_idx = block_idx;
        ar->n_used_blocks++;
        if (unlikely(ar->n_used_blocks == ar->n_blocks))
            list_del(&ar->free_link);
        return b->user_data;
    } else {
        return arena_malloc_large(rt, size);
    }
}""",
        """static size_t js_arena_usable_size(JSRuntime *rt, const void *ptr);
static inline void *js_arena_malloc_fast(JSRuntime *rt, size_t size, size_t *pusable)
{
    if (unlikely(size == 0)) { *pusable = 0; return arena_zero_block(rt)->user_data; }
    size_t total_size = ((size + JS_ARENA_ALIGN - 1) & ~(size_t)(JS_ARENA_ALIGN - 1)) + sizeof(JSMallocBlockHeader);
    if (!JS_ARENA_LARGE_BLOCKS_ONLY && likely(total_size <= JS_ARENA_MAX_SMALL_SIZE)) {
        int block_size_idx = arena_get_size_index(total_size);
        unsigned int block_size = arena_block_sizes[block_size_idx];
        struct list_head *head = &rt->arena_state.free_arena_list[block_size_idx], *el = head->next;
        JSArena *ar = unlikely(el == head) ? arena_new(rt, block_size_idx) : list_entry(el, JSArena, free_link);
        if (unlikely(!ar)) return NULL;
        unsigned int block_idx = ar->first_free_block;
        JSMallocBlockHeader *b = arena_get_block(ar, block_idx, block_size);
        ar->first_free_block = b->u.free_next;
        b->u.block_idx = block_idx;
        if (unlikely(++ar->n_used_blocks == ar->n_blocks)) list_del(&ar->free_link);
        *pusable = block_size - sizeof(JSMallocBlockHeader);
        return b->user_data;
    }
    void *ptr = arena_malloc_large(rt, size);
    if (ptr) *pusable = js_arena_usable_size(rt, ptr);
    return ptr;
}
static void *js_arena_malloc(JSRuntime *rt, size_t size)
{ size_t u; return js_arena_malloc_fast(rt, size, &u); }""",
    )
    text = replace_exact_lines(
        text,
        """void *js_malloc_rt(JSRuntime *rt, size_t size)
{
    void *ptr;
    JSMallocState *s;

    /* Do not allocate zero bytes: behavior is platform dependent */
    if (unlikely(size == 0))
        return NULL;

    s = &rt->malloc_state;
    /* When malloc_limit is 0 (unlimited), malloc_limit - 1 will be SIZE_MAX. */
    if (unlikely(s->malloc_size + size > s->malloc_limit - 1))
        return NULL;

    ptr = js_arena_malloc(rt, size);
    if (!ptr)
        return NULL;

    s->malloc_count++;
    s->malloc_size += js_arena_usable_size(rt, ptr) + MALLOC_OVERHEAD;
    return ptr;
}""",
        """void *js_malloc_rt(JSRuntime *rt, size_t size)
{
    void *ptr; JSMallocState *s; size_t usable = 0;
    if (unlikely(size == 0)) return NULL;
    s = &rt->malloc_state;
    if (unlikely(s->malloc_size + size > s->malloc_limit - 1)) return NULL;
    ptr = js_arena_malloc_fast(rt, size, &usable);
    if (unlikely(!ptr)) return NULL;
    s->malloc_count++;
    s->malloc_size += usable + MALLOC_OVERHEAD;
    return ptr;
}""",
    )
    text = replace_exact_lines(
        text,
        """void js_free_rt(JSRuntime *rt, void *ptr)
{
    JSMallocState *s;

    if (!ptr)
        return;

    s = &rt->malloc_state;
    size_t free_size = js_arena_usable_size(rt, ptr) + MALLOC_OVERHEAD;
    if (unlikely(free_size > s->malloc_size)) {
        printf("js_free_rt: malloc_size underflow: freeing %zu but only %zu tracked\\n", free_size, s->malloc_size);
        abort();
    }
    s->malloc_count--;
    s->malloc_size -= free_size;
    js_arena_free(rt, ptr);
}""",
        """void js_free_rt(JSRuntime *rt, void *ptr)
{   if (!ptr) return;
    JSMallocState *s = &rt->malloc_state;
    JSMallocBlockHeader *b = container_of(ptr, JSMallocBlockHeader, user_data);
    if (likely(b->u.block_idx != JS_ARENA_FREE_NIL)) {
        unsigned int bidx = b->u.block_idx, sidx = b->block_size_idx, bsz = arena_block_sizes[sidx];
        size_t free_size = bsz - sizeof(JSMallocBlockHeader) + MALLOC_OVERHEAD;
        if (unlikely(free_size > s->malloc_size)) { printf("js_free_rt: malloc_size underflow: freeing %zu but only %zu tracked\\n", free_size, s->malloc_size); abort(); }
        s->malloc_count--; s->malloc_size -= free_size;
        JSArena *ar = (JSArena *)((uint8_t *)b - (size_t)bsz * bidx - sizeof(JSArena));
        b->u.free_next = ar->first_free_block; ar->first_free_block = bidx;
        if (unlikely(ar->n_used_blocks == ar->n_blocks)) list_add(&ar->free_link, &rt->arena_state.free_arena_list[sidx]);
        if (unlikely(--ar->n_used_blocks == 0)) { list_del(&ar->link); list_del(&ar->free_link); rt->mf.js_free(s->opaque, ar); }
        return;
    }
    size_t free_size = js_arena_usable_size(rt, ptr) + MALLOC_OVERHEAD; if (unlikely(free_size > s->malloc_size)) { printf("js_free_rt: malloc_size underflow: freeing %zu but only %zu tracked\\n", free_size, s->malloc_size); abort(); } s->malloc_count--; s->malloc_size -= free_size; js_arena_free(rt, ptr);
}""",
    )

    # 2. Include hybrid-gc.h cleanly right before js_trigger_gc while preserving line numbers
    dup_trigger_old = (
        "JSValue JS_DupValueRT(JSRuntime *rt, JSValueConst v)\n"
        "{\n"
        "    return js_dup(v);\n"
        "}\n\n"
        "static void js_trigger_gc(JSRuntime *rt, size_t size)"
    )
    dup_trigger_new = (
        "JSValue JS_DupValueRT(JSRuntime *rt, JSValueConst v) { return js_dup(v); }\n\n"
        '#include "src/common/memory/hybrid-gc.h"\n\n\n'
        "static void js_trigger_gc(JSRuntime *rt, size_t size)"
    )
    text = replace_exact_lines(text, dup_trigger_old, dup_trigger_new)

    # 3. Restore static inline threshold check in js_trigger_gc -> slow-path helper
    trigger_old = """static void js_trigger_gc(JSRuntime *rt, size_t size)
{
    bool force_gc;
#ifdef FORCE_GC_AT_MALLOC
    force_gc = true;
#else
    force_gc = ((rt->malloc_state.malloc_size + size) >
                rt->malloc_gc_threshold);
#endif
    if (force_gc) {
#ifdef ENABLE_DUMPS // JS_DUMP_GC
        if (check_dump_flag(rt, JS_DUMP_GC)) {
            printf("GC: size=%zd\\n", rt->malloc_state.malloc_size);
        }
#endif
        JS_RunGC(rt);
        rt->malloc_gc_threshold = rt->malloc_state.malloc_size +
            (rt->malloc_state.malloc_size >> 1);
    }
}"""
    trigger_new = """static inline void js_trigger_gc(JSRuntime *rt, size_t size)
{
#ifdef FORCE_GC_AT_MALLOC
    js_hybrid_trigger_gc_slow(rt);
#else
    if (unlikely((rt->malloc_state.malloc_size + size) >
                 rt->malloc_gc_threshold)) {
        js_hybrid_trigger_gc_slow(rt);
    }
#endif
}"""
    text = replace_exact_lines(text, trigger_old, trigger_new)

    # 4. Lifecycle hooks: JS_NewRuntime2, JS_FreeRuntime, JS_FreeContext
    text = replace_exact_lines(
        text,
        "    init_list_head(&rt->gc_zero_ref_count_list);\n    rt->gc_phase = JS_GC_PHASE_NONE;",
        "    init_list_head(&rt->gc_zero_ref_count_list);\n    rt->gc_phase = JS_GC_PHASE_NONE; js_hybrid_gc_init(rt, mf);",
    )
    text = replace_exact_lines(
        text,
        "    rt->in_free = true;\n    JS_FreeValueRT(rt, rt->current_exception);",
        "    rt->in_free = true; js_hybrid_on_free_runtime(rt);\n    JS_FreeValueRT(rt, rt->current_exception);",
    )
    text = replace_exact_lines(
        text,
        "    list_del(&ctx->link);\n    remove_gc_object(&ctx->header);\n    js_free_rt(ctx->rt, ctx);",
        "    js_hybrid_unlink_boundary(rt); list_del(&ctx->link);\n    remove_gc_object(&ctx->header);\n    js_free_rt(ctx->rt, ctx);",
    )

    # 5. Core GC & RC hooks: js_free_value_rt, add_gc_object, JS_RunGC, include hybrid-gc.inc
    #    JS_FreeValueRT and JS_FreeValue stay 100% untouched upstream frameless leaves!
    text = replace_exact_lines(
        text,
        """            if (rt->gc_phase != JS_GC_PHASE_REMOVE_CYCLES) {
                list_del(&p->link);
                list_add(&p->link, &rt->gc_zero_ref_count_list);
                if (rt->gc_phase == JS_GC_PHASE_NONE) {
                    free_zero_refcount(rt);
                }
            }""",
        """            if (rt->gc_phase != JS_GC_PHASE_REMOVE_CYCLES) {
                if (rt->hybrid_free_active) { list_del(&p->link); p->link.next = (struct list_head *)rt->hybrid_free_stack; rt->hybrid_free_stack = p; }
                else if (rt->gc_phase == JS_GC_PHASE_NONE && tag == JS_TAG_OBJECT && (rt->hybrid_gc_mode & JS_HYBRID_MODE_FAST_RC) && !js_hybrid_dump_free_enabled(rt)) { js_hybrid_free_object_root(rt, p); }
                else { list_del(&p->link); list_add(&p->link, &rt->gc_zero_ref_count_list); if (rt->gc_phase == JS_GC_PHASE_NONE) { free_zero_refcount(rt); } }
            } else if (JS_GC_MARK(p) == 0) { JS_GC_MARK(p) = 1; list_del(&p->link); list_add_tail(&p->link, &rt->tmp_obj_list); }""",
    )
    text = replace_exact_lines(
        text,
        "    JS_GC_MARK(h) = 0;\n    JS_GC_TYPE(h) = type;\n    list_add_tail(&h->link, &rt->gc_obj_list);",
        "    JS_GC_MARK(h) = 0; JS_HYBRID_YOUNG(h) = 0;\n    JS_GC_TYPE(h) = type;\n    list_add_tail(&h->link, &rt->gc_obj_list);",
    )
    text = replace_exact_lines(
        text,
        """void JS_RunGC(JSRuntime *rt)
{
    /* decrement the reference of the children of each object. mark =
       1 after this pass. */
    gc_decref(rt);

    /* keep the GC objects with a non zero refcount and their childs */
    gc_scan(rt);

    /* free the GC objects in a cycle */
    gc_free_cycles(rt);
}""",
        """void JS_RunGC(JSRuntime *rt)
{
    js_hybrid_run_full_gc(rt);
}""",
    )
    text = replace_exact_lines(
        text,
        "\n\n/* Return false if not an object or if the object has already been",
        '\n#include "src/common/memory/hybrid-gc.inc"\n/* Return false if not an object or if the object has already been',
    )

    if text.count("\n") != before_lines:
        raise ValueError("Hybrid GC overlay changed logical line count")
    return text
