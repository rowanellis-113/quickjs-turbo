#include "src/common/call/interpreter-retained-context.inc"

/* A supported opcode is declared once, for validation and dispatch. */
static const uint8_t js_frame_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
};

#include <stdatomic.h>
#define JS_CALL_FLAG_COPY_ARGV (1 << 1)
#pragma section(".qzrocd$readonlycall", read, write)
__declspec(allocate(".qzrocd$readonlycall")) _Atomic(unsigned) JS_FrameReadonlyArgumentsControl = 0;
typedef struct {
    _Atomic(unsigned char) mode;
    unsigned char diagnostic, reserved[6];
    _Atomic(uint64_t) reads, methods, fills, misses, abi, allocations, base_bytes, reserved_bytes,
        fallbacks;
} ReadonlyOwnControl;
extern ReadonlyOwnControl JS_FrameOwnBytecodeData;
extern JSValue qjs_frame_core_JS_CallInternal(JSContext *, JSValueConst, JSValueConst, JSValueConst,
                                              int, JSValueConst *, int);
extern int JS_FrameInterpSlow(JSFrameRegisterState *);
_Static_assert(sizeof(ReadonlyOwnControl) == 80 && offsetof(ReadonlyOwnControl, mode) == 0 &&
                   sizeof(JSFrame) == 128 && sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame &&
                   sizeof(JSFrameRegisterState) == FRAME_REGISTER_STATE_BYTES &&
                   sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode &&
                   FRAME_MAX_CODE == 2048 && FRAME_ROOT_OFFSET == 62 && FRAME_FLAGS_OFFSET == 63,
               "Retained native value/frame/root/quota and owned bytecode ABI");
typedef struct {
    unsigned end, slot, max_index;
} ReadonlyPlan;
static FRAME_INLINE unsigned readonly_mode(void)
{
    unsigned mode = atomic_load_explicit(&JS_FrameReadonlyArgumentsControl, memory_order_relaxed);
    if (!mode) {
        unsigned expected = 0;
        mode = getenv("QJS_DISABLE_READONLY_ARGUMENTS") ? 2 : 1;
        atomic_compare_exchange_strong_explicit(&JS_FrameReadonlyArgumentsControl, &expected, mode,
                                                memory_order_relaxed, memory_order_relaxed);
        mode = atomic_load_explicit(&JS_FrameReadonlyArgumentsControl, memory_order_relaxed);
    }
    return mode;
}
static FRAME_INLINE int readonly_local(const uint8_t *pc, unsigned which)
{
    unsigned op = *pc;
    if (which == 0) {
        if (op >= OP_get_loc0 && op <= OP_get_loc3)
            return op - OP_get_loc0;
        if (op == OP_get_loc8)
            return pc[1];
        if (op == OP_get_loc)
            return get_u16(pc + 1);
    } else if (which == 1) {
        if (op >= OP_put_loc0 && op <= OP_put_loc3)
            return op - OP_put_loc0;
        if (op == OP_put_loc8)
            return pc[1];
        if (op == OP_put_loc)
            return get_u16(pc + 1);
    } else {
        if (op >= OP_set_loc0 && op <= OP_set_loc3)
            return op - OP_set_loc0;
        if (op == OP_set_loc8)
            return pc[1];
        if (op == OP_set_loc)
            return get_u16(pc + 1);
    }
    return -1;
}
static FRAME_INLINE int readonly_integer(const uint8_t *pc)
{
    unsigned op = *pc;
    if (op >= OP_push_0 && op <= OP_push_7)
        return op - OP_push_0;
    if (op == OP_push_i8)
        return (int8_t)pc[1];
    if (op == OP_push_i16)
        return (int16_t)get_u16(pc + 1);
    if (op == OP_push_i32)
        return (int32_t)get_u32(pc + 1);
    return -1;
}
static FRAME_INLINE int readonly_branch(const uint8_t *pc, int pos)
{
    switch (*pc) {
    case OP_goto:
    case OP_if_true:
    case OP_if_false:
        return pos + 1 + (int32_t)get_u32(pc + 1);
    case OP_goto16:
        return pos + 1 + (int16_t)get_u16(pc + 1);
    case OP_goto8:
    case OP_if_true8:
    case OP_if_false8:
        return pos + 1 + (int8_t)pc[1];
    default:
        return -1;
    }
}

