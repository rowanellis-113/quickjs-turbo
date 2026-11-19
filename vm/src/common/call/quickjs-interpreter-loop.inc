#include "src/common/call/interpreter-context-types.inc"

/* A supported opcode is declared once, for validation and dispatch. */
static const uint8_t js_frame_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
};

static FRAME_CODE bool js_frame_validate(JSFunctionBytecode *b)
{
    /* Admission and legacy slot-hint capacity are independent bounds. */
    uint8_t boundaries[(4096 + 7) / 8] = {0};
    const uint8_t *code = b->byte_code_buf;
    int pos, size, op, index, target;
    bool readonly_args = true;
    bool captured_args = false;
    if (b->func_kind != JS_FUNC_NORMAL || b->is_derived_class_constructor ||
        b->byte_code_len <= 0 || b->byte_code_len > 4096 || b->stack_size > 512 ||
        (b->byte_code_len > FRAME_MAX_CODE && getenv("QJS_DISABLE_FRAME_LONG_CODE") != NULL) ||
        /* Admission is cached in the bytecode before execution. Existing
         * frames already size/charge the operand area from stack_size; only
         * wider functions consult this process-start policy ablation. */
        (b->stack_size > 256 && getenv("QJS_DISABLE_FRAME_WIDE_STACK") != NULL) ||
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
    FRAME_KIND(b) = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);
    return true;
}

