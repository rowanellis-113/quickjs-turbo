#define REGEXP_INITIAL_MODE 1
#include "src/common/call/interpreter-retained-context.inc"

/* A supported opcode is declared once, for validation and dispatch. */
static const uint8_t js_frame_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
};

FRAME_CODE bool JS_FrameRegExpValidate(JSFunctionBytecode *b)
{
    uint8_t boundaries[(FRAME_MAX_CODE + 7) / 8] = {0};
    const uint8_t *code = b->byte_code_buf;
    int pos, size, op, index, target;
    bool readonly_args = true;
    bool captured_args = false;
    bool extended = false;
    bool name_needs_full = false;
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
            break;
        case OP_regexp:
            extended = true;
            break;
        case OP_append:
        case OP_apply:
            name_needs_full = true;
            extended = true;
            break;
        case OP_set_name:
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
    if (extended) {
        bool varargs = false, names = false;
        for (int p = 0; p < b->byte_code_len; p += js_frame_opcode_sizes[b->byte_code_buf[p]])
            if (b->byte_code_buf[p] == OP_append || b->byte_code_buf[p] == OP_apply)
                varargs = true;
            else if (b->byte_code_buf[p] == OP_set_name)
                names = true;
        if (names && getenv("QJS_DISABLE_FRAME_SET_NAME"))
            return false;
        if (varargs && getenv("QJS_DISABLE_FRAME_VARARGS"))
            return false;
        if (varargs)
            FRAME_VARARGS_DIRECT_MODE(b) = getenv("QJS_DISABLE_FRAME_VARARGS_DIRECT") ? 2 : 1;
        if (varargs)
            FRAME_VARARGS_FUSION_MODE(b) = getenv("QJS_DISABLE_FRAME_VARARGS_FUSION") ? 2 : 1;
        FRAME_ITERATOR_KIND(b) =
            (varargs ? 3 : 1) | (names ? 4 : 0) | ((names && name_needs_full) ? 8 : 0);
    } else
        FRAME_ITERATOR_KIND(b) = 0;
    FRAME_KIND(b) = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);
    return true;
}

extern JSValue qjs_frame_core_js_regexp_constructor_internal(JSContext *, JSValueConst, JSValue,
                                                             JSValue);
extern bool JS_FrameVarargsValidateSelect(JSFunctionBytecode *);
extern void JS_FrameCapturedReadonlyClassify(JSFunctionBytecode *);
extern int JS_FrameVarargsSlowSelect(JSFrameRegisterState *);

_Static_assert(
    sizeof(JSValue) == QJS_ABI_SIZE_JSValue && sizeof(JSFrame) == 128 &&
        sizeof(JSFrameRegisterState) == FRAME_REGISTER_STATE_BYTES &&
        offsetof(JSFrame, bytecode) == 80 && offsetof(JSFrame, saved_sp) == 104 &&
        offsetof(JSFrameRegisterState, frame) == 0 && offsetof(JSFrameRegisterState, pc) == 16 &&
        offsetof(JSFrameRegisterState, sp) == 24 &&
        offsetof(JSFrameRegisterState, exception_pending) == FRAME_REGISTER_STATE_EXCEPTION &&
        offsetof(JSFunctionBytecode, byte_code_buf) ==
            QJS_ABI_OFF_JSFunctionBytecode_byte_code_buf &&
        offsetof(JSFunctionBytecode, pc2line_buf) == QJS_ABI_OFF_JSFunctionBytecode_pc2line_buf,
    "regexp operation preserves the retained native register/frame ABI");

FRAME_CODE bool JS_FrameRegExpValidateSelect(JSFunctionBytecode *b)
{
    /* Old supported functions retain their exact old classification first. */
    if (JS_FrameVarargsValidateSelect(b))
        return true;
    if (!REGEXP_INITIAL_MODE || getenv("QJS_DISABLE_FRAME_REGEXP"))
        return false;
    if (!JS_FrameRegExpValidate(b))
        return false;
    JS_FrameCapturedReadonlyClassify(b);
    return true;
}

FRAME_CODE int JS_FrameRegExpStep(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *sp = state->sp;
    uint8_t *pc = state->pc + 1;
    js_frame_begin_c(state);
    /* The same boundary contract as retained VarargsNameStep. Publish every
       live value before allocation, GC, or an embedding allocator reentry. */
    state->pc = pc;
    sf->cur_pc = pc;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    /* Exact old OP_regexp ownership: constructor consumes both inputs on
       every path, creates a fresh object, and transfers both string owners. */
    sp[-2] = qjs_frame_core_js_regexp_constructor_internal(ctx, JS_UNDEFINED, sp[-2], sp[-1]);
    sp--;
    state->sp = sp;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    bool failed = JS_IsException(sp[-1]);
    if (failed)
        state->exception_pending = true;
    js_frame_finish_c(state);
    /* The original failure has consumed its operands and advanced its PC.
       Reuse the complete existing unwinder, including suspended ancestors.
       Do not emulate an OP_throw or add another JavaScript activation. */
    return failed ? JS_FrameVarargsSlowSelect(state) : 0;
}
