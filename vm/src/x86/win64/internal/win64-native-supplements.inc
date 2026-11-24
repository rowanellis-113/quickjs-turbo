/* Source-level Windows x86-64 native ASM VM supplements.
 * Provides shared entry dispatch, CRT-portable getenv bridge for ASM islands,
 * the decoupled native Property IC / own-bytecode tail controller,
 * JS_FrameSlowDirectData, and 3-tier constructor specialization/continuation. */
#include <stdatomic.h>
#include "src/common/internal/turbo-config.h"

#if defined(_MSC_VER)
#define WIN64_THREAD_LOCAL __declspec(thread)
#else
#define WIN64_THREAD_LOCAL _Thread_local
#endif

unsigned char JS_FrameSlowDirectData = 0;

SHARED_CODE JSValue JS_FrameCallEntryDispatch(JSContext *ctx, JSValueConst func,
                                              JSValueConst this_value, JSValueConst new_target,
                                              int argc, JSValueConst *argv, int flags)
{
    return JS_FrameCallEntryShared(ctx, func, this_value, new_target, argc, argv, flags);
}

/* CRT-portable getenv bridge (works identically under /MD, /MT, MSVC, clang-cl). */
const char *JS_FrameGetenv(const char *name)
{
    return getenv(name);
}

static _Atomic(unsigned) win64_construct_policy = 0;

static SHARED_INLINE bool win64_construct_enabled(void)
{
    unsigned policy = atomic_load_explicit(&win64_construct_policy, memory_order_relaxed);
    if (unlikely(!policy)) {
        policy = getenv("QJS_DISABLE_FRAME_CONSTRUCT_CONTINUATION") ? 2 : 1;
        atomic_store_explicit(&win64_construct_policy, policy, memory_order_relaxed);
    }
    return policy == 1;
}

enum {
    WIN64_CTOR_SRC_ARG = 1,
    WIN64_CTOR_SRC_I32 = 2,
    WIN64_CTOR_SRC_NULL = 3,
    WIN64_CTOR_SRC_UNDEF = 4,
    WIN64_CTOR_SRC_BOOL = 5,
    WIN64_CTOR_SRC_CPOOL = 6,
};

#define WIN64_CTOR_THIS_TAG 99

typedef struct Win64FastCtorMeta {
    uintptr_t rt_id;
    uintptr_t callee_id;
    uintptr_t bc_id;
    uintptr_t callee_shape_id;
    uintptr_t proto_id;
    uintptr_t proto_shape_id;
    uintptr_t shape_id;
    uintptr_t init_fn_id;
    uintptr_t init_fn_shape_id;
    uintptr_t fn_proto_id;
    uintptr_t fn_proto_shape_id;
    uintptr_t apply_id;
    uint64_t epoch;
    uint32_t shape_hash;
    uint32_t proto_slot;
    uint32_t init_slot;
    uint32_t apply_slot;
    uint8_t tier; /* 1=leaf fields, 2=general shared child, 3=va_wrapper, 4=declined */
    uint8_t n_fields;
    uint8_t need_undef_varref0;
    uint8_t ret_this;
    uint8_t src_kind[16];
    int32_t src_imm[16];
    JSAtom atoms[16];
} Win64FastCtorMeta;

static WIN64_THREAD_LOCAL Win64FastCtorMeta win64_fast_ctor_cache[64];

static SHARED_INLINE bool win64_ctor_parse_val(JSFunctionBytecode *b, const uint8_t *buf,
                                               uint32_t len, uint32_t *pk, uint8_t *kind,
                                               int32_t *imm)
{
    uint32_t k = *pk;
    if (k >= len)
        return false;
    uint8_t op = buf[k];
    if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        *kind = WIN64_CTOR_SRC_ARG;
        *imm = op - OP_get_arg0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_get_arg) {
        if (k + 3 > len)
            return false;
        *kind = WIN64_CTOR_SRC_ARG;
        *imm = (int32_t)get_u16(buf + k + 1);
        *pk = k + 3;
        return true;
    }
    if (op >= OP_push_minus1 && op <= OP_push_7) {
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int32_t)op - OP_push_0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_i8) {
        if (k + 2 > len)
            return false;
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int8_t)buf[k + 1];
        *pk = k + 2;
        return true;
    }
    if (op == OP_push_i16) {
        if (k + 3 > len)
            return false;
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int16_t)get_u16(buf + k + 1);
        *pk = k + 3;
        return true;
    }
    if (op == OP_push_i32) {
        if (k + 5 > len)
            return false;
        *kind = WIN64_CTOR_SRC_I32;
        *imm = (int32_t)get_u32(buf + k + 1);
        *pk = k + 5;
        return true;
    }
    if (op == OP_null) {
        *kind = WIN64_CTOR_SRC_NULL;
        *imm = 0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_undefined) {
        *kind = WIN64_CTOR_SRC_UNDEF;
        *imm = 0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_false || op == OP_push_true) {
        *kind = WIN64_CTOR_SRC_BOOL;
        *imm = (op == OP_push_true);
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_const8 || op == OP_push_const) {
        uint32_t idx;
        if (op == OP_push_const8) {
            if (k + 2 > len)
                return false;
            idx = buf[k + 1];
            *pk = k + 2;
        } else {
            if (k + 5 > len)
                return false;
            idx = get_u32(buf + k + 1);
            *pk = k + 5;
        }
        if (idx >= b->cpool_count)
            return false;
        int tag = JS_VALUE_GET_TAG(b->cpool[idx]);
        if (tag != JS_TAG_INT && tag != JS_TAG_FLOAT64 && tag != JS_TAG_STRING &&
            tag != JS_TAG_BOOL && tag != JS_TAG_NULL && tag != JS_TAG_UNDEFINED)
            return false;
        *kind = WIN64_CTOR_SRC_CPOOL;
        *imm = (int32_t)idx;
        return true;
    }
    return false;
}

