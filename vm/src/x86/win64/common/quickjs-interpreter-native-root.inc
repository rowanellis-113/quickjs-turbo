/* Register-only C -> JS activation, outside all previous machine code.
 * The 4096-byte nonmoving initial segment and weak activation-local hints
 * have exactly the old capacities. No root-size/arena/ownership change.
 * Admission in assembly requires warmed validation and original modes.
 */
#define FRAME_INLINE inline __attribute__((always_inline))
typedef struct JSFrameSegment {
    struct JSFrameSegment *next;
    size_t capacity, used;
    uint8_t *data;
} JSFrameSegment;

typedef struct JSFrame {
    JSStackFrame sf;
    FRAME_STACK_TAIL_PADDING
    JSFunctionBytecode *bytecode;
    JSValue this_value; /* borrowed until the caller consumes its call operands */
    JSValue *saved_sp;
    JSFrameSegment *segment;
    uint32_t frame_bytes;
    uint16_t owned_args; /* cleanup suffix; allocation can be larger */
    uint16_t pending;    /* low 15 bits: operand count, high bit: tail return */
} JSFrame;

/* Ordinary native frames already publish the same parent in sf.prev_frame.
 * A root may have an outer C/coroutine frame, which is NOT a JSFrame. Byte 62
 * is verified padding after is_strict_mode in the selected C header. Initialize it after
 * all named SF fields; no core type or GC/captured-slot address is changed. */
#define FRAME_ROOT_OFFSET (offsetof(JSStackFrame, is_strict_mode) + 2)
_Static_assert(FRAME_ROOT_OFFSET < offsetof(JSStackFrame, cur_sp),
               "native activation root marker requires C frame padding");
#define FRAME_ROOT(frame) (((unsigned char *)&(frame)->sf)[FRAME_ROOT_OFFSET])
static FRAME_INLINE JSFrame *js_frame_parent(JSFrame *frame)
{
    return FRAME_ROOT(frame) ? NULL : (JSFrame *)frame->sf.prev_frame;
}
static FRAME_INLINE size_t js_frame_segment_mark(JSFrame *frame)
{
    return (uint8_t *)frame - frame->segment->data;
}
static FRAME_INLINE unsigned js_frame_pending_count(JSFrame *frame)
{
    return frame->pending & 0x7fff;
}
static FRAME_INLINE bool js_frame_pending_tail(JSFrame *frame)
{
    return (frame->pending & 0x8000) != 0;
}

typedef struct JSFrameCallSite {
    uintptr_t continuation;
    uintptr_t identity;
    uintptr_t code_identity; /* address hints only; all reads use the live callee */
    int argc;
} JSFrameCallSite;

#include "src/common/call/quickjs-interpreter-register.h"
#undef FRAME_INLINE
volatile unsigned char JS_FrameNativeRootControl
    __attribute__((section(".qjsrmet$control"), aligned(1))) = 0;
_Static_assert(sizeof(JSFrameSegment) == 32 && FRAME_ROOT_OFFSET == 62 &&
                   offsetof(JSRuntime, current_stack_frame) ==
                       QJS_ABI_OFF_JSRuntime_current_stack_frame,
               "native root shares existing SF/arena/root-marker ABI");
