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
    has_ptr_hash = "/* float64 mixed */" in text
    text = replace_exact_lines(
        text,
        "    if (JS_REF_COUNT(p1) == 1 && p1->is_wide_char == p2->is_wide_char\n"
        "    &&  js_malloc_usable_size(ctx, p1) >= sizeof(*p1) + ((p1->len + p2->len) << p2->is_wide_char) + 1 - p1->is_wide_char) {\n"
        "        /* Concatenate in place in available space at the end of p1 */",
        "    if (JS_REF_COUNT(p1) == 1 && !p1->atom_type && p1->kind == JS_STRING_KIND_NORMAL && p1->is_wide_char == p2->is_wide_char\n"
        "    &&  js_malloc_usable_size(ctx, p1) >= sizeof(*p1) + ((p1->len + p2->len) << p2->is_wide_char) + 1 - p1->is_wide_char) {\n"
        "        if (unlikely(p1->hash)) p1->hash = 0; /* Invalidate cached Map hash before in-place concat */",
    )
    ptr_def = "#define QJS_MAP_POINTER_HASH 1\n" if has_ptr_hash else ""
    text = replace_exact_lines(
        text,
        "static JSValueConst map_normalize_key_const(JSContext *ctx, JSValueConst key)\n"
        "{\n"
        "    return safe_const(map_normalize_key(ctx, unsafe_unconst(key)));\n"
        "}\n\n"
        "/* XXX: better hash ? */\n"
        "static uint32_t map_hash_key(JSContext *ctx, JSValueConst key)",
        "static inline JSValueConst map_normalize_key_const(JSContext *ctx, JSValueConst key) { return safe_const(map_normalize_key(ctx, unsafe_unconst(key))); }\n"
        + ptr_def
        + '#include "src/common/value/map-string-keys.inc"\n'
        + "static uint32_t map_hash_key(JSContext *ctx, JSValueConst key)",
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
        "static JSMapRecord *map_find_record(JSContext *ctx, JSMapState *s,\n"
        "                                    JSValueConst key)\n"
        "{\n"
        "    struct list_head *el;\n"
        "    JSMapRecord *mr;\n"
        "    uint32_t h;\n"
        "    h = map_hash_key(ctx, key) & (s->hash_size - 1);\n"
        "    list_for_each(el, &s->hash_table[h]) {\n"
        "        mr = list_entry(el, JSMapRecord, hash_link);\n"
        "        if (js_same_value_zero(ctx, mr->key, key))\n"
        "            return mr;\n"
        "    }\n"
        "    return NULL;\n"
        "}",
        "static inline JSMapRecord *map_find_record(JSContext *ctx, JSMapState *s, JSValueConst key)\n"
        "{\n"
        "    uint32_t raw_h;\n"
        "    return js_map_find_record_hash(ctx, s, key, &raw_h);\n"
        "}",
    )
    text = replace_exact_lines(
        text,
        "    if (s->hash_size == 1)\n"
        "        new_hash_size = 4;\n"
        "    else\n"
        "        new_hash_size = s->hash_size * 2;",
        "    new_hash_size = (s->hash_size == 1) ? 8 : (s->hash_size * 2);",
    )
    text = replace_exact_lines(
        text,
        "        if (!mr->empty) {\n"
        "            h = map_hash_key(ctx, mr->key) & (new_hash_size - 1);\n"
        "            list_add_tail(&mr->hash_link, &new_hash_table[h]);\n"
        "        }\n"
        "    }\n"
        "    s->hash_table = new_hash_table;\n"
        "    s->hash_size = new_hash_size;\n"
        "    s->record_count_threshold = new_hash_size * 2;",
        "        if (!mr->empty) {\n"
        "            h = js_map_hash_key_fast(ctx, mr->key) & (new_hash_size - 1);\n"
        "            list_add_tail(&mr->hash_link, &new_hash_table[h]);\n"
        "        }\n"
        "    }\n"
        "    s->hash_table = new_hash_table;\n"
        "    s->hash_size = new_hash_size;\n"
        "    s->record_count_threshold = new_hash_size;",
    )
    text = replace_exact_lines(
        text,
        "static JSMapRecord *map_add_record(JSContext *ctx, JSMapState *s,\n"
        "                                   JSValueConst key)\n"
        "{\n"
        "    uint32_t h;\n"
        "    JSMapRecord *mr;\n"
        "\n"
        "    mr = js_malloc(ctx, sizeof(*mr));\n"
        "    if (!mr)\n"
        "        return NULL;\n"
        "    mr->ref_count = 1;\n"
        "    mr->map = s;\n"
        "    mr->empty = false;\n"
        "    if (s->is_weak) {\n"
        "        JSWeakRefRecord *wr = js_malloc(ctx, sizeof(*wr));\n"
        "        if (!wr) {\n"
        "            js_free(ctx, mr);\n"
        "            return NULL;\n"
        "        }\n"
        "        wr->kind = JS_WEAK_REF_KIND_MAP;\n"
        "        wr->u.map_record = mr;\n"
        "        insert_weakref_record(key, wr);\n"
        "        mr->key = unsafe_unconst(key);\n"
        "    } else {\n"
        "        mr->key = js_dup(key);\n"
        "    }\n"
        "    h = map_hash_key(ctx, key) & (s->hash_size - 1);\n"
        "    list_add_tail(&mr->hash_link, &s->hash_table[h]);\n"
        "    list_add_tail(&mr->link, &s->records);\n"
        "    s->record_count++;\n"
        "    if (s->record_count >= s->record_count_threshold) {\n"
        "        map_hash_resize(ctx, s);\n"
        "    }\n"
        "    return mr;\n"
        "}",
        "static JSMapRecord *map_add_record_hashed(JSContext *ctx, JSMapState *s, JSValueConst key, uint32_t raw_h)\n"
        "{\n"
        "    uint32_t h; JSMapRecord *mr = js_malloc(ctx, sizeof(*mr));\n"
        "    if (unlikely(!mr)) return NULL;\n"
        "    mr->ref_count = 1; mr->map = s; mr->empty = false;\n"
        "    if (s->is_weak) {\n"
        "        JSWeakRefRecord *wr = js_malloc(ctx, sizeof(*wr));\n"
        "        if (unlikely(!wr)) { js_free(ctx, mr); return NULL; }\n"
        "        wr->kind = JS_WEAK_REF_KIND_MAP; wr->u.map_record = mr; insert_weakref_record(key, wr); mr->key = unsafe_unconst(key);\n"
        "    } else if (JS_VALUE_GET_TAG(key) == JS_TAG_STRING_ROPE && string_rope_get_len(key) <= 4096) {\n"
        "        mr->key = js_linearize_string_rope(ctx, key); if (unlikely(JS_IsException(mr->key))) { js_free(ctx, mr); return NULL; }\n"
        "    } else { mr->key = js_dup(key); }\n"
        "    h = raw_h & (s->hash_size - 1);\n"
        "    list_add_tail(&mr->hash_link, &s->hash_table[h]);\n"
        "    list_add_tail(&mr->link, &s->records);\n"
        "    s->record_count++;\n"
        "    if (unlikely(s->record_count >= s->record_count_threshold)) map_hash_resize(ctx, s);\n"
        "    return mr;\n"
        "}\n"
        "static JSMapRecord *map_add_record(JSContext *ctx, JSMapState *s, JSValueConst key)\n"
        "{ return map_add_record_hashed(ctx, s, key, js_map_hash_key_fast(ctx, key)); }",
    )
    text = replace_exact_lines(
        text,
        "    mr = map_find_record(ctx, s, key);\n"
        "    if (mr) {\n"
        "        JS_FreeValue(ctx, mr->value);\n"
        "    } else {\n"
        "        mr = map_add_record(ctx, s, key);\n"
        "        if (!mr)\n"
        "            return JS_EXCEPTION;\n"
        "    }",
        "    { uint32_t raw_h; mr = js_map_find_record_hash(ctx, s, key, &raw_h);\n"
        "    if (mr) {\n"
        "        JS_FreeValue(ctx, mr->value);\n"
        "    } else {\n"
        "        mr = map_add_record_hashed(ctx, s, key, raw_h);\n"
        "        if (unlikely(!mr)) return JS_EXCEPTION;\n"
        "    } }",
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
    text = replace_exact_lines(
        text,
        "            /* await */\n"
        "            JS_FreeValue(ctx, func_ret); /* not used */\n"
        "            promise = js_promise_resolve(ctx, ctx->promise_ctor,\n"
        "                                         1, vc(&value), 0);\n"
        "            JS_FreeValue(ctx, value);",
        "            /* await */\n"
        "            JS_FreeValue(ctx, func_ret); /* not used */\n"
        "            { int _af = js_async_function_await_fast(ctx, s, value); if (likely(_af != 0)) { JS_FreeValue(ctx, value); if (_af < 0) goto fail; return is_success; } }\n"
        "            promise = js_promise_resolve(ctx, ctx->promise_ctor, 1, vc(&value), 0);\n"
        "            JS_FreeValue(ctx, value);",
    )
    text = replace_exact_lines(
        text,
        "static int js_async_generator_await(JSContext *ctx,\n"
        "                                    JSAsyncGeneratorData *s,\n"
        "                                    JSValue value)\n"
        "{\n"
        "    JSValue promise, resolving_funcs[2], resolving_funcs1[2];\n"
        "    int i, res;\n\n"
        "    promise = js_promise_resolve(ctx, ctx->promise_ctor,\n"
        "                                 1, vc(&value), 0);",
        "static JSValue js_async_gen_core_resume_job(JSContext *ctx, int argc, JSValueConst *argv) { (void)argc; if (unlikely(js_poll_interrupts(ctx))) return JS_EXCEPTION; if (unlikely(!JS_GetOpaque(argv[0], JS_CLASS_ASYNC_GENERATOR))) return JS_UNDEFINED; return js_async_generator_resolve_function(ctx, JS_UNDEFINED, 1, &argv[1], 0, &argv[0]); }\n"
        "static int js_async_generator_await(JSContext *ctx, JSAsyncGeneratorData *s, JSValue value)\n"
        "{\n"
        "    JSValue promise, resolving_funcs[2], resolving_funcs1[2]; int i, res;\n"
        "    if (likely(!ctx->rt->promise_hook && !js_check_stack_overflow(ctx->rt, 4096) && JS_IsObject(ctx->promise_ctor))) { JSValueConst _rv = value; bool _ok = false, _dir = false; if (JS_IsObject(value)) { JSObject *_po = JS_VALUE_GET_OBJ(value); if (_po->class_id == JS_CLASS_PROMISE) { if (js_async_promise_try_fulfilled(ctx, value, &_rv)) _ok = true; } else if (ctx->interrupt_counter > 1 && js_async_value_non_thenable(ctx, value)) { _dir = true; _ok = true; } } else if (ctx->interrupt_counter > 1) { _dir = true; _ok = true; } if (_ok) { JSJobEntry *_j = qjs_job2_alloc_fast(ctx); if (unlikely(!_j)) return -1; if (unlikely(ctx->rt->promise_hook || (_dir && (ctx->interrupt_counter <= 1 || !js_async_value_non_thenable(ctx, value))) || (!_dir && !js_async_promise_try_fulfilled(ctx, value, &_rv)))) { js_free(ctx, _j); } else { if (_dir) --ctx->interrupt_counter; else js_async_promise_mark_handled(value); _j->ctx = ctx; _j->job_func = js_async_gen_core_resume_job; _j->argc = 2; _j->argv[0] = js_dup(JS_MKPTR(JS_TAG_OBJECT, s->generator)); _j->argv[1] = js_dup(_rv); list_add_tail(&_j->link, &ctx->rt->job_list); return 0; } } }\n"
        "    promise = js_promise_resolve(ctx, ctx->promise_ctor, 1, vc(&value), 0);",
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
    new_resolve_fn = """static int js_async_promise_try_fulfilled(JSContext *ctx, JSValueConst promise, JSValueConst *out_res)
{
    JSObject *po = JS_VALUE_GET_OBJ(promise); JSPromiseData *d = po->u.promise_data;
    if (!d || d->promise_state != JS_PROMISE_FULFILLED || po->is_exotic || po->shape->prop_count != 0 || po->shape->proto != JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_PROMISE]) || !js_async_promise_proto_ctor_std(ctx)) return 0;
    *out_res = d->promise_result; return 1;
}
static void js_async_promise_mark_handled(JSValueConst promise)
{
    JSPromiseData *d = JS_GetOpaque(promise, JS_CLASS_PROMISE);
    if (likely(d)) d->is_handled = true;
}
static JSValue js_promise_settle(JSContext *ctx, JSValueConst promise, JSValueConst resolution, bool is_reject)
{
    JSValueConst args[3]; JSValue then;
    if (is_reject || !JS_IsObject(resolution)) { goto done; }
    else if (js_same_value(ctx, resolution, promise)) { JS_ThrowTypeError(ctx, "promise self resolution"); goto fail_reject; }
    if (js_async_value_non_thenable(ctx, resolution)) goto done;
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
        "/* return < 0 if exception, 0 if no job pending, 1 if a job was\n"
        "   executed successfully. the context of the job is stored in '*pctx' */\n"
        "int JS_ExecutePendingJob(JSRuntime *rt, JSContext **pctx)",
        "typedef struct QJSFastValuePools { JSBigInt *bigint_pool[19][8]; uint8_t bigint_count[19]; JSString *small_int_strings[90]; void *job2_pool[16]; uint8_t job2_count; void *promise_data_pool[16]; uint8_t promise_data_count; JSShape *iter_result_shape; } QJSFastValuePools; static JSValue js_async_func_fast_resume_job(JSContext *, int, JSValueConst *); static void qjs_runtime_drain_fast_pools(JSRuntime *rt);\n"
        "static inline JSJobEntry *qjs_job2_alloc_fast(JSContext *ctx) { QJSFastValuePools *fp = ctx->rt->fast_pools; if (likely(fp && fp->job2_count)) return (JSJobEntry *)fp->job2_pool[--fp->job2_count]; return js_malloc(ctx, sizeof(JSJobEntry) + 2 * sizeof(JSValue)); }\n"
        "int JS_ExecutePendingJob(JSRuntime *rt, JSContext **pctx)",
    )
    text = replace_exact_lines(
        text,
        "    if (JS_IsException(res))\n"
        "        ret = -1;\n"
        "    else\n"
        "        ret = 1;\n"
        "    JS_FreeValue(ctx, res);\n"
        "    js_free(ctx, e);\n"
        "    *pctx = ctx;\n"
        "    return ret;",
        "    ret = JS_IsException(res) ? -1 : 1;\n"
        "    JS_FreeValue(ctx, res);\n"
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "    if (likely(e->argc == 2 && rt->fast_pool_ok && !rt->in_free && !rt->malloc_state.malloc_limit && (rt->fast_pools || (rt->fast_pool_ok >= 8 ? (rt->fast_pools = js_mallocz_rt(rt, sizeof(QJSFastValuePools))) != NULL : (++rt->fast_pool_ok, false))) && rt->fast_pools->job2_count < 16u)) { rt->fast_pools->job2_pool[rt->fast_pools->job2_count++] = e; } else\n"
        "#endif\n"
        "    js_free(ctx, e);\n"
        "    *pctx = ctx;\n"
        "    return ret;",
    )
    text = replace_exact_lines(
        text,
        "    list_for_each_safe(el, el1, &rt->job_list) {\n"
        "        JSJobEntry *e = list_entry(el, JSJobEntry, link);\n"
        "        for(i = 0; i < e->argc; i++)\n"
        "            JS_FreeValueRT(rt, e->argv[i]);\n"
        "        js_free_rt(rt, e);\n"
        "    }",
        "    list_for_each_safe(el, el1, &rt->job_list) {\n"
        "        JSJobEntry *e = list_entry(el, JSJobEntry, link);\n"
        "        if (e->job_func == js_async_func_fast_resume_job) js_async_function_free(rt, JS_VALUE_GET_PTR(e->argv[0]));\n"
        "        for(i = 0; i < e->argc; i++) JS_FreeValueRT(rt, e->argv[i]);\n"
        "        js_free_rt(rt, e);\n"
        "    }",
    )
    text = replace_exact_lines(
        text,
        "void JS_SetClassProto(JSContext *ctx, JSClassID class_id, JSValue obj)\n"
        "{\n"
        "    assert(class_id < ctx->rt->class_count);",
        "void JS_SetClassProto(JSContext *ctx, JSClassID class_id, JSValue obj)\n"
        "{\n"
        "    assert(class_id < ctx->rt->class_count); if (unlikely(class_id == JS_CLASS_OBJECT && ctx->rt->fast_pools && ctx->rt->fast_pools->iter_result_shape)) { JSShape *_ish = ctx->rt->fast_pools->iter_result_shape; ctx->rt->fast_pools->iter_result_shape = NULL; js_free_shape(ctx->rt, _ish); }",
    )
    text = replace_exact_lines(
        text,
        "    js_free_modules(ctx, JS_FREE_MODULE_ALL);",
        "    js_free_modules(ctx, JS_FREE_MODULE_ALL); if (rt->fast_pools && rt->fast_pools->iter_result_shape) { JSShape *_ish = rt->fast_pools->iter_result_shape; rt->fast_pools->iter_result_shape = NULL; js_free_shape(rt, _ish); }",
    )
    text = replace_exact_lines(
        text,
        "static JSValue JS_IteratorGetCompleteValue(JSContext *ctx, JSValue obj,\n"
        "                                           int *pdone)\n"
        "{\n"
        "    JSValue done_val, value;\n"
        "    int done;\n"
        "    done_val = JS_GetProperty(ctx, obj, JS_ATOM_done);",
        "static JSValue JS_IteratorGetCompleteValue(JSContext *ctx, JSValue obj, int *pdone)\n"
        "{\n"
        "    JSValue done_val, value; int done;\n"
        "    if (likely(JS_VALUE_GET_TAG(obj) == JS_TAG_OBJECT)) { JSObject *_p = JS_VALUE_GET_OBJ(obj); JSShape *_sh = _p->shape; if (likely(!_p->is_exotic && _sh->prop_count == 2)) { JSShapeProperty *_prs = get_shape_prop(_sh); if (likely(_prs[0].atom == JS_ATOM_value && !(_prs[0].flags & JS_PROP_TMASK) && _prs[1].atom == JS_ATOM_done && !(_prs[1].flags & JS_PROP_TMASK))) { JSValue _dv = _p->prop[1].u.value; done = (JS_VALUE_GET_TAG(_dv) == JS_TAG_BOOL) ? JS_VALUE_GET_BOOL(_dv) : JS_ToBool(ctx, _dv); if (unlikely(done < 0)) goto fail; *pdone = done; return js_dup(_p->prop[0].u.value); } } }\n"
        "    done_val = JS_GetProperty(ctx, obj, JS_ATOM_done);",
    )
    text = replace_exact_lines(
        text,
        "static JSValue js_create_iterator_result(JSContext *ctx,\n"
        "                                         JSValue val,\n"
        "                                         bool done)\n"
        "{\n"
        "    JSValue obj;\n"
        "    obj = JS_NewObject(ctx);\n"
        "    if (JS_IsException(obj)) {\n"
        "        JS_FreeValue(ctx, val);\n"
        "        return obj;\n"
        "    }\n"
        "    if (JS_DefinePropertyValue(ctx, obj, JS_ATOM_value,\n"
        "                               val, JS_PROP_C_W_E) < 0) {\n"
        "        goto fail;\n"
        "    }\n"
        "    if (JS_DefinePropertyValue(ctx, obj, JS_ATOM_done,\n"
        "                               js_bool(done), JS_PROP_C_W_E) < 0) {\n"
        "    fail:\n"
        "        JS_FreeValue(ctx, obj);\n"
        "        return JS_EXCEPTION;\n"
        "    }\n"
        "    return obj;\n"
        "}",
        "static JSValue js_create_iterator_result(JSContext *ctx, JSValue val, bool done)\n"
        "{\n"
        "    JSValue obj;\n"
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "    { QJSFastValuePools *_fp = ctx->rt->fast_pools; if (likely(_fp && _fp->iter_result_shape && JS_IsObject(ctx->class_proto[JS_CLASS_OBJECT]) && _fp->iter_result_shape->proto == JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_OBJECT]))) { JSProperty _props[2]; _props[0].u.value = val; _props[1].u.value = js_bool(done); return JS_NewObjectFromShape(ctx, js_dup_shape(_fp->iter_result_shape), JS_CLASS_OBJECT, _props); } }\n"
        "#endif\n"
        "    obj = JS_NewObject(ctx);\n"
        "    if (JS_IsException(obj)) { JS_FreeValue(ctx, val); return obj; }\n"
        "    if (JS_DefinePropertyValue(ctx, obj, JS_ATOM_value, val, JS_PROP_C_W_E) < 0) goto fail;\n"
        "    if (JS_DefinePropertyValue(ctx, obj, JS_ATOM_done, js_bool(done), JS_PROP_C_W_E) < 0) { fail: JS_FreeValue(ctx, obj); return JS_EXCEPTION; }\n"
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "    { JSRuntime *_rt = ctx->rt; if (_rt->fast_pool_ok && !_rt->in_free && !_rt->malloc_state.malloc_limit && JS_IsObject(ctx->class_proto[JS_CLASS_OBJECT])) { JSShape *_sh = JS_VALUE_GET_OBJ(obj)->shape; if ((_sh->is_hashed & 1) && _sh->prop_count == 2 && !_sh->deleted_prop_count && _sh->proto == JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_OBJECT]) && get_shape_prop(_sh)[0].atom == JS_ATOM_value && get_shape_prop(_sh)[0].flags == JS_PROP_C_W_E && get_shape_prop(_sh)[1].atom == JS_ATOM_done && get_shape_prop(_sh)[1].flags == JS_PROP_C_W_E) { QJSFastValuePools *_fp = _rt->fast_pools ? _rt->fast_pools : (_rt->fast_pool_ok >= 8 ? (_rt->fast_pools = js_mallocz_rt(_rt, sizeof(QJSFastValuePools))) : (++_rt->fast_pool_ok, (QJSFastValuePools *)NULL)); if (_fp) { JSShape *_old = _fp->iter_result_shape; _fp->iter_result_shape = js_dup_shape(_sh); js_free_shape_null(_rt, _old); } } } }\n"
        "#endif\n"
        "    return obj;\n"
        "}",
    )
    text = replace_exact_lines(
        text,
        "    for(i = 0; i < 2; i++) {\n"
        "        list_for_each_safe(el, el1, &s->promise_reactions[i]) {\n"
        "            JSPromiseReactionData *rd =\n"
        "                list_entry(el, JSPromiseReactionData, link);\n"
        "            promise_reaction_data_free(rt, rd);\n"
        "        }\n"
        "    }\n"
        "    JS_FreeValueRT(rt, s->promise_result);\n"
        "    js_free_rt(rt, s);\n"
        "}",
        "    for(i = 0; i < 2; i++) { list_for_each_safe(el, el1, &s->promise_reactions[i]) { promise_reaction_data_free(rt, list_entry(el, JSPromiseReactionData, link)); } }\n"
        "    JS_FreeValueRT(rt, s->promise_result);\n"
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "    if (likely(rt->fast_pool_ok && !rt->in_free && !rt->malloc_state.malloc_limit && (rt->fast_pools || (rt->fast_pool_ok >= 8 ? (rt->fast_pools = js_mallocz_rt(rt, sizeof(QJSFastValuePools))) != NULL : (++rt->fast_pool_ok, false))) && rt->fast_pools->promise_data_count < 16u)) { rt->fast_pools->promise_data_pool[rt->fast_pools->promise_data_count++] = s; return; }\n"
        "#endif\n"
        "    js_free_rt(rt, s); }",
    )
    text = replace_exact_lines(
        text,
        "    obj = js_create_from_ctor(ctx, new_target, JS_CLASS_PROMISE);\n"
        "    if (JS_IsException(obj))\n"
        "        return JS_EXCEPTION;\n"
        "    s = js_mallocz(ctx, sizeof(*s));\n"
        "    if (!s) {\n"
        "        JS_FreeValue(ctx, obj);\n"
        "        return JS_EXCEPTION;\n"
        "    }",
        "    obj = JS_IsUndefined(new_target) ? JS_NewObjectProtoClass(ctx, ctx->class_proto[JS_CLASS_PROMISE], JS_CLASS_PROMISE) : js_create_from_ctor(ctx, new_target, JS_CLASS_PROMISE);\n"
        "    if (unlikely(JS_IsException(obj))) return JS_EXCEPTION;\n"
        "#ifndef FORCE_GC_AT_MALLOC\n"
        "    if (likely(ctx->rt->fast_pools && ctx->rt->fast_pools->promise_data_count)) { s = (JSPromiseData *)ctx->rt->fast_pools->promise_data_pool[--ctx->rt->fast_pools->promise_data_count]; memset(s, 0, sizeof(*s)); } else\n"
        "#endif\n"
        "    { s = js_mallocz(ctx, sizeof(*s));\n"
        "    if (unlikely(!s)) { JS_FreeValue(ctx, obj); return JS_EXCEPTION; } }",
    )
    text = replace_exact_lines(
        text,
        "    if (JS_ToIndex(ctx, &pos, argv[0]))\n"
        "        return JS_EXCEPTION;\n"
        "    littleEndian = argc > 1 && JS_ToBool(ctx, argv[1]);",
        "    if (likely(JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT && JS_VALUE_GET_INT(argv[0]) >= 0)) pos = (uint32_t)JS_VALUE_GET_INT(argv[0]); else if (JS_ToIndex(ctx, &pos, argv[0])) return JS_EXCEPTION;\n"
        "    littleEndian = argc > 1 && (JS_VALUE_GET_TAG(argv[1]) == JS_TAG_BOOL ? JS_VALUE_GET_BOOL(argv[1]) : JS_ToBool(ctx, argv[1]));",
    )
    text = replace_exact_lines(
        text,
        "    if (JS_ToIndex(ctx, &pos, argv[0]))\n"
        "        return JS_EXCEPTION;\n"
        "    val = argv[1];\n"
        "    v = 0; /* avoid warning */\n"
        "    v64 = 0; /* avoid warning */\n"
        "    if (class_id <= JS_CLASS_UINT32_ARRAY) {\n"
        "        if (JS_ToUint32(ctx, &v, val))\n"
        "            return JS_EXCEPTION;\n"
        "    } else if (class_id <= JS_CLASS_BIG_UINT64_ARRAY) {\n"
        "        if (JS_ToBigInt64(ctx, (int64_t *)&v64, val))\n"
        "            return JS_EXCEPTION;\n"
        "    } else {\n"
        "        double d;\n"
        "        if (JS_ToFloat64(ctx, &d, val))\n"
        "            return JS_EXCEPTION;",
        "    if (likely(JS_VALUE_GET_TAG(argv[0]) == JS_TAG_INT && JS_VALUE_GET_INT(argv[0]) >= 0)) pos = (uint32_t)JS_VALUE_GET_INT(argv[0]); else if (JS_ToIndex(ctx, &pos, argv[0])) return JS_EXCEPTION;\n"
        "    val = argv[1]; v = 0; v64 = 0;\n"
        "    if (class_id <= JS_CLASS_UINT32_ARRAY) {\n"
        "        if (likely(JS_VALUE_GET_TAG(val) == JS_TAG_INT)) v = (uint32_t)JS_VALUE_GET_INT(val); else if (JS_ToUint32(ctx, &v, val)) return JS_EXCEPTION;\n"
        "    } else if (class_id <= JS_CLASS_BIG_UINT64_ARRAY) {\n"
        "        if (JS_ToBigInt64(ctx, (int64_t *)&v64, val)) return JS_EXCEPTION;\n"
        "    } else {\n"
        "        double d;\n"
        "        if (likely(JS_VALUE_GET_TAG(val) == JS_TAG_FLOAT64)) d = JS_VALUE_GET_FLOAT64(val); else if (JS_VALUE_GET_TAG(val) == JS_TAG_INT) d = (double)JS_VALUE_GET_INT(val); else if (JS_ToFloat64(ctx, &d, val)) return JS_EXCEPTION;",
    )
    text = replace_exact_lines(
        text,
        "    littleEndian = argc > 2 && JS_ToBool(ctx, argv[2]);",
        "    littleEndian = argc > 2 && (JS_VALUE_GET_TAG(argv[2]) == JS_TAG_BOOL ? JS_VALUE_GET_BOOL(argv[2]) : JS_ToBool(ctx, argv[2]));",
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
        "        if ((uint32_t)(p->len - 1u) < 18u && rt->fast_pool_ok && !rt->in_free && !rt->malloc_state.malloc_limit && (rt->fast_pools || (rt->fast_pools = js_mallocz_rt(rt, sizeof(QJSFastValuePools))) != NULL) && rt->fast_pools->bigint_count[p->len] < 8u) { rt->fast_pools->bigint_pool[p->len][rt->fast_pools->bigint_count[p->len]++] = p; break; }\n"
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
    text = replace_exact_lines(
        text,
        "    if (JS_VALUE_GET_TAG(val) == JS_TAG_INT) {\n"
        "        char buf1[70];\n"
        "        int len;\n"
        "        len = i64toa_radix(buf1, JS_VALUE_GET_INT(val), base);\n"
        "        return js_new_string8_len(ctx, buf1, len);\n"
        "    }",
        "    if (JS_VALUE_GET_TAG(val) == JS_TAG_INT) {\n"
        "        char buf1[70]; int len;\n"
        "        if (likely(base == 10)) return qjs_int_to_string_fast(ctx, JS_VALUE_GET_INT(val));\n"
        "        len = i64toa_radix(buf1, JS_VALUE_GET_INT(val), base);\n"
        "        return js_new_string8_len(ctx, buf1, len);\n"
        "    }",
    )
    text = replace_exact_lines(
        text,
        "        return 0;\n"
        "    }\n"
        "    op1 = JS_ToNumericFree(ctx, op1);\n"
        "    if (JS_IsException(op1)) {\n"
        "        JS_FreeValue(ctx, op2);\n"
        "        goto exception;\n"
        "    }\n"
        "    op2 = JS_ToNumericFree(ctx, op2);\n"
        "    if (JS_IsException(op2)) {\n"
        "        JS_FreeValue(ctx, op1);\n"
        "        goto exception;\n"
        "    }\n"
        "    tag1 = JS_VALUE_GET_NORM_TAG(op1);",
        "        return 0;\n"
        "    }\n"
        "    if (unlikely((tag1 == JS_TAG_BIG_INT || tag1 == JS_TAG_SHORT_BIG_INT) && (tag2 == JS_TAG_BIG_INT || tag2 == JS_TAG_SHORT_BIG_INT))) {\n"
        "        int _br = qjs_binary_arith_bigint_fast(ctx, sp, op, op1, op2);\n"
        "        if (likely(_br > 0)) return 0;\n"
        "        if (unlikely(_br < 0)) goto exception;\n"
        "        goto slow_big_int;\n"
        "    }\n"
        "    op1 = JS_ToNumericFree(ctx, op1); if (JS_IsException(op1)) { JS_FreeValue(ctx, op2); goto exception; }\n"
        "    op2 = JS_ToNumericFree(ctx, op2); if (JS_IsException(op2)) { JS_FreeValue(ctx, op1); goto exception; }\n"
        "    \n"
        "    \n"
        "    tag1 = JS_VALUE_GET_NORM_TAG(op1);",
    )
    text = replace_exact_lines(
        text,
        "        sp[-2] = __JS_NewShortBigInt(ctx, v);\n"
        "        return 0;\n"
        "    }\n"
        "    op1 = JS_ToNumericFree(ctx, op1);\n"
        "    if (JS_IsException(op1)) {\n"
        "        JS_FreeValue(ctx, op2);\n"
        "        goto exception;\n"
        "    }\n"
        "    op2 = JS_ToNumericFree(ctx, op2);\n"
        "    if (JS_IsException(op2)) {\n"
        "        JS_FreeValue(ctx, op1);\n"
        "        goto exception;\n"
        "    }\n"
        "\n"
        "    tag1 = JS_VALUE_GET_TAG(op1);",
        "        sp[-2] = __JS_NewShortBigInt(ctx, v);\n"
        "        return 0;\n"
        "    }\n"
        "    if (unlikely((tag1 == JS_TAG_BIG_INT || tag1 == JS_TAG_SHORT_BIG_INT) && (tag2 == JS_TAG_BIG_INT || tag2 == JS_TAG_SHORT_BIG_INT))) {\n"
        "        int _br = qjs_binary_logic_bigint_fast(ctx, sp, op, op1, op2);\n"
        "        if (likely(_br > 0)) return 0;\n"
        "        if (unlikely(_br < 0)) goto exception;\n"
        "        goto slow_big_int;\n"
        "    }\n"
        "    op1 = JS_ToNumericFree(ctx, op1); if (JS_IsException(op1)) { JS_FreeValue(ctx, op2); goto exception; }\n"
        "    op2 = JS_ToNumericFree(ctx, op2); if (JS_IsException(op2)) { JS_FreeValue(ctx, op1); goto exception; }\n"
        "    \n"
        "    \n"
        "    \n"
        "    tag1 = JS_VALUE_GET_TAG(op1);",
    )
    text = replace_exact_lines(
        text,
        "    tag1 = JS_VALUE_GET_NORM_TAG(op1);\n"
        "    tag2 = JS_VALUE_GET_NORM_TAG(op2);\n"
        "\n"
        "    op1 = JS_ToPrimitiveFree(ctx, op1, HINT_NUMBER);\n"
        "    if (JS_IsException(op1)) {\n"
        "        JS_FreeValue(ctx, op2);\n"
        "        goto exception;\n"
        "    }\n"
        "    op2 = JS_ToPrimitiveFree(ctx, op2, HINT_NUMBER);\n"
        "    if (JS_IsException(op2)) {\n"
        "        JS_FreeValue(ctx, op1);\n"
        "        goto exception;\n"
        "    }",
        "    tag1 = JS_VALUE_GET_NORM_TAG(op1);\n"
        "    tag2 = JS_VALUE_GET_NORM_TAG(op2);\n"
        "    if (unlikely((tag1 == JS_TAG_BIG_INT || tag1 == JS_TAG_SHORT_BIG_INT) && (tag2 == JS_TAG_BIG_INT || tag2 == JS_TAG_SHORT_BIG_INT))) {\n"
        "        res = js_compare_bigint(ctx, op, op1, op2); if (unlikely(res < 0)) goto exception; goto done;\n"
        "    }\n"
        "    op1 = JS_ToPrimitiveFree(ctx, op1, HINT_NUMBER);\n"
        "    if (JS_IsException(op1)) { JS_FreeValue(ctx, op2); goto exception; }\n"
        "    op2 = JS_ToPrimitiveFree(ctx, op2, HINT_NUMBER);\n"
        "    if (JS_IsException(op2)) { JS_FreeValue(ctx, op1); goto exception; }\n"
        "    \n"
        "    \n"
        "    \n"
        "    ",
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


def free_and_generator_fast_paths(text):
    before_lines = text.count("\n")
    text = replace_exact_lines(
        text,
        "void JS_FreeValue(JSContext *ctx, JSValue v)\n"
        "{\n"
        "    JS_FreeValueRT(ctx->rt, v);\n"
        "}\n\n"
        "/* garbage collection */",
        "void JS_FreeValue(JSContext *ctx, JSValue v)\n"
        "{\n"
        "    JS_FreeValueRT(ctx->rt, v);\n"
        "}\n"
        '#include "src/common/value/free-value-inline.inc"\n'
        "/* garbage collection */",
    )
    text = replace_exact_lines(
        text,
        "static bool needs_backtrace(JSValue exc)\n"
        "{\n"
        "    return can_store_error_stack(exc) || can_add_backtrace(exc);\n"
        "}",
        "static bool needs_backtrace(JSValue exc) { return can_store_error_stack(exc) || can_add_backtrace(exc); }\n"
        "#define QJS_FREE_INLINE_DEF 1\n"
        '#include "src/common/value/free-value-inline.inc"\n',
    )
    text = replace_exact_lines(
        text,
        "\n/* warning: the refcount of the context is not incremented. Return\n"
        "   NULL in case of exception (case of revoked proxy only) */\n"
        "static JSContext *JS_GetFunctionRealm(JSContext *ctx, JSValueConst func_obj)",
        "#define QJS_FREE_INLINE_UNDEF 1\n"
        '#include "src/common/value/free-value-inline.inc"\n\n'
        "static JSContext *JS_GetFunctionRealm(JSContext *ctx, JSValueConst func_obj)",
    )
    text = replace_exact_lines(
        text,
        "/* enum_rec [objs] -> enum_rec [objs] value done. There are 'offset'\n"
        "   objs. If 'done' is true or in case of exception, 'enum_rec' is set\n"
        "   to undefined. If 'done' is true, 'value' is always set to\n"
        "   undefined. */\n"
        "static __exception int js_for_of_next(JSContext *ctx, JSValue *sp, int offset)\n"
        "{\n"
        "    JSValue value = JS_UNDEFINED;\n"
        "    int done = 1;\n\n"
        "    if (likely(!JS_IsUndefined(sp[offset]))) {\n"
        "        value = JS_IteratorNext(ctx, sp[offset], sp[offset + 1], 0, NULL, &done);",
        "static JSValue js_generator_next(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv, int *pdone, int magic); static int js_generator_for_of_next_fast(JSContext *ctx, JSValue *sp, int offset);\n"
        "static __exception int js_for_of_next(JSContext *ctx, JSValue *sp, int offset)\n"
        "{\n"
        "    JSValue value = JS_UNDEFINED; int done = 1;\n"
        "    if (likely(!JS_IsUndefined(sp[offset]))) {\n"
        "        JSValueConst iter_m = sp[offset + 1];\n"
        "        if (likely(JS_VALUE_GET_TAG(iter_m) == JS_TAG_OBJECT && JS_VALUE_GET_OBJ(iter_m)->class_id == JS_CLASS_C_FUNCTION && JS_VALUE_GET_OBJ(iter_m)->u.cfunc.cproto == JS_CFUNC_iterator_next)) {\n"
        "            JSObject *mp = JS_VALUE_GET_OBJ(iter_m); JSValueConst arg0 = JS_UNDEFINED;\n"
        "            if (mp->u.cfunc.c_function.iterator_next == js_generator_next && mp->u.cfunc.magic == 0) { int gres = js_generator_for_of_next_fast(ctx, sp, offset); if (likely(gres <= 0)) return gres; value = js_generator_next(ctx, sp[offset], 0, &arg0, &done, 0); } else { value = mp->u.cfunc.c_function.iterator_next(ctx, sp[offset], 0, &arg0, &done, mp->u.cfunc.magic); }\n"
        '            if (unlikely(!JS_IsException(value) && done == 2)) { if (!JS_IsObject(value)) { js_free_val_inline(ctx, value); JS_ThrowTypeError(ctx, "iterator must return an object"); value = JS_EXCEPTION; } else { JSValue dv = JS_GetProperty(ctx, value, JS_ATOM_done); if (JS_IsException(dv)) { js_free_val_inline(ctx, value); value = JS_EXCEPTION; } else { done = JS_ToBoolFree(ctx, dv); JSValue nv = done ? JS_UNDEFINED : JS_GetProperty(ctx, value, JS_ATOM_value); js_free_val_inline(ctx, value); value = nv; } } }\n'
        "        } else { value = JS_IteratorNext(ctx, sp[offset], iter_m, 0, NULL, &done); }",
    )
    text = replace_exact_lines(
        text,
        "    return ret;\n"
        "}\n\n"
        "static JSValue js_call_generator_function(JSContext *ctx, JSValueConst func_obj,",
        "    return ret;\n"
        "}\n"
        'static int js_generator_for_of_next_fast(JSContext *ctx, JSValue *sp, int offset) { JSValueConst gv = sp[offset]; if (likely(JS_VALUE_GET_TAG(gv) == JS_TAG_OBJECT)) { JSObject *go = JS_VALUE_GET_OBJ(gv); if (likely(go->class_id == JS_CLASS_GENERATOR)) { JSGeneratorData *s = go->u.generator_data; if (likely(s && s->state == JS_GENERATOR_STATE_SUSPENDED_YIELD)) { JSStackFrame *sf = &s->func_state.frame; JSValue func_ret; sf->cur_sp[-1] = JS_UNDEFINED; sf->cur_sp[0] = JS_MKVAL(JS_TAG_INT, GEN_MAGIC_NEXT); sf->cur_sp++; s->func_state.throw_flag = false; s->state = JS_GENERATOR_STATE_EXECUTING; func_ret = async_func_resume(ctx, &s->func_state); s->state = JS_GENERATOR_STATE_SUSPENDED_YIELD; if (likely(JS_VALUE_GET_TAG(func_ret) == JS_TAG_INT && JS_VALUE_GET_INT(func_ret) == FUNC_RET_YIELD)) { sp[0] = sf->cur_sp[-1]; sf->cur_sp[-1] = JS_UNDEFINED; sp[1] = JS_FALSE; return 0; } if (JS_IsException(func_ret)) { free_generator_stack(ctx, s); JSValue c = sp[offset]; sp[offset] = JS_UNDEFINED; js_free_val_inline(ctx, c); return -1; } if (JS_VALUE_GET_TAG(func_ret) == JS_TAG_INT) { JSValue yobj = sf->cur_sp[-1]; sf->cur_sp[-1] = JS_UNDEFINED; s->state = JS_GENERATOR_STATE_SUSPENDED_YIELD_STAR; if (!JS_IsObject(yobj)) { js_free_val_inline(ctx, yobj); JS_ThrowTypeError(ctx, "iterator must return an object"); JSValue c = sp[offset]; sp[offset] = JS_UNDEFINED; js_free_val_inline(ctx, c); return -1; } JSValue dv = JS_GetProperty(ctx, yobj, JS_ATOM_done); if (JS_IsException(dv)) { js_free_val_inline(ctx, yobj); JSValue c = sp[offset]; sp[offset] = JS_UNDEFINED; js_free_val_inline(ctx, c); return -1; } int done = JS_ToBoolFree(ctx, dv); if (done) { js_free_val_inline(ctx, yobj); JSValue c = sp[offset]; sp[offset] = JS_UNDEFINED; js_free_val_inline(ctx, c); sp[0] = JS_UNDEFINED; sp[1] = JS_TRUE; return 0; } JSValue nv = JS_GetProperty(ctx, yobj, JS_ATOM_value); js_free_val_inline(ctx, yobj); if (JS_IsException(nv)) { JSValue c = sp[offset]; sp[offset] = JS_UNDEFINED; js_free_val_inline(ctx, c); return -1; } sp[0] = nv; sp[1] = JS_FALSE; return 0; } js_free_val_inline(ctx, sf->cur_sp[-1]); sf->cur_sp[-1] = JS_UNDEFINED; js_free_val_inline(ctx, func_ret); free_generator_stack(ctx, s); JSValue c = sp[offset]; sp[offset] = JS_UNDEFINED; js_free_val_inline(ctx, c); sp[0] = JS_UNDEFINED; sp[1] = JS_TRUE; return 0; } } } return 1; }\n'
        "static JSValue js_call_generator_function(JSContext *ctx, JSValueConst func_obj,",
    )
    if text.count("\n") != before_lines:
        raise ValueError("free_and_generator_fast_paths overlay changed logical line count")
    return text


def core_overlay(text):
    return free_and_generator_fast_paths(
        string_key_lookup(value_fast_paths(async_output(map_keys(text))))
    )
