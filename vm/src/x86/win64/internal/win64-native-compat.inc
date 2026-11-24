/* Source-level Windows x86-64 native ASM VM compatibility definitions.
 * Works with MSVC (cl.exe + ml64.exe) and clang-cl without GNU binutils. */
#define QJS_FRAME_NUMBER_ADD_EMPTY_STRING 1
#define QJS_FRAME_LOCAL_ROPE_APPEND 1
#define FRAME_RT_SHARED_BYTE (offsetof(JSRuntime, current_stack_frame) - 5)
#define QJS_FRAME_SHARED_TLS_HEADER "src/x86/win64/common/interpreter-shared-tls.inc"
#define QJS_FRAME_SHARED_SUPPLEMENTS_HEADER "src/x86/win64/internal/win64-native-supplements.inc"
#if defined(_MSC_VER)
#define QJS_FRAME_SLOW_HOST_CODE __declspec(code_seg(".qjsvm$zzslow")) __declspec(noinline)
#elif defined(__has_attribute) && __has_attribute(noipa)
#define QJS_FRAME_SLOW_HOST_CODE __attribute__((section(".qjsvm$zzslow"), noipa))
#else
#define QJS_FRAME_SLOW_HOST_CODE __attribute__((section(".qjsvm$zzslow"), noinline))
#endif
#if QJS_ABI_HAS_CORO_OWNER
#define FRAME_STACK_TAIL_PADDING
#define FRAME_INIT_STACK_AUX(sf, is_ctor)                                                          \
    do {                                                                                           \
        (sf)->is_constructor = (is_ctor);                                                          \
        (sf)->cur_gc_obj = NULL;                                                                   \
    } while (0)
#define FRAME_CLEAR_STACK_AUX(sf) FRAME_INIT_STACK_AUX(sf, false)
#define FRAME_STACK_CORO_OFFSET_VALID (offsetof(JSStackFrame, cur_gc_obj) == 72)
#else
#define FRAME_STACK_TAIL_PADDING void *frame_abi_reserved;
#define FRAME_INIT_STACK_AUX(sf, is_ctor) ((void)(sf), (void)(is_ctor))
#define FRAME_CLEAR_STACK_AUX(sf) ((void)(sf))
#define FRAME_STACK_CORO_OFFSET_VALID (sizeof(JSStackFrame) == 72)
#endif
#if !QJS_ABI_HAS_PREFIX_RC
#define JS_REF_COUNT(p) (((JSRefCountHeader *)(p))->ref_count)
#define JS_GC_TYPE(p) (((JSGCObjectHeader *)(p))->gc_obj_type)
#define JS_GC_MARK(p) (((JSGCObjectHeader *)(p))->mark)
static inline JSShapeProperty *get_shape_prop(JSShape *shape)
{
    return shape->prop;
}
#endif

/* Both inputs are primitive strings. Consume the suffix on success or error,
 * and keep the original local intact if allocation fails. */
static int js_frame_append_local_rope(JSContext *ctx, JSValue *local, JSValue suffix)
{
    JSStringRope *rope = JS_VALUE_GET_STRING_ROPE(*local);
    JSString *part = JS_VALUE_GET_STRING(suffix);
    uint32_t added = part->len;
    JSValue joined;
    if (JS_REF_COUNT(rope) != 1 || JS_VALUE_GET_TAG(rope->right) != JS_TAG_STRING ||
        added > JS_STRING_ROPE_SHORT_LEN || rope->len > JS_STRING_LEN_MAX - added ||
        JS_VALUE_GET_STRING(rope->right)->len > JS_STRING_ROPE_SHORT_LEN) {
        joined = JS_ConcatString(ctx, js_dup(*local), suffix);
        if (JS_IsException(joined))
            return -1;
        set_value(ctx, local, joined);
        return 0;
    }

    JSString *tail = JS_VALUE_GET_STRING(rope->right);
    bool wide = part->is_wide_char;
    size_t length = tail->len + added;
    if (JS_REF_COUNT(tail) == 1 && !tail->atom_type && tail->kind == JS_STRING_KIND_NORMAL &&
        tail->is_wide_char == wide &&
        js_malloc_usable_size(ctx, tail) >= sizeof(*tail) + (length << wide) + !wide) {
        if (wide) {
            memcpy(str16(tail) + tail->len, str16(part), (size_t)added * 2);
        } else {
            memcpy(str8(tail) + tail->len, str8(part), added);
            str8(tail)[length] = 0;
        }
        tail->len = (uint32_t)length;
        tail->hash = 0;
        JS_FreeValue(ctx, suffix);
    } else {
        /* A shared leaf or a full allocation needs a new flat tail. The
         * unaliased rope node and its left subtree can still be retained. */
        joined = JS_ConcatString2(ctx, js_dup(rope->right), suffix);
        if (JS_IsException(joined))
            return -1;
        set_value(ctx, &rope->right, joined);
    }
    rope->len += added;
    rope->is_wide_char |= wide;
    return 0;
}
