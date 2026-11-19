#include "src/common/call/interpreter-retained-context.inc"

#include <stdatomic.h>
/* The iterator validator owns byte22; the varargs prefix owns byte108. */
#undef FRAME_ITERATOR_KIND
#define FRAME_ITERATOR_KIND(b)                                                                     \
    (((unsigned char *)(b))[offsetof(JSFunctionBytecode, byte_code_buf) - 2])
_Static_assert(sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode &&
                   FRAME_MAX_CODE == 2048,
               "regexp does not expand admission or own-bytecode hint capacity");
extern bool JS_FrameVarargsOldValidate(JSFunctionBytecode *);
extern int JS_FrameSlowDirectSelect(JSFrameRegisterState *);
extern JSValue qjs_frame_core_js_regexp_constructor_internal(JSContext *, JSValueConst, JSValue,
                                                             JSValue);
__attribute__((section(".qjzzpm"), aligned(4))) _Atomic(unsigned) JS_FrameRegexpMode = 0;
__attribute__((section(".qjzzpm"), aligned(8))) _Atomic(uint64_t) JS_FrameRegexpStats[3];
static FRAME_INLINE unsigned regexp_mode(void)
{
    unsigned mode = atomic_load_explicit(&JS_FrameRegexpMode, memory_order_relaxed);
    if (!mode) {
        unsigned expected = 0;
        mode = getenv("QJS_DISABLE_FRAME_REGEXP") ? 2 : 1;
        if (getenv("QJS_OBSERVE_FRAME_REGEXP"))
            mode |= 4;
        atomic_compare_exchange_strong_explicit(&JS_FrameRegexpMode, &expected, mode,
                                                memory_order_relaxed, memory_order_relaxed);
        mode = atomic_load_explicit(&JS_FrameRegexpMode, memory_order_relaxed);
    }
    return mode;
}
static const uint8_t js_frame_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
#undef DEF
#undef def
};

