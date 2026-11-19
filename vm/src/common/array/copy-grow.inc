/* The original splice builtin calls this at its original CopySubArray point,
 * after conversions, species creation and copying removed elements. Keep the
 * original builtin identity, item loop and exception paths. */
#ifdef _MSC_VER
extern unsigned char JS_FrameCallMetaLoadByte(unsigned char *);
extern unsigned char JS_FrameCallMetaInitByte(unsigned char *, unsigned char);
#pragma section(".qjsacm", read, write)
__declspec(allocate(".qjsacm"))
#else
__attribute__((section(".qjsacm"), aligned(1)))
#endif
static unsigned char js_frame_array_copy_mode;

static bool js_frame_array_copy_enabled(void)
{
    unsigned char mode;
#ifdef _MSC_VER
    mode = JS_FrameCallMetaLoadByte(&js_frame_array_copy_mode);
#else
    mode = __atomic_load_n(&js_frame_array_copy_mode, __ATOMIC_RELAXED);
#endif
    if (unlikely(!mode)) {
        unsigned char desired = getenv("QJS_DISABLE_ARRAY_COPY_GROW") ? 2 : 1;
#ifdef _MSC_VER
        mode = JS_FrameCallMetaInitByte(&js_frame_array_copy_mode, desired);
#else
        __atomic_compare_exchange_n(&js_frame_array_copy_mode, &mode, desired, false,
                                    __ATOMIC_RELAXED, __ATOMIC_RELAXED);
#endif
        if (!mode)
            mode = desired;
    }
    return mode == 1;
}

int JS_FrameArrayCopySubArray(JSContext *ctx, JSValue obj, int64_t to, int64_t from, int64_t count,
                              int dir)
{
    JSObject *p, *function, *array_prototype, *object_prototype;
    JSStackFrame *frame;
    JSValue *values;
    int64_t length, new_length;
    uint32_t i, duplicate_count;
    uintptr_t arguments, begin, end;

    if (!js_frame_array_copy_enabled() || dir >= 0 || from < 0 || to <= from || count <= 0 ||
        to > INT32_MAX || count > INT32_MAX - to || !JS_IsObject(obj))
        goto original;
    p = JS_VALUE_GET_OBJ(obj);
    length = from + count;
    new_length = to + count;
    if (p->class_id != JS_CLASS_ARRAY || !p->fast_array || !p->extensible ||
        !ctx->std_array_prototype || !JS_IsObject(ctx->class_proto[JS_CLASS_ARRAY]) ||
        p->shape->proto != JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_ARRAY]) ||
        p->u.array.count != length || JS_VALUE_GET_TAG(p->prop[0].u.value) != JS_TAG_INT ||
        JS_VALUE_GET_INT(p->prop[0].u.value) != length ||
        !(p->shape->prop->flags & JS_PROP_WRITABLE))
        goto original;

    /* Check the live chain as well as the upstream summary flag. Creation
     * and mutation of prototype objects need not have armed is_prototype in
     * every embedding initialization order. Bound this ordinary shape scan;
     * a modified, exotic or longer chain keeps the original algorithm. */
    if (!JS_IsObject(ctx->class_proto[JS_CLASS_OBJECT]))
        goto original;
    array_prototype = JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_ARRAY]);
    object_prototype = JS_VALUE_GET_OBJ(ctx->class_proto[JS_CLASS_OBJECT]);
    if (array_prototype->class_id != JS_CLASS_ARRAY || !array_prototype->fast_array ||
        array_prototype->u.array.count || array_prototype->shape->proto != object_prototype ||
        object_prototype->class_id != JS_CLASS_OBJECT || object_prototype->is_exotic ||
        object_prototype->shape->proto || object_prototype->shape->prop_count > 32)
        goto original;
    for (i = 0; i < object_prototype->shape->prop_count; i++)
        if (__JS_AtomIsTaggedInt(object_prototype->shape->prop[i].atom))
            goto original;

    /* Normal and native synthetic C frames both publish this original argv.
     * C-function-data frames, detached/JS frames and unknown entries miss.
     * The 16-bit frame arg_count is NOT used as a range bound: public C calls
     * can have wider argc. A valid argv overlapping this allocation must
     * start in it (the dense vector is itself an allocation base). */
    frame = ctx->rt->current_stack_frame;
    if (!frame || !JS_IsObject(frame->cur_func))
        goto original;
    function = JS_VALUE_GET_OBJ(frame->cur_func);
    if (function->class_id != JS_CLASS_C_FUNCTION ||
        function->u.cfunc.cproto != JS_CFUNC_generic_magic || function->u.cfunc.magic != 1 ||
        function->u.cfunc.realm != ctx ||
        function->u.cfunc.c_function.generic_magic != js_array_slice || !frame->arg_buf)
        goto original;
    arguments = (uintptr_t)frame->arg_buf;
    begin = (uintptr_t)p->u.array.u.values;
    end = begin + (size_t)p->u.array.u1.size * sizeof(JSValue);
    if (arguments >= begin && arguments < end)
        goto original;

    if (new_length > p->u.array.u1.size && expand_fast_array(ctx, p, (uint32_t)new_length))
        return -1;
    values = p->u.array.u.values;
    duplicate_count = (uint32_t)min_int64(to - from, count);
    /* Unlike the complete splice operation, CopySubArray leaves the source
     * prefix in the insertion gap. Those surviving values need a second
     * reference. The overlapping remainder transfers its existing ownership.
     * No allocation, final release, callback or GC occurs in this phase. */
    for (i = 0; i < duplicate_count; i++)
        js_dup(values[from + i]);
    memmove(values + to, values + from, (size_t)count * sizeof(JSValue));
    for (i = (uint32_t)length; i < (uint32_t)to; i++)
        values[i] = JS_UNDEFINED;
    p->u.array.count = (uint32_t)new_length;
    p->prop[0].u.value = js_uint32((uint32_t)new_length);
    return 0;
original:
    return JS_CopySubArray(ctx, obj, to, from, count, dir);
}
