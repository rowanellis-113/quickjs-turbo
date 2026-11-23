/* Same-activation argument construction. The original arguments TU and
   original general constructor executor remain source-identical to parent.
   The existing argument validator/push and cached constructor policy are
   exposed by typed symbol aliases; no helper body or frame/return ABI copy. */
#include "src/common/call/interpreter-retained-context.inc"
#include <stdatomic.h>
#define JS_CALL_FLAG_COPY_ARGV (1 << 1)
enum {
    OP_SPECIAL_OBJECT_ARGUMENTS,
    OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS,
    OP_SPECIAL_OBJECT_THIS_FUNC,
    OP_SPECIAL_OBJECT_NEW_TARGET
};
extern _Atomic(unsigned) JS_FrameArgumentsMode;
extern _Atomic(uint64_t) JS_FrameArgumentsStats[7];
extern _Atomic(unsigned) JS_FrameConstructPolicyForArguments;
extern bool JS_FrameArgumentsTargetForConstruct(JSFunctionBytecode *);
extern bool JS_FrameArgumentsPushForConstruct(JSFrameRegisterState *, JSValueConst, JSValueConst,
                                              JSFunctionBytecode *, unsigned, JSValueConst *, int,
                                              bool);
extern int JS_FrameSlowDirectSelect(JSFrameRegisterState *);
__attribute__((section(".qjzzpm"),
               aligned(8))) _Atomic(uint64_t) JS_FrameArgumentsConstructStats[2];
static _Atomic(unsigned) constructor_policy;
static FRAME_INLINE bool constructor_enabled(void)
{
    unsigned mode = atomic_load_explicit(&constructor_policy, memory_order_relaxed);
    if (!mode) {
        mode = getenv("QJS_DISABLE_FRAME_ARGUMENTS_CONSTRUCTOR") ? 2 : 1;
        atomic_store_explicit(&constructor_policy, mode, memory_order_relaxed);
    }
    return mode == 1;
}
static const uint8_t js_frame_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
#undef DEF
#undef def
};

/* Only the compiler's ordinary argument-binding prologue is considered here.
   In particular a non-argument constructor must not acquire our negative
   descriptor merely because its constructor call reached this cold bridge. */
static FRAME_INLINE bool js_frame_arguments_constructor_prefix(JSFunctionBytecode *b)
{
    const uint8_t *code = b->byte_code_buf;
    unsigned p = 0;
    if (b->byte_code_len < 2 || b->byte_code_len > FRAME_MAX_CODE)
        return false;
    if (code[p] == OP_push_this) {
        p++;
        if (code[p] == OP_put_loc)
            p += 3;
        else if (code[p] == OP_put_loc8)
            p += 2;
        else if (code[p] >= OP_put_loc0 && code[p] <= OP_put_loc3)
            p++;
        else
            return false;
    }
    return p + 2 <= (unsigned)b->byte_code_len && code[p] == OP_special_object &&
           (code[p + 1] == OP_SPECIAL_OBJECT_ARGUMENTS ||
            code[p + 1] == OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS);
}

/* The existing argument frame supplies undefined new.target for plain calls.
   This first constructor admission therefore retains the original interpreter
   for any use/capture of new.target. Bytecode has already passed validation.
   Only a ready kind2 argument descriptor reaches this proof. Its AUX low
   five bits remain owned by iterator/varargs controls; bits6/7 cache this
   immutable body check. Revalidation resets AUX before publishing ready.
   The cache belongs to the live bytecode, including when closures share it;
   it retains no object, realm, prototype or argument-list state. */
#define ARGUMENTS_CONSTRUCTOR_CHECKED 64
#define ARGUMENTS_CONSTRUCTOR_NEW_TARGET 128
_Static_assert(!((ARGUMENTS_CONSTRUCTOR_CHECKED | ARGUMENTS_CONSTRUCTOR_NEW_TARGET) & 31),
               "constructor proof preserves iterator and varargs controls");
