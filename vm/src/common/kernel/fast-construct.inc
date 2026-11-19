/* Tier-1 inline constructor execution and shape cache for OP_call_constructor. */
enum {
    FAST_CTOR_SRC_ARG = 1,
    FAST_CTOR_SRC_I32 = 2,
    FAST_CTOR_SRC_NULL = 3,
    FAST_CTOR_SRC_UNDEF = 4,
    FAST_CTOR_SRC_BOOL = 5,
    FAST_CTOR_SRC_CPOOL = 6,
};

typedef struct FastCtorMeta {
    uintptr_t callee_id;
    uintptr_t bc_id;
    uintptr_t callee_shape_id;
    uintptr_t proto_id;
    uintptr_t proto_shape_id;
    uintptr_t init_fn_id;
    uintptr_t init_fn_shape_id;
    uintptr_t fn_proto_id;
    uintptr_t fn_proto_shape_id;
    uintptr_t apply_id;
    uint64_t epoch;
    uint32_t proto_slot;
    uint32_t init_slot;
    uint32_t apply_slot;
    uint8_t tier;
    uint8_t n_fields;
    uint8_t need_undef_varref0;
    uint8_t ret_this;
    uint8_t src_kind[16];
    int32_t src_imm[16];
    JSAtom atoms[16];
} FastCtorMeta;

static FastCtorMeta fast_ctor_cache[64];

extern int JS_LinuxVirtualArgumentsFastOk(void);
extern int JS_FrameArgumentsConstructFastOk(void);

static inline OrdSite *ord_ctor_site(JSFrameRegisterState *state, unsigned mode, uintptr_t key,
                                     uintptr_t bc)
{
    if (!(mode & 1) || (mode & 16) || state->iterator_checkpoint_depth || state->exception_pending)
        return NULL;
    if (ORD_ACTIVE(state) == 0) {
        if (ORD_LAZY(state) != 1 || (mode & 512))
            return NULL;
        OrdLazy *lazy = (OrdLazy *)state->cache_next;
        OrdScope *sc = js_malloc_rt(state->rt, sizeof(*sc));
        if (!sc) {
            ORD_LAZY(state) = 3;
            return NULL;
        }
        memset(sc, 0, sizeof(*sc));
        memcpy(sc->legacy.cache_next, lazy->cache_next, 8);
        lazy->scope = sc;
        state->cache_next = sc->legacy.cache_next;
        ORD_ACTIVE(state) = 4;
        ORD_LAZY(state) = 2;
    } else if (ORD_ACTIVE(state) != 4) {
        return NULL;
    }
    OrdScope *scope = (OrdScope *)state->cache_next;
    unsigned h = (key ^ (key >> 5) ^ (key >> 11)) & 63;
    for (OrdRecord *r = scope->bucket[h]; r; r = r->next) {
        if (r->site.site == key && r->site.bytecode == bc)
            return &r->site;
    }
    OrdChunk *c = scope->chunks;
    if (!c || c->used == 16) {
        if (scope->count == 16)
            return NULL;
        c = js_malloc_rt(state->rt, sizeof(*c));
        if (!c)
            return NULL;
        memset(c, 0, sizeof(*c));
        c->next = scope->chunks;
        scope->chunks = c;
        scope->count++;
    }
    OrdRecord *r = &c->records[c->used++];
    r->site.site = key;
    r->site.bytecode = bc;
    r->next = scope->bucket[h];
    scope->bucket[h] = r;
    return &r->site;
}