FRAME_CODE bool readonly_base_validate(JSFunctionBytecode *b)
{
    uint8_t boundaries[(FRAME_MAX_CODE + 7) / 8] = {0};
    const uint8_t *code = b->byte_code_buf;
    int pos, size, op, index, target;
    bool readonly_args = true;
    unsigned validation_kind = 0;
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
        case OP_special_object:
            if (code[pos + 1] != 0)
                return false;
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
    validation_kind = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);
    return true;
}

/* Validation owns a byte after the numeric hint plane,only in stable own
   mode1. Native preparation bytes18..21 are valid only with kind bit16;
   these functions retain kind2 and never publish that native-builder bit. */
static FRAME_CODE bool readonly_classify(JSFunctionBytecode *b, ReadonlyPlan *plan)
{
    const uint8_t *code = b->byte_code_buf;
    int len = b->byte_code_len;
    unsigned char *fields = (unsigned char *)b + FRAME_CALL_META_OFFSET;
    if (atomic_load_explicit(&JS_FrameOwnBytecodeData.mode, memory_order_acquire) != 1 ||
        len <= 0 || len > 2048 || ((uintptr_t)code & 3) || (FRAME_KIND(b) & 17))
        return false;
    uint8_t *tag = (uint8_t *)code + 2 * ((len + 3) & ~3);
    if (*tag == 2)
        return false;
    if (*tag == 1) {
        plan->end = get_u16(fields);
        plan->slot = fields[2];
        plan->max_index = fields[3];
        return true;
    }
    if (*tag != 0)
        return false;
    bool valid = false;
    int special = -1, store = -1, slot = -1, last = 0, max_index = -1, reads = 0;
    uint8_t forbidden[256] = {0};
    if (!b->is_strict_mode || b->func_kind != JS_FUNC_NORMAL || b->is_derived_class_constructor)
        goto done;
    /* The compiler's arguments initializer is before effectful body work. */
    for (int pos = 0; pos < len && pos <= 8;) {
        int op = code[pos];
        if (op >= countof(js_frame_opcode_sizes))
            goto done;
        int size = js_frame_opcode_sizes[op];
        if (!size || size > len - pos)
            goto done;
        if (op == OP_special_object) {
            if (size != 2 || code[pos + 1] != 0)
                goto done;
            special = pos;
            store = pos + 2;
            break;
        }
        if (op != OP_push_this && readonly_local(code + pos, 1) < 0)
            goto done;
        pos += size;
    }
    if (special < 0 || store >= len || (slot = readonly_local(code + store, 1)) < 0)
        goto done;
    if (!readonly_base_validate(b) || slot >= b->var_count)
        goto done;
    if ((b->var_ref_count && !b->vardefs) ||
        (b->vardefs && b->vardefs[b->arg_count + slot].is_captured))
        goto done;
    for (int pos = 0; pos < len; pos += js_frame_opcode_sizes[code[pos]]) {
        int op = code[pos], size = js_frame_opcode_sizes[op];
        if (op == OP_special_object && pos != special)
            goto done;
        if (op == OP_regexp || op == OP_append || op == OP_apply || op == OP_set_name)
            goto done;
        if ((readonly_local(code + pos, 1) == slot && pos != store) ||
            readonly_local(code + pos, 2) == slot)
            goto done;
        if (op == OP_get_loc0_loc1 && slot < 2)
            goto done;
        if ((op == OP_inc_loc || op == OP_dec_loc || op == OP_add_loc) && code[pos + 1] == slot)
            goto done;
        if ((op == OP_get_loc_check || op == OP_put_loc_check || op == OP_put_loc_check_init ||
             op == OP_set_loc_uninitialized || op == OP_close_loc) &&
            get_u16(code + pos + 1) == slot)
            goto done;
        if (readonly_local(code + pos, 0) != slot)
            continue;
        int next = pos + size, end;
        if (next < len && code[next] == OP_get_length)
            end = next + 1;
        else {
            if (next >= len)
                goto done;
            int index = readonly_integer(code + next);
            int after = next + js_frame_opcode_sizes[code[next]];
            if (index < 0 || index > 254 || after >= len || code[after] != OP_get_array_el)
                goto done;
            if (index > max_index)
                max_index = index;
            end = after + 1;
        }
        for (int p = pos + 1; p < end; p++)
            forbidden[p >> 3] |= 1u << (p & 7);
        if (end > last)
            last = end;
        reads++;
    }
    if (!reads || last <= store || last >= len)
        goto done;
    for (int pos = 0; pos < len; pos += js_frame_opcode_sizes[code[pos]]) {
        int op = code[pos], target = readonly_branch(code + pos, pos);
        if (target >= 0) {
            if (forbidden[target >> 3] & (1u << (target & 7)))
                goto done;
            if ((pos < last && target <= pos) || (pos >= last && target < last))
                goto done;
        }
        if (pos < last && (op == OP_call || op == OP_tail_call || op == OP_call_method ||
                           op == OP_tail_call_method || (op >= OP_call0 && op <= OP_call3) ||
                           op == OP_call_constructor))
            goto done;
    }
    put_u16(fields, last);
    fields[2] = (uint8_t)slot;
    fields[3] = max_index < 0 ? 255 : (uint8_t)max_index;
    FRAME_KIND(b) = 2;
    valid = true;
done:
    *tag = valid ? 1 : 2;
    if (valid) {
        plan->end = get_u16(fields);
        plan->slot = fields[2];
        plan->max_index = fields[3];
    }
    return valid;
}
static FRAME_INLINE void readonly_publish(JSFrameRegisterState *s, JSValue *sp, uint8_t *pc)
{
    s->sp = sp;
    s->pc = pc;
    s->frame->saved_sp = sp;
    s->frame->sf.cur_sp = sp;
    s->frame->sf.cur_pc = pc;
    s->rt->current_stack_frame = &s->frame->sf;
}
static FRAME_INLINE void readonly_release(JSFrameRegisterState *s, JSValue value, JSValue *sp,
                                          uint8_t *pc)
{
    if (JS_VALUE_HAS_REF_COUNT(value)) {
        void *p = JS_VALUE_GET_PTR(value);
        if (JS_REF_COUNT(p) > 1)
            --JS_REF_COUNT(p);
        else {
            readonly_publish(s, sp, pc);
            JS_FreeValue(s->frame->bytecode->realm, value);
        }
    }
}
/* The original expression is executed,not converted to an IsUndefined
   shortcut. Effectful/uncommon opcodes use the actual retained slow selector. */
