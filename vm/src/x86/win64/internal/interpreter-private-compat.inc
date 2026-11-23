/* Win64 selected-source differences only. The preceding measured ABI contract
 * validates the original types; this file never changes an upstream type. */
#include "src/common/call/interpreter-bytecode-metadata.inc"
#define FRAME_RT_SHARED_BYTE (QJS_ABI_OFF_JSRuntime_current_stack_frame - 5)
#define QJS_FRAME_SHARED_TLS_HEADER "src/x86/win64/common/interpreter-shared-tls.inc"
#define QJS_FRAME_SHARED_SUPPLEMENTS_HEADER                                                        \
    "src/x86/win64/common/interpreter-shared-supplements.inc"
#define FRAME_RT_HOST_BYTE (QJS_ABI_OFF_JSRuntime_current_stack_frame - 4)
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
/* Keep the private native activation's established 80-byte prefix. This is
 * padding in our enclosing record, not a field added to JSStackFrame. Core
 * stack walkers continue to see their original 72-byte header. */
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
#if !QJS_ABI_HAS_CORO_OWNER
#include "src/common/value/arithmetic.inc"
#endif