ROOT_CODE JSValue JS_FrameNativeRootRun(JSContext *ctx, JSValueConst func, JSValueConst this_value,
                                        JSValueConst new_target, int argc, JSValueConst *argv,
                                        int flags)
{
    JSRuntime *rt = ctx->rt;
    JSFunctionBytecode *b = JS_VALUE_GET_OBJ(func)->u.func.function_bytecode;
    uint8_t storage[4096 + 15];
    JSFrameSegment initial = {NULL, 4096, 0, NULL}, *next, *following;
    JSFrameCallSite sites[16];
    uint8_t cache_next[8] = {0};
    JSFrameRegisterState state = {0};
    JSFrame *frame;
    JSStackFrame *sf;
    JSValue *locals, *args, *vars, *stack, result;
    size_t bytes;
    int owned, i;
    (void)new_target;
    /* Poll the CALLER realm before duplication, charge or SF publication. */
    if (unlikely(js_poll_interrupts(ctx)))
        return JS_EXCEPTION;
    owned = ((flags & JS_CALL_FLAG_COPY_ARGV) || argc < b->arg_count || (FRAME_KIND(b) & 4))
                ? b->arg_count
                : 0;
    bytes = 128 + sizeof(JSValue) * (owned + b->var_count + b->stack_size) +
            ((sizeof(JSVarRef *) * b->var_ref_count + 15) & ~(size_t)15);
    /* Admission already proved bytes<=4096 before allocating the C frame.
     * Keep the exact existing logical stack check and growth capacity. */
    if (unlikely(js_check_stack_overflow(rt, bytes)))
        return JS_ThrowStackOverflow(ctx);
    initial.data = (uint8_t *)(((uintptr_t)storage + 15) & ~(uintptr_t)15);
    initial.used = bytes;
    for (i = 0; i < 16; i++)
        sites[i].continuation = 0;
    state.rt = rt;
    state.caller_ctx = ctx;
    state.sites = sites;
    state.cache_next = cache_next;
    if (unlikely(!((unsigned char *)rt)[FRAME_RT_HOST_BYTE]))
        ((unsigned char *)rt)[FRAME_RT_HOST_BYTE] = getenv("QJS_DISABLE_DIRECT_HOST_CALL") ? 2 : 1;
    state.direct_host_calls = ((unsigned char *)rt)[FRAME_RT_HOST_BYTE] == 1;
    rt->stack_top += bytes;
    if (rt->stack_limit)
        rt->stack_limit += bytes;
    frame = (JSFrame *)initial.data;
    frame->segment = &initial;
    frame->frame_bytes = bytes;
    frame->bytecode = b;
    frame->this_value = unsafe_unconst(this_value);
    frame->owned_args = owned;
    frame->pending = 0;
    locals = (JSValue *)((uint8_t *)frame + 128);
    args = (JSValue *)argv;
    if (owned) {
        args = locals;
        for (i = 0; i < min_int(argc, b->arg_count); i++)
            args[i] = js_dup(argv[i]);
        for (; i < b->arg_count; i++)
            args[i] = JS_UNDEFINED;
    }
    vars = locals + owned;
    for (i = 0; i < b->var_count; i++)
        vars[i] = JS_UNDEFINED;
    stack = vars + b->var_count;
    sf = &frame->sf;
    sf->prev_frame = rt->current_stack_frame;
    sf->cur_func = unsafe_unconst(func);
    sf->arg_buf = args;
    sf->var_buf = vars;
    sf->var_refs = b->var_ref_count ? (JSVarRef **)(stack + b->stack_size) : NULL;
    sf->var_ref_count = b->var_ref_count;
    for (i = 0; i < sf->var_ref_count; i++)
        sf->var_refs[i] = NULL;
    sf->arg_count = owned ? b->arg_count : max_int(argc, b->arg_count);
    sf->is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = NULL;
    sf->cur_sp = NULL;
    ((unsigned char *)sf)[FRAME_ROOT_OFFSET + 1] = 0;
    FRAME_ROOT(frame) = 1;
    rt->current_stack_frame = sf;
    state.frame = frame;
    state.segment = &initial;
    state.pc = b->byte_code_buf;
    state.sp = stack;
    state.used_bytes = state.committed_bytes = bytes;
    state.shared_stack_limit = rt->stack_limit;
    state.native_stack_limit = rt->stack_limit ? rt->stack_limit - bytes : 0;
    state.result = JS_UNDEFINED;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state.pushes = state.depth = state.max_depth = 1;
    state.arities = argc < b->arg_count;
    state.copied_values = owned ? min_int(argc, b->arg_count) : 0;
    state.peak_bytes = bytes;
#endif
    /* Existing VM/native/slow root pop handles SF, captures and result roots. */
    JS_FrameInterp(&state);
    if (state.used_bytes != state.committed_bytes) {
        rt->stack_top += state.used_bytes - state.committed_bytes;
        if (rt->stack_limit)
            rt->stack_limit += state.used_bytes - state.committed_bytes;
    }
    result = state.result;
    for (next = initial.next; next; next = following) {
        following = next->next;
        js_free(ctx, next);
    }
    return result;
}
