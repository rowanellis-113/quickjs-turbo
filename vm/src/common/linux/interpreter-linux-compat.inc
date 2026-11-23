/* Shared Linux LP64 names for the owned executor. Platform gates are supplied
 * by the architecture adapter; upstream types remain unchanged. */
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
