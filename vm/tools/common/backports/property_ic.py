"""Declared property IC overlay. Preserve upstream input bytes and core lines.

Append private runtime/bytecode fields and use the measured shape padding;
every existing native offset remains measured by the pinned ABI.
"""


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Property IC source anchor changed: " + old[:100])
    if new.count("\n") > old.count("\n"):
        raise ValueError("Property IC overlay must retain logical source lines")
    new += "\n" * (old.count("\n") - new.count("\n"))
    return text.replace(old, new, 1)


def private_types(text, conditional=False):
    fields = [
        ("    uint8_t is_hashed;", "uint8_t property_ic_refs[3];"),
        (
            "    JSRuntimeFinalizerState *finalizers;",
            "uint64_t property_ic_epoch; uint32_t property_ic_mode, property_ic_gc_mode; struct JSPropertyIC *property_ic_list; uint32_t property_ic_warmup;",
        ),
        ("    char *source;\n} JSFunctionBytecode;", "struct JSPropertyIC *property_ic;"),
    ]
    for old, extra in fields:
        if old not in text:
            continue  # Private-source extractor unit fixtures need no engine types.
        if conditional:
            if old.endswith("JSFunctionBytecode;"):
                new = (
                    "    char *source;\n#ifdef QJS_PROPERTY_IC\n    "
                    + extra
                    + "\n#endif\n} JSFunctionBytecode;"
                )
            else:
                new = old + "\n#ifdef QJS_PROPERTY_IC\n    " + extra + "\n#endif"
            text = text.replace(old, new, 1)
        else:
            new = old.replace(";\n}", "; " + extra + "\n}") if "\n}" in old else old + " " + extra
            text = replace_once(text, old, new)
    from closure_templates import private_types as closure_private_types

    return closure_private_types(text, conditional)


def opcode_body(name):
    if name in ("get_field", "get_field2"):
        finish = (
            "JS_FreeValue(ctx, sp[-1]); sp[-1] = value;"
            if name == "get_field"
            else "*sp++ = value;"
        )
        return (
            """            { JSAtom atom = get_u32(pc); JSValue value; pc += 4;
                sf->cur_pc = pc;
                value = js_property_ic_get(ctx, b, pc - 5, sp[-1], atom);
                if (unlikely(JS_IsException(value))) goto exception;
                """
            + finish
            + """
            }
            BREAK;
"""
        )
    if name == "put_field":
        return """            { JSAtom atom = get_u32(pc); int ret; pc += 4;
                sf->cur_pc = pc;
                ret = js_property_ic_put(ctx, b, pc - 5, sp[-2], atom, sp[-1]);
                JS_FreeValue(ctx, sp[-2]); sp -= 2;
                if (unlikely(ret < 0)) goto exception;
            }
            BREAK;
"""
    raise ValueError(name)


def opcode_guard(name):
    slot = "-2" if name == "put_field" else "-1"
    return (
        "JS_VALUE_GET_TAG(sp[" + slot + "]) == JS_TAG_OBJECT && "
        "!JS_VALUE_GET_OBJ(sp[" + slot + "])->is_exotic && "
        "JS_VALUE_GET_OBJ(sp[" + slot + "])->shape->is_hashed && "
        "ctx->rt->property_ic_mode == 1 && "
        "b->property_ic != (struct JSPropertyIC *)(uintptr_t)1"
    )


def opcode_with_fallback(name, original, core=False):
    """Leave dictionary/primitive/OFF operations in the original inline body."""
    opening = "\n            {"
    if original.count(opening) != 1:
        raise ValueError("Property opcode opening changed: " + name)
    fast = opcode_body(name).strip()
    if core:
        # This boundary has no preprocessor statements. Keep every old line ID
        # and original branch body while adding one declared IC eligibility arm.
        fast = " ".join(fast.splitlines())
        return original.replace(
            opening, opening + " if (" + opcode_guard(name) + ") { " + fast + " }", 1
        )
    return original.replace(
        opening,
        opening + "\n#ifdef QJS_PROPERTY_IC\n"
        "                if ("
        + opcode_guard(name)
        + ") {\n"
        + opcode_body(name)
        + "                }\n#endif",
        1,
    )


