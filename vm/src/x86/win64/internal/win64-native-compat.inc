/* Source-level Windows x86-64 native ASM VM compatibility definitions.
 * Works with MSVC (cl.exe + ml64.exe) and clang-cl without GNU binutils. */
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
