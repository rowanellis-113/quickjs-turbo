/* Intrinsic apply forwards through the existing same-activation argument
   builder and root2/logical-C return protocol. No borrowed mutable vector. */
#include "src/common/call/interpreter-retained-context.inc"
#include <stdatomic.h>
#define JS_CALL_FLAG_COPY_ARGV (1 << 1)

extern bool JS_FrameArgumentsPushForConstruct(JSFrameRegisterState *, JSValueConst, JSValueConst,
                                              JSFunctionBytecode *, unsigned, JSValueConst *, int,
                                              bool);
extern int JS_FrameSlowDirectSelect(JSFrameRegisterState *);
typedef struct {
    JSValueConst *argv;
    uint32_t argc, signature;
} JSFrameApplyArgumentRecord;
_Static_assert(sizeof(JSFrameApplyArgumentRecord) == 16 && sizeof(JSFrame) == 128 &&
                   FRAME_ROOT_OFFSET == 62 && FRAME_FLAGS_OFFSET == 63 && FRAME_FORWARD_BYTES == 80,
               "reuse the checked argument prefix and original logical native frame");
_Static_assert(JS_CLASS_ARRAY == 2 && JS_CLASS_ARGUMENTS == 8 && JS_CLASS_BYTECODE_FUNCTION == 13 &&
                   JS_ATOM_length == 51 && JS_PROP_TMASK == 48 && JS_PROP_NORMAL == 0 &&
                   JS_CALL_FLAG_COPY_ARGV == 2,
               "pinned dense-list classes, own normal length and public argv copy flag");

__attribute__((section(".qjzzpm"), aligned(8))) _Atomic(uint64_t) JS_FrameApplyForwardStats[14];
static _Atomic(unsigned) apply_control;
static FRAME_INLINE unsigned apply_mode(void)
{
    unsigned mode = atomic_load_explicit(&apply_control, memory_order_relaxed);
    if (!mode) {
        mode =
            (getenv("QJS_DISABLE_FRAME_APPLY_DIRECT") || getenv("QJS_DISABLE_FRAME_CALL_FORWARD"))
                ? 2
                : 1;
        if (getenv("QJS_OBSERVE_FRAME_APPLY_DIRECT"))
            mode |= 4;
        atomic_store_explicit(&apply_control, mode, memory_order_relaxed);
    }
    return mode;
}
static FRAME_INLINE void count(unsigned mode, unsigned index, uint64_t n)
{
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_FrameApplyForwardStats[index], n, memory_order_relaxed);
}

/* Called only after the assembler proves the actual callee is the original
   apply intrinsic. A miss changes no operand, owner, PC, poll or frame. */