static FRAME_INLINE JSFunctionBytecode *js_frame_target(JSValueConst func)
{
    JSObject *p;
    JSFunctionBytecode *b;
    if (JS_VALUE_GET_TAG(func) != JS_TAG_OBJECT)
        return NULL;
    p = JS_VALUE_GET_OBJ(func);
    if (p->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return NULL;
    b = p->u.func.function_bytecode;
    if (!FRAME_KIND(b) && !js_frame_validate(b))
        FRAME_KIND(b) = 2;
    return FRAME_SUPPORTED(b) ? b : NULL;
}

static FRAME_CODE JSFrameSegment *js_frame_grow(JSContext *ctx, JSFrameSegment *segment,
                                                size_t size)
{
    JSFrameSegment *next = segment->next;
    if (next && next->capacity >= size) {
        next->used = 0;
        return next;
    }
    /* Existing segments and published frame/argument addresses never move. */
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

static FRAME_CODE JSValue js_frame_legacy_call(JSContext *ctx, JSValueConst func,
                                               JSValueConst this_value, int argc,
                                               JSValueConst *argv)
{
    /* Native/proxy/generator class calls do not need a recursive interpreter
       activation. Keep exactly the poll performed by the old call entry. */
    if (JS_VALUE_GET_TAG(func) == JS_TAG_OBJECT) {
        JSObject *object = JS_VALUE_GET_OBJ(func);
        if (object->class_id != JS_CLASS_BYTECODE_FUNCTION) {
            JSClassCall *call = ctx->rt->class_array[object->class_id].call;
            if (call) {
                if (unlikely(js_poll_interrupts(ctx)))
                    return JS_EXCEPTION;
                return call(ctx, func, this_value, argc, argv, 0);
            }
        }
    }
    return JS_CallInternal(ctx, func, this_value, JS_UNDEFINED, argc, argv, 0);
}

/* The caller's operands own the supplied prefix. Only read-only nested callees
 * may extend this window. Return added bytes, or SIZE_MAX for the f19 fallback.
 * No allocation, callback or address movement occurs here. Keep this helper
 * after the executor's subsection, outside its register/temporary allocation. */
#ifdef QJS_INTERP_FRAME_INLINE_WINDOW
static FRAME_WINDOW_CODE size_t js_frame_extend_window(JSFrame *caller, JSValueConst *argv,
                                                       int formal)
{
    JSFrameSegment *owner = caller->segment;
    size_t end = (uint8_t *)argv - owner->data + sizeof(JSValue) * formal;
    size_t added;
    /* The allocation segment can be a returned child's segment. Always use
     * the caller's owner, and never overwrite any following live frame. */
    if (owner->used != js_frame_segment_mark(caller) + caller->frame_bytes || end > owner->capacity)
        return SIZE_MAX;
    /* The inline capacity check only calls here when extension is needed. */
    added = end - owner->used;
    owner->used = end;
    caller->frame_bytes += added;
    return added;
}
#else
/* Keep the padding loop outside the large executor for the GCC path. Both
 * strategies have identical value ownership and segment-extension rules. */
static FRAME_WINDOW_CODE size_t js_frame_pad_window(JSFrame *caller, JSValue *argv, int argc,
                                                    int formal)
{
    JSFrameSegment *owner = caller->segment;
    size_t end = (uint8_t *)argv - owner->data + sizeof(JSValue) * formal;
    size_t added = 0;
    int i;
    if (owner->used != js_frame_segment_mark(caller) + caller->frame_bytes || end > owner->capacity)
        return SIZE_MAX;
    if (end > owner->used) {
        added = end - owner->used;
        owner->used = end;
        caller->frame_bytes += added;
    }
    for (i = argc; i < formal; i++)
        argv[i] = JS_UNDEFINED;
    return added;
}
#endif

#ifdef QJS_INTERP_FRAME_REGISTER_ABI
#include "quickjs-interpreter-slow.h"
#include "src/common/call/quickjs-interpreter-bigint.inc"

/* A host call needs the standard value ABI, one interrupt poll and original
 * class-call semantics. It does not need the C opcode/interpreter-step activation. */
FRAME_CODE int JS_FrameInterpHost(JSFrameRegisterState *state, JSValue *argv, int argc, bool method)
{
    JSContext *ctx = state->frame->bytecode->realm;
    JSValue this_value = method ? argv[-2] : JS_UNDEFINED;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state->bridges++;
#endif
    state->result = js_frame_legacy_call(ctx, argv[-1], this_value, argc, vc(argv));
    state->exception_pending = JS_IsException(state->result);
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_finish_c(state);
#endif
    return state->exception_pending;
}

FRAME_HOST_CODE int JS_FrameInterpHostDirect(JSFrameRegisterState *state, JSValue *argv, int argc,
                                             bool method)
{
    JSContext *ctx = state->frame->bytecode->realm;
    JSValue this_value = method ? argv[-2] : JS_UNDEFINED;
    JSValueConst callee = argv[-1];
    JSObject *object = JS_VALUE_GET_OBJ(callee);
    JSStackFrame host_frame;
    JSValueConst *arg_buf;
    int formal, i;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state->bridges++;
#endif
    /* The leaf native dispatcher has checked the live callee's exact class
     * and signature without touching the argument registers or native stack.
     * This dedicated bridge keeps native C frames out of the fallback host
     * function's prologue and preserves its code/stack-allocation contract. */
    {
        if (unlikely(js_poll_interrupts(ctx))) {
            state->result = JS_EXCEPTION;
            goto host_done;
        }
        formal = object->u.cfunc.length;
        if (unlikely(js_check_stack_overflow(state->rt, sizeof(JSValue) * formal))) {
            state->result = JS_ThrowStackOverflow(ctx);
            goto host_done;
        }
        arg_buf = vc(argv);
        if (unlikely(argc < formal)) {
            arg_buf = alloca(sizeof(JSValue) * formal);
            for (i = 0; i < argc; i++)
                arg_buf[i] = argv[i];
            for (i = argc; i < formal; i++)
                arg_buf[i] = JS_UNDEFINED;
        }
        host_frame.prev_frame = state->rt->current_stack_frame;
        host_frame.cur_func = unsafe_unconst(callee);
        host_frame.arg_buf = (JSValue *)arg_buf;
        host_frame.arg_count = argc < formal ? formal : argc;
        host_frame.is_strict_mode = false;
        FRAME_CLEAR_STACK_AUX(&host_frame);
        state->rt->current_stack_frame = &host_frame;
        ctx = object->u.cfunc.realm;
        if (object->u.cfunc.cproto == JS_CFUNC_generic) {
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            state->direct_host_generic++;
#endif
            state->result = object->u.cfunc.c_function.generic(ctx, this_value, argc, arg_buf);
        } else {
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            state->direct_host_magic++;
#endif
            state->result = object->u.cfunc.c_function.generic_magic(ctx, this_value, argc, arg_buf,
                                                                     object->u.cfunc.magic);
        }
        state->rt->current_stack_frame = host_frame.prev_frame;
    }
host_done:
    state->exception_pending = JS_IsException(state->result);
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_finish_c(state);
#endif
    return state->exception_pending;
}

/* The native return carries an owned value across this cold boundary.
 * The original helper detaches cells before any slot owner is released. */
FRAME_CODE void JS_FrameInterpClose(JSFrameRegisterState *state)
{
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
    close_var_refs(state->rt, &state->frame->sf);
    state->frame->sf.var_ref_count = 0;
    state->frame->sf.var_refs = NULL;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_finish_c(state);
#endif
}

#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
/* Assembly can retain a stale snapshot of this activation's arena charge.
 * The last release
 * can run an arbitrary native finalizer, including a nested JS activation.
 * Use the live realm supplied by assembly: state->frame is only refreshed at
 * opcode/host boundaries and may still name an earlier native frame here. */
FRAME_CODE void JS_FrameInterpFree(JSFrameRegisterState *state, JSContext *ctx, JSValue value)
{
    js_frame_begin_c(state);
    JS_FreeValue(ctx, value);
    js_frame_finish_c(state);
}
#endif
#endif

/* This is one C activation for the complete supported JS call chain. Nested
 * JS calls save a continuation, push a data frame and jump to enter_frame. */
static FRAME_CODE JSValue JS_RunFrame(JSContext *caller_ctx, JSValueConst root_func,
                                      JSValueConst root_this, int root_argc,
                                      JSValueConst *root_argv, JSFunctionBytecode *root_b
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
                                      ,
                                      int root_flags
#endif
)
{
    uint8_t storage[FRAME_INITIAL_BYTES + 15];
    JSFrameSegment initial, *segment = &initial, *seg_next;
    JSFrameCallSite sites[FRAME_CACHE_SLOTS];
    uint8_t cache_next[FRAME_CACHE_SLOTS / 2] = {0};
    JSFrame *frame = NULL, *parent;
    JSRuntime *rt = caller_ctx->rt;
    JSContext *ctx = caller_ctx;
    JSFunctionBytecode *b = root_b;
#if defined(_MSC_VER)
    JSObject *p;
#endif
    JSStackFrame *sf;
#if defined(_MSC_VER)
    JSVarRef **var_refs;
#endif
    JSValue this_obj = unsafe_unconst(root_this), func_obj = unsafe_unconst(root_func);
    JSValue *sp = NULL, *arg_buf, *var_buf, *stack_buf, *local_buf, *pval;
    JSValue *call_argv;
    JSValue ret_val;
    JSValueConst *incoming_argv = root_argv;
    uint8_t *pc;
    int incoming_argc = root_argc, incoming_copy =
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
                                       (root_flags & JS_CALL_FLAG_COPY_ARGV) != 0;
#else
                                       1;
#endif
    int opcode, i, call_argc, owned_args;
    size_t frame_size, used_bytes = 0;
#ifdef QJS_INTERP_FRAME_REGISTER_ABI
    JSFrameRegisterState registers = {0};
    bool register_abi =
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
        js_frame_register_enabled(rt);
#else
        !qjs_internal_interp_register_disabled();
#endif
    registers.rt = rt;
    registers.caller_ctx = caller_ctx;
    registers.sites = sites;
    registers.cache_next = cache_next;
    registers.direct_host_calls =
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
        js_frame_direct_host_enabled(rt);
#else
        getenv("QJS_DISABLE_DIRECT_HOST_CALL") == NULL;
#endif
#endif
#undef CASE
#undef BREAK
#if DIRECT_DISPATCH
    __extension__ static const void *const frame_dispatch_table[256] = {
#define FRAME_TARGET(id, label) &&frame_##label,
#include "src/common/call/quickjs-interpreter-dispatch.inc"
#undef FRAME_TARGET
        [OP_COUNT... 255] = &&frame_invalid};
#define FRAME_NEXT() __extension__({ goto *frame_dispatch_table[opcode = *pc++]; });
#define CASE(op) frame_##op
#define BREAK FRAME_NEXT()
#else
#define FRAME_NEXT() switch (opcode = *pc++)
#define CASE(op) case op
#define BREAK goto dispatch
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    uint64_t pushes = 0, arities = 0, cache_hits = 0, cache_misses = 0, bridges = 0;
    uint64_t borrowed_values = 0, copied_values = 0;
    uint64_t windows = 0, window_fallbacks = 0, window_bytes = 0, shallow_values = 0,
             cross_windows = 0;
    uint64_t window_helpers = 0;
    size_t peak_bytes = 0;
    unsigned depth = 0, max_depth = 0;
#endif
    initial.next = NULL;
    initial.data = (uint8_t *)(((uintptr_t)storage + 15) & ~(uintptr_t)15);
    initial.capacity = FRAME_INITIAL_BYTES;
    initial.used = 0;
    for (i = 0; i < FRAME_CACHE_SLOTS; i++) {
        sites[i].continuation = 0;
    }
enter_frame:
    /* Poll before publication/allocation, matching the legacy call entry. */
    if (unlikely(js_poll_interrupts(ctx)))
        goto push_exception;
    owned_args = (incoming_copy || incoming_argc < b->arg_count || FRAME_CAPTURED_ARGS(b))
                     ? b->arg_count
                     : 0;
    if (owned_args && !incoming_copy &&
        FRAME_READONLY_ARGS(b)
        /* A captured caller's table follows its declared operand stack.
         * Padding a borrowed window must never overwrite that table. */
        && frame && !frame->sf.var_ref_count
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
        && frame
#endif
    ) {
#ifdef QJS_INTERP_FRAME_INLINE_WINDOW
        /* A paused caller's reserved tail already belongs to that caller.
         * Repeated calls can use it directly, even when the allocator is on
         * another segment. Only extensions need the owner-segment helper. */
        frame_size =
            (const uint8_t *)incoming_argv - (const uint8_t *)frame + sizeof(JSValue) * owned_args;
        if (frame_size <= frame->frame_bytes) {
            frame_size = 0;
        } else {
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            window_helpers++;
#endif
            frame_size = js_frame_extend_window(frame, incoming_argv, owned_args);
        }
#else
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        window_helpers++;
#endif
        frame_size =
            js_frame_pad_window(frame, (JSValue *)incoming_argv, incoming_argc, b->arg_count);
#endif
        if (frame_size != SIZE_MAX) {
            /* Parent extensions remain charged until that parent is popped.
             * The ordinary combined stack check below includes this charge. */
            used_bytes += frame_size;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
            js_frame_charge_stack(rt, frame_size);
#endif
            owned_args = 0;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            windows++;
            window_bytes += frame_size;
            borrowed_values += incoming_argc;
            cross_windows += frame->segment != segment;
#endif
        }
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        else
            window_fallbacks++;
#endif
    }
    frame_size = FRAME_HEADER_BYTES +
                 sizeof(JSValue) * (owned_args + b->var_count + b->stack_size) +
                 FRAME_CAPTURE_BYTES(b);
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    if (unlikely(js_check_stack_overflow(rt, frame_size))) {
#else
    if (unlikely(js_check_stack_overflow(rt, used_bytes + frame_size))) {
#endif
        JS_ThrowStackOverflow(ctx);
        goto push_exception;
    }
    if (unlikely(frame_size > segment->capacity - segment->used)) {
        JSFrameSegment *next = js_frame_grow(ctx, segment, frame_size);
        if (!next)
            goto push_exception;
        segment = next;
    }
    parent = frame;
    frame = (JSFrame *)(segment->data + segment->used);
    frame->segment = segment;
    frame->frame_bytes = frame_size;
    segment->used += frame_size;
    used_bytes += frame_size;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_charge_stack(rt, frame_size);
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    if (used_bytes > peak_bytes)
        peak_bytes = used_bytes;
#endif
    frame->bytecode = b;
    frame->this_value = this_obj;
    frame->owned_args = owned_args;
    frame->pending = 0;
    sf = &frame->sf;
    local_buf = (JSValue *)((uint8_t *)frame + FRAME_HEADER_BYTES);
    arg_buf = (JSValue *)incoming_argv;
    if (owned_args) {
        arg_buf = local_buf;
        if (!incoming_copy && FRAME_READONLY_ARGS(b)
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
            && parent
#endif
        ) {
            /* Missing-arity, read-only slots may borrow the caller's owners.
             * Its call operands stay live until this child returns/unwinds.
             * Keep a contiguous padded buffer, but skip freeing its borrowed
             * prefix. Missing-arity roots and writable slots own their copies.
             * Unsupported arguments/eval/local captures cannot alias slots. */
            for (i = 0; i < incoming_argc; i++)
                arg_buf[i] = unsafe_unconst(incoming_argv[i]);
            frame->owned_args -= incoming_argc;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            borrowed_values += incoming_argc;
            shallow_values += incoming_argc;
#endif
        } else {
            for (i = 0; i < min_int(incoming_argc, b->arg_count); i++)
                arg_buf[i] = js_dup(incoming_argv[i]);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            copied_values += i;
#endif
        }
        for (; i < b->arg_count; i++)
            arg_buf[i] = JS_UNDEFINED;
#ifdef QJS_INTERP_FRAME_INLINE_WINDOW
    } else if (incoming_argc < b->arg_count) {
        /* Borrowed windows are padded only after the child has storage.
         * No provided value is copied, duplicated or freed here. */
        for (i = incoming_argc; i < b->arg_count; i++)
            arg_buf[i] = JS_UNDEFINED;
#endif
    }
    var_buf = local_buf + owned_args;
    for (i = 0; i < b->var_count; i++)
        var_buf[i] = JS_UNDEFINED;
    stack_buf = var_buf + b->var_count;
    sp = stack_buf;
    pc = b->byte_code_buf;
    sf->prev_frame = rt->current_stack_frame;
    sf->cur_func = func_obj;
    sf->arg_buf = arg_buf;
    sf->var_buf = var_buf;
    sf->var_refs = b->var_ref_count ? (JSVarRef **)(stack_buf + b->stack_size) : NULL;
    sf->var_ref_count = b->var_ref_count;
    for (i = 0; i < sf->var_ref_count; i++)
        sf->var_refs[i] = NULL;
    sf->arg_count = owned_args ? b->arg_count : max_int(incoming_argc, b->arg_count);
    sf->is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = NULL;
    sf->cur_sp = NULL;
    FRAME_FLAGS(frame) = 0;
    FRAME_ROOT(frame) = parent == NULL;
    rt->current_stack_frame = sf;
    ctx = b->realm;
#if defined(_MSC_VER)
    p = JS_VALUE_GET_OBJ(func_obj);
    var_refs = p->u.func.var_refs;
#endif
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    pushes++;
    arities += incoming_argc < b->arg_count;
    if (++depth > max_depth)
        max_depth = depth;
#endif
dispatch:
#ifdef QJS_INTERP_FRAME_REGISTER_ABI
    if (register_abi) {
        int event;
        registers.frame = frame;
        registers.segment = segment;
        registers.pc = pc;
        registers.sp = sp;
        registers.used_bytes = used_bytes;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        registers.pushes = pushes;
        registers.arities = arities;
        registers.borrowed_values = borrowed_values;
        registers.windows = windows;
        registers.peak_bytes = peak_bytes;
        registers.depth = depth;
        registers.max_depth = max_depth;
        registers.cache_hits = cache_hits;
        registers.cache_misses = cache_misses;
        registers.bridges = bridges;
        registers.copied_values = copied_values;
        registers.window_fallbacks = window_fallbacks;
        registers.window_bytes = window_bytes;
        registers.shallow_values = shallow_values;
        registers.cross_windows = cross_windows;
        registers.window_helpers = window_helpers;
#endif
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
        /* C already committed the live frames. Pure JS retains that snapshot
         * and checks against a cached limit excluding only its own charge. */
        registers.committed_bytes = used_bytes;
        registers.shared_stack_limit = rt->stack_limit;
        registers.native_stack_limit = rt->stack_limit ? rt->stack_limit - used_bytes : 0;
#endif
        event = JS_FrameInterp(&registers);
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
        /* A native root return has used_bytes=0 but can still have a deep
         * snapshot committed by its last host/interrupt/finalizer boundary. */
        if (registers.used_bytes != registers.committed_bytes)
            js_frame_charge_stack(rt, registers.used_bytes - registers.committed_bytes);
#endif
        frame = registers.frame;
        segment = registers.segment;
        pc = registers.pc;
        sp = registers.sp;
        used_bytes = registers.used_bytes;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        pushes = registers.pushes;
        arities = registers.arities;
        borrowed_values = registers.borrowed_values;
        windows = registers.windows;
        peak_bytes = registers.peak_bytes;
        depth = registers.depth;
        max_depth = registers.max_depth;
        cache_hits = registers.cache_hits;
        cache_misses = registers.cache_misses;
        bridges = registers.bridges;
        copied_values = registers.copied_values;
        window_fallbacks = registers.window_fallbacks;
        window_bytes = registers.window_bytes;
        shallow_values = registers.shallow_values;
        cross_windows = registers.cross_windows;
        window_helpers = registers.window_helpers;
#endif
        if (event == 1) {
            ret_val = registers.result;
            goto exit_activation;
        }
        sf = &frame->sf;
        b = frame->bytecode;
        ctx = b->realm;
        var_buf = sf->var_buf;
        arg_buf = sf->arg_buf;
        stack_buf = var_buf + b->var_count;
        this_obj = frame->this_value;
#if defined(_MSC_VER)
        p = JS_VALUE_GET_OBJ(sf->cur_func);
        var_refs = p->u.func.var_refs;
#endif
    }
#endif
    FRAME_NEXT()
    {
#include "src/common/call/quickjs-interpreter-ops.inc"
        CASE(OP_call0)
            : CASE(OP_call1) : CASE(OP_call2) : CASE(OP_call3) : call_argc = opcode - OP_call0;
        goto prepare_call;
        CASE(OP_call)
            : CASE(OP_tail_call)
            : CASE(OP_call_method) : CASE(OP_tail_call_method) : call_argc = get_u16(pc);
        pc += 2;
    prepare_call: {
        const uint8_t *site_pc = pc;
        uintptr_t site_key = (uintptr_t)site_pc;
        unsigned bucket =
            (site_key ^ (site_key >> 6) ^ (site_key >> 12)) & (FRAME_CACHE_SLOTS / 2 - 1);
        JSFrameCallSite *site = &sites[bucket * 2];
        bool method = opcode == OP_call_method || opcode == OP_tail_call_method;
        JSValue callee, call_this;
        JSFunctionBytecode *call_b = NULL;
        call_argv = sp - call_argc;
        callee = call_argv[-1];
        call_this = method ? call_argv[-2] : JS_UNDEFINED;
        sf->cur_pc = pc;
        frame->saved_sp = sp;
        frame->pending =
            (uint16_t)((call_argc + 1 + method) |
                       ((opcode == OP_tail_call || opcode == OP_tail_call_method) ? 0x8000 : 0));
        if (site->continuation != site_key) {
            if (site[1].continuation == site_key)
                site++;
            else if (!site->continuation)
                cache_next[bucket] = 1;
            else if (!site[1].continuation) {
                site++;
                cache_next[bucket] = 0;
            } else {
                site += cache_next[bucket];
                cache_next[bucket] ^= 1;
            }
        }
        if (site->continuation == site_key && site->argc == call_argc &&
            JS_VALUE_GET_TAG(callee) == JS_TAG_OBJECT &&
            (uintptr_t)JS_VALUE_GET_OBJ(callee) == site->identity &&
            (!site->code_identity ||
             (JS_VALUE_GET_OBJ(callee)->class_id == JS_CLASS_BYTECODE_FUNCTION &&
              (uintptr_t)JS_VALUE_GET_OBJ(callee)->u.func.function_bytecode ==
                  site->code_identity &&
              FRAME_SUPPORTED(JS_VALUE_GET_OBJ(callee)->u.func.function_bytecode)))) {
            if (site->code_identity)
                call_b = JS_VALUE_GET_OBJ(callee)->u.func.function_bytecode;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            cache_hits++;
#endif
        } else {
            site->continuation = site_key;
            site->identity =
                JS_VALUE_GET_TAG(callee) == JS_TAG_OBJECT ? (uintptr_t)JS_VALUE_GET_OBJ(callee) : 0;
            site->argc = call_argc;
            call_b = js_frame_target(callee);
            site->code_identity = (uintptr_t)call_b;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
            cache_misses++;
#endif
        }
        if (call_b) {
            b = call_b;
            func_obj = callee;
            this_obj = call_this;
            incoming_argc = call_argc;
            incoming_argv = vc(call_argv);
            incoming_copy = 0;
            goto enter_frame;
        }
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
        bridges++;
#endif
        ret_val = js_frame_legacy_call(ctx, callee, call_this, call_argc, vc(call_argv));
        if (unlikely(JS_IsException(ret_val)))
            goto exception;
        goto finish_call;
    }
        CASE(OP_return) : ret_val = *--sp;
        goto return_frame;
        CASE(OP_return_undef) : ret_val = JS_UNDEFINED;
        goto return_frame;
        CASE(OP_nop) : goto dispatch;
#if DIRECT_DISPATCH
    frame_invalid:
#else
    default:
#endif
        JS_ThrowInternalError(ctx, "invalid explicit-frame opcode");
        goto exception;
    }
finish_call:
    call_argv = frame->saved_sp - js_frame_pending_count(frame);
    for (pval = call_argv; pval < frame->saved_sp; pval++)
        JS_FreeValue(ctx, *pval);
    sp = call_argv;
    if (js_frame_pending_tail(frame))
        goto return_frame;
    *sp++ = ret_val;
    frame->pending = 0;
    goto dispatch;

push_exception:
    if (!frame) {
        ret_val = JS_EXCEPTION;
        goto exit_activation;
    }
    goto restore_exception;
exception:
    sf->cur_pc = pc;
    if (needs_backtrace(rt->current_exception) || JS_IsUndefined(ctx->error_back_trace))
        build_backtrace(ctx, rt->current_exception, JS_UNDEFINED, NULL, 0, 0, 0);
    ret_val = JS_EXCEPTION;
return_frame:
    if (frame->sf.var_ref_count) {
        close_var_refs(rt, &frame->sf);
        frame->sf.var_ref_count = 0;
        frame->sf.var_refs = NULL;
    }
    local_buf = frame->sf.var_buf - frame->owned_args;
    for (pval = local_buf; pval < sp; pval++)
        JS_FreeValue(ctx, *pval);
    rt->current_stack_frame = frame->sf.prev_frame;
    segment = frame->segment;
    segment->used = js_frame_segment_mark(frame);
    used_bytes -= frame->frame_bytes;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_release_stack(rt, frame->frame_bytes);
#endif
    frame = js_frame_parent(frame);
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    depth--;
#endif
    if (!frame)
        goto exit_activation;
    sf = &frame->sf;
    b = frame->bytecode;
    ctx = b->realm;
#if defined(_MSC_VER)
    p = JS_VALUE_GET_OBJ(sf->cur_func);
    var_refs = p->u.func.var_refs;
#endif
    var_buf = sf->var_buf;
    arg_buf = sf->arg_buf;
    stack_buf = var_buf + b->var_count;
    this_obj = frame->this_value;
    sp = frame->saved_sp;
    pc = sf->cur_pc;
    if (unlikely(JS_IsException(ret_val)))
        goto exception;
    goto finish_call;
restore_exception:
    sf = &frame->sf;
    b = frame->bytecode;
    ctx = b->realm;
    sp = frame->saved_sp;
    pc = sf->cur_pc;
    goto exception;
exit_activation:
    /* Cache pointers are only compared, never followed after their owner dies.
       A positive hit checks the CURRENT object class, code pointer and validated
       kind before dereferencing code. Reuse of either address is safe because
       frame sizes/PCs/closure refs are loaded afresh from that live object.
       Keeping cache entries weak also preserves native-resource finalization. */
    segment = initial.next;
    while (segment) {
        seg_next = segment->next;
        js_free(caller_ctx, segment);
        segment = seg_next;
    }
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
#ifdef QJS_INTERP_FRAME_REGISTER_ABI
    if (qjs_internal_interp_trace_enabled()) {
        fprintf(
            stderr, "INTERP calls=%llu returns=%llu slow=%llu active=%u windows=%llu hosts=%llu\n",
            (unsigned long long)registers.native_calls,
            (unsigned long long)registers.native_returns, (unsigned long long)registers.slow_exits,
            register_abi, (unsigned long long)registers.native_windows,
            (unsigned long long)registers.native_hosts);
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
        fprintf(stderr, "QUOTA syncs=%llu refreshes=%llu\n",
                (unsigned long long)registers.budget_syncs,
                (unsigned long long)registers.budget_refreshes);
#endif
        fprintf(
            stderr,
            "RETABI root_stores=%llu finalizer_spills=%llu host_loads=%llu caller_stores=%llu\n",
            (unsigned long long)registers.return_root_stores,
            (unsigned long long)registers.return_finalizer_spills,
            (unsigned long long)registers.return_host_loads,
            (unsigned long long)registers.return_caller_stores);
        fprintf(stderr, "CALLPREP hits=%llu inits=%llu\n",
                (unsigned long long)registers.call_prepare_hits,
                (unsigned long long)registers.call_prepare_inits);
        fprintf(stderr, "HOSTDIRECT generic=%llu magic=%llu enabled=%u\n",
                (unsigned long long)registers.direct_host_generic,
                (unsigned long long)registers.direct_host_magic, registers.direct_host_calls);
        for (i = 0; i < 256; i++)
            if (registers.slow_opcodes[i])
                fprintf(stderr, "INTERP_OP opcode=%u exits=%llu\n", i,
                        (unsigned long long)registers.slow_opcodes[i]);
    }
#endif
    if (qjs_internal_interp_trace_enabled())
        fprintf(
            stderr,
            "FRAME pushes=%llu arities=%llu hits=%llu misses=%llu bridges=%llu depth=%u borrowed=%llu copied=%llu windows=%llu fallback=%llu grown=%llu shallow=%llu cross=%llu peak=%zu helpers=%llu inline=%u\n",
            (unsigned long long)pushes, (unsigned long long)arities, (unsigned long long)cache_hits,
            (unsigned long long)cache_misses, (unsigned long long)bridges, max_depth,
            (unsigned long long)borrowed_values, (unsigned long long)copied_values,
            (unsigned long long)windows, (unsigned long long)window_fallbacks,
            (unsigned long long)window_bytes, (unsigned long long)shallow_values,
            (unsigned long long)cross_windows, peak_bytes, (unsigned long long)window_helpers,
#ifdef QJS_INTERP_FRAME_INLINE_WINDOW
            1u);
#else
            0u);
#endif
#endif
    return ret_val;
}

static FRAME_CODE JSValue js_frame_call_entry(JSContext *ctx, JSValueConst func,
                                              JSValueConst this_value, JSValueConst new_target,
                                              int argc, JSValueConst *argv, int flags)
{
    JSFunctionBytecode *b;
    if (unlikely(!FRAME_STATE(ctx->rt)))
        FRAME_STATE(ctx->rt) =
            !qjs_internal_interp_frame_disabled() && getenv("QJS_DISABLE_MIN_CALL_FRAME") == NULL
                ? 1
                : 2;
    if (FRAME_STATE(ctx->rt) == 1 && (flags == 0 || flags == JS_CALL_FLAG_COPY_ARGV)
#ifdef ENABLE_DUMPS
        && !check_dump_flag(ctx->rt, JS_DUMP_BYTECODE_STEP)
#endif
        && (b = js_frame_target(func))) {
        if (unlikely(js_check_stack_overflow(ctx->rt, FRAME_INITIAL_BYTES + 4096)))
            return JS_ThrowStackOverflow(ctx);
        return JS_RunFrame(ctx, func, this_value, argc, argv, b
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
                           ,
                           flags
#endif
        );
    }
    /* Public API fallbacks must retain the ORIGINAL wrapper: bypassing it
       loses GCC's fixed-flag specialization and lets linkers discard
       its 128-byte section, moving the entire old interpreter. */
    if (flags == JS_CALL_FLAG_COPY_ARGV && JS_IsUndefined(new_target))
        return JS_LegacyCall(ctx, func, this_value, argc, argv);
    return JS_CallInternal(ctx, func, this_value, new_target, argc, argv, flags);
}

#undef FRAME_INLINE
#undef FRAME_VAR_REFS
#undef FRAME_HOST_CODE
#undef FRAME_CODE
#undef FRAME_WINDOW_CODE
#undef FRAME_OPCODE_CODE
#undef CASE
#undef BREAK
#undef FRAME_NEXT
