"""One declared whole closure-initialization template overlay; pinned core held."""

import hashlib

FUNCTIONS = {
    "JS_NewObjectFromShape": (
        "static JSValue JS_NewObjectFromShape(",
        "e81578f4a6807b1dc97b49c2698b213e277cb2f764bd1543f15534ac6223c58c",
    ),
    "js_closure2": (
        "static JSValue js_closure2(",
        "faa7a9dde472205ed040a4affe635167a5ce6a0a1ec0bc61b51028ac56abc89c",
    ),
    "js_create_module_bytecode_function": (
        "static int js_create_module_bytecode_function(JSContext *ctx, JSModuleDef *m)\n{",
        "97af52a0177b4a49689c4ff76b799c0db8c26e2e6888ec944370724be7b1e859",
    ),
    "js_bytecode_function_finalizer": (
        "static void js_bytecode_function_finalizer(JSRuntime *rt, JSValueConst val)\n{",
        "a86601630b3c36538340dba432f9c2275f59d00cac12fa35210eaa433fd29d92",
    ),
    "JS_ComputeMemoryUsage": (
        "void JS_ComputeMemoryUsage(",
        "41029f7c34eb2757a7e949dccf6eda4f87ff03564701582119e2037647e5094a",
    ),
    "js_closure": (
        "static JSValue js_closure(",
        "36914e62e3cbfcc4bce34b2937addbf103fbc895dfa814e669124315dd0c087c",
    ),
    "JS_SetClassProto": (
        "void JS_SetClassProto(",
        "6f1c2db0de596392858cfed2584f7f918d191292971be5f83b2640cca18b0d28",
    ),
    "JS_MarkContext": (
        "static void JS_MarkContext(",
        "cc92ca16a9759ba20dc7270edb78dc8acc6af6a3e6beb2c06bada12a3c8e55e3",
    ),
    "JS_FreeContext": (
        "void JS_FreeContext(",
        "6e60f4c57e0d73aaae2f85834fd7a84e3259ffb3221c096ad608a38abff6cb2a",
    ),
    "JS_NewCFunctionData2": (
        "JSValue JS_NewCFunctionData2(",
        "c2836ead6163f7dd8a4aa0e5aa48ee76538cbc949c52d08fd20d306860aa5c28",
    ),
    "js_create_resolving_functions": (
        "static int js_create_resolving_functions(JSContext *ctx,\n                                         JSValue *resolving_funcs,\n                                         JSValueConst promise)\n\n{",
        "85b4294240c01eec5c83727c98415f5cf7b90c5c43ef80dc2ae73856d7ff3ba9",
    ),
}


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    assert old.count("\n") == new.count("\n"), "Keep original logical source lines"
    return text.replace(old, new, 1)


def private_types(text, conditional=False):
    obj_old = "    uint8_t is_HTMLDDA : 1; /* specific annex B IsHtmlDDA behavior */"
    if obj_old in text:
        if conditional:
            assert text.count(obj_old) == 1
            text = text.replace(
                obj_old,
                obj_old + "\n#ifdef QJS_PROPERTY_IC\n    uint8_t turbo_obj_flags : 7;\n#endif",
                1,
            )
        else:
            text = replace_once(
                text,
                obj_old,
                "    uint8_t is_HTMLDDA : 1; uint8_t turbo_obj_flags : 7; /* specific annex B IsHtmlDDA behavior */",
            )
    old = "    void *user_opaque;\n};"
    if old not in text:
        return text
    extra = (
        "JSShape *closure_template_shapes[4]; uint32_t closure_template_mode; "
        "JSShape *internal_function_shape; uint32_t internal_function_mode;"
    )
    if conditional:
        new = "    void *user_opaque;\n#ifdef QJS_PROPERTY_IC\n    " + extra + "\n#endif\n};"
        assert text.count(old) == 1
        return text.replace(old, new, 1)
    return replace_once(text, old, "    void *user_opaque; " + extra + "\n};")