static FRAME_CODE bool JS_FrameRegexpValidateBody(JSFunctionBytecode *b)
{
    uint8_t boundaries[(FRAME_MAX_CODE + 7) / 8] = {0};
    const uint8_t *code = b->byte_code_buf;
    int pos, size, op, index, target;
    bool readonly_args = true;
    bool captured_args = false;
    bool extended = false;
    FRAME_ITERATOR_KIND(b) = 0;
    if (b->func_kind != JS_FUNC_NORMAL || b->is_derived_class_constructor ||
        b->byte_code_len <= 0 || b->byte_code_len > FRAME_MAX_CODE || b->stack_size > 256 ||
        b->var_count > 128 || b->arg_count > 128 || b->var_ref_count > b->arg_count + b->var_count)
        return false;
    if (b->var_ref_count) {
        if (!b->vardefs)
            return false;
        for (index = 0; index < b->arg_count + b->var_count; index++) {
            JSVarDef *vd = &b->vardefs[index];
            if (!vd->is_captured)
                continue;
            if (vd->var_ref_idx >= b->var_ref_count)
                return false;
            if (index < b->arg_count)
                captured_args = true;
        }
    }
    for (pos = 0; pos < b->byte_code_len; pos += size) {
        op = code[pos];
        if (op >= countof(js_frame_opcode_sizes))
            return false;
        size = js_frame_opcode_sizes[op];
        if (size == 0 || size > b->byte_code_len - pos)
            return false;
        boundaries[pos >> 3] |= 1u << (pos & 7);
        switch (op) {
#define FRAME_OP(id) case OP_##id:
#include "src/common/call/quickjs-interpreter-opcodes.h"
#undef FRAME_OP
        case OP_regexp:
            break;
        case OP_for_of_start:
        case OP_for_of_next:
        case OP_iterator_close:
        case OP_catch:
        case OP_gosub:
        case OP_ret:
        case OP_nip_catch:
        case OP_check_object:
            extended = true;
            break;
        default:
            return false;
        }
        if (op == OP_put_arg || op == OP_set_arg || (op >= OP_put_arg0 && op <= OP_put_arg3) ||
            (op >= OP_set_arg0 && op <= OP_set_arg3))
            readonly_args = false;
        /* Validation is completed before any opcode in this function executes. */
        switch (op) {
        case OP_call:
        case OP_tail_call:
        case OP_call_method:
        case OP_tail_call_method:
            /* Reserve the pending word's high bit, including function/this.
             * This is a function eligibility check, never an API argc limit. */
            if (get_u16(code + pos + 1) > 32765)
                return false;
            break;
        case OP_get_loc:
        case OP_put_loc:
        case OP_set_loc:
        case OP_set_loc_uninitialized:
        case OP_get_loc_check:
        case OP_put_loc_check:
        case OP_put_loc_check_init:
            index = get_u16(code + pos + 1);
            if (index >= b->var_count)
                return false;
            break;
        case OP_close_loc:
            index = get_u16(code + pos + 1);
            if (index >= b->var_count || !b->vardefs ||
                !b->vardefs[b->arg_count + index].is_captured ||
                b->vardefs[b->arg_count + index].var_ref_idx >= b->var_ref_count)
                return false;
            break;
        case OP_get_loc8:
        case OP_put_loc8:
        case OP_set_loc8:
        case OP_inc_loc:
        case OP_dec_loc:
        case OP_add_loc:
            if (code[pos + 1] >= b->var_count)
                return false;
            break;
        case OP_get_arg:
        case OP_put_arg:
        case OP_set_arg:
            if (get_u16(code + pos + 1) >= b->arg_count)
                return false;
            break;
        case OP_get_var_ref:
        case OP_put_var_ref:
        case OP_set_var_ref:
        case OP_get_var_ref_check:
        case OP_put_var_ref_check:
        case OP_put_var_ref_check_init:
            if (get_u16(code + pos + 1) >= b->closure_var_count)
                return false;
            break;
        case OP_push_const:
        case OP_fclosure:
            if (get_u32(code + pos + 1) >= (uint32_t)b->cpool_count)
                return false;
            if (op == OP_fclosure &&
                JS_VALUE_GET_TAG(b->cpool[get_u32(code + pos + 1)]) != JS_TAG_FUNCTION_BYTECODE)
                return false;
            break;
        case OP_push_const8:
        case OP_fclosure8:
            if (code[pos + 1] >= b->cpool_count)
                return false;
            if (op == OP_fclosure8 &&
                JS_VALUE_GET_TAG(b->cpool[code[pos + 1]]) != JS_TAG_FUNCTION_BYTECODE)
                return false;
            break;
        default:
            if (op >= OP_get_loc0 && op <= OP_get_loc3 && op - OP_get_loc0 >= b->var_count)
                return false;
            if (op >= OP_put_loc0 && op <= OP_put_loc3 && op - OP_put_loc0 >= b->var_count)
                return false;
            if (op >= OP_set_loc0 && op <= OP_set_loc3 && op - OP_set_loc0 >= b->var_count)
                return false;
            if (op == OP_get_loc0_loc1 && b->var_count < 2)
                return false;
            if (op >= OP_get_arg0 && op <= OP_get_arg3 && op - OP_get_arg0 >= b->arg_count)
                return false;
            if (op >= OP_put_arg0 && op <= OP_put_arg3 && op - OP_put_arg0 >= b->arg_count)
                return false;
            if (op >= OP_set_arg0 && op <= OP_set_arg3 && op - OP_set_arg0 >= b->arg_count)
                return false;
            if (op >= OP_get_var_ref0 && op <= OP_get_var_ref3 &&
                op - OP_get_var_ref0 >= b->closure_var_count)
                return false;
            if (op >= OP_put_var_ref0 && op <= OP_put_var_ref3 &&
                op - OP_put_var_ref0 >= b->closure_var_count)
                return false;
            if (op >= OP_set_var_ref0 && op <= OP_set_var_ref3 &&
                op - OP_set_var_ref0 >= b->closure_var_count)
                return false;
            break;
        }
    }
    for (pos = 0; pos < b->byte_code_len; pos += js_frame_opcode_sizes[code[pos]]) {
        switch (code[pos]) {
        case OP_catch:
        case OP_gosub:
        case OP_goto:
        case OP_if_true:
        case OP_if_false:
            target = pos + 1 + (int32_t)get_u32(code + pos + 1);
            break;
        case OP_goto16:
            target = pos + 1 + (int16_t)get_u16(code + pos + 1);
            break;
        case OP_goto8:
        case OP_if_true8:
        case OP_if_false8:
            target = pos + 1 + (int8_t)code[pos + 1];
            break;
        default:
            continue;
        }
        if (target < 0 || target >= b->byte_code_len ||
            !(boundaries[target >> 3] & (1u << (target & 7))))
            return false;
    }
    if (extended &&
        (getenv("QJS_DISABLE_FRAME_ITERATOR") != NULL || !js_frame_register_enabled(b->realm->rt)))
        return false;
    FRAME_ITERATOR_KIND(b) = extended;
    FRAME_KIND(b) = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);
    return true;
}