static SHARED_INLINE bool win64_ctor_proto_ok(JSObject *proto_obj, JSAtom atom)
{
    if (atom == JS_ATOM___proto__ || __JS_AtomIsTaggedInt(atom))
        return false;
    unsigned depth = 0;
    for (JSObject *cur = proto_obj; cur; cur = cur->shape->proto) {
        JSProperty *p2;
        JSShapeProperty *prs;
        if (++depth > 16 || cur->is_exotic)
            return false;
        cur->is_prototype = true;
        prs = find_own_property(&p2, cur, atom);
        if (prs)
            return (prs->flags & (JS_PROP_TMASK | JS_PROP_WRITABLE | JS_PROP_LENGTH)) ==
                   JS_PROP_WRITABLE;
    }
    return true;
}

static SHARED_INLINE int win64_ctor_to_bool(JSValueConst v)
{
    switch (JS_VALUE_GET_TAG(v)) {
    case JS_TAG_INT:
    case JS_TAG_BOOL:
        return JS_VALUE_GET_INT(v) != 0;
    case JS_TAG_NULL:
    case JS_TAG_UNDEFINED:
        return 0;
    case JS_TAG_FLOAT64: {
        double d = JS_VALUE_GET_FLOAT64(v);
        return !(d != d) && d != 0.0;
    }
    case JS_TAG_STRING:
        return JS_VALUE_GET_STRING(v)->len != 0;
    case JS_TAG_OBJECT:
        return !JS_VALUE_GET_OBJ(v)->is_HTMLDDA;
    default:
        return -1;
    }
}

