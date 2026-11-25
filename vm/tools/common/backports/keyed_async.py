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


def value_fast_paths(text):
    before_lines = text.count("\n")
    text = replace_exact_lines(
        text,
        "    void *libc_opaque;\n    JSRuntimeFinalizerState *finalizers;\n};",
        "    void *libc_opaque;\n    JSRuntimeFinalizerState *finalizers; uint8_t fast_pool_ok; struct QJSFastValuePools *fast_pools;\n};",
    )
    text = replace_exact_lines(
        text,
        "JSRuntime *JS_NewRuntime(void)\n{\n    return JS_NewRuntime2(&def_malloc_funcs, NULL);\n}",
        "JSRuntime *JS_NewRuntime(void)\n{\n    JSRuntime *rt = JS_NewRuntime2(&def_malloc_funcs, NULL); if (rt) rt->fast_pool_ok = 1; return rt;\n}",
    )
    text = replace_exact_lines(
        text,
        "\n\nvoid JS_FreeRuntime(JSRuntime *rt)",
        "\ntypedef struct QJSFastValuePools { JSBigInt *bigint_pool[9][8]; uint8_t bigint_count[9]; JSString *small_int_strings[90]; } QJSFastValuePools; static void qjs_runtime_drain_fast_pools(JSRuntime *rt);\nvoid JS_FreeRuntime(JSRuntime *rt)",
    )
    text = replace_exact_lines(
        text,
        "    init_list_head(&rt->job_list);\n\n    JS_RunGC(rt);",
        "    init_list_head(&rt->job_list);\n    qjs_runtime_drain_fast_pools(rt);\n    JS_RunGC(rt);",
    )
    text = replace_exact_lines(
        text,
        "    case JS_TAG_BIG_INT:\n"
        "        {\n"
        "            JSBigInt *p = JS_VALUE_GET_PTR(v);\n"
        "            js_free_rt(rt, p);\n"
        "        }\n"
        "        break;",
        "    case JS_TAG_BIG_INT: {\n"
        "        JSBigInt *p = JS_VALUE_GET_PTR(v);\n"
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "        if ((uint32_t)(p->len - 1u) < 8u && rt->fast_pool_ok && !rt->in_free && !rt->malloc_state.malloc_limit && (rt->fast_pools || (rt->fast_pools = js_mallocz_rt(rt, sizeof(QJSFastValuePools))) != NULL) && rt->fast_pools->bigint_count[p->len] < 8u) { rt->fast_pools->bigint_pool[p->len][rt->fast_pools->bigint_count[p->len]++] = p; break; }\n"
        "#endif\n"
        "        js_free_rt(rt, p); } break;",
    )
    text = replace_exact_lines(
        text,
        "\n\nstatic JSBigInt *js_bigint_new(JSContext *ctx, int len)\n"
        "{\n"
        "    JSBigInt *r;\n"
        "    if (len > JS_BIGINT_MAX_SIZE) {\n"
        '        JS_ThrowRangeError(ctx, "BigInt is too large to allocate");\n'
        "        return NULL;\n"
        "    }\n"
        "    r = js_malloc(ctx, sizeof(JSBigInt) + len * sizeof(js_limb_t));",
        '\n#include "src/common/value/dtoa-fast.inc"\n'
        "static JSBigInt *js_bigint_new(JSContext *ctx, int len)\n"
        "{\n"
        "    JSBigInt *r;\n"
        '    if (len > JS_BIGINT_MAX_SIZE) { JS_ThrowRangeError(ctx, "BigInt is too large to allocate"); return NULL; }\n'
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "    { JSBigInt *fast_r = qjs_bigint_pool_get(ctx, len); if (fast_r) return fast_r; }\n"
        "#endif\n"
        "    r = js_malloc(ctx, sizeof(JSBigInt) + len * sizeof(js_limb_t));",
    )
    text = replace_exact_lines(
        text,
        "static JSBigInt *js_bigint_mul(JSContext *ctx, const JSBigInt *a,\n"
        "                               const JSBigInt *b)\n"
        "{\n"
        "    JSBigInt *r;\n\n"
        "    r = js_bigint_new(ctx, a->len + b->len);",
        "static JSBigInt *js_bigint_mul(JSContext *ctx, const JSBigInt *a,\n"
        "                               const JSBigInt *b)\n"
        "{\n"
        "    JSBigInt *r;\n"
        "    if (qjs_bigint_mul_fast(ctx, a, b, &r)) return r;\n"
        "    r = js_bigint_new(ctx, a->len + b->len);",
    )
    text = replace_exact_lines(
        text,
        "    case JS_TAG_STRING:\n"
        "    case JS_TAG_STRING_ROPE:\n"
        "        {\n"
        "            const char *str;\n"
        "            const char *p;\n"
        "            size_t len;\n\n"
        "            str = JS_ToCStringLen(ctx, &len, val);\n"
        "            JS_FreeValue(ctx, val);",
        "    case JS_TAG_STRING:\n"
        "    case JS_TAG_STRING_ROPE:\n"
        "        {\n"
        "            const char *str; const char *p; size_t len; JSValue fast_num;\n"
        "            if (JS_VALUE_GET_TAG(val) == JS_TAG_STRING && qjs_try_flat_str_to_number(ctx, JS_VALUE_GET_STRING(val), &fast_num)) { JS_FreeValue(ctx, val); return fast_num; }\n"
        "            str = JS_ToCStringLen(ctx, &len, val);\n"
        "            JS_FreeValue(ctx, val);",
    )
    text = replace_exact_lines(
        text,
        "    str = JS_ToCString(ctx, argv[0]);\n"
        "    if (!str)\n"
        "        return JS_EXCEPTION;\n"
        "    p = str;\n"
        "    p += skip_spaces(p);\n"
        "    ret = js_atof(ctx, p, NULL, 10, 0);",
        "    if (JS_VALUE_GET_TAG(argv[0]) == JS_TAG_STRING && !JS_VALUE_GET_STRING(argv[0])->is_wide_char) { double fast_d; if (qjs_fast_atod_str8((const uint8_t *)str8(JS_VALUE_GET_STRING(argv[0])), JS_VALUE_GET_STRING(argv[0])->len, true, &fast_d)) return js_number(fast_d); }\n"
        "    str = JS_ToCString(ctx, argv[0]);\n"
        "    if (!str) return JS_EXCEPTION;\n"
        "    p = str;\n"
        "    p += skip_spaces(p);\n"
        "    ret = js_atof(ctx, p, NULL, 10, 0);",
    )
    text = replace_exact_lines(
        text,
        "    default:\n"
        "        val = JS_ToNumberFree(ctx, val);\n"
        "        if (JS_IsException(val)) {\n"
        "            *pres = 0;\n"
        "            return -1;\n"
        "        }\n"
        "        goto redo;\n"
        "    }\n"
        "    *pres = ret;\n"
        "    return 0;\n"
        "}\n\n"
        "int JS_ToInt32(",
        "    default:\n"
        "        { int32_t fast_i32; if (tag == JS_TAG_STRING && qjs_try_flat_str_to_int32(JS_VALUE_GET_STRING(val), &fast_i32, true)) { JS_FreeValue(ctx, val); *pres = fast_i32; return 0; } }\n"
        "        val = JS_ToNumberFree(ctx, val);\n"
        "        if (JS_IsException(val)) { *pres = 0; return -1; }\n"
        "        goto redo;\n"
        "    }\n"
        "    *pres = ret;\n"
        "    return 0;\n"
        "}\n\n"
        "int JS_ToInt32(",
    )
    text = replace_exact_lines(
        text,
        "static JSValue js_dtoa2(JSContext *ctx,\n"
        "                        double d, int radix, int n_digits, int flags)\n"
        "{\n"
        "    char static_buf[128], *buf, *tmp_buf;\n"
        "    int len, len_max;\n"
        "    JSValue res;\n"
        "    JSDTOATempMem dtoa_mem;\n"
        "    len_max = js_dtoa_max_len(d, radix, n_digits, flags);",
        "static JSValue js_dtoa2(JSContext *ctx,\n"
        "                        double d, int radix, int n_digits, int flags)\n"
        "{\n"
        "    char static_buf[128], *buf, *tmp_buf; int len, len_max; JSValue res; JSDTOATempMem dtoa_mem;\n"
        "    if (likely(radix == 10 && n_digits == 0 && flags == JS_DTOA_FORMAT_FREE)) { len = qjs_dtoa_fast_free10(static_buf, d); return js_new_string8_len(ctx, static_buf, len); }\n"
        "    len_max = js_dtoa_max_len(d, radix, n_digits, flags);",
    )
    text = replace_exact_lines(
        text,
        "    case JS_TAG_INT:\n"
        "        { int32_t v = JS_VALUE_GET_INT(val); if ((uint32_t)v < 10u) return js_new_string_char(ctx, '0' + v);\n"
        "        len = i32toa(buf, v); return js_new_string8_len(ctx, buf, len); }",
        "    case JS_TAG_INT:\n"
        "        { (void)buf; (void)len; return qjs_int_to_string_fast(ctx, JS_VALUE_GET_INT(val)); }",
    )
    if text.count("\n") != before_lines:
        raise ValueError("value_fast_paths overlay changed logical line count")
    return text


