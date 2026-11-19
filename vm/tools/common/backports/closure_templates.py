"""One declared whole closure-initialization template overlay; pinned core held."""

import hashlib

FUNCTIONS = {
    "JS_NewObjectFromShape": (
        "static JSValue JS_NewObjectFromShape(",
        "ad9d8d6ad2352e4d244447a926ef02424c71344f0660d911b83f6e4619b007b7",
    ),
    "js_closure2": (
        "static JSValue js_closure2(",
        "330f7c7d9d45d6224605281d1053e1dce77cfa164875d7a3954a54f36331f396",
    ),
    "js_create_module_bytecode_function": (
        "static int js_create_module_bytecode_function(JSContext *ctx, JSModuleDef *m)\n{",
        "4a962938bcf332eadff3be4562fbc3997610f7c626baa99fd3d4419f8285bfc3",
    ),
    "js_bytecode_function_finalizer": (
        "static void js_bytecode_function_finalizer(JSRuntime *rt, JSValueConst val)\n{",
        "a86601630b3c36538340dba432f9c2275f59d00cac12fa35210eaa433fd29d92",
    ),
    "JS_ComputeMemoryUsage": (
        "void JS_ComputeMemoryUsage(",
        "dd87916e26844b5c3bde07b1fe55826777d6ee31b7f448f490e0cee064178047",
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
        "583c657bcacdfe93d9ebedd5f805e06438cecc7e80c1188cc9820d675d7f5dab",
    ),
    "JS_NewCFunctionData2": (
        "JSValue JS_NewCFunctionData2(",
        "c2836ead6163f7dd8a4aa0e5aa48ee76538cbc949c52d08fd20d306860aa5c28",
    ),
    "js_create_resolving_functions": (
        "static int js_create_resolving_functions(JSContext *ctx,\n                                         JSValue *resolving_funcs,\n                                         JSValueConst promise)\n\n{",
        "4d81b91dc3f8b1c43e2e92aa8139190605264b7c73c4987159bd6a32015c95f4",
    ),
}


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    assert old.count("\n") == new.count("\n"), "Keep original logical source lines"
    return text.replace(old, new, 1)


def private_types(text, conditional=False):
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
        "    assert(ctx->header.ref_count == 0);",
        "    assert(ctx->header.ref_count == 0); ctx->closure_template_mode = 2; ctx->internal_function_mode = 2;",
    )
    text = replace_once(
        text,
        "    js_free_shape_null(ctx->rt, ctx->array_shape);",
        "    js_free_shape_null(ctx->rt, ctx->array_shape); js_closure_templates_cleanup(ctx);",
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
        "            if (!(p->__gc_mark & 64)) js_free_rt(rt, var_refs);\n        }\n        JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_FUNCTION_BYTECODE, b));",
    )
    text = replace_once(
        text,
        "                    s->memory_used_count++;\n                    s->js_func_size += b->closure_var_count * sizeof(*var_refs);",
        "                    if (!(p->__gc_mark & 64)) s->memory_used_count++;\n                    s->js_func_size += b->closure_var_count * sizeof(*var_refs);",
    )
    # Bit6 is an unused JSObject header bit, independent of GC mark/type and
    # prototype bit7. Every ordinary bytecode-function publisher clears it.
    old = "    p->u.func.function_bytecode = b;"
    assert text.count(old) == 2
    text = text.replace(old, old + " p->__gc_mark &= ~64;")
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
