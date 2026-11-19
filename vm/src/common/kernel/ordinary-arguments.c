#include "src/common/call/interpreter-retained-context.inc"

typedef enum {
    OP_SPECIAL_OBJECT_ARGUMENTS,
    OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS,
    OP_SPECIAL_OBJECT_THIS_FUNC,
    OP_SPECIAL_OBJECT_NEW_TARGET,
    OP_SPECIAL_OBJECT_HOME_OBJECT,
    OP_SPECIAL_OBJECT_VAR_OBJECT,
    OP_SPECIAL_OBJECT_IMPORT_META,
    OP_SPECIAL_OBJECT_NULL_PROTO,
} OPSpecialObjectEnum;

#include <stdatomic.h>
#define JS_CALL_FLAG_COPY_ARGV (1 << 1)
/* Kind2 is the original unsupported negative-cache contract. Reserve only
   high bits in the existing varargs padding byte108, and only for kind2.
   Old varargs/name states occupy bits0..3; no old admitted builder sees a
   kind2 frame. Existing full-slow selectors mask bits1/3 and keep working. */
#define ARGUMENTS_KIND 2
#define ARGUMENTS_REJECTED 2
#define ARGUMENTS_MARKER(b) FRAME_ITERATOR_KIND(b)
#define ARGUMENTS_READY 128
#define ARGUMENTS_DENIED 64
_Static_assert(offsetof(JSFunctionBytecode, pc2line_len) ==
                       QJS_ABI_OFF_JSFunctionBytecode_pc2line_len &&
                   offsetof(JSFunctionBytecode, pc2line_buf) ==
                       QJS_ABI_OFF_JSFunctionBytecode_pc2line_buf &&
                   !(ARGUMENTS_READY & 15) && !(ARGUMENTS_DENIED & 15),
               "high descriptor bits remain disjoint from existing varargs");
#define ARGUMENTS_SIGNATURE 0x41524746u
typedef struct JSFrameArgumentsRecord {
    JSValueConst *argv;
    uint32_t argc, signature;
} JSFrameArgumentsRecord;
_Static_assert(sizeof(JSFrameArgumentsRecord) == 16 && sizeof(JSFrame) == 128 &&
                   sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame && FRAME_MAX_CODE == 2048,
               "separate argument prefix does not change any original frame type");
_Static_assert(!(ARGUMENTS_KIND & 1) && !(ARGUMENTS_KIND & 16) && !(ARGUMENTS_REJECTED & 1) &&
                   !(ARGUMENTS_REJECTED & 16),
               "old supported/prepared builders must reject both new states");
__attribute__((section(".qjzzpm"), aligned(4))) _Atomic(unsigned) JS_FrameArgumentsMode = 0;
__attribute__((section(".qjzzpm"), aligned(8))) _Atomic(uint64_t) JS_FrameArgumentsStats[7];
extern JSValue qjs_frame_core_JS_NewObjectFromShape(JSContext *, JSShape *, JSClassID,
                                                    JSProperty *);
extern JSVarRef *qjs_frame_core_get_var_ref(JSContext *, JSStackFrame *, int, bool);
extern void qjs_frame_core_free_var_ref(JSRuntime *, JSVarRef *);
#define JS_NewObjectFromShape qjs_frame_core_JS_NewObjectFromShape
#define get_var_ref qjs_frame_core_get_var_ref
#define free_var_ref qjs_frame_core_free_var_ref
extern int JS_FrameSlowDirectSelect(JSFrameRegisterState *);
extern int JS_FrameInterp(JSFrameRegisterState *);
extern int JS_FrameResolveInternal(JSContext *, const JSValue *);
extern JSValue JS_FrameCEntry(JSContext *, JSValueConst, JSValueConst, JSValueConst, int,
                              JSValueConst *, int);