FRAME_CODE int JS_FrameApplyForwardCall(JSFrameRegisterState *state)
{
    JSFrame *parent = state->frame;
    JSContext *ctx = parent->bytecode->realm;
    JSRuntime *rt = state->rt;
    JSValue *sp = state->sp, *argv = sp - 2;
    JSValue callee, func, this_value, list;
    JSObject *function, *array;
    JSFunctionBytecode *b;
    unsigned mode = apply_mode(), length = 0, capacity, op = *state->pc;
    size_t regular, need;
    bool found = false;
    js_frame_begin_c(state);
    count(mode, 0, 1);
#define MISS(index)                                                                                \
    do {                                                                                           \
        count(mode, index, 1);                                                                     \
        goto miss;                                                                                 \
    } while (0)
    if ((mode & 3) != 1)
        MISS(1);
    if ((op != OP_call_method && op != OP_tail_call_method) || get_u16(state->pc + 1) != 2)
        MISS(2);
    callee = argv[-1];
    func = argv[-2];
    this_value = argv[0];
    list = argv[1];
    if (!JS_IsObject(func) || !JS_IsObject(this_value))
        MISS(3);
    function = JS_VALUE_GET_OBJ(func);
    if (function->class_id != JS_CLASS_BYTECODE_FUNCTION)
        MISS(3);
    b = function->u.func.function_bytecode;
    if (b->realm != ctx || JS_VALUE_GET_OBJ(callee)->u.cfunc.realm != ctx)
        MISS(4);
    /* Cold targets keep the original complete preparation path. No new
       bytecode validator, negative descriptor or dispatch table is created. */
    if (!FRAME_SUPPORTED(b) || b->func_kind != JS_FUNC_NORMAL || b->is_derived_class_constructor ||
        b->arg_count > 128 || b->var_count > 128 || b->stack_size > 256)
        MISS(7);
    if (!JS_IsObject(list))
        MISS(5);
    array = JS_VALUE_GET_OBJ(list);
    if ((array->class_id != JS_CLASS_ARRAY && array->class_id != JS_CLASS_ARGUMENTS) ||
        !array->fast_array || array->u.array.count > 32765)
        MISS(5);
    /* This bounded ordinary shape walk invokes no getter or exotic method.
       Actual Get(length)/ToLength side effects retain the original apply. */
    JSShape *shape = array->shape;
    if (shape->prop_count > 32)
        MISS(6);
    for (int i = 0; i < shape->prop_count; i++) {
        JSShapeProperty *property = &get_shape_prop(shape)[i];
        if (property->atom != JS_ATOM_length)
            continue;
        JSValue value = array->prop[i].u.value;
        if ((property->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
            JS_VALUE_GET_TAG(value) != JS_TAG_INT || JS_VALUE_GET_INT(value) < 0 ||
            (unsigned)JS_VALUE_GET_INT(value) != array->u.array.count)
            MISS(6);
        length = JS_VALUE_GET_INT(value);
        found = true;
        break;
    }
    if (!found)
        MISS(6);
    capacity = max_int(length, b->arg_count);
    regular = FRAME_HEADER_BYTES + sizeof(JSFrameApplyArgumentRecord) +
              sizeof(JSValue) * (capacity + b->var_count + b->stack_size) + FRAME_CAPTURE_BYTES(b);
    need = regular + FRAME_FORWARD_BYTES;
    if (need > state->segment->capacity - state->segment->used) {
        JSFrameSegment *next = state->segment->next;
        /* The original builder switches segments only when regular does not
           fit. Reuse its empty cached successor only if the complete child,
           including the logical native frame, fits there. No allocation or
           live segment reset is admitted by this extra path. */
        if (regular <= state->segment->capacity - state->segment->used || !next || next->used ||
            next->capacity < need)
            MISS(8);
    }
    /* Bound the original noinline builder's extra physical C stack as well.
       Only a cached empty-segment switch can occur after this preflight;
       it invokes no allocator, GC or callback. */
    if (js_check_stack_overflow(rt, need + 8192))
        MISS(9);
    if (ctx->interrupt_counter <= 2)
        MISS(10);
    parent->sf.cur_pc = state->pc + 3;
    parent->sf.cur_sp = sp;
    parent->saved_sp = sp;
    parent->pending = 4 | (op == OP_tail_call_method ? 0x8000 : 0);
    ctx->interrupt_counter--; /* original apply entry, no handler can run */
    if (!JS_FrameArgumentsPushForConstruct(state, func, this_value, b, length,
                                           vc(array->u.array.u.values), JS_CALL_FLAG_COPY_ARGV,
                                           false)) {
        /* Defensive original exception protocol; the bounded in-capacity
           path above normally leaves no failing builder operation. */
        count(mode, 11, 1);
        state->pc = parent->sf.cur_pc;
        state->sp = sp;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameSlowDirectSelect(state) ? 2 : 1;
    }
    JSFrame *child = state->frame;
    JSFrameApplyArgumentRecord *record = (void *)((uint8_t *)child + FRAME_HEADER_BYTES);
    /* The source vector may move/change during JS execution. All actuals,
       captures and any later argument-record reads use the owned snapshot. */
    record->argv = vc(child->sf.arg_buf);
    JSStackFrame *logical = (void *)((uint8_t *)child + regular);
    logical->prev_frame = &parent->sf;
    logical->cur_func = callee;
    logical->arg_buf = argv;
    logical->arg_count = 2;
    logical->var_buf = NULL;
    logical->var_refs = NULL;
    logical->var_ref_count = 0;
    logical->is_strict_mode = false;
    FRAME_CLEAR_STACK_AUX(logical);
    logical->cur_pc = NULL;
    logical->cur_sp = NULL;
    ((unsigned char *)logical)[62] = 0;
    ((unsigned char *)logical)[63] = FRAME_FORWARD_TAG;
    child->sf.prev_frame = logical;
    FRAME_ROOT(child) = 2;
    state->segment->used += FRAME_FORWARD_BYTES;
    state->used_bytes += FRAME_FORWARD_BYTES;
    js_frame_charge_stack(rt, FRAME_FORWARD_BYTES);
    ctx->interrupt_counter--; /* original JS body entry, after snapshot */
    count(mode, 12, 1);
    count(mode, 13, length);
    js_frame_finish_c(state);
    return 1;
miss:
    js_frame_finish_c(state);
    return 0;
#undef MISS
}
