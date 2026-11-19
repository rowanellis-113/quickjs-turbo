#ifndef QJS_FRAME_RETAINED_CONTEXT
#define QJS_FRAME_RETAINED_CONTEXT
#if defined(QJS_INTERP_FRAME_LINUX)
#include "interpreter-private-abi.h"
#else
#include "quickjs-interpreter-retained-private.h"
#endif
/* Retained selectors follow logical forward records as well as real JS frames. */
#define js_frame_parent js_frame_plain_parent
#include "src/common/call/interpreter-context-types.inc"
#undef js_frame_parent
#define FRAME_ITERATOR_OFFSET                                                                      \
    (offsetof(JSFunctionBytecode, pc2line_len) + sizeof(((JSFunctionBytecode *)0)->pc2line_len))
#define FRAME_ITERATOR_KIND(b) (((unsigned char *)(b))[FRAME_ITERATOR_OFFSET])
#define FRAME_VARARGS_DIRECT_MODE(b) (((unsigned char *)(b))[FRAME_ITERATOR_OFFSET + 1])
#define FRAME_VARARGS_FUSION_MODE(b) (((unsigned char *)(b))[FRAME_ITERATOR_OFFSET + 2])
#define FRAME_CALL_FORWARD_MODE(b) (((unsigned char *)(b))[FRAME_ITERATOR_OFFSET + 3])
_Static_assert(FRAME_ITERATOR_OFFSET + 4 <= offsetof(JSFunctionBytecode, pc2line_buf),
               "iterator metadata uses original bytecode padding");
#define FRAME_FORWARD_TAG 199
#define FRAME_FORWARD_BYTES 80
_Static_assert(sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame && sizeof(JSFrame) == 128 &&
                   offsetof(JSStackFrame, cur_sp) == 64 && offsetof(JSStackFrame, var_buf) == 32 &&
                   FRAME_ROOT_OFFSET == 62,
               "logical native frame retains the measured upstream prefix");
_Static_assert(FRAME_FORWARD_BYTES >= sizeof(JSStackFrame) &&
                   FRAME_FORWARD_BYTES - sizeof(JSStackFrame) <= 8,
               "fixed logical allocation includes only measured tail padding");
static FRAME_INLINE bool js_frame_forward_sf(JSStackFrame *sf)
{
    return sf && sf->var_buf == NULL && ((unsigned char *)sf)[63] == FRAME_FORWARD_TAG;
}
static FRAME_INLINE JSStackFrame *js_frame_forward_parent(JSFrame *frame)
{
    JSStackFrame *sf = frame->sf.prev_frame;
    if (FRAME_ROOT(frame) != 1)
        while (js_frame_forward_sf(sf))
            sf = sf->prev_frame;
    return sf;
}
/* Called only after closing/freeing the child. Keep logical frames visible
   throughout all observable cleanup; normalize before their storage is freed. */
static FRAME_INLINE size_t js_frame_forward_take(JSFrame *frame)
{
    JSStackFrame *sf = frame->sf.prev_frame;
    size_t bytes = 0;
    if (FRAME_ROOT(frame) != 1) {
        while (js_frame_forward_sf(sf)) {
            bytes += FRAME_FORWARD_BYTES;
            sf = sf->prev_frame;
        }
        frame->sf.prev_frame = sf;
    }
    return bytes;
}

static FRAME_INLINE JSFrame *js_frame_parent(JSFrame *frame)
{
    return FRAME_ROOT(frame) == 1 ? NULL : (JSFrame *)js_frame_forward_parent(frame);
}

#endif