static FRAME_INLINE unsigned arguments_mode(void)
{
    unsigned mode = atomic_load_explicit(&JS_FrameArgumentsMode, memory_order_relaxed);
    if (!mode) {
        unsigned expected = 0;
        mode = getenv("QJS_DISABLE_FRAME_ARGUMENTS") ? 2 : 1;
        if (getenv("QJS_DISABLE_FRAME_ARGUMENTS_BORROW"))
            mode |= 8;
        if (getenv("QJS_DISABLE_FRAME_ARGUMENTS_NATIVE"))
            mode |= 16;
        if (getenv("QJS_DISABLE_FRAME_ARGUMENTS_ACCESS"))
            mode |= 32;
        if (getenv("QJS_DISABLE_FRAME_ARGUMENTS_FORWARD"))
            mode |= 256;
        if (getenv("QJS_DISABLE_FRAME_ARGUMENTS_INDEX"))
            mode |= 64;
        if (getenv("QJS_DISABLE_FRAME_ARGUMENTS_LENGTH"))
            mode |= 128;
        if (getenv("QJS_OBSERVE_FRAME_ARGUMENTS"))
            mode |= 4;
        atomic_compare_exchange_strong_explicit(&JS_FrameArgumentsMode, &expected, mode,
                                                memory_order_relaxed, memory_order_relaxed);
        mode = atomic_load_explicit(&JS_FrameArgumentsMode, memory_order_relaxed);
    }
    return mode;
}
static FRAME_INLINE void arguments_count(unsigned n)
{
    if (atomic_load_explicit(&JS_FrameArgumentsMode, memory_order_relaxed) & 4)
        atomic_fetch_add_explicit(&JS_FrameArgumentsStats[n], 1, memory_order_relaxed);
}
static const uint8_t js_frame_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
#undef DEF
#undef def
};

static FRAME_CODE bool JS_FrameArgumentsValidate(JSFunctionBytecode *b)
{
    uint8_t boundaries[(FRAME_MAX_CODE + 7) / 8] = {0};
    const uint8_t *code = b->byte_code_buf;
    int pos, size, op, index, target;
    bool readonly_args = true;
    bool has_arguments = false;
    unsigned kind = 0, iterator_kind = 0;
    bool captured_args = false;
    bool extended = false;
    bool name_needs_full = false;
    iterator_kind = 0;
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
        case OP_special_object:
            if (code[pos + 1] == OP_SPECIAL_OBJECT_ARGUMENTS ||
                code[pos + 1] == OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS)
                has_arguments = true;
            else if (code[pos + 1] != OP_SPECIAL_OBJECT_THIS_FUNC &&
                     code[pos + 1] != OP_SPECIAL_OBJECT_NEW_TARGET &&
                     code[pos + 1] != OP_SPECIAL_OBJECT_HOME_OBJECT &&
                     code[pos + 1] != OP_SPECIAL_OBJECT_NULL_PROTO)
                return false;
            break;
        case OP_for_of_start:
        case OP_for_of_next:
        case OP_iterator_close:
        case OP_catch:
        case OP_gosub:
        case OP_ret:
        case OP_nip_catch:
        case OP_check_object:
            name_needs_full = true;
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
        iterator_kind = (varargs ? 3 : 1) | (names ? 4 : 0) | ((names && name_needs_full) ? 8 : 0);
    } else
        iterator_kind = 0;
    kind = (captured_args ? 5 : readonly_args ? 3 : 1) | (b->var_ref_count ? 8 : 0);
    if (!has_arguments)
        return false;
    ((unsigned char *)b)[FRAME_CALL_AUX_OFFSET] = (unsigned char)iterator_kind;
    ((unsigned char *)b)[FRAME_CALL_LOCALS_OFFSET] = (unsigned char)b->var_count;
    ((unsigned char *)b)[FRAME_CALL_FORMALS_OFFSET] = (unsigned char)b->arg_count;
    /* Exact no-owned-argument frame bytes. Only our native constructor reads
       this descriptor: old supported/prepared bits remain zero. */
    uint16_t native_bytes = FRAME_HEADER_BYTES + sizeof(JSFrameArgumentsRecord) +
                            sizeof(JSValue) * (b->var_count + b->stack_size) +
                            FRAME_CAPTURE_BYTES(b);
    memcpy((unsigned char *)b + FRAME_CALL_META_OFFSET, &native_bytes, sizeof(native_bytes));
    ARGUMENTS_MARKER(b) = ARGUMENTS_READY;
    FRAME_KIND(b) = ARGUMENTS_KIND;
    return true;
}

