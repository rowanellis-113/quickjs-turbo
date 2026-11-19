#include "src/common/call/interpreter-retained-context.inc"

static FRAME_INLINE void *string_index_data(JSString *p)
{
    JSStringSlice *slice;
    void **indirect;

    switch (p->kind) {
    case JS_STRING_KIND_NORMAL:
        return (void *)&p[1];
    case JS_STRING_KIND_SLICE:
        slice = (void *)&p[1];
        return (char *)&slice->parent[1] + slice->start;
    case JS_STRING_KIND_INDIRECT:
        indirect = (void *)&p[1];
        return *indirect;
    }
    abort();
    return NULL;
}

static FRAME_INLINE uint8_t *string_index_data8(JSString *p)
{
    return string_index_data(p);
}

static FRAME_INLINE uint16_t *string_index_data16(JSString *p)
{
    return string_index_data(p);
}
static FRAME_INLINE int string_index_get(JSString *p, int idx)
{
    return p->is_wide_char ? string_index_data16(p)[idx] : string_index_data8(p)[idx];
}

#include <stdatomic.h>
extern int JS_FrameSlowDirectSelect(JSFrameRegisterState *);
extern JSValue JS_FrameSmallCharNew(JSContext *, uint16_t);
_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   offsetof(JSString, hash_next) == QJS_ABI_OFF_JSString_hash_next &&
                   offsetof(JSString, first_weak_ref) == QJS_ABI_OFF_JSString_first_weak_ref &&
                   JS_TAG_STRING == -7,
               "original string layout and single-code-unit constructor ABI");
__attribute__((section(".qjzzpm"), aligned(4))) _Atomic(unsigned) JS_FrameStringIndexMode = 0;
__attribute__((section(".qjzzpm"), aligned(8))) _Atomic(uint64_t) JS_FrameStringIndexStats[5];
static FRAME_CODE int JS_FrameStringIndexConfigure(JSFrameRegisterState *state);
FRAME_CODE int JS_FrameStringIndexStep(JSFrameRegisterState *state)
{
    unsigned mode = atomic_load_explicit(&JS_FrameStringIndexMode, memory_order_relaxed);
    if (!mode)
        return JS_FrameStringIndexConfigure(state);
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSValue *sp = state->sp;
    unsigned op = *state->pc;
    if ((mode & 3) != 1 || (op != OP_get_array_el && op != OP_get_array_el2) ||
        JS_VALUE_GET_TAG(sp[-2]) != JS_TAG_STRING || JS_VALUE_GET_TAG(sp[-1]) != JS_TAG_INT)
        return JS_FrameSlowDirectSelect(state);
    JSString *string = JS_VALUE_GET_STRING(sp[-2]);
    uint32_t index = JS_VALUE_GET_INT(sp[-1]);
    if (index >= string->len)
        return JS_FrameSlowDirectSelect(state);
    JSContext *ctx = frame->bytecode->realm;
    uint8_t *pc = state->pc + 1;
    state->rt->current_stack_frame = sf;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    sf->cur_pc = pc;
    js_frame_begin_c(state);
    if (mode & 4) {
        atomic_fetch_add_explicit(&JS_FrameStringIndexStats[op == OP_get_array_el2], 1,
                                  memory_order_relaxed);
        if (string->is_wide_char)
            atomic_fetch_add_explicit(&JS_FrameStringIndexStats[2], 1, memory_order_relaxed);
        if (string->kind == JS_STRING_KIND_SLICE)
            atomic_fetch_add_explicit(&JS_FrameStringIndexStats[3], 1, memory_order_relaxed);
        if (string->kind == JS_STRING_KIND_INDIRECT)
            atomic_fetch_add_explicit(&JS_FrameStringIndexStats[4], 1, memory_order_relaxed);
    }
    /* Retain the accepted UTF-16 single-character cache route. A cache miss
       uses the original allocator; the source remains live across allocation,
       GC and host callbacks, and the returned value owns one reference. */
    JSValue value = JS_FrameSmallCharNew(ctx, (uint16_t)string_index_get(string, index));
    if (op == OP_get_array_el) {
        JSValue consumed = sp[-2];
        sp[-2] = value;
        sp[-1] = JS_UNDEFINED;
        sp--;
        state->sp = sp;
        state->pc = pc;
        frame->saved_sp = sp;
        sf->cur_sp = sp;
        sf->cur_pc = pc;
        /* Publish the new owning result/cursor before a custom allocator's
           release observer can reenter. Never leave a freed source alias. */
        JS_FreeValue(ctx, consumed);
    } else {
        sp[-1] = value;
        state->sp = sp;
        state->pc = pc;
        frame->saved_sp = sp;
        sf->cur_sp = sp;
        sf->cur_pc = pc;
    }
    js_frame_finish_c(state);
    if (JS_IsException(value)) {
        state->exception_pending = true;
        return JS_FrameSlowDirectSelect(state);
    }
    return 0;
}
static FRAME_CODE int JS_FrameStringIndexConfigure(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    state->rt->current_stack_frame = &frame->sf;
    frame->saved_sp = state->sp;
    frame->sf.cur_sp = state->sp;
    frame->sf.cur_pc = state->pc;
    js_frame_begin_c(state);
    unsigned mode = getenv("QJS_DISABLE_FRAME_STRING_INDEX") ? 2 : 1, expected = 0;
    if (getenv("QJS_OBSERVE_FRAME_STRING_INDEX"))
        mode |= 4;
    atomic_compare_exchange_strong_explicit(&JS_FrameStringIndexMode, &expected, mode,
                                            memory_order_relaxed, memory_order_relaxed);
    js_frame_finish_c(state);
    return JS_FrameStringIndexStep(state);
}