def core_overlay(text, raw):
    for name, (signature, expected) in FUNCTIONS.items():
        start = raw.index(signature)
        end = raw.index("\n}\n", start) + 3
        assert hashlib.sha256(raw[start:end].encode()).hexdigest() == expected, name
    before = text.count("\n")
    text = replace_once(
        text,
        "\n\nvoid JS_SetClassProto(",
        '\n#include "src/common/function/closure-template-lifetime.inc"\nvoid JS_SetClassProto(',
    )
    text = replace_once(
        text,
        "    set_value(ctx, &ctx->class_proto[class_id], obj);",
        "    js_closure_templates_set_class_proto(ctx, class_id, obj);",
    )
    text = replace_once(
        text,
        "        mark_func(rt, &ctx->array_shape->header);",
        "        mark_func(rt, &ctx->array_shape->header); for (int t = 0; t < 4; t++) if (ctx->closure_template_shapes[t]) mark_func(rt, &ctx->closure_template_shapes[t]->header); if (ctx->internal_function_shape) mark_func(rt, &ctx->internal_function_shape->header);",
    )
    text = replace_once(
        text,
        "    assert(JS_REF_COUNT(ctx) == 0);",
        "    assert(JS_REF_COUNT(ctx) == 0); ctx->closure_template_mode = 2; ctx->internal_function_mode = 2;",
    )
    text = replace_once(
        text,
        "    js_free_shape_null(ctx->rt, ctx->array_shape);",
        "    js_free_shape_null(ctx->rt, ctx->array_shape); js_closure_templates_cleanup(ctx);",
    )
    text = replace_once(
        text,
        "    p->is_prototype = 0;",
        "    p->is_prototype = 0; p->turbo_obj_flags = 0;",
    )
    text = replace_once(
        text,
        "static JSValue js_closure(JSContext *ctx, JSValue bfunc,",
        "static JSValue js_closure_template_original(JSContext *ctx, JSValue bfunc,",
    )
    text = replace_once(
        text,
        "\n\n#define JS_DEFINE_CLASS_HAS_HERITAGE",
        '\n#include "src/common/function/closure-template.inc"\n#define JS_DEFINE_CLASS_HAS_HERITAGE',
    )
    text = replace_once(
        text,
        "            js_free_rt(rt, var_refs);\n        }\n        JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_FUNCTION_BYTECODE, b));",
        "            if (!(p->turbo_obj_flags & 64)) js_free_rt(rt, var_refs);\n        }\n        JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_FUNCTION_BYTECODE, b));",
    )
    text = replace_once(
        text,
        "                    s->memory_used_count++;\n                    s->js_func_size += b->closure_var_count * sizeof(*var_refs);",
        "                    if (!(p->turbo_obj_flags & 64)) s->memory_used_count++;\n                    s->js_func_size += b->closure_var_count * sizeof(*var_refs);",
    )
    # Use private bit 6 in turbo_obj_flags, independent of GC mark/type and
    # prototype bit. Every ordinary bytecode-function publisher clears it.
    old = "    p->u.func.function_bytecode = b;"
    assert text.count(old) == 2
    text = text.replace(old, old + " p->turbo_obj_flags &= ~64;")
    text = replace_once(
        text,
        "\n\nJSValue JS_NewCFunctionData2(",
        '\n#include "src/common/function/internal-function-template.inc"\nJSValue JS_NewCFunctionData2(',
    )
    for signature, allocation, replacement in (
        (
            "JSValue JS_NewCFunctionData2(",
            "    func_obj = JS_NewObjectProtoClass(ctx, ctx->function_proto,\n                                      JS_CLASS_C_FUNCTION_DATA);",
            "    func_obj = js_internal_function_object(ctx, ctx->function_proto,\n                                      JS_CLASS_C_FUNCTION_DATA, !name || !*name);",
        ),
        (
            FUNCTIONS["js_create_resolving_functions"][0],
            "        obj = JS_NewObjectProtoClass(ctx, ctx->function_proto,\n                                     JS_CLASS_PROMISE_RESOLVE_FUNCTION + i);",
            "        obj = js_internal_function_object(ctx, ctx->function_proto,\n                                     JS_CLASS_PROMISE_RESOLVE_FUNCTION + i, true);",
        ),
    ):
        start = text.index(signature)
        end = text.index("\n}\n", start) + 3
        original = text[start:end]
        body = replace_once(original, allocation, replacement)
        assert body.count("js_function_set_properties(ctx,") == 1
        body = body.replace(
            "js_function_set_properties(ctx,", "js_internal_function_finish_properties(ctx,"
        )
        text = text[:start] + body + text[end:]
    assert text.count("\n") == before
    return text