static FRAME_CODE int readonly_prefix(JSFrameRegisterState *s, const ReadonlyPlan *plan,
                                      unsigned argc, JSValueConst *argv, JSValue *snapshot)
{
    JSFrame *frame = s->frame;
    JSValue *vars = frame->sf.var_buf, *sp = s->sp;
    uint8_t *base = frame->bytecode->byte_code_buf, *pc = s->pc;
    for (;;) {
        if (pc >= base + plan->end) {
            readonly_publish(s, sp, pc);
            return 0;
        }
        unsigned op = *pc, size = js_frame_opcode_sizes[op];
        uint8_t *next = pc + size;
        int slot = readonly_local(pc, 0);
        if (slot == (int)plan->slot) {
            unsigned following = *next;
            if (following == OP_get_length) {
                uint8_t *number = next + 1;
                if (number < base + plan->end) {
                    int threshold = readonly_integer(number);
                    uint8_t *compare = number + js_frame_opcode_sizes[*number];
                    if (threshold >= 0 && compare < base + plan->end && *compare == OP_lte) {
                        *sp++ = js_bool(argc <= (unsigned)threshold);
                        pc = compare + 1;
                        continue;
                    }
                }
                *sp++ = js_int32(argc);
                pc = next + 1;
                continue;
            }
            unsigned index = readonly_integer(next);
            *sp++ = js_dup(snapshot[index]);
            pc = next + js_frame_opcode_sizes[following] + 1;
            continue;
        }
        if (op == OP_special_object) {
            for (unsigned i = 0; i < argc; i++)
                snapshot[i] = js_dup(argv[i]);
            *sp++ = JS_UNDEFINED;
            pc = next;
            continue;
        }
        if (slot >= 0) {
            *sp++ = js_dup(vars[slot]);
            pc = next;
            continue;
        }
        slot = readonly_local(pc, 1);
        if (slot >= 0) {
            JSValue value = *--sp, old = vars[slot];
            *sp = JS_UNDEFINED;
            vars[slot] = value;
            readonly_release(s, old, sp, next);
            pc = next;
            continue;
        }
        slot = readonly_local(pc, 2);
        if (slot >= 0) {
            JSValue old = vars[slot];
            vars[slot] = js_dup(sp[-1]);
            readonly_release(s, old, sp, next);
            pc = next;
            continue;
        }
        if (op == OP_push_this) {
            *sp++ = js_dup(frame->this_value);
            pc = next;
            continue;
        }
        if (op == OP_dup) {
            *sp = js_dup(sp[-1]);
            sp++;
            pc = next;
            continue;
        }
        if (op == OP_drop) {
            JSValue old = *--sp;
            *sp = JS_UNDEFINED;
            readonly_release(s, old, sp, next);
            pc = next;
            continue;
        }
        int integer = readonly_integer(pc);
        if (integer >= 0) {
            *sp++ = js_int32(integer);
            pc = next;
            continue;
        }
        if (op == OP_undefined || op == OP_null || op == OP_push_true || op == OP_push_false) {
            *sp++ = op == OP_undefined ? JS_UNDEFINED
                    : op == OP_null    ? JS_NULL
                                       : js_bool(op == OP_push_true);
            pc = next;
            continue;
        }
        if (op == OP_goto || op == OP_goto16 || op == OP_goto8) {
            pc = base + readonly_branch(pc, (int)(pc - base));
            continue;
        }
        if ((op == OP_if_true || op == OP_if_false || op == OP_if_true8 || op == OP_if_false8) &&
            (JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_BOOL || JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_INT)) {
            bool truth = JS_VALUE_GET_INT(*--sp) != 0;
            *sp = JS_UNDEFINED;
            bool want = op == OP_if_true || op == OP_if_true8;
            pc = truth == want ? base + readonly_branch(pc, (int)(pc - base)) : next;
            continue;
        }
        if (op == OP_lte && JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_INT &&
            JS_VALUE_GET_TAG(sp[-2]) == JS_TAG_INT) {
            sp[-2] = js_bool(JS_VALUE_GET_INT(sp[-2]) <= JS_VALUE_GET_INT(sp[-1]));
            *--sp = JS_UNDEFINED;
            pc = next;
            continue;
        }
        if (op == OP_get_var || op == OP_get_var_undef) {
            readonly_publish(s, sp, next);
#ifdef QJS_PROPERTY_IC
            JSValue value =
                JS_FrameGlobalBindingCellGet(frame->bytecode->realm, frame->bytecode, pc,
                                             get_u32(pc + 1), op - OP_get_var_undef);
#else
            JSValue value =
                JS_GetGlobalVar(frame->bytecode->realm, get_u32(pc + 1), op - OP_get_var_undef);
#endif
            if (JS_IsException(value)) {
                s->exception_pending = true;
                return JS_FrameInterpSlow(s);
            }
            *sp++ = value;
            pc = next;
            continue;
        }
        if ((op == OP_strict_eq || op == OP_strict_neq) &&
            (JS_IsUndefined(sp[-2]) || JS_IsUndefined(sp[-1]))) {
            JSValue left = sp[-2], right = sp[-1];
            bool equal = JS_IsUndefined(left) && JS_IsUndefined(right);
            sp[-2] = js_bool(equal ^ (op == OP_strict_neq));
            *--sp = JS_UNDEFINED;
            readonly_release(s, left, sp, next);
            readonly_release(s, right, sp, next);
            pc = next;
            continue;
        }
        readonly_publish(s, sp, pc);
        if (JS_FrameInterpSlow(s))
            return 1;
        if (s->frame != frame)
            return 1; /* no direct bytecode call is admitted above */
        sp = s->sp;
        pc = s->pc;
    }
}

