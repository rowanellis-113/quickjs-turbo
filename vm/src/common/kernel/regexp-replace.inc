/* Preserve the original compiler-inlined JS_Call + adapter route.
 * This is the existing seven-argument platform value ABI, with COPY_ARGV.
 * Non-bytecode/native/disabled cases remain in its legacy selector path. */
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
extern JSValue JS_FrameDispatchInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                                        JSValueConst *, int);
#endif
/* Owned callback argv; independently compiled from the frozen P2 transplant. */
JSValue JS_RegExpOwnedReplace(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    /* Native string replacement keeps the exact inherited builtin path. */
    if (!JS_IsFunction(ctx, argv[1]))
        return js_regexp_Symbol_replace(ctx, this_val, argc, argv);

    // [Symbol.replace](str, rep)
    JSValueConst rx = this_val, rep = argv[1];
    JSValue args[6], *callback_argv = NULL;
    uint32_t callback_argc = 0;
    JSValue flags, str, rep_val, matched, tab, rep_str, namedCaptures, res;
    JSString *p, *sp;
    StringBuffer b_s, *b = &b_s;
    ValueBuffer v_b, *results = &v_b;
    int nextSourcePosition, n, j, functionalReplace, is_global, fullUnicode;
    uint32_t nCaptures;
    bool use_callback_argv;
    int64_t position;

    if (!JS_IsObject(rx))
        return JS_ThrowTypeErrorNotAnObject(ctx);

    string_buffer_init(ctx, b, 0);
    value_buffer_init(ctx, results);

    rep_val = JS_UNDEFINED;
    matched = JS_UNDEFINED;
    tab = JS_UNDEFINED;
    flags = JS_UNDEFINED;
    rep_str = JS_UNDEFINED;
    namedCaptures = JS_UNDEFINED;

    str = JS_ToString(ctx, argv[0]);
    if (JS_IsException(str))
        goto exception;

    sp = JS_VALUE_GET_STRING(str);
    functionalReplace = 1;
    use_callback_argv = functionalReplace;
    flags = JS_GetProperty(ctx, rx, JS_ATOM_flags);
    if (JS_IsException(flags))
        goto exception;
    flags = JS_ToStringFree(ctx, flags);
    if (JS_IsException(flags))
        goto exception;
    p = JS_VALUE_GET_STRING(flags);

    fullUnicode = 0;
    is_global = (-1 != string_indexof_char(p, 'g', 0));
    if (is_global) {
        // 'v' flag implies full Unicode, like 'u'
        fullUnicode = (string_indexof_char(p, 'u', 0) >= 0 || string_indexof_char(p, 'v', 0) >= 0);
        if (JS_SetProperty(ctx, rx, JS_ATOM_lastIndex, js_int32(0)) < 0)
            goto exception;
    }

    for (;;) {
        JSValue result;
        result = JS_RegExpExec(ctx, rx, str);
        if (JS_IsException(result))
            goto exception;
        if (JS_IsNull(result))
            break;
        if (value_buffer_append(results, result) < 0)
            goto exception;
        if (!is_global)
            break;
        JS_FreeValue(ctx, matched);
        matched = JS_ToStringFree(ctx, JS_GetPropertyInt64(ctx, result, 0));
        if (JS_IsException(matched))
            goto exception;
        if (JS_IsEmptyString(matched)) {
            /* always advance of at least one char */
            int64_t thisIndex, nextIndex;
            if (JS_ToLengthFree(ctx, &thisIndex, JS_GetProperty(ctx, rx, JS_ATOM_lastIndex)) < 0)
                goto exception;
            nextIndex = string_advance_index(sp, thisIndex, fullUnicode);
            if (JS_SetProperty(ctx, rx, JS_ATOM_lastIndex, js_int64(nextIndex)) < 0)
                goto exception;
        }
    }
    nextSourcePosition = 0;
    for (j = 0; j < results->len; j++) {
        JSValue result;
        result = results->arr[j];
        if (js_get_length32(ctx, &nCaptures, result) < 0)
            goto exception;
        JS_FreeValue(ctx, matched);
        matched = JS_ToStringFree(ctx, JS_GetPropertyInt64(ctx, result, 0));
        if (JS_IsException(matched))
            goto exception;
        if (JS_ToLengthFree(ctx, &position, JS_GetProperty(ctx, result, JS_ATOM_index)))
            goto exception;
        if (position > sp->len)
            position = sp->len;
        else if (position < 0)
            position = 0;
        /* ignore substition if going backward (can happen
           with custom regexp object) */
        JS_FreeValue(ctx, tab);
        tab = JS_UNDEFINED;
        if (callback_argv) {
            /* Keep the same lifetime as the former private match array. */
            for (n = 0; n < callback_argc; n++)
                JS_FreeValue(ctx, callback_argv[n]);
            if (callback_argv != args)
                js_free(ctx, callback_argv);
            callback_argv = NULL;
            callback_argc = 0;
        }
        /* Preserve the old near-limit path and its getter/error ordering.
           A custom exec result of length zero still supplies the match. */
        if (use_callback_argv && nCaptures <= JS_MAX_LOCAL_VARS - 3) {
            uint32_t capacity = max_uint32(1, nCaptures) + 3;
            callback_argv = capacity <= countof(args)
                                ? args
                                : js_malloc(ctx, sizeof(*callback_argv) * capacity);
            if (!callback_argv)
                goto exception;
            callback_argv[callback_argc++] = js_dup(matched);
        } else {
            tab = JS_NewArray(ctx);
            if (JS_IsException(tab))
                goto exception;
            if (JS_DefinePropertyValueInt64Const(ctx, tab, 0, matched,
                                                 JS_PROP_C_W_E | JS_PROP_THROW) < 0)
                goto exception;
        }
        for (n = 1; n < nCaptures; n++) {
            JSValue capN;
            capN = JS_GetPropertyInt64(ctx, result, n);
            if (JS_IsException(capN))
                goto exception;
            if (!JS_IsUndefined(capN)) {
                capN = JS_ToStringFree(ctx, capN);
                if (JS_IsException(capN))
                    goto exception;
            }
            if (callback_argv) {
                callback_argv[callback_argc++] = capN;
            } else if (JS_DefinePropertyValueInt64(ctx, tab, n, capN,
                                                   JS_PROP_C_W_E | JS_PROP_THROW) < 0) {
                goto exception;
            }
        }
        JS_FreeValue(ctx, namedCaptures);
        namedCaptures = JS_GetProperty(ctx, result, JS_ATOM_groups);
        if (JS_IsException(namedCaptures))
            goto exception;
        if (functionalReplace) {
            if (callback_argv) {
                callback_argv[callback_argc++] = js_int32(position);
                callback_argv[callback_argc++] = js_dup(str);
                if (!JS_IsUndefined(namedCaptures))
                    callback_argv[callback_argc++] = js_dup(namedCaptures);
            } else {
                if (JS_DefinePropertyValueInt64(ctx, tab, n++, js_int32(position),
                                                JS_PROP_C_W_E | JS_PROP_THROW) < 0)
                    goto exception;
                if (JS_DefinePropertyValueInt64Const(ctx, tab, n++, str,
                                                     JS_PROP_C_W_E | JS_PROP_THROW) < 0)
                    goto exception;
                if (!JS_IsUndefined(namedCaptures)) {
                    if (JS_DefinePropertyValueInt64Const(ctx, tab, n++, namedCaptures,
                                                         JS_PROP_C_W_E | JS_PROP_THROW) < 0)
                        goto exception;
                }
                args[0] = JS_UNDEFINED;
                args[1] = tab;
            }
            JS_FreeValue(ctx, rep_str);
            if (callback_argv) {
                if (check_function(ctx, rep))
                    rep_str = JS_EXCEPTION;
                else
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
                    rep_str = JS_FrameDispatchInternal(ctx, rep, JS_UNDEFINED, JS_UNDEFINED,
                                                       callback_argc, vc(callback_argv),
                                                       JS_CALL_FLAG_COPY_ARGV);
#else
                    rep_str = JS_Call(ctx, rep, JS_UNDEFINED, callback_argc, vc(callback_argv));
#endif
            } else {
                rep_str = js_function_apply(ctx, rep, 2, args, 0);
            }
            rep_str = JS_ToStringFree(ctx, rep_str);
        }
        if (JS_IsException(rep_str))
            goto exception;
        if (position >= nextSourcePosition) {
            string_buffer_concat(b, sp, nextSourcePosition, position);
            string_buffer_concat_value(b, rep_str);
            nextSourcePosition = position + JS_VALUE_GET_STRING(matched)->len;
        }
    }
    string_buffer_concat(b, sp, nextSourcePosition, sp->len);
    res = string_buffer_end(b);
    goto done1;

exception:
    res = JS_EXCEPTION;
    string_buffer_free(b);
done1:
    value_buffer_free(results);
    JS_FreeValue(ctx, rep_val);
    JS_FreeValue(ctx, matched);
    JS_FreeValue(ctx, flags);
    JS_FreeValue(ctx, tab);
    if (callback_argv) {
        /* Keep the same lifetime as the former private match array. */
        for (n = 0; n < callback_argc; n++)
            JS_FreeValue(ctx, callback_argv[n]);
        if (callback_argv != args)
            js_free(ctx, callback_argv);
        callback_argv = NULL;
        callback_argc = 0;
    }
    JS_FreeValue(ctx, rep_str);
    JS_FreeValue(ctx, namedCaptures);
    JS_FreeValue(ctx, str);
    return res;
}