static FRAME_INLINE bool js_frame_arguments_constructor_body(JSFunctionBytecode *b)
{
    unsigned char *flags = (unsigned char *)b + FRAME_CALL_AUX_OFFSET;
    if (*flags & ARGUMENTS_CONSTRUCTOR_CHECKED)
        return !(*flags & ARGUMENTS_CONSTRUCTOR_NEW_TARGET);
    for (int p = 0; p < b->byte_code_len; p += js_frame_opcode_sizes[b->byte_code_buf[p]])
        if (b->byte_code_buf[p] == OP_special_object &&
            b->byte_code_buf[p + 1] == OP_SPECIAL_OBJECT_NEW_TARGET) {
            *flags |= ARGUMENTS_CONSTRUCTOR_CHECKED | ARGUMENTS_CONSTRUCTOR_NEW_TARGET;
            return false;
        }
    *flags |= ARGUMENTS_CONSTRUCTOR_CHECKED;
    return true;
}

FRAME_CODE int JS_FrameArgumentsConstructCall(JSFrameRegisterState *state)
{
    JSFrame *parent = state->frame;
    JSContext *ctx = parent->bytecode->realm;
    unsigned argc = get_u16(state->pc + 1);
    JSValue *sp = state->sp, *argv = sp - argc;
    JSValue func = argv[-2], object;
    JSFunctionBytecode *b;
    if (argc > 32765 || !JS_IsObject(func) || !JS_IsObject(argv[-1]) ||
        JS_VALUE_GET_OBJ(func) != JS_VALUE_GET_OBJ(argv[-1]))
        return -1;
    JSObject *checked = JS_VALUE_GET_OBJ(func);
    if (checked->class_id != JS_CLASS_BYTECODE_FUNCTION || !checked->is_constructor ||
        checked->u.func.function_bytecode->is_derived_class_constructor)
        return -1;
    b = checked->u.func.function_bytecode;
    unsigned mode;
    js_frame_begin_c(state);
    if (atomic_load_explicit(&JS_FrameConstructPolicyForArguments, memory_order_relaxed) != 1 ||
        !constructor_enabled()) {
        js_frame_finish_c(state);
        return -1;
    }
    /* The original constructor body entry reports stack overflow in the
       caller realm. The existing argument builder reports it in b->realm.
       Keep foreign-realm construction on the complete original path. */
    if (b->realm != ctx || !js_frame_arguments_constructor_prefix(b) ||
        !JS_FrameArgumentsTargetForConstruct(b) || !js_frame_arguments_constructor_body(b)) {
        js_frame_finish_c(state);
        return -1;
    }
    mode = atomic_load_explicit(&JS_FrameArgumentsMode, memory_order_relaxed);
    if ((mode & 3) != 1) {
        js_frame_finish_c(state);
        return -1;
    }
    parent->sf.cur_pc = state->pc + 3;
    parent->sf.cur_sp = sp;
    parent->saved_sp = sp;
    parent->pending = (uint16_t)(argc + 2);
    if (js_poll_interrupts(ctx))
        goto exception;
    object = js_create_from_ctor(ctx, argv[-1], JS_CLASS_OBJECT);
    if (JS_IsException(object))
        goto exception;
    /* Exact existing continuation transfer. The second function owner stays
       live; the first operand now roots the newly allocated receiver. */
    JSObject *callee = JS_VALUE_GET_OBJ(func);
    assert(JS_REF_COUNT(callee) >= 2);
    JS_REF_COUNT(callee)--;
    argv[-2] = object;
    /* Constructor and JS body entry each retain their original poll. No
       allocation/callback occurs with an unrooted receiver or argument. */
    if (js_poll_interrupts(ctx) ||
        !JS_FrameArgumentsPushForConstruct(state, func, object, b, argc, vc(argv),
                                           (mode & 8) ? JS_CALL_FLAG_COPY_ARGV : 0, false)) {
        object = argv[-2];
        argv[-2] = JS_UNDEFINED;
        JS_FreeValue(ctx, object);
        goto exception;
    }
    FRAME_ROOT(state->frame) = 3;
    FRAME_INIT_STACK_AUX(&state->frame->sf, true);
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_FrameArgumentsStats[2], 1, memory_order_relaxed);
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_FrameArgumentsConstructStats[0], 1, memory_order_relaxed);
    js_frame_finish_c(state);
    return 0;
exception:
    state->pc = parent->sf.cur_pc;
    state->sp = parent->saved_sp;
    state->exception_pending = true;
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_FrameArgumentsConstructStats[1], 1, memory_order_relaxed);
    js_frame_finish_c(state);
    return JS_FrameSlowDirectSelect(state);
}