FRAME_CODE bool JS_FrameRegexpValidateSelect(JSFunctionBytecode *b)
{
    /* Existing admissions keep their original metadata and decision. The
       original caller still classifies captured readonly arguments. */
    if (JS_FrameVarargsOldValidate(b))
        return true;
    if (b->byte_code_len <= 0 || b->byte_code_len > FRAME_MAX_CODE)
        return false;
    unsigned mode = regexp_mode();
    /* The existing native VM crosses the intercepted complete slow gateway.
       Pure C/no-register frames retain their original admission policy. */
    if ((mode & 3) != 1 || !js_frame_register_enabled(b->realm->rt) ||
        js_check_stack_overflow(b->realm->rt, 1024))
        return false;
    if (mode & 4)
        atomic_fetch_add_explicit(&JS_FrameRegexpStats[0], 1, memory_order_relaxed);
    bool result = JS_FrameRegexpValidateBody(b);
    if (result && (mode & 4))
        atomic_fetch_add_explicit(&JS_FrameRegexpStats[1], 1, memory_order_relaxed);
    return result;
}

FRAME_CODE int JS_FrameRegexpStep(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *sp = state->sp;
    uint8_t *pc = state->pc + 1;
    JSValue pattern = sp[-2], bc = sp[-1], value;
    state->rt->current_stack_frame = sf;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    sf->cur_pc = pc;
    js_frame_begin_c(state);
    if (atomic_load_explicit(&JS_FrameRegexpMode, memory_order_relaxed) & 4)
        atomic_fetch_add_explicit(&JS_FrameRegexpStats[2], 1, memory_order_relaxed);
    /* The original constructor consumes both owning arguments on every
       outcome. Remove the stack aliases before transferring them, as at
       other consuming C boundaries. All unrelated live operands stay rooted.
       Its original realm/shape/prototype/allocation/failure path is reused. */
    sp[-2] = sp[-1] = JS_UNDEFINED;
    value = qjs_frame_core_js_regexp_constructor_internal(ctx, JS_UNDEFINED, pattern, bc);
    sp[-2] = value;
    sp--;
    state->sp = sp;
    state->pc = pc;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    sf->cur_pc = pc;
    js_frame_finish_c(state);
    if (JS_IsException(value)) {
        state->exception_pending = true;
        return JS_FrameSlowDirectSelect(state);
    }
    return 0;
}

FRAME_CODE int JS_FrameRegexpSlowSelect(JSFrameRegisterState *state)
{
    if (!state->exception_pending && *state->pc == OP_regexp)
        return JS_FrameRegexpStep(state);
    return JS_FrameSlowDirectSelect(state);
}
