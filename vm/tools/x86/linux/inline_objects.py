"""Wire the shared co-allocation owner for ordinary Linux objects only."""

from c_workers import replace_one


def core_storage(core, *, property_ic):
    def change(old, new, label):
        nonlocal core
        core = replace_one(core, old, new, label)

    change(
        "static no_inline int resize_properties(JSContext *ctx, JSShape **psh,",
        '#include "src/common/property/inline-properties.h"\n'
        "#define QJS_HYBRID_INLINE_PROPERTIES 1\n\n"
        "static no_inline int resize_properties(JSContext *ctx, JSShape **psh,",
        "Linux property storage helper types",
    )
    change(
        "    js_trigger_gc(ctx->rt, sizeof(JSObject));\n    p = js_malloc(ctx, sizeof(JSObject));",
        "    /* Reserve extra slots only when the caller supplies a complete payload. */\n"
        "    size_t inline_bytes = class_id == JS_CLASS_OBJECT\n"
        "        ? qjs_inline_property_plan(sh, 0, props ? 4u : 0u) : 0;\n"
        "    size_t object_bytes = inline_bytes ? inline_bytes : sizeof(JSObject);\n"
        "    js_trigger_gc(ctx->rt, object_bytes);\n"
        "    p = js_malloc(ctx, object_bytes);",
        "Linux plain-object allocation",
    )
    change(
        "    p->is_prototype = 0;\n    p->first_weak_ref = NULL;",
        "    p->__gc_mark = 0;\n    p->is_prototype = 0;\n    p->first_weak_ref = NULL;",
        "initialize inline bit before installing GC header",
    )
    change(
        "    p->prop = js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);",
        "    p->prop = inline_bytes ? qjs_inline_property_initialize(p, sh, 0, inline_bytes)\n"
        "                           : js_malloc(ctx, sizeof(JSProperty) * sh->prop_size);",
        "ordinary property storage owner",
    )
    old = "js_realloc(ctx, p->prop, sizeof(new_prop[0]) * new_size)"
    if core.count(old) != 2:
        raise ValueError("Review both property growth and compaction")
    core = core.replace(
        old, old.replace("js_realloc(ctx, p->prop,", "qjs_inline_property_realloc(ctx, p,")
    )
    change(
        "js_realloc(ctx, p->prop, sizeof(p->prop[0]) *",
        "qjs_inline_property_realloc(ctx, p, sizeof(p->prop[0]) *",
        "resized hashed property transition",
    )
    change(
        "    js_free_rt(rt, p->prop);",
        "    if (!qjs_inline_property_current(p))\n        js_free_rt(rt, p->prop);",
        "ordinary destruction (Hybrid GC uses its existing inline guard)",
    )
    change(
        "            s->prop_count += sh->prop_count;",
        "            s->prop_count += sh->prop_count;\n            qjs_inline_property_account(s, p);",
        "memory usage excludes phantom property allocation",
    )
    if property_ic:
        change(
            '#include "src/common/property/property-ic.inc"',
            '#include "src/common/property/inline-property-ic-storage.inc"',
            "co-allocated property IC resize",
        )
    return core
