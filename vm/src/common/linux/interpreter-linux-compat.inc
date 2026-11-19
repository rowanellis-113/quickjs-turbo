/* Shared Linux LP64 names for the owned executor. Platform gates are supplied
 * by the architecture adapter; upstream types remain unchanged. */
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
