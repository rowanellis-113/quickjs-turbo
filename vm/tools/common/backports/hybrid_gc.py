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
    has_fp = "FramePool_NewRuntime" in text

    # 1. Reorder JSGCObjectTypeEnum + struct JSGCObjectHeader right before struct JSRuntime
    #    so JSRuntime can embed JSGCObjectHeader hybrid_gc_boundary_node inline without changing
    #    line numbers or existing offsets, and split gc_obj_type : 4 into 3 + 1 for UBSan safety.
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
        " JSGCObjectHeader hybrid_gc_boundary_node;"
        " JSGCObjectHeader *hybrid_free_stack;"
        " size_t hybrid_gc_full_malloc;"
        " uint64_t hybrid_gc_full_count, hybrid_gc_minor_count, hybrid_gc_skipped_count, hybrid_gc_fast_frees;"
        " uint32_t hybrid_gc_mode, hybrid_gc_minor_since_full;"
        " uint8_t hybrid_gc_boundary_linked, hybrid_gc_report, drc_ok, is_frame_pool, hybrid_free_active;"
    )
    rt_part = rt_final_re.sub(r"\1" + rt_fields + r"\n\2", rt_part, count=1)

    gc_bit_old = "    JSGCObjectTypeEnum gc_obj_type : 4;"
    gc_bit_new = "    JSGCObjectTypeEnum gc_obj_type : 3; uint8_t hybrid_young : 1;"
    if gc_part.count(gc_bit_old) != 1:
        raise ValueError("JSGCObjectHeader bitfield anchor missing")
    gc_part = gc_part.replace(gc_bit_old, gc_bit_new, 1)

    new_block = gc_part + rt_part
    if new_block.count("\n") != block.count("\n"):
        raise ValueError("Header reorder changed line count")
    text = text[:rt_start] + new_block + text[varref_start:]

    # 2. Include hybrid-gc.h cleanly right before js_trigger_gc while preserving line numbers
    dup_trigger_old = (
        "JSValue JS_DupValueRT(JSRuntime *rt, JSValueConst v)\n"
        "{\n"
        "    return js_dup(v);\n"
        "}\n\n"
        "static void js_trigger_gc(JSRuntime *rt, size_t size)"
    )
    dup_trigger_new = (
        "JSValue JS_DupValueRT(JSRuntime *rt, JSValueConst v) { return js_dup(v); }\n"
        + ("#define QJS_HYBRID_HAS_FRAME_POOL 1\n" if has_fp else "\n")
        + '#include "src/common/memory/hybrid-gc.h"\n\n\n'
        + "static void js_trigger_gc(JSRuntime *rt, size_t size)"
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

    # 4. Inline pool usable-size lookup inside core allocators
    text = replace_exact_lines(
        text,
        "    s->malloc_count++;\n    s->malloc_size += rt->mf.js_malloc_usable_size(ptr) + MALLOC_OVERHEAD;\n    return ptr;\n}\n\nvoid *js_malloc_rt",
        "    s->malloc_count++;\n    s->malloc_size += js_hybrid_usable_size_nonnull(rt, ptr) + MALLOC_OVERHEAD;\n    return ptr;\n}\n\nvoid *js_malloc_rt",
    )
    text = replace_exact_lines(
        text,
        "    s->malloc_count++;\n    s->malloc_size += rt->mf.js_malloc_usable_size(ptr) + MALLOC_OVERHEAD;\n    return ptr;\n}\n\nvoid js_free_rt",
        "    s->malloc_count++;\n    s->malloc_size += js_hybrid_usable_size_nonnull(rt, ptr) + MALLOC_OVERHEAD;\n    return ptr;\n}\n\nvoid js_free_rt",
    )
    text = replace_exact_lines(
        text,
        "    s = &rt->malloc_state;\n    size_t free_size = rt->mf.js_malloc_usable_size(ptr) + MALLOC_OVERHEAD;",
        "    s = &rt->malloc_state;\n    size_t free_size = js_hybrid_usable_size_nonnull(rt, ptr) + MALLOC_OVERHEAD;",
    )
    text = replace_exact_lines(
        text,
        """    old_size = rt->mf.js_malloc_usable_size(ptr);
    s = &rt->malloc_state;
    /* When malloc_limit is 0 (unlimited), malloc_limit - 1 will be SIZE_MAX. */
    if (s->malloc_size + size - old_size > s->malloc_limit - 1)
        return NULL;

    ptr = rt->mf.js_realloc(s->opaque, ptr, size);
    if (!ptr)
        return NULL;

    s->malloc_size += rt->mf.js_malloc_usable_size(ptr) - old_size;""",
        """    old_size = js_hybrid_usable_size_nonnull(rt, ptr);
    s = &rt->malloc_state;
    /* When malloc_limit is 0 (unlimited), malloc_limit - 1 will be SIZE_MAX. */
    if (s->malloc_size + size - old_size > s->malloc_limit - 1)
        return NULL;

    ptr = rt->mf.js_realloc(s->opaque, ptr, size);
    if (!ptr)
        return NULL;

    s->malloc_size += js_hybrid_usable_size_nonnull(rt, ptr) - old_size;""",
    )
    text = replace_exact_lines(
        text,
        "size_t js_malloc_usable_size_rt(JSRuntime *rt, const void *ptr)\n{\n    return rt->mf.js_malloc_usable_size(ptr);\n}",
        "size_t js_malloc_usable_size_rt(JSRuntime *rt, const void *ptr)\n{\n    return js_hybrid_usable_size(rt, ptr);\n}",
    )

    # 5. Lifecycle hooks: JS_NewRuntime2, JS_FreeRuntime, JS_FreeContext
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

    # 6. Core GC & RC hooks: js_free_value_rt, add_gc_object, JS_RunGC, include hybrid-gc.inc
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
            } else if (p->mark == 0) { p->mark = 1; list_del(&p->link); list_add_tail(&p->link, &rt->tmp_obj_list); }""",
    )
    text = replace_exact_lines(
        text,
        "    h->mark = 0;\n    h->gc_obj_type = type;\n    list_add_tail(&h->link, &rt->gc_obj_list);",
        "    h->mark = 0; h->hybrid_young = 0;\n    h->gc_obj_type = type;\n    list_add_tail(&h->link, &rt->gc_obj_list);",
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
