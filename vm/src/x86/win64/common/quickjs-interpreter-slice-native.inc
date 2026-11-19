/* Internal interpreter-view builtin: no padded argv, by-value this or hidden result.
 * The assembler publishes the retained C SF/TLS/GC protocol. SF var_buf points
 * to the stable borrowed this cell; arg_buf/arg_count describe actual values.
 * Neither the frame nor the cells are owned by this builtin. MIT. */
/* Nonmoving transient C view. The parent JSFrame owns every borrowed cell.
 * RT charge includes record128; the JS-state record and its layout stay fixed.
 * Shared child JS frames start at segment.used after this C record. */
typedef struct JSNativeFrameView {
    JSStackFrame sf;
    FRAME_STACK_TAIL_PADDING
    void *anchor_prev, *anchor_state;
    unsigned anchor_kind;
    void **tls_slot;
    unsigned char saved_active, padding[15];
} JSNativeFrameView;
_Static_assert(sizeof(JSNativeFrameView) == 128 && offsetof(JSNativeFrameView, anchor_prev) == 80 &&
                   offsetof(JSNativeFrameView, anchor_state) == 88 &&
                   offsetof(JSNativeFrameView, anchor_kind) == 96 &&
                   offsetof(JSNativeFrameView, tls_slot) == 104 &&
                   offsetof(JSNativeFrameView, saved_active) == 112,
               "arena C-frame ABI");
extern JSValue js_string_slice(JSContext *, JSValueConst, int, JSValueConst *);
_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame &&
                   offsetof(JSStackFrame, var_buf) == QJS_ABI_OFF_JSStackFrame_var_buf &&
                   offsetof(JSStackFrame, arg_count) == QJS_ABI_OFF_JSStackFrame_arg_count,
               "native builtin view ABI");
_Static_assert(offsetof(JSRuntime, module_loader_has_attr) ==
                       QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
                   sizeof(bool) == 1 && offsetof(JSRuntime, u) == QJS_ABI_OFF_JSRuntime_u,
               "slice mode1365 is separate from arena1366 and owned1367");
static inline JSValueConst frame_slice_argument(const JSStackFrame *sf, unsigned i)
{
    return i < sf->arg_count ? sf->arg_buf[i] : JS_UNDEFINED;
}
NATIVE_SLICE_CODE void JS_FrameStringSliceNative(JSStackFrame *sf, JSValue *out)
{
    JSContext *ctx = JS_VALUE_GET_OBJ(sf->cur_func)->u.cfunc.realm;
    JSValue str, end_value;
    JSString *p;
    int len, start, end;
    str = JS_ToStringCheckObject(ctx, sf->var_buf[0]);
    if (JS_IsException(str)) {
        *out = str;
        return;
    }
    p = JS_VALUE_GET_STRING(str);
    len = p->len;
    if (JS_ToInt32Clamp(ctx, &start, frame_slice_argument(sf, 0), 0, len, len))
        goto fail;
    end = len;
    end_value = frame_slice_argument(sf, 1);
    if (!JS_IsUndefined(end_value) && JS_ToInt32Clamp(ctx, &end, end_value, 0, len, len))
        goto fail;
    *out = js_sub_string(ctx, p, start, max_int(end, start));
    JS_FreeValue(ctx, str);
    return;
fail:
    JS_FreeValue(ctx, str);
    *out = JS_EXCEPTION;
}

_Static_assert(offsetof(JSStackFrame, is_strict_mode) == QJS_ABI_OFF_JSStackFrame_is_strict_mode &&
                   offsetof(JSStackFrame, cur_sp) == QJS_ABI_OFF_JSStackFrame_cur_sp,
               "private prepared-window marker uses padding63; root62 unchanged");

/* Byte1365 alone owns native controls. Existing null validation1362,
 * add_loc1363 and borrowed slot free1364 must remain independent. */
/* Descriptor contract: live C function, private length1/generic_magic/magic0,
 * exact js_number_toString code pointer, actual argc0. Explicit radix and
 * toLocaleString retain the core entry. This is the exact decimal reduction
 * of the core semantic body, including boxed numbers, NaN/-0 and exceptions.
 * Its helper bodies are copied/inlined by the audited adapter; no user
 * coercion is omitted. Allocation still runs with SF/TLS/GC published. */
extern JSValue js_number_toString(JSContext *, JSValueConst, int, JSValueConst *, int);
NATIVE_SLICE_CODE void JS_FrameNumberToStringNative(JSStackFrame *sf, JSValue *out)
{
    JSContext *ctx = JS_VALUE_GET_OBJ(sf->cur_func)->u.cfunc.realm;
    JSValue val = js_thisNumberValue(ctx, sf->var_buf[0]);
    double d;
    if (JS_IsException(val)) {
        *out = val;
        return;
    }
    if (JS_VALUE_GET_TAG(val) == JS_TAG_INT) {
        char buf[70];
        int len = i64toa_radix(buf, JS_VALUE_GET_INT(val), 10);
        *out = js_new_string8_len(ctx, buf, len);
        return;
    }
    if (JS_ToFloat64Free(ctx, &d, val)) {
        *out = JS_EXCEPTION;
        return;
    }
    *out = js_dtoa2(ctx, d, 10, 0, JS_DTOA_FORMAT_FREE);
}
NATIVE_SLICE_CODE void JS_FrameBuiltinNative(JSStackFrame *sf, JSValue *out)
{
    JSCFunctionMagic *target;
    __asm__("lea qjs_frame_core_js_number_toString(%%rip), %0" : "=r"(target));
    if (JS_VALUE_GET_OBJ(sf->cur_func)->u.cfunc.c_function.generic_magic == target)
        JS_FrameNumberToStringNative(sf, out);
    else
        JS_FrameStringSliceNative(sf, out);
}
_Static_assert(offsetof(JSRuntime, module_loader_has_attr) ==
                       QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
                   offsetof(JSRuntime, u) == QJS_ABI_OFF_JSRuntime_u,
               "packed native mode1365 stays in runtime padding");
