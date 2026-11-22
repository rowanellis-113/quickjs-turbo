/* Source-level Windows x86-64 native ASM VM compatibility definitions.
 * Works with MSVC (cl.exe + ml64.exe) and clang-cl without GNU binutils. */
#define FRAME_RT_SHARED_BYTE (offsetof(JSRuntime, current_stack_frame) - 5)
#define QJS_FRAME_SHARED_TLS_HEADER "src/x86/win64/common/interpreter-shared-tls.inc"
#define QJS_FRAME_SHARED_SUPPLEMENTS_HEADER "src/x86/win64/internal/win64-native-supplements.inc"
#if defined(_MSC_VER)
#define QJS_FRAME_SLOW_HOST_CODE __declspec(code_seg(".qjsvm$zzslow")) __declspec(noinline)
#else
#define QJS_FRAME_SLOW_HOST_CODE __attribute__((section(".qjsvm$zzslow"), noipa))
#endif
#define FRAME_STACK_TAIL_PADDING void *frame_abi_reserved;
#define FRAME_CLEAR_STACK_AUX(sf) ((void)(sf))
#define FRAME_STACK_CORO_OFFSET_VALID (sizeof(JSStackFrame) == 72)
#define JS_REF_COUNT(p) (((JSRefCountHeader *)(p))->ref_count)
#define JS_GC_TYPE(p) (((JSGCObjectHeader *)(p))->gc_obj_type)
#define JS_GC_MARK(p) (((JSGCObjectHeader *)(p))->mark)
static inline JSShapeProperty *get_shape_prop(JSShape *shape)
{
    return shape->prop;
}