/* Same allocator/segment policy as retained js_frame_grow; existing frame
   and argument addresses never move. Caller is fully published beforehand. */
static FRAME_CODE JSFrameSegment *readonly_child_grow(JSContext *ctx, JSFrameSegment *segment,
                                                      size_t size)
{
    JSFrameSegment *next = segment->next;
    if (next && next->capacity >= size) {
        next->used = 0;
        return next;
    }
    if (size < 16384)
        size = 16384;
    next = js_malloc(ctx, sizeof(*next) + 15 + size);
    if (!next)
        return NULL;
    next->next = segment->next;
    next->capacity = size;
    next->used = 0;
    next->data = (uint8_t *)(((uintptr_t)(next + 1) + 15) & ~(uintptr_t)15);
    segment->next = next;
    return next;
}
/* Return0 is a pure call decline: no poll,owners or frame were created.
   Return1 resumes the original ASM activation;return2 exits its completed
   root. Original full slow unwinder owns both child and ancestor failures. */
FRAME_CODE int JS_FrameReadonlyCallTry(JSFrameRegisterState *s)
{
    JSFrame *parent = s->frame;
    JSRuntime *rt = s->rt;
    JSContext *caller = parent->bytecode->realm;
    unsigned op = *s->pc, argc;
    bool method = false, tail = false;
    switch (op) {
    case OP_call0:
    case OP_call1:
    case OP_call2:
    case OP_call3:
        argc = op - OP_call0;
        break;
    case OP_call:
    case OP_tail_call:
    case OP_call_method:
    case OP_tail_call_method:
        argc = get_u16(s->pc + 1);
        method = op == OP_call_method || op == OP_tail_call_method;
        tail = op == OP_tail_call || op == OP_tail_call_method;
        break;
    default:
        return 0;
    }
    if (s->exception_pending || argc > 32765)
        return 0;
    JSValue *argv = s->sp - argc;
    JSValue func = argv[-1], receiver = method ? argv[-2] : JS_UNDEFINED;
    if (!JS_IsObject(func) || JS_VALUE_GET_OBJ(func)->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return 0;
    JSFunctionBytecode *b = JS_VALUE_GET_OBJ(func)->u.func.function_bytecode;
    ReadonlyPlan plan;
    js_frame_begin_c(s);
    if (readonly_mode() != 1 || !readonly_classify(b, &plan) ||
        (plan.max_index != 255 && argc <= plan.max_index))
        goto decline;
    bool captured = false;
    if (b->vardefs)
        for (unsigned i = 0; i < b->arg_count; i++)
            if (b->vardefs[i].is_captured) {
                captured = true;
                break;
            }
    unsigned mutable_count = (argc < b->arg_count || captured) ? max_int(argc, b->arg_count) : 0;
    unsigned owned = mutable_count + argc;
    size_t bytes =
        128 + sizeof(JSValue) * (owned + b->var_count + b->stack_size) + FRAME_CAPTURE_BYTES(b);
    if (bytes > 4096 || js_check_stack_overflow(rt, bytes))
        goto decline;
    /* Poll in the caller realm,once,before creating the child or its owners. */
    if (js_poll_interrupts(caller))
        goto exception;
    if (js_check_stack_overflow(rt, bytes)) {
        JS_ThrowStackOverflow(caller);
        goto exception;
    }
    JSFrameSegment *segment = s->segment;
    if (bytes > segment->capacity - segment->used) {
        segment = readonly_child_grow(caller, segment, bytes);
        if (!segment)
            goto exception;
    }
    JSFrame *f = (JSFrame *)(segment->data + segment->used);
    JSStackFrame *sf = &f->sf;
    f->segment = segment;
    f->frame_bytes = (uint32_t)bytes;
    f->bytecode = b;
    f->this_value = receiver;
    f->owned_args = (uint16_t)owned;
    f->pending = 0;
    JSValue *local = (JSValue *)((uint8_t *)f + 128), *snapshot = local + mutable_count,
            *args = argv;
    for (unsigned i = 0; i < owned; i++)
        local[i] = JS_UNDEFINED;
    if (mutable_count) {
        args = local;
        for (unsigned i = 0; i < argc; i++)
            args[i] = js_dup(argv[i]);
    }
    JSValue *vars = local + owned, *stack = vars + b->var_count;
    for (unsigned i = 0; i < b->var_count; i++)
        vars[i] = JS_UNDEFINED;
    sf->prev_frame = &parent->sf;
    sf->cur_func = func;
    sf->arg_buf = args;
    sf->var_buf = vars;
    sf->arg_count = mutable_count ? mutable_count : argc;
    sf->var_ref_count = b->var_ref_count;
    sf->var_refs = b->var_ref_count ? (JSVarRef **)(stack + b->stack_size) : NULL;
    for (unsigned i = 0; i < sf->var_ref_count; i++)
        sf->var_refs[i] = NULL;
    sf->is_strict_mode = true;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = b->byte_code_buf;
    sf->cur_sp = stack;
    f->saved_sp = stack;
    FRAME_ROOT(f) = 0;
    FRAME_FLAGS(f) = 0;
    parent->pending = (uint16_t)((argc + 1 + method) | (tail ? 0x8000 : 0));
    segment->used += bytes;
    s->used_bytes += bytes;
    js_frame_charge_stack(rt, bytes);
    s->frame = f;
    s->segment = segment;
    s->pc = b->byte_code_buf;
    s->sp = stack;
    rt->current_stack_frame = sf;
    js_frame_finish_c(s);
    (void)readonly_prefix(s, &plan, argc, vc(argv), snapshot);
    js_frame_finish_c(s);
    return s->frame ? 1 : 2;
exception:
    s->pc = parent->sf.cur_pc;
    s->sp = parent->saved_sp;
    s->exception_pending = true;
    js_frame_finish_c(s);
    return JS_FrameInterpSlow(s) ? 2 : 1;
decline:
    js_frame_finish_c(s);
    return 0;
}