static inline bool fast_ctor_parse_val(JSFunctionBytecode *b, const uint8_t *buf, uint32_t len,
                                       uint32_t *pk, uint8_t *kind, int32_t *imm)
{
    uint32_t k = *pk;
    if (k >= len)
        return false;
    uint8_t op = buf[k];
    if (op >= OP_get_arg0 && op <= OP_get_arg3) {
        *kind = FAST_CTOR_SRC_ARG;
        *imm = op - OP_get_arg0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_get_arg) {
        if (k + 3 > len)
            return false;
        *kind = FAST_CTOR_SRC_ARG;
        *imm = (int32_t)get_u16(buf + k + 1);
        *pk = k + 3;
        return true;
    }
    if (op >= OP_push_minus1 && op <= OP_push_7) {
        *kind = FAST_CTOR_SRC_I32;
        *imm = (int32_t)op - OP_push_0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_i8) {
        if (k + 2 > len)
            return false;
        *kind = FAST_CTOR_SRC_I32;
        *imm = (int8_t)buf[k + 1];
        *pk = k + 2;
        return true;
    }
    if (op == OP_push_i16) {
        if (k + 3 > len)
            return false;
        *kind = FAST_CTOR_SRC_I32;
        *imm = (int16_t)get_u16(buf + k + 1);
        *pk = k + 3;
        return true;
    }
    if (op == OP_push_i32) {
        if (k + 5 > len)
            return false;
        *kind = FAST_CTOR_SRC_I32;
        *imm = (int32_t)get_u32(buf + k + 1);
        *pk = k + 5;
        return true;
    }
    if (op == OP_null) {
        *kind = FAST_CTOR_SRC_NULL;
        *imm = 0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_undefined) {
        *kind = FAST_CTOR_SRC_UNDEF;
        *imm = 0;
        *pk = k + 1;
        return true;
    }
    if (op == OP_push_false || op == OP_push_true) {
        *kind = FAST_CTOR_SRC_BOOL;
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
        *kind = FAST_CTOR_SRC_CPOOL;
        *imm = (int32_t)idx;
        return true;
    }
    return false;
}

#define FAST_CTOR_THIS_TAG 99

static inline bool fast_ctor_proto_ok(JSObject *proto_obj, JSAtom atom)
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

static inline int fast_ctor_to_bool(JSValueConst v)
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
        return !isnan(d) && d != 0.0;
    }
    case JS_TAG_STRING:
        return JS_VALUE_GET_STRING(v)->len != 0;
    case JS_TAG_OBJECT:
        return !JS_VALUE_GET_OBJ(v)->is_HTMLDDA;
    default:
        return -1;
    }
}