static bool win64_ctor_eval_init(JSFunctionBytecode *ib, uint16_t incoming_argc,
                                 const JSValue *argv, JSObject *proto_obj, Win64FastCtorMeta *m,
                                 JSAtom *out_atoms, JSValue *out_vals, uint8_t *out_n,
                                 bool *hit_unsupported_op)
{
    const uint8_t *ibuf = ib->byte_code_buf;
    uint32_t len = ib->byte_code_len;
    *out_n = 0;
    *hit_unsupported_op = false;
    if (ib->arg_count > 8)
        return false;
    if (ib->var_count == 0) {
        if (len == 1 && ibuf[0] == OP_return_undef)
            return true;
        *hit_unsupported_op = true;
        return false;
    }
    if (ib->var_count != 1 || len < 3 || ibuf[0] != OP_push_this || ibuf[1] != OP_put_loc0) {
        *hit_unsupported_op = true;
        return false;
    }
    JSValue loc_args[8];
    for (uint32_t i = 0; i < ib->arg_count; i++)
        loc_args[i] = i < incoming_argc ? argv[i] : JS_UNDEFINED;
    JSValue eval_sp[16];
    int sp_top = 0;
    JSValue this_sentinel = JS_MKVAL(WIN64_CTOR_THIS_TAG, 0);
    uint32_t ip = 2;
    uint8_t n = 0;
    for (unsigned step = 0; step < 64; step++) {
        if (ip >= len) {
            *hit_unsupported_op = true;
            return false;
        }
        uint8_t op = ibuf[ip];
        switch (op) {
        case OP_return_undef:
            if (sp_top != 0) {
                *hit_unsupported_op = true;
                return false;
            }
            *out_n = n;
            return true;
        case OP_get_loc0:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = this_sentinel;
            ip += 1;
            break;
        case OP_get_arg0:
        case OP_get_arg1:
        case OP_get_arg2:
        case OP_get_arg3: {
            uint32_t idx = (uint32_t)(op - OP_get_arg0);
            if (idx >= ib->arg_count || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = loc_args[idx];
            ip += 1;
            break;
        }
        case OP_get_arg: {
            if (ip + 3 > len) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = get_u16(ibuf + ip + 1);
            if (idx >= ib->arg_count || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = loc_args[idx];
            ip += 3;
            break;
        }
        case OP_put_arg0:
        case OP_put_arg1:
        case OP_put_arg2:
        case OP_put_arg3: {
            uint32_t idx = (uint32_t)(op - OP_put_arg0);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[--sp_top];
            ip += 1;
            break;
        }
        case OP_put_arg: {
            if (ip + 3 > len) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = get_u16(ibuf + ip + 1);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[--sp_top];
            ip += 3;
            break;
        }
        case OP_set_arg0:
        case OP_set_arg1:
        case OP_set_arg2:
        case OP_set_arg3: {
            uint32_t idx = (uint32_t)(op - OP_set_arg0);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[sp_top - 1];
            ip += 1;
            break;
        }
        case OP_set_arg: {
            if (ip + 3 > len) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = get_u16(ibuf + ip + 1);
            if (idx >= ib->arg_count || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[sp_top - 1];
            ip += 3;
            break;
        }
        case OP_dup:
            if (sp_top < 1 || sp_top >= 16 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top] = eval_sp[sp_top - 1];
            sp_top++;
            ip += 1;
            break;
        case OP_drop:
            if (sp_top < 1) {
                *hit_unsupported_op = true;
                return false;
            }
            sp_top--;
            ip += 1;
            break;
        case OP_push_minus1:
        case OP_push_0:
        case OP_push_1:
        case OP_push_2:
        case OP_push_3:
        case OP_push_4:
        case OP_push_5:
        case OP_push_6:
        case OP_push_7:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int32_t)op - OP_push_0);
            ip += 1;
            break;
        case OP_push_i8:
            if (ip + 2 > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int8_t)ibuf[ip + 1]);
            ip += 2;
            break;
        case OP_push_i16:
            if (ip + 3 > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int16_t)get_u16(ibuf + ip + 1));
            ip += 3;
            break;
        case OP_push_i32:
            if (ip + 5 > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = js_int32((int32_t)get_u32(ibuf + ip + 1));
            ip += 5;
            break;
        case OP_undefined:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = JS_UNDEFINED;
            ip += 1;
            break;
        case OP_null:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = JS_NULL;
            ip += 1;
            break;
        case OP_push_false:
        case OP_push_true:
            if (sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = JS_MKVAL(JS_TAG_BOOL, op == OP_push_true);
            ip += 1;
            break;
        case OP_push_const8:
        case OP_push_const: {
            uint32_t ilen = (op == OP_push_const8) ? 2 : 5;
            if (ip + ilen > len || sp_top >= 16) {
                *hit_unsupported_op = true;
                return false;
            }
            uint32_t idx = (op == OP_push_const8) ? ibuf[ip + 1] : get_u32(ibuf + ip + 1);
            if (idx >= ib->cpool_count) {
                *hit_unsupported_op = true;
                return false;
            }
            int ctag = JS_VALUE_GET_TAG(ib->cpool[idx]);
            if (ctag != JS_TAG_INT && ctag != JS_TAG_FLOAT64 && ctag != JS_TAG_STRING &&
                ctag != JS_TAG_BOOL && ctag != JS_TAG_NULL && ctag != JS_TAG_UNDEFINED) {
                *hit_unsupported_op = true;
                return false;
            }
            eval_sp[sp_top++] = ib->cpool[idx];
            ip += ilen;
            break;
        }
        case OP_lnot: {
            if (sp_top < 1 || JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            int bval = win64_ctor_to_bool(eval_sp[sp_top - 1]);
            if (bval < 0)
                return false;
            eval_sp[sp_top - 1] = JS_MKVAL(JS_TAG_BOOL, !bval);
            ip += 1;
            break;
        }
        case OP_if_false8:
        case OP_if_true8:
        case OP_if_false:
        case OP_if_true: {
            bool is8 = (op == OP_if_false8 || op == OP_if_true8);
            bool want_true = (op == OP_if_true8 || op == OP_if_true);
            uint32_t ilen = is8 ? 2 : 5;
            if (ip + ilen > len || sp_top < 1 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            int bval = win64_ctor_to_bool(eval_sp[--sp_top]);
            if (bval < 0)
                return false;
            if ((bval != 0) == want_true) {
                int32_t disp = is8 ? (int8_t)ibuf[ip + 1] : (int32_t)get_u32(ibuf + ip + 1);
                int32_t next_ip = (int32_t)(ip + 1) + disp;
                if (next_ip < 2 || (uint32_t)next_ip >= len) {
                    *hit_unsupported_op = true;
                    return false;
                }
                ip = (uint32_t)next_ip;
            } else {
                ip += ilen;
            }
            break;
        }
        case OP_goto8:
        case OP_goto16:
        case OP_goto: {
            uint32_t ilen = (op == OP_goto8) ? 2 : (op == OP_goto16 ? 3 : 5);
            if (ip + ilen > len) {
                *hit_unsupported_op = true;
                return false;
            }
            int32_t disp = (op == OP_goto8) ? (int8_t)ibuf[ip + 1]
                                            : (op == OP_goto16 ? (int16_t)get_u16(ibuf + ip + 1)
                                                               : (int32_t)get_u32(ibuf + ip + 1));
            int32_t next_ip = (int32_t)(ip + 1) + disp;
            if (next_ip < 2 || (uint32_t)next_ip >= len) {
                *hit_unsupported_op = true;
                return false;
            }
            ip = (uint32_t)next_ip;
            break;
        }
        case OP_put_field: {
            if (ip + 5 > len || sp_top < 2 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 2]) != WIN64_CTOR_THIS_TAG ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == WIN64_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            JSValue val = eval_sp[--sp_top];
            sp_top--;
            JSAtom atom = get_u32(ibuf + ip + 1);
            bool updated_slot = false;
            for (uint8_t j = 0; j < n; j++) {
                if (out_atoms[j] == atom) {
                    out_vals[j] = val;
                    updated_slot = true;
                    break;
                }
            }
            if (!updated_slot) {
                if (n >= 16) {
                    *hit_unsupported_op = true;
                    return false;
                }
                if (!(m->n_fields != 0xFF && n < m->n_fields && m->atoms[n] == atom)) {
                    if (!win64_ctor_proto_ok(proto_obj, atom))
                        return false;
                }
                out_atoms[n] = atom;
                out_vals[n] = val;
                n++;
            }
            ip += 5;
            break;
        }
        default:
            *hit_unsupported_op = true;
            return false;
        }
    }
    *hit_unsupported_op = true;
    return false;
}

/* Borrowed shape lookup: verifies cached shape inside rt->shape_hash without holding
 * an owned refcount in TLS so runtime destruction never leaks shapes or atoms. */
static JSShape *win64_ctor_ensure_shape(JSContext *ctx, JSRuntime *rt, Win64FastCtorMeta *m,
                                        JSObject *proto_obj, uint8_t n_fields, const JSAtom *atoms)
{
    if (m->rt_id == (uintptr_t)rt && m->shape_id != 0) {
        uint32_t h = get_shape_hash(m->shape_hash, rt->shape_hash_bits);
        for (JSShape *p = rt->shape_hash[h]; p; p = p->shape_hash_next) {
            if ((uintptr_t)p == m->shape_id && p->hash == m->shape_hash && p->proto == proto_obj &&
                p->is_hashed && !p->deleted_prop_count && p->prop_count == n_fields) {
                bool match = true;
                JSShapeProperty *props = get_shape_prop(p);
                for (uint8_t f = 0; f < n_fields; f++) {
                    if (props[f].atom != atoms[f] || props[f].flags != JS_PROP_C_W_E) {
                        match = false;
                        break;
                    }
                }
                if (match)
                    return js_dup_shape(p);
            }
        }
    }
    JSShape *sh = find_hashed_shape_proto(rt, proto_obj);
    sh = sh ? js_dup_shape(sh) : js_new_shape(ctx, proto_obj);
    if (!sh)
        return NULL;
    for (uint8_t f = 0; f < n_fields; f++) {
        JSShape *next = find_hashed_shape_prop(rt, sh, atoms[f], JS_PROP_C_W_E);
        if (next) {
            JSShape *old_sh = sh;
            sh = js_dup_shape(next);
            js_free_shape(rt, old_sh);
        } else {
            if (JS_REF_COUNT(sh) != 1) {
                JSShape *clone = js_clone_shape(ctx, sh);
                if (!clone) {
                    js_free_shape(rt, sh);
                    return NULL;
                }
                clone->is_hashed = true;
                js_shape_hash_link(rt, clone);
                js_free_shape(rt, sh);
                sh = clone;
            }
            if (add_shape_property(ctx, &sh, NULL, atoms[f], JS_PROP_C_W_E)) {
                js_free_shape(rt, sh);
                return NULL;
            }
        }
    }
    m->rt_id = (uintptr_t)rt;
    m->shape_id = (uintptr_t)sh;
    m->shape_hash = sh->hash;
    return sh;
}

static bool win64_ctor_has_check_ctor(JSFunctionBytecode *b)
{
    const uint8_t *buf = b->byte_code_buf;
    for (int pos = 0; pos < b->byte_code_len; pos += js_frame_opcode_sizes[buf[pos]]) {
        if (buf[pos] == OP_check_ctor)
            return true;
    }
    return false;
}

int JS_FrameVarargsConstructCall(JSFrameRegisterState *state)
{
#ifndef QJS_PROPERTY_IC
    (void)state;
    return -1;
#else
    uint8_t *pc = state->pc;
    uint16_t incoming_argc = get_u16(pc + 1);
    if (!win64_construct_enabled() || incoming_argc > 32765)
        return -1;
    JSFrame *frame = state->frame;
    JSRuntime *rt = state->rt;
    JSContext *ctx = frame->bytecode->realm;
    if (FRAME_REGISTER_STATE(rt) != 1 || rt->dump_flags || rt->property_ic_mode != 1 ||
        !rt->property_ic_epoch || ctx->interrupt_counter <= 2)
        return -1;
    JSValue *sp = state->sp;
    JSValue *argv = sp - incoming_argc;
    JSValue func_obj = argv[-2];
    if (!JS_IsObject(func_obj) || !JS_IsObject(argv[-1]) ||
        JS_VALUE_GET_OBJ(func_obj) != JS_VALUE_GET_OBJ(argv[-1]))
        return -1;
    JSObject *callee = JS_VALUE_GET_OBJ(func_obj);
    if (callee->class_id != JS_CLASS_BYTECODE_FUNCTION || !callee->is_constructor ||
        callee->is_exotic)
        return -1;
    JSFunctionBytecode *b = callee->u.func.function_bytecode;
    if (b->is_derived_class_constructor || b->func_kind != JS_FUNC_NORMAL || b->realm != ctx)
        return -1;
    if (!FRAME_KIND(b) && !js_frame_validate(b))
        FRAME_KIND(b) = 2;
    bool is_kind1 = FRAME_SUPPORTED(b) != 0;
    bool is_va_wrapper =
        !is_kind1 && FRAME_KIND(b) == 2 && !rt->interrupt_handler && ctx->interrupt_counter > 4 &&
        b->byte_code_len == 21 && b->arg_count == 0 && b->var_count == 2 && b->var_ref_count == 0 &&
        b->closure_var_count == 0 && b->stack_size == 4 && b->byte_code_buf[0] == OP_push_this;
    if (!is_kind1 && !is_va_wrapper)
        return -1;

    uint32_t slot =
        (uint32_t)((((uintptr_t)callee >> 4) ^ ((uintptr_t)callee >> 10) ^ ((uintptr_t)b >> 4)) &
                   63u);
    Win64FastCtorMeta *m = &win64_fast_ctor_cache[slot];
    JSObject *proto_obj = NULL;
    JSFunctionBytecode *init_b = NULL;
    if (m->rt_id == (uintptr_t)rt && m->tier != 0 &&
        (is_va_wrapper ? (m->tier >= 3) : (m->tier <= 2 || m->tier == 4)) &&
        m->callee_id == (uintptr_t)callee && m->bc_id == (uintptr_t)b &&
        m->callee_shape_id == (uintptr_t)callee->shape && m->epoch == rt->property_ic_epoch) {
        JSValue pval = callee->prop[m->proto_slot].u.value;
        if (JS_IsObject(pval)) {
            JSObject *po = JS_VALUE_GET_OBJ(pval);
            if ((uintptr_t)po == m->proto_id && po->is_prototype && !po->is_exotic &&
                (uintptr_t)po->shape == m->proto_shape_id) {
                proto_obj = po;
            }
        }
    }
    if (proto_obj && is_va_wrapper) {
        if (m->tier == 4)
            return -1;
        JSValue iv = proto_obj->prop[m->init_slot].u.value;
        if (JS_IsObject(iv)) {
            JSObject *ifo = JS_VALUE_GET_OBJ(iv);
            if ((uintptr_t)ifo == m->init_fn_id && !ifo->is_exotic &&
                (uintptr_t)ifo->shape == m->init_fn_shape_id && ifo->shape->proto &&
                (uintptr_t)ifo->shape->proto == m->fn_proto_id && ifo->shape->proto->is_prototype &&
                !ifo->shape->proto->is_exotic &&
                (uintptr_t)ifo->shape->proto->shape == m->fn_proto_shape_id) {
                JSValue apv = ifo->shape->proto->prop[m->apply_slot].u.value;
                if (JS_IsObject(apv) && (uintptr_t)JS_VALUE_GET_OBJ(apv) == m->apply_id)
                    init_b = ifo->u.func.function_bytecode;
            }
        }
        if (!init_b)
            proto_obj = NULL;
    }
    if (!proto_obj) {
        JSProperty *pr = NULL;
        JSShapeProperty *ps = find_own_property(&pr, callee, JS_ATOM_prototype);
        if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL || !JS_IsObject(pr->u.value))
            return -1;
        proto_obj = JS_VALUE_GET_OBJ(pr->u.value);
        if (proto_obj->is_exotic || proto_obj->class_id != JS_CLASS_OBJECT)
            return -1;
        proto_obj->is_prototype = true;

        m->rt_id = (uintptr_t)rt;
        m->callee_id = (uintptr_t)callee;
        m->bc_id = (uintptr_t)b;
        m->callee_shape_id = (uintptr_t)callee->shape;
        m->proto_id = (uintptr_t)proto_obj;
        m->proto_shape_id = (uintptr_t)proto_obj->shape;
        m->shape_id = 0;
        m->shape_hash = 0;
        m->proto_slot = (uint32_t)(pr - callee->prop);
        m->epoch = rt->property_ic_epoch;
        m->init_fn_id = 0;
        m->init_fn_shape_id = 0;
        m->fn_proto_id = 0;
        m->fn_proto_shape_id = 0;
        m->apply_id = 0;
        m->init_slot = 0;
        m->apply_slot = 0;
        m->tier = 4;
        m->n_fields = 0;
        m->need_undef_varref0 = 0;
        m->ret_this = 0;

        const uint8_t *buf = b->byte_code_buf;
        uint32_t len = b->byte_code_len;
        if (is_va_wrapper) {
            if (buf[1] != OP_put_loc0 || buf[2] != OP_special_object ||
                (buf[3] != OP_SPECIAL_OBJECT_ARGUMENTS &&
                 buf[3] != OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS) ||
                buf[4] != OP_put_loc1 || buf[5] != OP_get_loc0 || buf[6] != OP_get_field ||
                buf[11] != OP_get_field2 || get_u32(buf + 12) != JS_ATOM_apply ||
                buf[16] != OP_get_loc0_loc1 || buf[17] != OP_call_method ||
                get_u16(buf + 18) != 2 || buf[20] != OP_return_undef) {
                return -1;
            }
            JSAtom init_atom = get_u32(buf + 7);
            JSProperty *init_pr = NULL, *own_apply = NULL, *proto_apply = NULL;
            JSShapeProperty *init_ps = find_own_property(&init_pr, proto_obj, init_atom);
            if (!init_ps || (init_ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                !JS_IsObject(init_pr->u.value)) {
                m->tier = 0;
                return -1;
            }
            JSObject *init_fn = JS_VALUE_GET_OBJ(init_pr->u.value);
            if (init_fn->class_id != JS_CLASS_BYTECODE_FUNCTION || init_fn->is_exotic ||
                find_own_property(&own_apply, init_fn, JS_ATOM_apply)) {
                m->tier = 0;
                return -1;
            }
            JSObject *fn_proto = init_fn->shape->proto;
            if (!fn_proto || fn_proto->is_exotic) {
                m->tier = 0;
                return -1;
            }
            JSShapeProperty *apply_ps = find_own_property(&proto_apply, fn_proto, JS_ATOM_apply);
            if (!apply_ps || (apply_ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                !JS_IsObject(proto_apply->u.value)) {
                m->tier = 0;
                return -1;
            }
            JSObject *apply_obj = JS_VALUE_GET_OBJ(proto_apply->u.value);
            if (apply_obj->class_id != JS_CLASS_C_FUNCTION ||
                apply_obj->u.cfunc.cproto != JS_CFUNC_generic_magic ||
                apply_obj->u.cfunc.magic != 0 || apply_obj->u.cfunc.length != 2 ||
                apply_obj->u.cfunc.realm != ctx ||
                apply_obj->u.cfunc.c_function.generic_magic != js_function_apply) {
                m->tier = 0;
                return -1;
            }
            init_b = init_fn->u.func.function_bytecode;
            if (!FRAME_KIND(init_b) && !js_frame_validate(init_b))
                FRAME_KIND(init_b) = 2;
            if (init_b->realm != ctx || !(FRAME_KIND(init_b) & 1) ||
                init_b->func_kind != JS_FUNC_NORMAL || init_b->is_derived_class_constructor ||
                init_b->arg_count > 8 || init_b->var_count > 1 || init_b->var_ref_count != 0 ||
                init_b->closure_var_count != 0 || init_b->stack_size > 8 ||
                init_b->byte_code_len > 128) {
                m->tier = 4;
                return -1;
            }
            fn_proto->is_prototype = true;
            m->init_fn_id = (uintptr_t)init_fn;
            m->init_fn_shape_id = (uintptr_t)init_fn->shape;
            m->fn_proto_id = (uintptr_t)fn_proto;
            m->fn_proto_shape_id = (uintptr_t)fn_proto->shape;
            m->apply_id = (uintptr_t)apply_obj;
            m->init_slot = (uint32_t)(init_pr - proto_obj->prop);
            m->apply_slot = (uint32_t)(proto_apply - fn_proto->prop);
            m->tier = 3;
            m->n_fields = 0xFF;
        } else if (len == 1 && buf[0] == OP_return_undef && b->var_count == 0 &&
                   b->var_ref_count == 0 && b->closure_var_count == 0) {
            m->tier = 1;
        } else if (b->var_count == 1 && b->var_ref_count == 0 && len >= 3 &&
                   buf[0] == OP_push_this && buf[1] == OP_put_loc0) {
            uint32_t k = 2;
            uint8_t n_f = 0, need_vr0 = 0, ret_this = 0;
            bool ok = true;
            if (b->closure_var_count == 1) {
                if (len >= 15 && buf[2] == OP_check_ctor && buf[3] == OP_get_var_ref_check &&
                    buf[4] == 0 && buf[5] == 0 && buf[6] == OP_dup && buf[7] == OP_if_false8 &&
                    buf[8] == 6 && buf[9] == OP_get_loc0 && buf[10] == OP_swap &&
                    buf[11] == OP_call_method && buf[12] == 0 && buf[13] == 0 &&
                    buf[14] == OP_drop) {
                    need_vr0 = 1;
                    k = 15;
                } else {
                    ok = false;
                }
            } else if (b->closure_var_count == 0) {
                if (k < len && buf[k] == OP_check_ctor)
                    k++;
            } else {
                ok = false;
            }
            while (ok && k < len && buf[k] == OP_get_loc0) {
                if (k + 2 == len && buf[k + 1] == OP_return) {
                    ret_this = 1;
                    k += 2;
                    break;
                }
                if (n_f >= 16) {
                    ok = false;
                    break;
                }
                k++;
                uint8_t kind = 0;
                int32_t imm = 0;
                if (!win64_ctor_parse_val(b, buf, len, &k, &kind, &imm) || k + 5 > len ||
                    buf[k] != OP_put_field) {
                    ok = false;
                    break;
                }
                JSAtom atom = get_u32(buf + k + 1);
                k += 5;
                for (uint8_t j = 0; j < n_f; j++) {
                    if (m->atoms[j] == atom) {
                        ok = false;
                        break;
                    }
                }
                if (!ok || !win64_ctor_proto_ok(proto_obj, atom)) {
                    ok = false;
                    break;
                }
                m->src_kind[n_f] = kind;
                m->src_imm[n_f] = imm;
                m->atoms[n_f] = atom;
                n_f++;
            }
            if (ok && ((ret_this && k == len) ||
                       (!ret_this && k + 1 == len && buf[k] == OP_return_undef))) {
                m->tier = 1;
                m->n_fields = n_f;
                m->need_undef_varref0 = need_vr0;
                m->ret_this = ret_this;
            }
        }
        if (m->tier == 4 && is_kind1) {
            m->tier = win64_ctor_has_check_ctor(b) ? 4 : 2;
        }
    }

    /* Tier 3: Prototype.js 21-byte varargs wrapper around pure this.initialize(...) */
    if (is_va_wrapper) {
        if (m->tier != 3 || !init_b)
            return -1;
        JSAtom out_atoms[16];
        JSValue out_vals[16];
        uint8_t n_f = 0;
        bool hit_unsup = false;
        if (!win64_ctor_eval_init(init_b, incoming_argc, argv, proto_obj, m, out_atoms, out_vals,
                                  &n_f, &hit_unsup)) {
            if (hit_unsup)
                m->tier = 4;
            return -1;
        }
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc + 3;
        state->sp = sp;
        js_frame_begin_c(state);
        if (m->n_fields == 0xFF) {
            m->n_fields = n_f;
            if (n_f)
                memcpy(m->atoms, out_atoms, (size_t)n_f * sizeof(JSAtom));
        }
        JSShape *sh = win64_ctor_ensure_shape(ctx, rt, m, proto_obj, n_f, out_atoms);
        if (!sh) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSProperty props[16];
        props[0].u.value = JS_UNDEFINED;
        for (unsigned f = 0; f < n_f; f++)
            props[f].u.value = js_dup(out_vals[f]);
        JSValue this_obj = JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, props);
        if (JS_IsException(this_obj)) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter -= 4;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        argv[-1] = JS_UNDEFINED;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        JS_FreeValue(ctx, old_f0);
        JS_FreeValue(ctx, old_f1);
        for (int i = 0; i < incoming_argc; i++) {
            JSValue a = argv[i];
            argv[i] = JS_UNDEFINED;
            JS_FreeValue(ctx, a);
        }
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 0;
    }

    /* Tier 1: Direct leaf constructor object materialization */
    if (m->tier == 1 &&
        (!m->need_undef_varref0 || (callee->u.func.var_refs && callee->u.func.var_refs[0] &&
                                    JS_IsUndefined(*callee->u.func.var_refs[0]->pvalue)))) {
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc + 3;
        state->sp = sp;
        js_frame_begin_c(state);
        JSShape *sh = win64_ctor_ensure_shape(ctx, rt, m, proto_obj, m->n_fields, m->atoms);
        if (!sh) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSProperty props[16];
        props[0].u.value = JS_UNDEFINED;
        for (unsigned f = 0; f < m->n_fields; f++) {
            JSValue v;
            switch (m->src_kind[f]) {
            case WIN64_CTOR_SRC_ARG:
                v = (uint32_t)m->src_imm[f] < incoming_argc ? js_dup(argv[m->src_imm[f]])
                                                            : JS_UNDEFINED;
                break;
            case WIN64_CTOR_SRC_I32:
                v = js_int32(m->src_imm[f]);
                break;
            case WIN64_CTOR_SRC_NULL:
                v = JS_NULL;
                break;
            case WIN64_CTOR_SRC_UNDEF:
                v = JS_UNDEFINED;
                break;
            case WIN64_CTOR_SRC_BOOL:
                v = JS_MKVAL(JS_TAG_BOOL, m->src_imm[f]);
                break;
            default:
                v = js_dup(b->cpool[m->src_imm[f]]);
                break;
            }
            props[f].u.value = v;
        }
        JSValue this_obj = JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, props);
        if (JS_IsException(this_obj)) {
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter -= 2;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        argv[-1] = JS_UNDEFINED;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        JS_FreeValue(ctx, old_f0);
        JS_FreeValue(ctx, old_f1);
        for (int i = 0; i < incoming_argc; i++) {
            JSValue a = argv[i];
            argv[i] = JS_UNDEFINED;
            JS_FreeValue(ctx, a);
        }
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 0;
    }

    /* Tier 2: General ordinary bytecode constructor via shared-segment ASM execution */
    if (m->tier != 2 || !is_kind1 || !js_frame_shared_enabled(rt) ||
        unlikely(js_check_stack_overflow(rt, 4096)))
        return -1;

    frame->saved_sp = sp;
    frame->sf.cur_sp = sp;
    frame->sf.cur_pc = pc + 3;
    state->pc = pc + 3;
    state->sp = sp;
    js_frame_begin_c(state);
    JSShape *sh = win64_ctor_ensure_shape(ctx, rt, m, proto_obj, 0, NULL);
    if (!sh) {
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    JSProperty dummy_prop;
    dummy_prop.u.value = JS_UNDEFINED;
    JSValue this_obj = JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, &dummy_prop);
    if (JS_IsException(this_obj)) {
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }

    /* Root this_obj in argv[-2]; argv[-1] still roots callee across the shared call. */
    JSValue old_m2 = argv[-2];
    argv[-2] = this_obj;
    JS_FreeValue(ctx, old_m2);
    js_frame_finish_c(state);

    JSFrameSharedAnchor **slot_ptr = js_frame_shared_slot(), anchor;
    anchor.prev = *slot_ptr;
    anchor.state = state;
    anchor.kind = 0;
    unsigned char prev_active = FRAME_SHARED_ACTIVE(rt);
    FRAME_SHARED_BITS(rt) |= 4;
    *slot_ptr = &anchor;
    JSValue res = js_frame_run_shared(ctx, argv[-1], argv[-2], incoming_argc, (JSValueConst *)argv,
                                      0, b, &anchor);
    *slot_ptr = anchor.prev;
    FRAME_SHARED_BITS(rt) = (FRAME_SHARED_BITS(rt) & ~4) | prev_active;

    js_frame_begin_c(state);
    JSValue constructed = argv[-2];
    JSValue old_callee = argv[-1];
    argv[-2] = JS_UNDEFINED;
    argv[-1] = JS_UNDEFINED;
    JS_FreeValue(ctx, old_callee);
    for (int i = 0; i < incoming_argc; i++) {
        JSValue a = argv[i];
        argv[i] = JS_UNDEFINED;
        JS_FreeValue(ctx, a);
    }
    if (JS_IsException(res)) {
        JS_FreeValue(ctx, constructed);
        state->sp = argv - 2;
        frame->saved_sp = argv - 2;
        frame->sf.cur_sp = argv - 2;
        state->pc = pc + 3;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameInterpSlow(state);
    }
    if (JS_IsObject(res)) {
        JS_FreeValue(ctx, constructed);
        constructed = res;
    } else {
        JS_FreeValue(ctx, res);
    }
    argv[-2] = constructed;
    JSValue *new_sp = argv - 1;
    state->sp = new_sp;
    frame->saved_sp = new_sp;
    frame->sf.cur_sp = new_sp;
    state->pc = pc + 3;
    if (!FRAME_CHECKPOINT(frame))
        frame->sf.cur_sp = NULL;
    js_frame_finish_c(state);
    return 0;
#endif
}

/* Native Property IC & own-bytecode control block (80-byte ABI).
 * Byte 0: tail mode (1 = tail ON, 2 = OFF, 4 = PIC-only no tail)
 * Byte 5 (reserved[3]): PIC dispatch active (1 = native PIC ON, 2 = OFF) */
struct JSFrameOwnBytecodeState {
    unsigned char mode;
    unsigned char initialized;
    unsigned char reserved[6];
    uint64_t counts[9];
};

struct JSFrameOwnBytecodeState JS_FrameOwnBytecodeData = {0};

static void qjs_win64_own_bytecode_apply_mode(unsigned char mode)
{
    JS_FrameOwnBytecodeData.mode = mode;
    JS_FrameOwnBytecodeData.reserved[3] = (mode == 1 || mode == 4) ? 1 : 2;
    JS_FrameOwnBytecodeData.initialized = 1;
}

static void qjs_win64_own_bytecode_set_tail(int enabled)
{
#ifdef QJS_PROPERTY_IC
    /* Win64 source-level VM uses PIC-only mode (zero tail copy overhead) when
     * Property IC is enabled, regardless of tail toggle, unless PIC is disabled. */
    (void)enabled;
    int pic_disabled = (qjs_turbo_default_property_ic_mode() != 1);
    qjs_win64_own_bytecode_apply_mode(pic_disabled ? 2 : 4);
#else
    (void)enabled;
    qjs_win64_own_bytecode_apply_mode(2);
#endif
}

static int qjs_win64_own_bytecode_tail_active(void)
{
    return JS_FrameOwnBytecodeData.mode == 1 ? 1 : 0;
}

static void qjs_win64_own_bytecode_init(void)
{
    if (!JS_FrameOwnBytecodeData.initialized) {
#ifdef QJS_PROPERTY_IC
        int pic_disabled = (qjs_turbo_default_property_ic_mode() != 1);
        qjs_win64_own_bytecode_apply_mode(pic_disabled ? 2 : 4);
#else
        qjs_win64_own_bytecode_apply_mode(2);
#endif
    }
    qjs_turbo_register_own_bytecode_hooks(qjs_win64_own_bytecode_set_tail,
                                          qjs_win64_own_bytecode_tail_active);
}

#if defined(_MSC_VER)
#pragma section(".CRT$XCU", read)
__declspec(allocate(".CRT$XCU")) void (*const qjs_win64_own_bytecode_ctor)(void) =
    qjs_win64_own_bytecode_init;
#pragma comment(linker, "/include:qjs_win64_own_bytecode_ctor")
#else
__attribute__((constructor)) static void qjs_win64_own_bytecode_ctor(void)
{
    qjs_win64_own_bytecode_init();
}
#endif