def core_overlay(text):
    text = private_types(text)
    marker = "static inline bool double_is_int32"
    text = replace_once(
        text, "\n\n" + marker, '\n#include "src/common/property/property-ic.h"\n' + marker
    )
    text = replace_once(
        text,
        "    rt->js_class_id_alloc = JS_CLASS_INIT_COUNT;",
        '    rt->js_class_id_alloc = JS_CLASS_INIT_COUNT; rt->property_ic_epoch = 1; rt->property_ic_mode = qjs_turbo_default_property_ic_mode(); rt->property_ic_gc_mode = getenv("QJS_DISABLE_PROPERTY_IC_WEAK_PROTO") ? JS_IC_RETAIN_ORPHANS : 0; rt->property_ic_warmup = qjs_turbo_default_property_ic_warmup();',
    )
    text = replace_once(
        text,
        "    sh->proto = proto;\n    /* prop_hash_mask must be set",
        "    sh->proto = proto; if (proto) proto->is_prototype = true;\n    /* prop_hash_mask must be set",
    )
    # Allocation/cloning assign is_hashed=0/1. Its private validity bit makes
    # their padding unreadable until the first cache edge initializes it.
    # is_hashed remains boolean to all semantic users; normalize debug indexing.
    assert text.count('" *"[sh->is_hashed]') == 2
    text = text.replace('" *"[sh->is_hashed]', '" *"[!!sh->is_hashed]')
    # Other separately compiled allocation modules call this exact C boundary.
    text = replace_once(
        text,
        "static void js_free_shape0(JSRuntime *rt, JSShape *sh)\n{",
        "static no_inline void js_free_shape0(JSRuntime *rt, JSShape *sh)\n{",
    )
    text = replace_once(
        text,
        "static JSShape *js_dup_shape(JSShape *sh)\n{\n    JS_REF_COUNT(sh)++;\n    return sh;\n}",
        "static JSShape *js_dup_shape(JSShape *sh)\n{\n    return js_property_ic_acquire_shape_ref(sh);\n}",
    )
    text = replace_once(
        text,
        "    if (sh->proto != NULL) {\n        JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_OBJECT, sh->proto));",
        "    if (sh->proto != NULL && !(sh->is_hashed & JS_IC_PROTO_WEAK)) {\n        JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_OBJECT, sh->proto));",
    )
    text = replace_once(
        text,
        "            if (sh->proto != NULL) {\n                mark_func(rt, &sh->proto->header);",
        "            if (sh->proto != NULL && !(sh->is_hashed & JS_IC_PROTO_WEAK)) {\n                mark_func(rt, &sh->proto->header);",
    )
    text = replace_once(
        text,
        "    p->free_mark = 1; /* used to tell the object is invalid when",
        "    if (p->is_prototype) js_property_ic_prototype_free(rt, p); p->free_mark = 1; /* used to tell the object is invalid when",
    )
    text = replace_once(
        text,
        "        js_free_shape0(rt, sh);\n    }\n}\n\nstatic void js_free_shape_null",
        "        js_free_shape0(rt, sh);\n    } else if (js_property_ic_shape_refs(sh) && (uint32_t)JS_REF_COUNT(sh) == js_property_ic_shape_refs(sh)) { js_property_ic_shape_released(rt, sh); }\n}\n\nstatic void js_free_shape_null",
    )
    text = replace_once(
        text,
        "    if (unlikely(p->is_prototype)) {\n        /* track addition",
        "    js_property_ic_invalidate_proto(ctx, p); if (unlikely(p->is_prototype)) {\n        /* track addition",
    )
    start = text.rindex("static int js_shape_prepare_update(JSContext *ctx, JSObject *p,\n")
    end = text.index("\nstatic int js_update_property_flags", start)
    body = text[start:end]
    body = replace_once(
        body, "    sh = p->shape;", "    js_property_ic_invalidate_proto(ctx, p); sh = p->shape;"
    )
    text = text[:start] + body + text[end:]
    text = replace_once(
        text,
        "            int i;\n            for(i = 0; i < b->cpool_count; i++) {",
        "            int i; js_property_ic_mark(rt, b, mark_func);\n            for(i = 0; i < b->cpool_count; i++) {",
    )
    text = replace_once(
        text,
        "static void free_function_bytecode(JSRuntime *rt, JSFunctionBytecode *b)\n{\n    int i;",
        "static void free_function_bytecode(JSRuntime *rt, JSFunctionBytecode *b)\n{\n    int i; js_property_ic_free(rt, b);",
    )
    start = text.index("static void gc_scan(JSRuntime *rt)\n{")
    end = text.index("\nstatic void gc_free_cycles", start)
    scan = text[start:end]
    scan = replace_once(
        scan,
        "    struct list_head *el;",
        "    struct list_head *el, *ic_cursor; rt->property_ic_gc_mode |= JS_IC_GC_SCAN;",
    )
    scan = replace_once(
        scan,
        "    /* restore the refcount of the objects to be deleted. */",
        "    ic_cursor = rt->gc_obj_list.prev; while (js_property_ic_gc_propagate(rt, gc_scan_incref_child)) { while (ic_cursor->next != &rt->gc_obj_list) { ic_cursor = ic_cursor->next; p = list_entry(ic_cursor, JSGCObjectHeader, link); mark_children(rt, p, gc_scan_incref_child); } } js_property_ic_gc_restore(rt); rt->property_ic_gc_mode &= ~JS_IC_GC_SCAN; /* restore the refcount of the objects to be deleted. */",
    )
    scan = replace_once(
        scan,
        "        mark_children(rt, p, gc_scan_incref_child2);\n    }",
        "        mark_children(rt, p, gc_scan_incref_child2);\n    } rt->gc_phase = JS_GC_PHASE_REMOVE_CYCLES; js_property_ic_gc_prune(rt); rt->gc_phase = JS_GC_PHASE_NONE;",
    )
    text = text[:start] + scan + text[end:]
    text = replace_once(
        text,
        "    js_free_rt(rt, rt->atom_hash);\n    js_free_rt(rt, rt->shape_hash);",
        "    js_free_rt(rt, rt->atom_hash);\n    js_free_rt(rt, rt->shape_hash); assert(rt->property_ic_list == NULL);",
    )
    text = replace_once(
        text,
        "    js_func_size = sizeof(*b);\n",
        "    js_func_size = sizeof(*b); js_func_size += js_property_ic_memory_size(b, &memory_used_count);\n",
    )
    # Reuse one of the existing blank lines; preserve all subsequent line IDs.
    anchor = "\n\nstatic int JS_SetPropertyInternal(JSContext *ctx, JSValueConst obj, JSAtom prop,"
    text = replace_once(
        text,
        anchor,
        '\n#include "src/common/property/property-ic.inc"\nstatic int JS_SetPropertyInternal(JSContext *ctx, JSValueConst obj, JSAtom prop,',
    )
    text = replace_once(
        text,
        "                val = JS_GetGlobalVar(ctx, atom, opcode - OP_get_var_undef);",
        "                val = js_global_binding_cell_get(ctx, b, pc - 5, atom, opcode - OP_get_var_undef);",
    )
    for name in ("get_field", "get_field2", "put_field"):
        start = text.index("        CASE(OP_" + name + "):")
        end = text.index("        CASE(", start + 1)
        old = text[start:end]
        text = replace_once(text, old, opcode_with_fallback(name, old, core=True))
    return text