/* These two states deliberately have supported bit zero. No original leaf,
   cache, shared/C-window or native preparation path can create this prefix. */
static FRAME_CODE bool js_frame_arguments_target(JSFunctionBytecode *b)
{
    if (FRAME_KIND(b) == ARGUMENTS_KIND && ARGUMENTS_MARKER(b) == ARGUMENTS_READY)
        return true;
    if ((FRAME_KIND(b) == ARGUMENTS_REJECTED && ARGUMENTS_MARKER(b) == ARGUMENTS_DENIED) ||
        FRAME_SUPPORTED(b))
        return false;
    if ((arguments_mode() & 3) != 1 || !js_frame_register_enabled(b->realm->rt))
        return false;
    arguments_count(0);
    bool valid = JS_FrameArgumentsValidate(b);
    if (!valid) {
        ARGUMENTS_MARKER(b) = ARGUMENTS_DENIED;
        FRAME_KIND(b) = ARGUMENTS_REJECTED;
    }
    return valid;
}

/* Original segment growth body: every published argument/var-ref address is
   stable. It can allocate/reenter only while the paused caller is published. */
static FRAME_CODE JSFrameSegment *js_frame_arguments_grow(JSContext *ctx, JSFrameSegment *segment,
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

/* Returns false only with an exception. The caller has performed the one
   original entry poll. COPY and captured frames own every actual argument,
   including extras; a complete non-COPY window remains the original alias. */
static FRAME_CODE bool js_frame_arguments_push(JSFrameRegisterState *state, JSValueConst func,
                                               JSValueConst this_value, JSFunctionBytecode *b,
                                               unsigned argc, JSValueConst *argv, int flags,
                                               bool root)
{
    JSRuntime *rt = state->rt;
    JSContext *ctx = b->realm;
    JSFrameSegment *segment = state->segment;
    unsigned capacity = max_int(argc, b->arg_count);
    /* Non-COPY complete roots preserve the original writable argv alias.
       Captures are detached by the original close_var_refs on every exit. */
    unsigned owned = ((flags & JS_CALL_FLAG_COPY_ARGV) || argc < b->arg_count) ? capacity : 0;
    size_t bytes = FRAME_HEADER_BYTES + sizeof(JSFrameArgumentsRecord) +
                   sizeof(JSValue) * (owned + b->var_count + b->stack_size) +
                   FRAME_CAPTURE_BYTES(b);
    if (js_check_stack_overflow(rt, bytes)) {
        JS_ThrowStackOverflow(ctx);
        return false;
    }
    if (bytes > segment->capacity - segment->used) {
        segment = js_frame_arguments_grow(ctx, segment, bytes);
        if (!segment)
            return false;
    }
    JSFrame *frame = (JSFrame *)(segment->data + segment->used);
    JSFrameArgumentsRecord *record =
        (JSFrameArgumentsRecord *)((uint8_t *)frame + FRAME_HEADER_BYTES);
    JSValue *local = (JSValue *)(record + 1), *args = (JSValue *)argv;
    frame->segment = segment;
    frame->frame_bytes = bytes;
    frame->bytecode = b;
    frame->this_value = unsafe_unconst(this_value);
    frame->owned_args = owned;
    frame->pending = 0;
    record->argv = argv;
    record->argc = argc;
    record->signature = ARGUMENTS_SIGNATURE;
    if (owned) {
        args = local;
        unsigned i = 0;
        for (; i < argc; i++)
            args[i] = js_dup(argv[i]);
        for (; i < owned; i++)
            args[i] = JS_UNDEFINED;
    }
    JSValue *vars = local + owned, *stack = vars + b->var_count;
    for (unsigned i = 0; i < b->var_count; i++)
        vars[i] = JS_UNDEFINED;
    JSStackFrame *sf = &frame->sf;
    sf->prev_frame = rt->current_stack_frame;
    sf->cur_func = unsafe_unconst(func);
    sf->arg_buf = args;
    sf->var_buf = vars;
    sf->arg_count = capacity;
    sf->var_refs = b->var_ref_count ? (JSVarRef **)(stack + b->stack_size) : NULL;
    sf->var_ref_count = b->var_ref_count;
    for (unsigned i = 0; i < sf->var_ref_count; i++)
        sf->var_refs[i] = NULL;
    sf->is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = b->byte_code_buf;
    sf->cur_sp = stack;
    FRAME_ROOT(frame) = root;
    FRAME_FLAGS(frame) = 0;
    frame->saved_sp = stack;
    segment->used += bytes;
    state->used_bytes += bytes;
    js_frame_charge_stack(rt, bytes);
    state->frame = frame;
    state->segment = segment;
    state->sp = stack;
    state->pc = b->byte_code_buf;
    rt->current_stack_frame = sf;
    return true;
}

FRAME_CODE int JS_FrameArgumentsStep(JSFrameRegisterState *state)
{
    JSFrame *frame = state->frame;
    JSStackFrame *sf = &frame->sf;
    JSFunctionBytecode *b = frame->bytecode;
    JSContext *ctx = b->realm;
    JSFrameArgumentsRecord *record =
        (JSFrameArgumentsRecord *)((uint8_t *)frame + FRAME_HEADER_BYTES);
    JSValue *sp = state->sp, value;
    uint8_t *pc = state->pc + 2;
    state->rt->current_stack_frame = sf;
    frame->saved_sp = sp;
    sf->cur_sp = sp;
    sf->cur_pc = pc;
    js_frame_begin_c(state);
    if (record->signature != ARGUMENTS_SIGNATURE) {
        value = JS_ThrowInternalError(ctx, "invalid argument frame record");
    } else
        switch (state->pc[1]) {
        case OP_SPECIAL_OBJECT_ARGUMENTS:
            arguments_count(3);
            value = js_build_arguments(ctx, record->argc, record->argv);
            break;
        case OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS:
            arguments_count(4);
            value = js_build_mapped_arguments(ctx, record->argc, record->argv, sf,
                                              min_int(record->argc, b->arg_count));
            break;
        case OP_SPECIAL_OBJECT_THIS_FUNC:
            value = js_dup(sf->cur_func);
            break;
        case OP_SPECIAL_OBJECT_NEW_TARGET:
            value = JS_UNDEFINED;
            break;
        case OP_SPECIAL_OBJECT_HOME_OBJECT: {
            JSObject *p = JS_VALUE_GET_OBJ(sf->cur_func);
            value = p->u.func.home_object ? js_dup(JS_MKPTR(JS_TAG_OBJECT, p->u.func.home_object))
                                          : JS_UNDEFINED;
            break;
        }
        case OP_SPECIAL_OBJECT_NULL_PROTO:
            value = JS_NewObjectProtoClass(ctx, JS_NULL, JS_CLASS_OBJECT);
            break;
        default:
            value = JS_ThrowInternalError(ctx, "unsupported argument-frame special object");
            break;
        }
    *sp++ = value;
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

/* Called at the original native call decline. No accepted frame reaches an
   old builder; no rejected call is polled or has its operands consumed here.
   Result: 1 entered,0 rejected,-1 exception published for original unwinder. */
FRAME_CODE int JS_FrameArgumentsTry(JSFrameRegisterState *state)
{
    JSFrame *parent = state->frame;
    JSContext *ctx = parent->bytecode->realm;
    unsigned op = *state->pc;
    bool method = op == OP_call_method || op == OP_tail_call_method;
    unsigned argc = op >= OP_call0 && op <= OP_call3 ? op - OP_call0 : get_u16(state->pc + 1);
    JSValue *argv = state->sp - argc;
    JSValue func = argv[-1], this_value = method ? argv[-2] : JS_UNDEFINED;
    JSFunctionBytecode *b = JS_VALUE_GET_OBJ(func)->u.func.function_bytecode;
    js_frame_begin_c(state);
    unsigned mode = arguments_mode();
    if ((mode & 3) != 1 || argc > 32765 || !js_frame_arguments_target(b)) {
        js_frame_finish_c(state);
        return 0;
    }
    if (js_poll_interrupts(ctx))
        goto exception;
    /* The parent owns all call operands until return/unwind. Segments never
       move. Complete windows can therefore retain the original non-COPY
       alias, including captured/mapped formals closed before consumption. */
    if (!js_frame_arguments_push(state, func, this_value, b, argc, vc(argv),
                                 (mode & 8) ? JS_CALL_FLAG_COPY_ARGV : 0, false))
        goto exception;
    parent->pending = (uint16_t)((argc + 1 + method) |
                                 ((op == OP_tail_call || op == OP_tail_call_method) ? 0x8000 : 0));
    arguments_count(2);
    js_frame_finish_c(state);
    return 1;
exception:
    state->pc = parent->sf.cur_pc;
    state->exception_pending = true;
    js_frame_finish_c(state);
    return -1;
}

/* Only an admitted argument function pays for a new VM activation. Ordinary
   nested bytecode calls use the same-activation builder above. This C API
   root retains the original caller SF, quota and segment cleanup protocol. */
static FRAME_CODE JSValue js_frame_arguments_root(JSContext *ctx, JSValueConst func,
                                                  JSValueConst this_value, int argc,
                                                  JSValueConst *argv, int flags,
                                                  JSFunctionBytecode *b)
{
    uint8_t storage[FRAME_INITIAL_BYTES + 15];
    JSFrameSegment initial = {0}, *segment, *next;
    JSFrameCallSite sites[FRAME_CACHE_SLOTS] = {0};
    uint8_t cache_next[FRAME_CACHE_SLOTS / 2] = {0};
    JSFrameRegisterState state = {0};
    JSRuntime *rt = ctx->rt;
    if (js_poll_interrupts(ctx))
        return JS_EXCEPTION;
    initial.data = (uint8_t *)(((uintptr_t)storage + 15) & ~(uintptr_t)15);
    initial.capacity = FRAME_INITIAL_BYTES;
    state.rt = rt;
    state.caller_ctx = ctx;
    state.segment = &initial;
    state.sites = sites;
    state.cache_next = cache_next;
    state.direct_host_calls = js_frame_direct_host_enabled(rt);
    if (!js_frame_arguments_push(&state, func, this_value, b, argc, argv, flags, true)) {
        state.result = JS_EXCEPTION;
        goto done;
    }
    js_frame_finish_c(&state);
    while (!JS_FrameInterp(&state)) {
        if (JS_FrameSlowDirectSelect(&state))
            break;
    }
    if (state.used_bytes != state.committed_bytes)
        js_frame_charge_stack(rt, state.used_bytes - state.committed_bytes);
done:
    for (segment = initial.next; segment; segment = next) {
        next = segment->next;
        js_free(ctx, segment);
    }
    return state.result;
}

FRAME_CODE JSValue JS_FrameArgumentsRootBridge(JSContext *ctx, JSValueConst func,
                                               JSValueConst this_value, JSValueConst new_target,
                                               int argc, JSValueConst *argv, int flags)
{
    JSRuntime *rt = ctx->rt;
    if (js_check_stack_overflow(rt, 8192))
        goto fallback;
    /* Kind2 intentionally bypasses the old selector's C initialization.
       Initialize its existing controls once, then respect them unchanged. */
    if (!FRAME_STATE(rt) || !FRAME_INTERNAL_STATE(rt))
        (void)JS_FrameResolveInternal(ctx, &func);
    if (FRAME_STATE(rt) != 1 || FRAME_INTERNAL_STATE(rt) == 2 ||
        (flags & ~JS_CALL_FLAG_COPY_ARGV) || !JS_IsUndefined(new_target) || argc < 0 ||
        argc > 32765 || (arguments_mode() & 3) != 1 || !js_frame_register_enabled(rt))
        goto fallback;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(rt, JS_DUMP_BYTECODE_STEP))
        goto fallback;
#endif
    JSFunctionBytecode *b = JS_VALUE_GET_OBJ(func)->u.func.function_bytecode;
    if (!js_frame_arguments_target(b))
        goto fallback;
    arguments_count(1);
    return js_frame_arguments_root(ctx, func, this_value, argc, argv, flags, b);
fallback:
    arguments_count(5);
    return JS_FrameCEntry(ctx, func, this_value, new_target, argc, argv, flags);
}

__attribute__((section(".qjzzpm"), aligned(8))) _Atomic(uint64_t) JS_FrameArgumentsAccessStats[4];
_Static_assert(JS_CLASS_ARGUMENTS == 8 && JS_CLASS_MAPPED_ARGUMENTS == 9 &&
                   offsetof(JSObject, shape) == QJS_ABI_OFF_JSObject_shape &&
                   offsetof(JSObject, prop) == QJS_ABI_OFF_JSObject_prop &&
                   offsetof(JSObject, u.array.u.values) == QJS_ABI_OFF_JSObject_u_array_u_values &&
                   offsetof(JSObject, u.array.count) == QJS_ABI_OFF_JSObject_u_array_count &&
                   offsetof(JSVarRef, pvalue) == QJS_ABI_OFF_JSVarRef_pvalue &&
                   offsetof(JSShape, prop_hash_mask) == QJS_ABI_OFF_JSShape_prop_hash_mask &&
                   offsetof(JSShape, prop_count) == QJS_ABI_OFF_JSShape_prop_count &&
                   sizeof(JSShapeProperty) == QJS_ABI_SIZE_JSShapeProperty &&
                   offsetof(JSShapeProperty, atom) == QJS_ABI_OFF_JSShapeProperty_atom &&
                   JS_PROP_TMASK == 48 && JS_PROP_NORMAL == 0 && JS_TAG_INT == 0 &&
                   JS_TAG_FLOAT64 == 8,
               "argument access native layout and normal property type");
_Static_assert(JS_ATOM_length == 51, "argument length atom");

/* Original F14's call identity, logical C SF80/tag199 and original public
   JS_Call COPY_ARGV contract. A new kind2 descriptor never reaches an old
   128-byte constructor; its original argc/argv record is before owned args. */
extern int JS_FrameCallForwardNativeProbe(JSFrameRegisterState *);
__attribute__((section(".qjzzpm"), aligned(8))) _Atomic(uint64_t) JS_FrameArgumentsForwardStats[2];
static FRAME_INLINE JSFunctionBytecode *js_frame_arguments_forward_target(JSValueConst value)
{
    if (!JS_IsObject(value))
        return NULL;
    JSObject *p = JS_VALUE_GET_OBJ(value);
    if (p->class_id != JS_CLASS_BYTECODE_FUNCTION)
        return NULL;
    JSFunctionBytecode *b = p->u.func.function_bytecode;
    return js_frame_arguments_target(b) ? b : NULL;
}
static FRAME_INLINE bool js_frame_forward_is_call(JSValueConst value)
{
    if (!JS_IsObject(value))
        return false;
    JSObject *p = JS_VALUE_GET_OBJ(value);
    return p->class_id == JS_CLASS_C_FUNCTION && p->u.cfunc.cproto == JS_CFUNC_generic &&
           p->u.cfunc.magic == 0 && p->u.cfunc.length == 1 &&
           p->u.cfunc.c_function.generic == js_function_call;
}

FRAME_CODE int JS_FrameArgumentsForwardTry(JSFrameRegisterState *state)
{
    JSFrame *parent = state->frame, *child;
    JSFrameSegment *segment = state->segment;
    JSRuntime *rt = state->rt;
    JSFunctionBytecode *caller = parent->bytecode, *target;
    JSContext *ctx = caller->realm, *poll_ctx, *walk_ctx;
    JSValue *sp = state->sp, *original_argv, *argv, *owned, *vars, *stack;
    JSValue callee, receiver, original_func, original_this, target_func, target_this;
    unsigned op = *state->pc, argc, size, method, tail, depth = 0, count, committed = 0;
    size_t regular, extra, need;
    int result = 0;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_begin_c(state);
#endif
    unsigned mode = arguments_mode();
    if ((mode & (3 | 256)) != 1)
        goto done;
    if (!FRAME_CALL_FORWARD_MODE(caller))
        FRAME_CALL_FORWARD_MODE(caller) = getenv("QJS_DISABLE_FRAME_CALL_FORWARD")        ? 2
                                          : getenv("QJS_DISABLE_FRAME_CALL_FORWARD_LEAF") ? 5
                                                                                          : 1;
    if ((FRAME_CALL_FORWARD_MODE(caller) & 3) != 1)
        goto done;
    if (op >= OP_call0 && op <= OP_call3) {
        argc = op - OP_call0;
        size = 1;
        method = tail = 0;
    } else if (op == OP_call || op == OP_call_method || op == OP_tail_call ||
               op == OP_tail_call_method) {
        argc = get_u16(state->pc + 1);
        size = 3;
        method = op == OP_call_method || op == OP_tail_call_method;
        tail = op == OP_tail_call || op == OP_tail_call_method;
    } else
        goto done;
    if (argc + 1 + method > 0x7fff)
        goto done;
    original_argv = sp - argc;
    original_func = original_argv[-1];
    original_this = method ? original_argv[-2] : JS_UNDEFINED;
    callee = original_func;
    receiver = original_this;
    argv = original_argv;
    count = argc;
    while (js_frame_forward_is_call(callee)) {
        if (++depth > 64)
            goto done;
        callee = receiver;
        receiver = count ? argv[0] : JS_UNDEFINED;
        if (count) {
            count--;
            argv++;
        }
    }
    if (!depth || !(target = js_frame_arguments_forward_target(callee)))
        goto done;
    target_func = callee;
    target_this = receiver;
    unsigned owned_count = max_int((int)count, target->arg_count);
    regular = FRAME_HEADER_BYTES + sizeof(JSFrameArgumentsRecord) +
              sizeof(JSValue) * (owned_count + target->var_count + target->stack_size) +
              FRAME_CAPTURE_BYTES(target);
    extra = (size_t)depth * FRAME_FORWARD_BYTES;
    need = regular + extra;
    /* Do not allocate before the original logical C frames/poll are visible.
       A grow or pending interrupt uses the complete inherited protocol. */
    if (need > segment->capacity - segment->used || js_check_stack_overflow(rt, need))
        goto done;
    callee = original_func;
    receiver = original_this;
    argv = original_argv;
    unsigned native_argc = argc;
    poll_ctx = ctx;
    for (unsigned i = 0; i < depth; i++) {
        if (poll_ctx->interrupt_counter <= 1)
            goto rollback_polls;
        poll_ctx->interrupt_counter--;
        committed++;
        JSObject *function = JS_VALUE_GET_OBJ(callee);
        poll_ctx = function->u.cfunc.realm;
        callee = receiver;
        receiver = native_argc ? argv[0] : JS_UNDEFINED;
        if (native_argc) {
            native_argc--;
            argv++;
        }
    }
    if (poll_ctx->interrupt_counter <= 1)
        goto rollback_polls;
    /* There is now no allocation, JS, callback, failing operation or poll
       handler until the entire owned child and logical SF chain are ready. */
    child = (JSFrame *)(segment->data + segment->used);
    JSFrameArgumentsRecord *record =
        (JSFrameArgumentsRecord *)((uint8_t *)child + FRAME_HEADER_BYTES);
    record->argv = vc(argv);
    record->argc = count;
    record->signature = ARGUMENTS_SIGNATURE;
    owned = (JSValue *)(record + 1);
    for (unsigned i = 0; i < count; i++)
        owned[i] = js_dup(argv[i]);
    for (unsigned i = count; i < owned_count; i++)
        owned[i] = JS_UNDEFINED;
    vars = owned + owned_count;
    for (unsigned i = 0; i < target->var_count; i++)
        vars[i] = JS_UNDEFINED;
    stack = vars + target->var_count;
    child->segment = segment;
    child->frame_bytes = (uint32_t)regular;
    child->bytecode = target;
    child->this_value = target_this;
    child->owned_args = owned_count;
    child->pending = 0;
    child->saved_sp = stack;
    JSStackFrame *sf = &child->sf, *previous = &parent->sf;
    sf->cur_func = target_func;
    sf->arg_buf = owned;
    sf->var_buf = vars;
    sf->arg_count = owned_count;
    sf->var_ref_count = target->var_ref_count;
    sf->var_refs = target->var_ref_count ? (JSVarRef **)(stack + target->stack_size) : NULL;
    for (unsigned i = 0; i < target->var_ref_count; i++)
        sf->var_refs[i] = NULL;
    sf->is_strict_mode = target->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(sf);
    sf->cur_pc = NULL;
    sf->cur_sp = stack;
    FRAME_ROOT(child) = 2;
    ((unsigned char *)sf)[63] = 0;
    callee = original_func;
    receiver = original_this;
    argv = original_argv;
    native_argc = argc;
    for (unsigned i = 0; i < depth; i++) {
        JSStackFrame *logical =
            (JSStackFrame *)((uint8_t *)child + regular + i * FRAME_FORWARD_BYTES);
        /* A successful zero-argc wrapper is the last layer; target this
           is undefined and remains borrowed/immutable through logical pop. */
        JSValue *undefined_slot = &child->this_value;
        assert(native_argc || JS_IsUndefined(*undefined_slot));
        logical->prev_frame = previous;
        logical->cur_func = callee;
        logical->arg_buf = native_argc ? argv : undefined_slot;
        logical->arg_count = native_argc ? native_argc : 1;
        logical->var_buf = NULL;
        logical->var_refs = NULL;
        logical->var_ref_count = 0;
        logical->is_strict_mode = false;
        FRAME_CLEAR_STACK_AUX(logical);
        logical->cur_pc = NULL;
        logical->cur_sp = NULL;
        ((unsigned char *)logical)[62] = 0;
        ((unsigned char *)logical)[63] = FRAME_FORWARD_TAG;
        previous = logical;
        callee = receiver;
        receiver = native_argc ? argv[0] : JS_UNDEFINED;
        if (native_argc) {
            native_argc--;
            argv++;
        }
    }
    sf->prev_frame = previous;
    parent->sf.cur_pc = state->pc + size;
    parent->sf.cur_sp = sp;
    parent->saved_sp = sp;
    parent->pending = (argc + 1 + method) | (tail ? 0x8000 : 0);
    segment->used += need;
    state->used_bytes += need;
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_charge_stack(rt, need);
#endif
    poll_ctx->interrupt_counter--;
    state->frame = child;
    state->pc = target->byte_code_buf;
    state->sp = stack;
    rt->current_stack_frame = sf;
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    state->pushes++;
    state->copied_values += count;
    state->depth++;
    if (count < target->arg_count)
        state->arities++;
    if (state->depth > state->max_depth)
        state->max_depth = state->depth;
    if (state->used_bytes > state->peak_bytes)
        state->peak_bytes = state->used_bytes;
#endif
    arguments_count(2);
    if (mode & 4) {
        atomic_fetch_add_explicit(&JS_FrameArgumentsForwardStats[0], 1, memory_order_relaxed);
        atomic_fetch_add_explicit(&JS_FrameArgumentsForwardStats[1], depth, memory_order_relaxed);
    }
    result = 1;
    goto done;
rollback_polls:
    /* No callback has run and no operand, frame or owner has changed. Refund
       precisely the successful native-prefix decrements before full fallback. */
    callee = original_func;
    receiver = original_this;
    argv = original_argv;
    native_argc = argc;
    walk_ctx = ctx;
    for (unsigned i = 0; i < committed; i++) {
        walk_ctx->interrupt_counter++;
        walk_ctx = JS_VALUE_GET_OBJ(callee)->u.cfunc.realm;
        callee = receiver;
        receiver = native_argc ? argv[0] : JS_UNDEFINED;
        if (native_argc) {
            native_argc--;
            argv++;
        }
    }
done:
#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
    js_frame_finish_c(state);
#endif
    if (!result)
        return JS_FrameCallForwardNativeProbe(state);
    return result;
}
