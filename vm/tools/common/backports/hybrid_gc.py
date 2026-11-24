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