static bool fast_ctor_eval_init(JSFunctionBytecode *ib, uint16_t incoming_argc, const JSValue *argv,
                                JSObject *proto_obj, FastCtorMeta *m, JSAtom *out_atoms,
                                JSValue *out_vals, uint8_t *out_n, bool *hit_unsupported_op)
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
    JSValue this_sentinel = JS_MKVAL(FAST_CTOR_THIS_TAG, 0);
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
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
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
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
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
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
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
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            loc_args[idx] = eval_sp[sp_top - 1];
            ip += 3;
            break;
        }
        case OP_dup:
            if (sp_top < 1 || sp_top >= 16 ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
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
            if (sp_top < 1 || JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            int bval = fast_ctor_to_bool(eval_sp[sp_top - 1]);
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
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
                *hit_unsupported_op = true;
                return false;
            }
            int bval = fast_ctor_to_bool(eval_sp[--sp_top]);
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
                JS_VALUE_GET_TAG(eval_sp[sp_top - 2]) != FAST_CTOR_THIS_TAG ||
                JS_VALUE_GET_TAG(eval_sp[sp_top - 1]) == FAST_CTOR_THIS_TAG) {
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
                    if (!fast_ctor_proto_ok(proto_obj, atom))
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

static inline JSShape *fast_ctor_ensure_shape(JSContext *ctx, JSRuntime *rt, OrdSite *site,
                                              JSObject *proto_obj, uint8_t n_fields,
                                              const JSAtom *atoms)
{
    JSShape *sh = site->new_shape;
    if (sh && sh->proto == proto_obj && sh->is_hashed && !sh->deleted_prop_count &&
        sh->prop_count == n_fields) {
        bool match = true;
        for (uint8_t f = 0; f < n_fields; f++) {
            if (sh->prop[f].atom != atoms[f] || sh->prop[f].flags != JS_PROP_C_W_E) {
                match = false;
                break;
            }
        }
        if (match)
            return sh;
    }
    sh = find_hashed_shape_proto(rt, proto_obj);
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
            if (sh->header.ref_count != 1) {
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
    ord_release(rt, site->new_shape);
    site->new_shape = sh;
    return sh;
}

__attribute__((visibility("hidden"), section(".text.qjs_frame"), noipa)) int
JS_FastConstructCall(JSFrameRegisterState *state)
{
    uint8_t *pc = state->pc;
    uint16_t incoming_argc = get_u16(pc + 1);
    if (!js_frame_construct_enabled() || incoming_argc > 32765)
        return JS_FrameInterpProperty_call_constructor(state);
    JSFrame *frame = state->frame;
    JSRuntime *rt = state->rt;
    JSContext *ctx = frame->bytecode->realm;
    JSValue *sp = state->sp;
    JSValue *argv = sp - incoming_argc;
    JSValue func_obj = argv[-2];
    if (!JS_IsObject(func_obj) || !JS_IsObject(argv[-1]) ||
        JS_VALUE_GET_OBJ(func_obj) != JS_VALUE_GET_OBJ(argv[-1]))
        return JS_FrameInterpProperty_call_constructor(state);
    JSObject *callee = JS_VALUE_GET_OBJ(func_obj);
    if (callee->class_id != JS_CLASS_BYTECODE_FUNCTION || !callee->is_constructor ||
        callee->is_exotic)
        return JS_FrameInterpProperty_call_constructor(state);
    JSFunctionBytecode *b = callee->u.func.function_bytecode;
    if (b->is_derived_class_constructor || b->func_kind != JS_FUNC_NORMAL || b->realm != ctx)
        return JS_FrameInterpProperty_call_constructor(state);
    bool is_kind1 = (FRAME_KIND(b) & 1) != 0;
    bool is_va_wrapper = !is_kind1 && FRAME_KIND(b) == 2 && FRAME_ITERATOR_KIND(b) == 128 &&
                         !rt->interrupt_handler && ctx->interrupt_counter > 4 &&
                         b->byte_code_len == 21 && JS_FrameArgumentsConstructFastOk() &&
                         JS_LinuxVirtualArgumentsFastOk();
    if (!is_kind1 && !is_va_wrapper)
        return JS_FrameInterpProperty_call_constructor(state);
    if (FRAME_REGISTER_STATE(rt) != 1 || rt->dump_flags || rt->property_ic_mode != 1 ||
        !rt->property_ic_epoch || ctx->interrupt_counter <= 2 || state->iterator_checkpoint_depth ||
        !(ORD_ACTIVE(state) == 4 || (ORD_ACTIVE(state) == 0 && ORD_LAZY(state) == 1)))
        return JS_FrameInterpProperty_call_constructor(state);

    unsigned mode = atomic_load_explicit(&JS_FrameOrdinaryLiteralMode, memory_order_relaxed);
    if (!mode || !(mode & 1) || (mode & 16))
        return JS_FrameInterpProperty_call_constructor(state);

    uint32_t slot =
        (uint32_t)((((uintptr_t)callee >> 4) ^ ((uintptr_t)callee >> 10) ^ ((uintptr_t)b >> 4)) &
                   63u);
    FastCtorMeta *m = &fast_ctor_cache[slot];
    JSObject *proto_obj = NULL;
    JSFunctionBytecode *init_b = NULL;
    if (m->tier != 0 && (is_va_wrapper ? (m->tier >= 3) : (m->tier <= 2)) &&
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
            return JS_FrameInterpProperty_call_constructor(state);
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
            return JS_FrameInterpProperty_call_constructor(state);
        proto_obj = JS_VALUE_GET_OBJ(pr->u.value);
        if (proto_obj->is_exotic || proto_obj->class_id != JS_CLASS_OBJECT)
            return JS_FrameInterpProperty_call_constructor(state);
        proto_obj->is_prototype = true;

        m->callee_id = (uintptr_t)callee;
        m->bc_id = (uintptr_t)b;
        m->callee_shape_id = (uintptr_t)callee->shape;
        m->proto_id = (uintptr_t)proto_obj;
        m->proto_shape_id = (uintptr_t)proto_obj->shape;
        m->proto_slot = (uint32_t)(pr - callee->prop);
        m->epoch = rt->property_ic_epoch;
        m->init_fn_id = 0;
        m->init_fn_shape_id = 0;
        m->fn_proto_id = 0;
        m->fn_proto_shape_id = 0;
        m->apply_id = 0;
        m->init_slot = 0;
        m->apply_slot = 0;
        m->tier = is_va_wrapper ? 4 : 2;
        m->n_fields = 0;
        m->need_undef_varref0 = 0;
        m->ret_this = 0;

        const uint8_t *buf = b->byte_code_buf;
        uint32_t len = b->byte_code_len;
        if (is_va_wrapper) {
            if (b->arg_count != 0 || b->var_count != 2 || b->var_ref_count != 0 ||
                b->closure_var_count != 0 || b->stack_size != 4 || buf[0] != OP_push_this ||
                buf[1] != OP_put_loc0 || buf[2] != OP_special_object ||
                (buf[3] != OP_SPECIAL_OBJECT_ARGUMENTS &&
                 buf[3] != OP_SPECIAL_OBJECT_MAPPED_ARGUMENTS) ||
                buf[4] != OP_put_loc1 || buf[5] != OP_get_loc0 || buf[6] != OP_get_field ||
                buf[11] != OP_get_field2 || get_u32(buf + 12) != JS_ATOM_apply ||
                buf[16] != OP_get_loc0_loc1 || buf[17] != OP_call_method ||
                get_u16(buf + 18) != 2 || buf[20] != OP_return_undef) {
                return JS_FrameInterpProperty_call_constructor(state);
            }
            JSAtom init_atom = get_u32(buf + 7);
            JSProperty *init_pr = NULL, *own_apply = NULL, *proto_apply = NULL;
            JSShapeProperty *init_ps = find_own_property(&init_pr, proto_obj, init_atom);
            if (!init_ps || (init_ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                !JS_IsObject(init_pr->u.value)) {
                m->tier = 0;
                return JS_FrameInterpProperty_call_constructor(state);
            }
            JSObject *init_fn = JS_VALUE_GET_OBJ(init_pr->u.value);
            if (init_fn->class_id != JS_CLASS_BYTECODE_FUNCTION || init_fn->is_exotic ||
                find_own_property(&own_apply, init_fn, JS_ATOM_apply)) {
                m->tier = 0;
                return JS_FrameInterpProperty_call_constructor(state);
            }
            JSObject *fn_proto = init_fn->shape->proto;
            if (!fn_proto || fn_proto->is_exotic) {
                m->tier = 0;
                return JS_FrameInterpProperty_call_constructor(state);
            }
            JSShapeProperty *apply_ps = find_own_property(&proto_apply, fn_proto, JS_ATOM_apply);
            if (!apply_ps || (apply_ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                !JS_IsObject(proto_apply->u.value)) {
                m->tier = 0;
                return JS_FrameInterpProperty_call_constructor(state);
            }
            JSObject *apply_obj = JS_VALUE_GET_OBJ(proto_apply->u.value);
            if (apply_obj->class_id != JS_CLASS_C_FUNCTION ||
                apply_obj->u.cfunc.cproto != JS_CFUNC_generic_magic ||
                apply_obj->u.cfunc.magic != 0 || apply_obj->u.cfunc.length != 2 ||
                apply_obj->u.cfunc.realm != ctx ||
                apply_obj->u.cfunc.c_function.generic_magic != js_function_apply) {
                m->tier = 0;
                return JS_FrameInterpProperty_call_constructor(state);
            }
            init_b = init_fn->u.func.function_bytecode;
            if (FRAME_KIND(init_b) == 0) {
                m->tier = 0;
                return JS_FrameInterpProperty_call_constructor(state);
            }
            if (init_b->realm != ctx || !(FRAME_KIND(init_b) & 1) ||
                init_b->func_kind != JS_FUNC_NORMAL || init_b->is_derived_class_constructor ||
                init_b->arg_count > 8 || init_b->var_count > 1 || init_b->var_ref_count != 0 ||
                init_b->closure_var_count != 0 || init_b->stack_size > 8 ||
                init_b->byte_code_len > 128) {
                m->tier = 4;
                return JS_FrameInterpProperty_call_constructor(state);
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
                if (!fast_ctor_parse_val(b, buf, len, &k, &kind, &imm) || k + 5 > len ||
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
                if (!ok || !fast_ctor_proto_ok(proto_obj, atom)) {
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
    }

    if (is_va_wrapper) {
        if (m->tier != 3 || !init_b)
            return JS_FrameInterpProperty_call_constructor(state);
        JSAtom out_atoms[16];
        JSValue out_vals[16];
        uint8_t n_f = 0;
        bool hit_unsup = false;
        if (!fast_ctor_eval_init(init_b, incoming_argc, argv, proto_obj, m, out_atoms, out_vals,
                                 &n_f, &hit_unsup)) {
            if (hit_unsup)
                m->tier = 4;
            return JS_FrameInterpProperty_call_constructor(state);
        }
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc;
        state->sp = sp;
        js_frame_begin_c(state);
        OrdSite *site = ord_ctor_site(state, mode, ((uintptr_t)callee) | 1u, ~((uintptr_t)b));
        if (!site) {
            if (!FRAME_CHECKPOINT(frame))
                frame->sf.cur_sp = NULL;
            js_frame_finish_c(state);
            return JS_FrameInterpProperty_call_constructor(state);
        }
        if (m->n_fields == 0xFF) {
            m->n_fields = n_f;
            if (n_f)
                memcpy(m->atoms, out_atoms, (size_t)n_f * sizeof(JSAtom));
        }
        JSShape *sh = fast_ctor_ensure_shape(ctx, rt, site, proto_obj, n_f, out_atoms);
        if (!sh) {
            state->pc = pc + 3;
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSProperty props[16];
        props[0].u.value = JS_UNDEFINED;
        for (unsigned f = 0; f < n_f; f++)
            props[f].u.value = js_dup(out_vals[f]);
        JSValue this_obj = JS_NewObjectFromShape(ctx, js_dup_shape(sh), JS_CLASS_OBJECT, props);
        if (JS_IsException(this_obj)) {
            state->pc = pc + 3;
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter -= 4;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        if (callee->header.ref_count > 2) {
            callee->header.ref_count -= 2;
        } else {
            JS_FreeValue(ctx, old_f0);
            JS_FreeValue(ctx, old_f1);
        }
        for (int i = 0; i < incoming_argc; i++)
            JS_FreeValue(ctx, argv[i]);
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 2;
    }

    if (m->tier == 1 &&
        (!m->need_undef_varref0 || (callee->u.func.var_refs && callee->u.func.var_refs[0] &&
                                    JS_IsUndefined(*callee->u.func.var_refs[0]->pvalue)))) {
        frame->saved_sp = sp;
        frame->sf.cur_sp = sp;
        frame->sf.cur_pc = pc + 3;
        state->pc = pc;
        state->sp = sp;
        js_frame_begin_c(state);
        OrdSite *site = ord_ctor_site(state, mode, ((uintptr_t)callee) | 1u, ~((uintptr_t)b));
        if (!site) {
            if (!FRAME_CHECKPOINT(frame))
                frame->sf.cur_sp = NULL;
            js_frame_finish_c(state);
            return JS_FrameInterpProperty_call_constructor(state);
        }
        JSShape *sh = fast_ctor_ensure_shape(ctx, rt, site, proto_obj, m->n_fields, m->atoms);
        if (!sh) {
            state->pc = pc + 3;
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        JSProperty props[16];
        props[0].u.value = JS_UNDEFINED;
        for (unsigned f = 0; f < m->n_fields; f++) {
            JSValue v;
            switch (m->src_kind[f]) {
            case FAST_CTOR_SRC_ARG:
                v = (uint32_t)m->src_imm[f] < incoming_argc ? js_dup(argv[m->src_imm[f]])
                                                            : JS_UNDEFINED;
                break;
            case FAST_CTOR_SRC_I32:
                v = js_int32(m->src_imm[f]);
                break;
            case FAST_CTOR_SRC_NULL:
                v = JS_NULL;
                break;
            case FAST_CTOR_SRC_UNDEF:
                v = JS_UNDEFINED;
                break;
            case FAST_CTOR_SRC_BOOL:
                v = JS_MKVAL(JS_TAG_BOOL, m->src_imm[f]);
                break;
            default:
                v = js_dup(b->cpool[m->src_imm[f]]);
                break;
            }
            props[f].u.value = v;
        }
        JSValue this_obj = JS_NewObjectFromShape(ctx, js_dup_shape(sh), JS_CLASS_OBJECT, props);
        if (JS_IsException(this_obj)) {
            state->pc = pc + 3;
            state->exception_pending = true;
            js_frame_finish_c(state);
            return JS_FrameInterpSlow(state);
        }
        ctx->interrupt_counter -= 2;
        JSValue old_f0 = argv[-2], old_f1 = argv[-1];
        JSValue *new_sp = argv - 1;
        argv[-2] = this_obj;
        state->pc = pc + 3;
        state->sp = new_sp;
        frame->saved_sp = new_sp;
        frame->sf.cur_pc = pc + 3;
        if (callee->header.ref_count > 2) {
            callee->header.ref_count -= 2;
        } else {
            JS_FreeValue(ctx, old_f0);
            JS_FreeValue(ctx, old_f1);
        }
        for (int i = 0; i < incoming_argc; i++)
            JS_FreeValue(ctx, argv[i]);
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return 2;
    }

    if (FRAME_CAPTURED_ARGS(b))
        return JS_FrameInterpProperty_call_constructor(state);
    uint16_t owned_args = incoming_argc < b->arg_count ? b->arg_count : 0;
    JSFrameSegment *segment = state->segment;
    size_t frame_size = FRAME_HEADER_BYTES +
                        sizeof(JSValue) * (owned_args + b->var_count + b->stack_size) +
                        FRAME_CAPTURE_BYTES(b);
    if (frame_size > segment->capacity - segment->used)
        return JS_FrameInterpProperty_call_constructor(state);
    frame->saved_sp = sp;
    frame->sf.cur_sp = sp;
    frame->sf.cur_pc = pc + 3;
    state->pc = pc;
    state->sp = sp;
    js_frame_begin_c(state);
    if (unlikely(js_check_stack_overflow(rt, frame_size))) {
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return JS_FrameInterpProperty_call_constructor(state);
    }
    OrdSite *site = ord_ctor_site(state, mode, ((uintptr_t)callee) | 1u, ~((uintptr_t)b));
    if (!site) {
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return JS_FrameInterpProperty_call_constructor(state);
    }
    JSShape *sh = fast_ctor_ensure_shape(ctx, rt, site, proto_obj, 0, NULL);
    if (!sh) {
        frame->pending = (uint16_t)(incoming_argc + 2);
        state->pc = pc + 3;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameVarargsSlow(state);
    }
    if (unlikely(state->segment != segment || frame_size > segment->capacity - segment->used)) {
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return JS_FrameInterpProperty_call_constructor(state);
    }
    frame->pending = (uint16_t)(incoming_argc + 2);
    JSProperty dummy_prop;
    dummy_prop.u.value = JS_UNDEFINED;
    JSValue this_obj = JS_NewObjectFromShape(ctx, js_dup_shape(sh), JS_CLASS_OBJECT, &dummy_prop);
    if (JS_IsException(this_obj)) {
        state->pc = pc + 3;
        state->sp = sp;
        state->exception_pending = true;
        js_frame_finish_c(state);
        return JS_FrameVarargsSlow(state);
    }
    if (unlikely(state->segment != segment || frame_size > segment->capacity - segment->used)) {
        JS_FreeValue(ctx, this_obj);
        frame->pending = 0;
        if (!FRAME_CHECKPOINT(frame))
            frame->sf.cur_sp = NULL;
        js_frame_finish_c(state);
        return JS_FrameInterpProperty_call_constructor(state);
    }
    ctx->interrupt_counter -= 2;
    assert(callee->header.ref_count >= 2);
    callee->header.ref_count--;
    argv[-2] = this_obj;
    JSFrame *child = (JSFrame *)(segment->data + segment->used);
    segment->used += frame_size;
    state->used_bytes += frame_size;
    js_frame_charge_stack(rt, frame_size);
    child->segment = segment;
    child->frame_bytes = frame_size;
    child->bytecode = b;
    child->this_value = this_obj;
    child->owned_args = owned_args;
    child->pending = 0;
    child->saved_sp = NULL;
    JSValue *base_buf = (JSValue *)((uint8_t *)child + FRAME_HEADER_BYTES);
    JSValue *arg_buf = argv;
    if (owned_args) {
        arg_buf = base_buf;
        for (uint16_t i = 0; i < incoming_argc; i++)
            arg_buf[i] = js_dup(argv[i]);
        for (uint16_t i = incoming_argc; i < owned_args; i++)
            arg_buf[i] = JS_UNDEFINED;
    }
    JSValue *var_buf = base_buf + owned_args;
    for (int i = 0; i < b->var_count; i++)
        var_buf[i] = JS_UNDEFINED;
    JSValue *stack_buf = var_buf + b->var_count;
    child->sf.prev_frame = &frame->sf;
    child->sf.cur_func = func_obj;
    child->sf.arg_buf = arg_buf;
    child->sf.var_buf = var_buf;
    child->sf.var_refs = b->var_ref_count ? (JSVarRef **)(stack_buf + b->stack_size) : NULL;
    child->sf.var_ref_count = b->var_ref_count;
    for (int i = 0; i < b->var_ref_count; i++)
        child->sf.var_refs[i] = NULL;
    child->sf.arg_count = owned_args ? owned_args : incoming_argc;
    child->sf.is_strict_mode = b->is_strict_mode;
    FRAME_CLEAR_STACK_AUX(&child->sf);
    child->sf.cur_pc = NULL;
    child->sf.cur_sp = NULL;
    FRAME_FLAGS(child) = 0;
    FRAME_ROOT(child) = 3;
    rt->current_stack_frame = &child->sf;
    state->frame = child;
    state->pc = b->byte_code_buf;
    state->sp = stack_buf;
    js_frame_finish_c(state);
    return 0;
}
