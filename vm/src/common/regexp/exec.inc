/*
 * QuickJS Javascript Engine
 *
 * Copyright (c) 2017-2026 Fabrice Bellard
 * Copyright (c) 2017-2025 Charlie Gordon
 * Copyright (c) 2023-2026 Ben Noordhuis
 * Copyright (c) 2023-2026 Saúl Ibarra Corretgé
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
/* Shared exec ownership and observable operations for native and C backends. */
static JSValue js_regexp_exec(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    int rc, capture_count, alloc_count, shift, index, i, re_flags, prop_flags;
    JSRegExp *re = js_get_regexp(ctx, this_val, true);
    JSString *str;
    JSValue t, ret, str_val, obj, val, groups;
    JSValue indices, indices_groups;
    uint8_t *re_bytecode;
    uint8_t **capture, *str_buf;
    uint8_t *small_capture[32];
    int64_t last_index;
    const char *group_name_ptr;
    JSAtom group_name;
    JSProperty props[4]; // length, index, input, groups, in that order

    if (!re)
        return JS_EXCEPTION;

    str_val = JS_ToString(ctx, argv[0]);
    if (JS_IsException(str_val))
        return JS_EXCEPTION;

    ret = JS_EXCEPTION;
    obj = JS_NULL;
    groups = JS_UNDEFINED;
    indices = JS_UNDEFINED;
    indices_groups = JS_UNDEFINED;
    group_name = JS_ATOM_NULL;
    capture = NULL;

    val = JS_GetProperty(ctx, this_val, JS_ATOM_lastIndex);
    if (JS_IsException(val) || JS_ToLengthFree(ctx, &last_index, val))
        goto fail;

    re_bytecode = str8(re->bytecode);
    re_flags = lre_get_flags(re_bytecode);
    if ((re_flags & (LRE_FLAG_GLOBAL | LRE_FLAG_STICKY)) == 0) {
        last_index = 0;
    }
    str = JS_VALUE_GET_STRING(str_val);
    capture_count = lre_get_capture_count(re_bytecode);
    alloc_count = lre_get_alloc_count(re_bytecode);
    if (alloc_count > 0) {
        if (alloc_count <= (int)countof(small_capture)) {
            capture = small_capture;
        } else {
            capture = js_malloc(ctx, sizeof(capture[0]) * alloc_count);
            if (!capture)
                goto fail;
        }
    }
    shift = str->is_wide_char;
    str_buf = str8(str);
    if (last_index > str->len) {
        rc = 2;
    } else {
        rc = lre_exec(capture, re_bytecode, str_buf, last_index, str->len, shift, ctx);
    }
    if (rc != 1) {
        if (rc >= 0) {
            if (rc == 2 || (re_flags & (LRE_FLAG_GLOBAL | LRE_FLAG_STICKY))) {
                if (JS_SetProperty(ctx, this_val, JS_ATOM_lastIndex, js_int32(0)) < 0)
                    goto fail;
            }
        } else {
            switch (rc) {
            case LRE_RET_TIMEOUT:
                JS_ThrowInterrupted(ctx);
                break;
            case LRE_RET_MEMORY_ERROR:
                JS_ThrowOutOfMemory(ctx);
                break;
            case LRE_RET_BYTECODE_ERROR:
                JS_ThrowInternalError(ctx, "corrupted bytecode in regexp execution");
                break;
            default:
                abort();
            }
            goto fail;
        }
    } else {
        if (re_flags & (LRE_FLAG_GLOBAL | LRE_FLAG_STICKY)) {
            if (JS_SetProperty(ctx, this_val, JS_ATOM_lastIndex,
                               js_int32((capture[1] - str_buf) >> shift)) < 0)
                goto fail;
        }
        group_name_ptr = lre_get_groupnames(re_bytecode);
        if (group_name_ptr) {
            groups = JS_NewObjectProto(ctx, JS_NULL);
            if (JS_IsException(groups))
                goto fail;
        }
        if (re_flags & LRE_FLAG_INDICES) {
            indices = JS_NewArray(ctx);
            if (JS_IsException(indices))
                goto fail;
            if (group_name_ptr) {
                indices_groups = JS_NewObjectProto(ctx, JS_NULL);
                if (JS_IsException(indices_groups))
                    goto fail;
            }
        }
        index = (capture[0] - str_buf) >> shift;
        props[0].u.value = js_int32(capture_count); // length
        props[1].u.value = js_int32(index);         // index
        props[2].u.value = str_val;                 // input
        props[3].u.value = js_dup(groups);          // groups
        str_val = JS_UNDEFINED;
        obj = JS_NewObjectFromShape(ctx, js_dup_shape(ctx->regexp_result_shape), JS_CLASS_ARRAY,
                                    props);
        if (JS_IsException(obj))
            goto fail;
        /* The new result has no published alias. Reserve once, but keep its
         * initialized prefix count exact across every allocating operation.
         * Partial failure/GC frees only slots whose JSValues we already own.
         */
        if (capture_count && expand_fast_array(ctx, JS_VALUE_GET_OBJ(obj), capture_count))
            goto fail;
        prop_flags = JS_PROP_C_W_E | JS_PROP_THROW;
        for (i = 0; i < capture_count; i++) {
            uint8_t **match = &capture[2 * i];
            int start = -1;
            int end = -1;

            if (group_name_ptr && i > 0) {
                if (*group_name_ptr) {
                    group_name = JS_NewAtom(ctx, group_name_ptr);
                    if (group_name == JS_ATOM_NULL)
                        goto fail;
                }
                group_name_ptr += strlen(group_name_ptr) + LRE_GROUP_NAME_TRAILER_LEN;
            }

            if (match[0] && match[1]) {
                start = (match[0] - str_buf) >> shift;
                end = (match[1] - str_buf) >> shift;
            }

            if (!JS_IsUndefined(indices)) {
                JSValue val = JS_UNDEFINED;
                if (start != -1) {
                    val = JS_NewArray(ctx);
                    if (JS_IsException(val))
                        goto fail;
                    if (JS_DefinePropertyValueUint32(ctx, val, 0, js_int32(start), prop_flags) <
                        0) {
                        JS_FreeValue(ctx, val);
                        goto fail;
                    }
                    if (JS_DefinePropertyValueUint32(ctx, val, 1, js_int32(end), prop_flags) < 0) {
                        JS_FreeValue(ctx, val);
                        goto fail;
                    }
                }
                if (group_name != JS_ATOM_NULL && !JS_IsUndefined(indices_groups)) {
                    /* For duplicate named groups, only the alternative that
                       actually matched (non-undefined) wins; a later
                       undefined alternative must not clobber it. */
                    if (!JS_IsUndefined(val) || !JS_HasProperty(ctx, indices_groups, group_name)) {
                        if (JS_DefinePropertyValue(ctx, indices_groups, group_name, js_dup(val),
                                                   prop_flags) < 0) {
                            JS_FreeValue(ctx, val);
                            goto fail;
                        }
                    }
                }
                if (JS_DefinePropertyValueUint32(ctx, indices, i, val, prop_flags) < 0) {
                    goto fail;
                }
            }

            JSValue val = JS_UNDEFINED;
            if (start != -1) {
                val = js_sub_string(ctx, str, start, end);
                if (JS_IsException(val))
                    goto fail;
            }

            if (group_name != JS_ATOM_NULL) {
                /* duplicate named groups: matched alternative wins (see above) */
                if (!JS_IsUndefined(val) || !JS_HasProperty(ctx, groups, group_name)) {
                    if (JS_DefinePropertyValue(ctx, groups, group_name, js_dup(val), prop_flags) <
                        0) {
                        JS_FreeValue(ctx, val);
                        goto fail;
                    }
                }
                JS_FreeAtom(ctx, group_name);
                group_name = JS_ATOM_NULL;
            }

            JS_VALUE_GET_OBJ(obj)->u.array.u.values[i] = val;
            JS_VALUE_GET_OBJ(obj)->u.array.count = (uint32_t)i + 1;
        }

        if (!JS_IsUndefined(indices)) {
            t = indices_groups, indices_groups = JS_UNDEFINED;
            if (JS_DefinePropertyValue(ctx, indices, JS_ATOM_groups, t, prop_flags) < 0) {
                goto fail;
            }
            t = indices, indices = JS_UNDEFINED;
            if (JS_DefinePropertyValue(ctx, obj, JS_ATOM_indices, t, prop_flags) < 0) {
                goto fail;
            }
        }
    }
    ret = obj;
    obj = JS_UNDEFINED;
fail:
    JS_FreeAtom(ctx, group_name);
    JS_FreeValue(ctx, indices_groups);
    JS_FreeValue(ctx, indices);
    JS_FreeValue(ctx, str_val);
    JS_FreeValue(ctx, groups);
    JS_FreeValue(ctx, obj);
    if (capture != small_capture)
        js_free(ctx, capture);
    return ret;
}