def string_key_lookup(text):
    before_lines = text.count("\n")
    text = replace_exact_lines(
        text,
        "        /* try and locate an already registered atom */\n"
        "        len = str->len;\n"
        "        h = hash_string(str, atom_type);\n"
        "        h &= JS_ATOM_HASH_MASK;",
        "        /* try and locate an already registered atom */\n"
        "        len = str->len;\n"
        "        h = (atom_type == JS_ATOM_TYPE_STRING && !str->atom_type && str->hash) ? str->hash : (hash_string(str, atom_type) & JS_ATOM_HASH_MASK);\n"
        "        if (atom_type == JS_ATOM_TYPE_STRING && !str->atom_type) str->hash = h;",
    )
    text = replace_exact_lines(
        text,
        "\n\nJSValue JS_GetPropertyValue(JSContext *ctx, JSValueConst this_obj,",
        '\n#include "src/common/property/string-key-lookup.inc"\n'
        "JSValue JS_GetPropertyValue(JSContext *ctx, JSValueConst this_obj,",
    )
    text = replace_exact_lines(
        text,
        "    tag = JS_VALUE_GET_TAG(this_obj);\n"
        "    if (likely(tag == JS_TAG_OBJECT)) {\n"
        "        if (JS_VALUE_GET_TAG(prop) == JS_TAG_INT) {\n"
        "            JSObject *p = JS_VALUE_GET_OBJ(this_obj);\n"
        "            uint32_t idx = JS_VALUE_GET_INT(prop);\n"
        "            JSValue val;\n"
        "            /* fast path for array and typed array access */\n"
        "            if (js_get_fast_array_element(ctx, p, idx, &val))\n"
        "                return val;\n"
        "        }",
        "    tag = JS_VALUE_GET_TAG(this_obj);\n"
        "    if (likely(tag == JS_TAG_OBJECT)) {\n"
        "        if (JS_VALUE_GET_TAG(prop) == JS_TAG_INT) {\n"
        "            JSObject *p = JS_VALUE_GET_OBJ(this_obj);\n"
        "            uint32_t idx = JS_VALUE_GET_INT(prop);\n"
        "            JSValue val;\n"
        "            /* fast path for array and typed array access */\n"
        "            if (js_get_fast_array_element(ctx, p, idx, &val))\n"
        "                return val;\n"
        "        } else if (JS_VALUE_GET_TAG(prop) == JS_TAG_STRING) { JSValue val; if (js_try_get_property_string(ctx, this_obj, prop, &val)) return val; }",
    )
    text = replace_exact_lines(
        text,
        "    slow_path:\n        atom = JS_ValueToAtom(ctx, prop);",
        "    slow_path:\n"
        "        if (JS_VALUE_GET_TAG(this_obj) == JS_TAG_OBJECT && JS_VALUE_GET_TAG(prop) == JS_TAG_STRING) { int f_ret; if (js_try_set_property_string(ctx, this_obj, prop, val, flags, &f_ret)) return f_ret; } atom = JS_ValueToAtom(ctx, prop);",
    )
    text = replace_exact_lines(
        text,
        "    if (JS_VALUE_GET_TAG(op2) != JS_TAG_OBJECT) {\n"
        "        JS_ThrowTypeError(ctx, \"invalid 'in' operand\");\n"
        "        return -1;\n"
        "    }\n"
        "    atom = JS_ValueToAtom(ctx, op1);",
        "    if (JS_VALUE_GET_TAG(op2) != JS_TAG_OBJECT) { JS_ThrowTypeError(ctx, \"invalid 'in' operand\"); return -1; }\n"
        "    if (JS_VALUE_GET_TAG(op1) == JS_TAG_STRING && js_try_has_property_string(ctx, op2, op1, &ret)) { JS_FreeValue(ctx, op1); JS_FreeValue(ctx, op2); sp[-2] = js_bool(ret); return 0; }\n"
        "    atom = JS_ValueToAtom(ctx, op1);",
    )
    text = replace_exact_lines(
        text,
        "    p = JS_VALUE_GET_OBJ(it->obj);\n    if (is_typed_array(p->class_id)) {",
        "    p = JS_VALUE_GET_OBJ(it->obj);\n"
        "    if (p->class_id == JS_CLASS_ARRAY && p->fast_array && it->kind == JS_ITERATOR_KIND_VALUE && it->idx < p->u.array.count) { *pdone = false; return js_dup(p->u.array.u.values[it->idx++]); } if (is_typed_array(p->class_id)) {",
    )
    if text.count("\n") != before_lines:
        raise ValueError("string_key_lookup overlay changed logical line count")
    return text


def core_overlay(text):
    return string_key_lookup(value_fast_paths(async_output(map_keys(text))))
