"""Shared core overlays for unified Map/Set string hashing and ordinary async output.

Preserves exact logical source line counts so native creator-call and object
adapters retain identical upstream line tables across all backends.
"""


def replace_exact_lines(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Keyed/async source anchor changed: " + old[:100])
    old_lines = old.count("\n")
    new_lines = new.count("\n")
    if new_lines > old_lines:
        raise ValueError(
            f"Keyed/async overlay grew line count ({new_lines} > {old_lines}): " + old[:80]
        )
    new += "\n" * (old_lines - new_lines)
    return text.replace(old, new, 1)


def map_keys(text):
    before_lines = text.count("\n")
    text = replace_exact_lines(
        text,
        "    if (JS_REF_COUNT(p1) == 1 && p1->is_wide_char == p2->is_wide_char\n"
        "    &&  js_malloc_usable_size(ctx, p1) >= sizeof(*p1) + ((p1->len + p2->len) << p2->is_wide_char) + 1 - p1->is_wide_char) {\n"
        "        /* Concatenate in place in available space at the end of p1 */",
        "    if (JS_REF_COUNT(p1) == 1 && !p1->atom_type && p1->kind == JS_STRING_KIND_NORMAL && p1->is_wide_char == p2->is_wide_char\n"
        "    &&  js_malloc_usable_size(ctx, p1) >= sizeof(*p1) + ((p1->len + p2->len) << p2->is_wide_char) + 1 - p1->is_wide_char) {\n"
        "        if (unlikely(p1->hash)) p1->hash = 0; /* Invalidate cached Map hash before in-place concat */",
    )
    text = replace_exact_lines(
        text,
        "/* XXX: better hash ? */\nstatic uint32_t map_hash_key(JSContext *ctx, JSValueConst key)",
        '#include "src/common/value/map-string-keys.inc"\n'
        "static uint32_t map_hash_key(JSContext *ctx, JSValueConst key)",
    )
    text = replace_exact_lines(
        text,
        "    case JS_TAG_STRING:\n"
        "        h = hash_string(JS_VALUE_GET_STRING(key), 0);\n"
        "        break;\n"
        "    case JS_TAG_STRING_ROPE:\n"
        "        h = hash_string_rope(key, 0);\n"
        "        break;",
        "    case JS_TAG_STRING:\n"
        "        return js_map_flat_string_hash(JS_VALUE_GET_STRING(key)) ^ ctx->hash_seed ^ hash32((uint32_t)JS_TAG_STRING);\n"
        "    case JS_TAG_STRING_ROPE:\n"
        "        h = hash_string_rope(key, JS_ATOM_TYPE_STRING) & JS_ATOM_HASH_MASK;\n"
        "        return h ^ ctx->hash_seed ^ hash32((uint32_t)JS_TAG_STRING);",
    )
    text = replace_exact_lines(
        text,
        "    h = map_hash_key(ctx, key) & (s->hash_size - 1);\n"
        "    list_for_each(el, &s->hash_table[h]) {",
        "    if (JS_VALUE_GET_TAG(key) == JS_TAG_STRING) { h = js_map_flat_string_hash(JS_VALUE_GET_STRING(key)); return js_map_find_string_record(ctx, &s->hash_table[(h ^ ctx->hash_seed ^ hash32((uint32_t)JS_TAG_STRING)) & (s->hash_size - 1)], key, h); }\n"
        "    h = map_hash_key(ctx, key) & (s->hash_size - 1); list_for_each(el, &s->hash_table[h]) {",
    )
    text = replace_exact_lines(
        text,
        "        mr->key = unsafe_unconst(key);\n"
        "    } else {\n"
        "        mr->key = js_dup(key);\n"
        "    }\n"
        "    h = map_hash_key(ctx, key) & (s->hash_size - 1);",
        "        mr->key = unsafe_unconst(key);\n"
        "    } else if (JS_VALUE_GET_TAG(key) == JS_TAG_STRING_ROPE && string_rope_get_len(key) <= 4096) {\n"
        "        mr->key = js_linearize_string_rope(ctx, key); if (unlikely(JS_IsException(mr->key))) { js_free(ctx, mr); return NULL; }\n"
        "    } else { mr->key = js_dup(key); }\n"
        "    h = map_hash_key(ctx, mr->key) & (s->hash_size - 1);",
    )
    if text.count("\n") != before_lines:
        raise ValueError("map_keys overlay changed logical line count")
    return text


def async_output(text):
    before_lines = text.count("\n")
    text = replace_exact_lines(
        text,
        "\n\nstatic void js_async_function_terminate(JSRuntime *rt, JSAsyncFunctionData *s)",
        '\n#include "src/common/promise/async-output.inc"\n'
        "static void js_async_function_terminate(JSRuntime *rt, JSAsyncFunctionData *s)",
    )
    for slot, arg, reject in ((1, "error", "true"), (0, "value", "false")):
        text = replace_exact_lines(
            text,
            f"            ret2 = JS_Call(ctx, s->resolving_funcs[{slot}], JS_UNDEFINED,\n"
            f"                           1, vc(&{arg}));",
            f"            ret2 = js_async_output_settle(ctx, s, {arg}, {reject});",
        )
    text = replace_exact_lines(
        text,
        "    promise = JS_NewPromiseCapability(ctx, s->resolving_funcs);",
        "    if (unlikely(ctx->rt->promise_hook)) { promise = JS_NewPromiseCapability(ctx, s->resolving_funcs); } else { promise = js_promise_new(ctx, JS_UNDEFINED, NULL); if (!JS_IsException(promise)) s->resolving_funcs[0] = js_dup(promise); }",
    )
    old_resolve_fn = """static JSValue js_promise_resolve_function_call(JSContext *ctx,
                                                JSValueConst func_obj,
                                                JSValueConst this_val,
                                                int argc, JSValueConst *argv,
                                                int flags)
{
    JSObject *p = JS_VALUE_GET_OBJ(func_obj);
    JSPromiseFunctionData *s;
    JSValueConst args[3];
    JSValueConst resolution;
    JSValue then;
    bool is_reject;

    s = p->u.promise_function_data;
    if (!s || s->presolved->already_resolved)
        return JS_UNDEFINED;
    s->presolved->already_resolved = true;
    is_reject = p->class_id - JS_CLASS_PROMISE_RESOLVE_FUNCTION;
    if (argc > 0)
        resolution = argv[0];
    else
        resolution = JS_UNDEFINED;
#ifdef ENABLE_DUMPS // JS_DUMP_PROMISE
    if (check_dump_flag(ctx->rt, JS_DUMP_PROMISE)) {
        printf("js_promise_resolving_function_call: is_reject=%d resolution=", is_reject);
        JS_DumpValue(ctx->rt, resolution);
        printf("\\n");
    }
#endif
    if (is_reject || !JS_IsObject(resolution)) {
        goto done;
    } else if (js_same_value(ctx, resolution, s->promise)) {
        JS_ThrowTypeError(ctx, "promise self resolution");
        goto fail_reject;
    }
    then = JS_GetProperty(ctx, resolution, JS_ATOM_then);
    if (JS_IsException(then)) {
        JSValue error;
    fail_reject:
        error = JS_GetException(ctx);
        fulfill_or_reject_promise(ctx, s->promise, error, true);
        JS_FreeValue(ctx, error);
    } else if (!JS_IsFunction(ctx, then)) {
        JS_FreeValue(ctx, then);
    done:
        fulfill_or_reject_promise(ctx, s->promise, resolution, is_reject);
    } else {
        args[0] = s->promise;
        args[1] = resolution;
        args[2] = then;
        JS_EnqueueJob(ctx, js_promise_resolve_thenable_job, 3, args);
        JS_FreeValue(ctx, then);
    }
    return JS_UNDEFINED;
}"""
    new_resolve_fn = """static JSValue js_promise_settle(JSContext *ctx, JSValueConst promise, JSValueConst resolution, bool is_reject)
{
    JSValueConst args[3]; JSValue then;
    if (is_reject || !JS_IsObject(resolution)) { goto done; }
    else if (js_same_value(ctx, resolution, promise)) { JS_ThrowTypeError(ctx, "promise self resolution"); goto fail_reject; }
    then = JS_GetProperty(ctx, resolution, JS_ATOM_then);
    if (JS_IsException(then)) { JSValue error; fail_reject: error = JS_GetException(ctx); fulfill_or_reject_promise(ctx, promise, error, true); JS_FreeValue(ctx, error); }
    else if (!JS_IsFunction(ctx, then)) { JS_FreeValue(ctx, then); done: fulfill_or_reject_promise(ctx, promise, resolution, is_reject); }
    else { args[0] = promise; args[1] = resolution; args[2] = then; JS_EnqueueJob(ctx, js_promise_resolve_thenable_job, 3, args); JS_FreeValue(ctx, then); }
    return JS_UNDEFINED;
}
static JSValue js_promise_resolve_function_call(JSContext *ctx, JSValueConst func_obj, JSValueConst this_val, int argc, JSValueConst *argv, int flags)
{
    JSObject *p = JS_VALUE_GET_OBJ(func_obj); JSPromiseFunctionData *s = p->u.promise_function_data; JSValueConst resolution; bool is_reject;
    if (!s || s->presolved->already_resolved) return JS_UNDEFINED;
    s->presolved->already_resolved = true; is_reject = p->class_id - JS_CLASS_PROMISE_RESOLVE_FUNCTION; resolution = argc > 0 ? argv[0] : JS_UNDEFINED;
#ifdef ENABLE_DUMPS // JS_DUMP_PROMISE
    if (check_dump_flag(ctx->rt, JS_DUMP_PROMISE)) { printf("js_promise_resolving_function_call: is_reject=%d resolution=", is_reject); JS_DumpValue(ctx->rt, resolution); printf("\\n"); }
#endif
    return js_promise_settle(ctx, s->promise, resolution, is_reject);
}"""
    text = replace_exact_lines(text, old_resolve_fn, new_resolve_fn)
    text = replace_exact_lines(
        text,
        "    if (js_create_resolving_functions(ctx, resolving_funcs, obj)) {",
        "    if (resolving_funcs && js_create_resolving_functions(ctx, resolving_funcs, obj)) {",
    )
    text = replace_exact_lines(
        text,
        "    result_promise = js_new_promise_capability(ctx, resolving_funcs, this_val);\n"
        "    if (JS_IsException(result_promise))\n"
        "        return result_promise;\n"
        "    ret = JS_Call(ctx, resolving_funcs[is_reject], JS_UNDEFINED, 1, argv);",
        "    if (!is_reject && !ctx->rt->promise_hook && !JS_IsObject(argv[0]) && js_same_value(ctx, this_val, ctx->promise_ctor)) { result_promise = js_promise_new(ctx, JS_UNDEFINED, NULL); if (unlikely(JS_IsException(result_promise))) return JS_EXCEPTION; if (unlikely(js_poll_interrupts(ctx))) { JS_FreeValue(ctx, result_promise); return JS_EXCEPTION; } fulfill_or_reject_promise(ctx, result_promise, argv[0], false); return result_promise; }\n"
        "    result_promise = js_new_promise_capability(ctx, resolving_funcs, this_val);\n"
        "    if (JS_IsException(result_promise)) return result_promise;\n"
        "    ret = JS_Call(ctx, resolving_funcs[is_reject], JS_UNDEFINED, 1, argv);",
    )
    if text.count("\n") != before_lines:
        raise ValueError("async_output overlay changed logical line count")
    return text


def core_overlay(text):
    return async_output(map_keys(text))
