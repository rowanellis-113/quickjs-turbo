/* Frame-free specialized evaluator for small compound leaf bytecode callees. */
#ifdef QJS_EMIT_FAST_CORE_BUILTINS
__attribute__((visibility("hidden"))) void *const qjs_fast_core_js_array_push =
    (void *)(uintptr_t)&js_array_push;
__attribute__((visibility("hidden"))) void *const qjs_fast_core_js_string_charCodeAt =
    (void *)(uintptr_t)&js_string_charCodeAt;
__attribute__((visibility("hidden"))) void *const qjs_fast_core_js_string_codePointAt =
    (void *)(uintptr_t)&js_string_codePointAt;
#endif

typedef struct {
    JSContext *ctx;
    JSFunctionBytecode *b;
    uint64_t bc_head;
    uint64_t bc_tail;
    int bc_len;
    uint8_t kind;
    uint8_t op_extra;
    uint8_t glob1_which;
    uint8_t glob2_which;
    JSAtom a0, a1, a2, a3, a4;
    JSShape *sh0, *sh0_alt, *sh1, *sh2, *sh_g1, *sh_g1_alt, *sh_g2, *sh_g2_alt;
    uint32_t slot0, slot0_alt, slot1, slot2, slot2_alt, slot3, slot3_alt, slot_g1, slot_g2;
} CLCacheEntry;

static CLCacheEntry cl_cache[64];

enum {
    CL_NONE = 0,
    CL_IS_PAIR = 1,
    CL_IS_SATISFIED = 2,
    CL_MARK_AS = 3,
    CL_IS_HELD_OR_SUSP = 4,
    CL_SELECT_DIR = 5,
    CL_TYPEOF_EQ = 6,
    CL_SET_GLOBAL_PROP = 7,
};

static inline int cl_read_own_normal_slot(JSObject *o, JSShape **sh_io, uint32_t *slot_io,
                                          JSAtom atom, JSValue *out)
{
    if (unlikely(o->is_exotic))
        return 0;
    JSShape *sh = o->shape;
    if (likely(sh && *sh_io == sh)) {
        uint32_t s = *slot_io;
        if (likely(s < (uint32_t)sh->prop_size && get_shape_prop(sh)[s].atom == atom &&
                   (get_shape_prop(sh)[s].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
            JSValue v = o->prop[s].u.value;
            if (unlikely(JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v)))
                return 0;
            *out = v;
            return 1;
        }
    }
    JSProperty *pr = NULL;
    JSShapeProperty *ps = find_own_property(&pr, o, atom);
    if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
        return 0;
    JSValue v = pr->u.value;
    if (JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v))
        return 0;
    *sh_io = sh;
    *slot_io = (uint32_t)(pr - o->prop);
    *out = v;
    return 1;
}

static inline int cl_read_own_normal_slot2(JSObject *o, JSShape **sh0_io, uint32_t *slot0_io,
                                           JSShape **sh1_io, uint32_t *slot1_io, JSAtom atom,
                                           JSValue *out)
{
    if (unlikely(o->is_exotic))
        return 0;
    JSShape *sh = o->shape;
    if (likely(sh)) {
        if (*sh0_io == sh) {
            uint32_t s = *slot0_io;
            if (likely(s < (uint32_t)sh->prop_size && get_shape_prop(sh)[s].atom == atom &&
                       (get_shape_prop(sh)[s].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
                JSValue v = o->prop[s].u.value;
                if (unlikely(JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v)))
                    return 0;
                *out = v;
                return 1;
            }
        }
        if (*sh1_io == sh) {
            uint32_t s = *slot1_io;
            if (likely(s < (uint32_t)sh->prop_size && get_shape_prop(sh)[s].atom == atom &&
                       (get_shape_prop(sh)[s].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
                JSValue v = o->prop[s].u.value;
                if (unlikely(JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v)))
                    return 0;
                *out = v;
                return 1;
            }
        }
    }
    JSProperty *pr = NULL;
    JSShapeProperty *ps = find_own_property(&pr, o, atom);
    if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
        return 0;
    JSValue v = pr->u.value;
    if (JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v))
        return 0;
    uint32_t ns = (uint32_t)(pr - o->prop);
    if (!*sh0_io || *sh0_io == sh) {
        *sh0_io = sh;
        *slot0_io = ns;
    } else if (!*sh1_io || *sh1_io == sh) {
        *sh1_io = sh;
        *slot1_io = ns;
    } else {
        *sh1_io = *sh0_io;
        *slot1_io = *slot0_io;
        *sh0_io = sh;
        *slot0_io = ns;
    }
    *out = v;
    return 1;
}

static inline JSProperty *cl_find_own_writable_normal_slot2(JSObject *o, JSShape **sh0_io,
                                                            uint32_t *slot0_io, JSShape **sh1_io,
                                                            uint32_t *slot1_io, JSAtom atom,
                                                            uint32_t forbid_flags)
{
    JSShape *sh = o->shape;
    uint32_t req = JS_PROP_NORMAL | JS_PROP_WRITABLE;
    uint32_t mask = JS_PROP_TMASK | JS_PROP_WRITABLE | forbid_flags;
    if (likely(sh)) {
        if (*sh0_io == sh) {
            uint32_t s = *slot0_io;
            if (likely(s < (uint32_t)sh->prop_size && get_shape_prop(sh)[s].atom == atom &&
                       (get_shape_prop(sh)[s].flags & mask) == req))
                return &o->prop[s];
        }
        if (*sh1_io == sh) {
            uint32_t s = *slot1_io;
            if (likely(s < (uint32_t)sh->prop_size && get_shape_prop(sh)[s].atom == atom &&
                       (get_shape_prop(sh)[s].flags & mask) == req))
                return &o->prop[s];
        }
    }
    JSProperty *pr = NULL;
    JSShapeProperty *ps = find_own_property(&pr, o, atom);
    if (!ps || (ps->flags & mask) != req)
        return NULL;
    uint32_t ns = (uint32_t)(pr - o->prop);
    if (!*sh0_io || *sh0_io == sh) {
        *sh0_io = sh;
        *slot0_io = ns;
    } else if (!*sh1_io || *sh1_io == sh) {
        *sh1_io = sh;
        *slot1_io = ns;
    } else {
        *sh1_io = *sh0_io;
        *slot1_io = *slot0_io;
        *sh0_io = sh;
        *slot0_io = ns;
    }
    return pr;
}

static inline int cl_resolve_global(JSContext *ctx, JSShape **sh_io, JSShape **sh_alt_io,
                                    uint32_t *slot_io, uint8_t *which_io, JSAtom atom, JSValue *out)
{
    JSObject *gv = JS_VALUE_GET_OBJ(ctx->global_var_obj);
    JSObject *go = JS_VALUE_GET_OBJ(ctx->global_obj);
    if (unlikely(gv->is_exotic || go->is_exotic))
        return 0;
    JSShape *gv_sh = gv->shape;
    JSShape *go_sh = go->shape;
    uint8_t w = *which_io;
    if (w == 1 && likely(gv_sh == *sh_io)) {
        uint32_t s = *slot_io;
        if (likely(s < (uint32_t)gv_sh->prop_size && get_shape_prop(gv_sh)[s].atom == atom &&
                   (get_shape_prop(gv_sh)[s].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
            JSValue v = gv->prop[s].u.value;
            if (likely(JS_VALUE_GET_TAG(v) != JS_TAG_UNINITIALIZED && !JS_IsException(v))) {
                *out = v;
                return 1;
            }
        }
    } else if (w == 2 && likely(gv_sh == *sh_io && go_sh == *sh_alt_io)) {
        uint32_t s = *slot_io;
        if (likely(s < (uint32_t)go_sh->prop_size && get_shape_prop(go_sh)[s].atom == atom &&
                   (get_shape_prop(go_sh)[s].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
            JSValue v = go->prop[s].u.value;
            if (likely(JS_VALUE_GET_TAG(v) != JS_TAG_UNINITIALIZED && !JS_IsException(v))) {
                *out = v;
                return 1;
            }
        }
    }
    JSProperty *pr = NULL;
    JSShapeProperty *ps = find_own_property(&pr, gv, atom);
    if (ps) {
        if ((ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
            return 0;
        JSValue v = pr->u.value;
        if (JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v))
            return 0;
        *which_io = 1;
        *sh_io = gv_sh;
        *sh_alt_io = go_sh;
        *slot_io = (uint32_t)(pr - gv->prop);
        *out = v;
        return 1;
    }
    ps = find_own_property(&pr, go, atom);
    if (ps && (ps->flags & JS_PROP_TMASK) == JS_PROP_NORMAL) {
        JSValue v = pr->u.value;
        if (JS_VALUE_GET_TAG(v) == JS_TAG_UNINITIALIZED || JS_IsException(v))
            return 0;
        *which_io = 2;
        *sh_io = gv_sh;
        *sh_alt_io = go_sh;
        *slot_io = (uint32_t)(pr - go->prop);
        *out = v;
        return 1;
    }
    return 0;
}

__attribute__((visibility("hidden"), section(".text.qjs_frame"), noipa)) int
JS_FastCompoundLeaf(JSFrameRegisterState *state, JSFunctionBytecode *b, JSValue *argv, int argc,
                    uint32_t call_flags, JSValue *out_res)
{
    int len = b->byte_code_len;
    const uint8_t *bc = b->byte_code_buf;
    if (unlikely(!bc || len < 8))
        return -1;
    uint64_t head, tail;
    memcpy(&head, bc, 8);
    memcpy(&tail, bc + len - 8, 8);
    JSContext *ctx = b->realm;
    CLCacheEntry *e = &cl_cache[((uintptr_t)b >> 4) & 63u];
    if (unlikely(e->b != b || e->ctx != ctx || e->bc_len != len || e->bc_head != head ||
                 e->bc_tail != tail)) {
        memset(e, 0, sizeof(*e));
        e->ctx = ctx;
        e->b = b;
        e->bc_len = len;
        e->bc_head = head;
        e->bc_tail = tail;
        if (len == 8 && b->var_count == 0 && b->arg_count == 1 && bc[0] == OP_get_arg0 &&
            bc[1] == OP_get_var && bc[6] == OP_instanceof && bc[7] == OP_return) {
            e->kind = CL_IS_PAIR;
            e->a0 = get_u32(bc + 2);
        } else if (len == 9 && b->var_count == 0 && b->arg_count == 1 && bc[0] == OP_get_arg0 &&
                   bc[1] == OP_typeof && bc[2] == OP_push_atom_value &&
                   (bc[7] == OP_strict_eq || bc[7] == OP_strict_neq) && bc[8] == OP_return) {
            e->kind = CL_TYPEOF_EQ;
            e->op_extra = bc[7];
            e->a0 = get_u32(bc + 3);
        } else if (len == 19 && b->var_count == 1 && b->arg_count == 0 && bc[0] == OP_push_this &&
                   bc[1] == OP_put_loc0 && bc[2] == OP_get_loc0 && bc[3] == OP_get_var &&
                   bc[8] == OP_get_field && bc[13] == OP_put_field && bc[18] == OP_return_undef) {
            e->kind = CL_SET_GLOBAL_PROP;
            e->a0 = get_u32(bc + 4);
            e->a1 = get_u32(bc + 9);
            e->a2 = get_u32(bc + 14);
        } else if (len == 20 && b->var_count == 1 && b->arg_count == 0 && bc[0] == OP_push_this &&
                   bc[1] == OP_put_loc0 && bc[2] == OP_get_loc0 && bc[3] == OP_get_field &&
                   bc[8] == OP_get_var && bc[13] == OP_get_field && bc[18] == OP_neq &&
                   bc[19] == OP_return) {
            e->kind = CL_IS_SATISFIED;
            e->a0 = get_u32(bc + 4);
            e->a1 = get_u32(bc + 9);
            e->a2 = get_u32(bc + 14);
        } else if (len == 21 && b->var_count == 1 && b->arg_count == 0 && bc[0] == OP_push_this &&
                   bc[1] == OP_put_loc0 && bc[2] == OP_get_loc0 && bc[3] == OP_get_loc0 &&
                   bc[4] == OP_get_field && bc[9] == OP_get_var &&
                   (bc[14] == OP_and || bc[14] == OP_or) && bc[15] == OP_put_field &&
                   bc[20] == OP_return_undef && get_u32(bc + 5) == get_u32(bc + 16)) {
            e->kind = CL_MARK_AS;
            e->op_extra = bc[14];
            e->a0 = get_u32(bc + 5);
            e->a1 = get_u32(bc + 10);
        } else if (len == 33 && b->var_count == 1 && b->arg_count == 0 && bc[0] == OP_push_this &&
                   bc[1] == OP_put_loc0 && bc[2] == OP_get_loc0 && bc[3] == OP_get_field &&
                   bc[8] == OP_get_var && bc[13] == OP_and && bc[14] == OP_push_0 &&
                   bc[15] == OP_neq && bc[16] == OP_dup && bc[17] == OP_if_true8 &&
                   bc[18] == OP_drop && bc[19] == OP_drop && bc[20] == OP_get_loc0 &&
                   bc[21] == OP_get_field && get_u32(bc + 4) == get_u32(bc + 22) &&
                   bc[26] == OP_get_var && bc[31] == OP_eq && bc[32] == OP_return) {
            e->kind = CL_IS_HELD_OR_SUSP;
            e->a0 = get_u32(bc + 4);
            e->a1 = get_u32(bc + 9);
            e->a2 = get_u32(bc + 27);
        } else if (len == 35 && b->var_count == 1 && b->arg_count == 0 && bc[0] == OP_push_this &&
                   bc[1] == OP_put_loc0 && bc[2] == OP_get_loc0 && bc[3] == OP_get_field &&
                   bc[8] == OP_get_var && bc[13] == OP_get_field && bc[18] == OP_eq &&
                   bc[19] == OP_if_false8 && bc[20] == OP_push_this && bc[21] == OP_get_loc0 &&
                   bc[22] == OP_get_field && bc[27] == OP_return && bc[28] == OP_get_loc0 &&
                   bc[29] == OP_get_field && bc[34] == OP_return) {
            e->kind = CL_SELECT_DIR;
            e->a0 = get_u32(bc + 4);
            e->a1 = get_u32(bc + 9);
            e->a2 = get_u32(bc + 14);
            e->a3 = get_u32(bc + 23);
            e->a4 = get_u32(bc + 30);
        } else {
            e->kind = CL_NONE;
            return -1;
        }
    }
    if (e->kind == CL_NONE)
        return -1;

    if (e->kind == CL_TYPEOF_EQ) {
        JSValue v = argc >= 1 ? argv[0] : JS_UNDEFINED;
        uint32_t tag = JS_VALUE_GET_NORM_TAG(v);
        JSAtom ta;
        switch (tag) {
        case JS_TAG_SHORT_BIG_INT:
        case JS_TAG_BIG_INT:
            ta = JS_ATOM_bigint;
            break;
        case JS_TAG_INT:
        case JS_TAG_FLOAT64:
            ta = JS_ATOM_number;
            break;
        case JS_TAG_UNDEFINED:
            ta = JS_ATOM_undefined;
            break;
        case JS_TAG_BOOL:
            ta = JS_ATOM_boolean;
            break;
        case JS_TAG_STRING:
        case JS_TAG_STRING_ROPE:
            ta = JS_ATOM_string;
            break;
        case JS_TAG_OBJECT: {
            JSObject *o = JS_VALUE_GET_OBJ(v);
            if (unlikely(o->is_HTMLDDA))
                ta = JS_ATOM_undefined;
            else if (JS_IsFunction(ctx, v))
                ta = JS_ATOM_function;
            else
                ta = JS_ATOM_object;
            break;
        }
        case JS_TAG_NULL:
            ta = JS_ATOM_object;
            break;
        case JS_TAG_SYMBOL:
            ta = JS_ATOM_symbol;
            break;
        default:
            return 0;
        }
        int eq = (ta == e->a0);
        if (e->op_extra == OP_strict_neq)
            eq = !eq;
        *out_res = js_bool(eq);
        return 1;
    }

    if (e->kind == CL_IS_PAIR) {
        if (argc < 1)
            return 0;
        JSValue ctor_val;
        if (!cl_resolve_global(ctx, &e->sh_g1, &e->sh_g1_alt, &e->slot_g1, &e->glob1_which, e->a0,
                               &ctor_val))
            return 0;
        if (JS_VALUE_GET_TAG(ctor_val) != JS_TAG_OBJECT)
            return 0;
        JSObject *ctor = JS_VALUE_GET_OBJ(ctor_val);
        if (ctor->is_exotic || !JS_IsFunction(ctx, ctor_val))
            return 0;
        JSObject *fp = JS_VALUE_GET_OBJ(ctx->function_proto);
        if (unlikely(fp->is_exotic))
            return 0;
        JSShape *csh = ctor->shape;
        JSShape *fsh = fp->shape;
        JSValue proto_val = JS_UNDEFINED;
        int fast_ok = 0;
        if (likely(e->sh1 == csh && e->sh2 == fsh && csh && fsh && csh->proto == fp &&
                   e->slot1 < (uint32_t)csh->prop_size &&
                   get_shape_prop(csh)[e->slot1].atom == JS_ATOM_prototype &&
                   (get_shape_prop(csh)[e->slot1].flags & JS_PROP_TMASK) == JS_PROP_NORMAL &&
                   e->slot2 < (uint32_t)fsh->prop_size &&
                   get_shape_prop(fsh)[e->slot2].atom == JS_ATOM_Symbol_hasInstance &&
                   (get_shape_prop(fsh)[e->slot2].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
            JSValue hi_val = fp->prop[e->slot2].u.value;
            if (JS_VALUE_GET_TAG(hi_val) == JS_TAG_OBJECT) {
                JSObject *hi = JS_VALUE_GET_OBJ(hi_val);
                if (hi->class_id == JS_CLASS_C_FUNCTION && hi->u.cfunc.cproto == JS_CFUNC_generic &&
                    hi->u.cfunc.c_function.generic == js_function_hasInstance) {
                    proto_val = ctor->prop[e->slot1].u.value;
                    fast_ok = 1;
                }
            }
        }
        if (!fast_ok) {
            JSProperty *pr = NULL;
            JSShapeProperty *ps = find_own_property(&pr, ctor, JS_ATOM_prototype);
            if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
                return 0;
            uint32_t pslot = (uint32_t)(pr - ctor->prop);
            proto_val = pr->u.value;
            int found_fp = 0;
            JSObject *cur = ctor;
            for (int hop = 0; cur && hop < 8; hop++) {
                if (cur->is_exotic)
                    return 0;
                if (cur == fp) {
                    JSShapeProperty *hps = find_own_property(&pr, fp, JS_ATOM_Symbol_hasInstance);
                    if (!hps || (hps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
                        return 0;
                    if (JS_VALUE_GET_TAG(pr->u.value) != JS_TAG_OBJECT)
                        return 0;
                    JSObject *hi = JS_VALUE_GET_OBJ(pr->u.value);
                    if (hi->class_id != JS_CLASS_C_FUNCTION ||
                        hi->u.cfunc.cproto != JS_CFUNC_generic ||
                        hi->u.cfunc.c_function.generic != js_function_hasInstance)
                        return 0;
                    if (csh && csh->proto == fp) {
                        e->sh1 = csh;
                        e->slot1 = pslot;
                        e->sh2 = fsh;
                        e->slot2 = (uint32_t)(pr - fp->prop);
                    }
                    found_fp = 1;
                    break;
                }
                if (find_own_property(&pr, cur, JS_ATOM_Symbol_hasInstance))
                    return 0;
                cur = cur->shape ? cur->shape->proto : NULL;
            }
            if (!found_fp)
                return 0;
        }
        if (JS_VALUE_GET_TAG(proto_val) != JS_TAG_OBJECT)
            return 0;
        JSObject *target_proto = JS_VALUE_GET_OBJ(proto_val);
        if (JS_VALUE_GET_TAG(argv[0]) != JS_TAG_OBJECT) {
            *out_res = JS_FALSE;
            return 1;
        }
        JSObject *p = JS_VALUE_GET_OBJ(argv[0]);
        for (int hop = 0; hop < 32; hop++) {
            if (p->is_exotic)
                return 0;
            p = p->shape ? p->shape->proto : NULL;
            if (!p) {
                *out_res = JS_FALSE;
                return 1;
            }
            if (p == target_proto) {
                *out_res = JS_TRUE;
                return 1;
            }
        }
        return 0;
    }

    if (!(call_flags & 1))
        return 0;
    JSValue this_val = argv[-2];
    if (JS_VALUE_GET_TAG(this_val) != JS_TAG_OBJECT)
        return 0;
    JSObject *this_obj = JS_VALUE_GET_OBJ(this_val);
    if (this_obj->is_exotic)
        return 0;

    if (e->kind == CL_SET_GLOBAL_PROP) {
        JSValue v_glob, v_val;
        if (!cl_resolve_global(ctx, &e->sh_g1, &e->sh_g1_alt, &e->slot_g1, &e->glob1_which, e->a0,
                               &v_glob) ||
            JS_VALUE_GET_TAG(v_glob) != JS_TAG_OBJECT)
            return 0;
        if (!cl_read_own_normal_slot(JS_VALUE_GET_OBJ(v_glob), &e->sh1, &e->slot1, e->a1, &v_val) ||
            JS_VALUE_HAS_REF_COUNT(v_val))
            return 0;
        JSShape *sh = this_obj->shape;
        (void)sh;
        JSProperty *pr = cl_find_own_writable_normal_slot2(
            this_obj, &e->sh0, &e->slot0, &e->sh0_alt, &e->slot0_alt, e->a2, JS_PROP_LENGTH);
        if (!pr)
            return 0;
        if (JS_VALUE_HAS_REF_COUNT(pr->u.value))
            return 0;
        pr->u.value = v_val;
        *out_res = JS_UNDEFINED;
        return 1;
    }

    if (e->kind == CL_IS_SATISFIED) {
        JSValue v_dir, v_glob, v_c;
        if (!cl_read_own_normal_slot2(this_obj, &e->sh0, &e->slot0, &e->sh0_alt, &e->slot0_alt,
                                      e->a0, &v_dir) ||
            JS_VALUE_GET_TAG(v_dir) != JS_TAG_INT)
            return 0;
        if (!cl_resolve_global(ctx, &e->sh_g1, &e->sh_g1_alt, &e->slot_g1, &e->glob1_which, e->a1,
                               &v_glob) ||
            JS_VALUE_GET_TAG(v_glob) != JS_TAG_OBJECT)
            return 0;
        if (!cl_read_own_normal_slot(JS_VALUE_GET_OBJ(v_glob), &e->sh1, &e->slot1, e->a2, &v_c) ||
            JS_VALUE_GET_TAG(v_c) != JS_TAG_INT)
            return 0;
        *out_res = js_bool(JS_VALUE_GET_INT(v_dir) != JS_VALUE_GET_INT(v_c));
        return 1;
    }

    if (e->kind == CL_MARK_AS) {
        JSProperty *pr = cl_find_own_writable_normal_slot2(this_obj, &e->sh0, &e->slot0,
                                                           &e->sh0_alt, &e->slot0_alt, e->a0, 0);
        if (!pr || JS_VALUE_GET_TAG(pr->u.value) != JS_TAG_INT)
            return 0;
        JSValue v_mask;
        if (!cl_resolve_global(ctx, &e->sh_g1, &e->sh_g1_alt, &e->slot_g1, &e->glob1_which, e->a1,
                               &v_mask) ||
            JS_VALUE_GET_TAG(v_mask) != JS_TAG_INT)
            return 0;
        int32_t cur = JS_VALUE_GET_INT(pr->u.value);
        int32_t m = JS_VALUE_GET_INT(v_mask);
        pr->u.value = js_int32(e->op_extra == OP_and ? (cur & m) : (cur | m));
        *out_res = JS_UNDEFINED;
        return 1;
    }

    if (e->kind == CL_IS_HELD_OR_SUSP) {
        JSValue v_state, v_held, v_susp;
        if (!cl_read_own_normal_slot2(this_obj, &e->sh0, &e->slot0, &e->sh0_alt, &e->slot0_alt,
                                      e->a0, &v_state) ||
            JS_VALUE_GET_TAG(v_state) != JS_TAG_INT)
            return 0;
        if (!cl_resolve_global(ctx, &e->sh_g1, &e->sh_g1_alt, &e->slot_g1, &e->glob1_which, e->a1,
                               &v_held) ||
            JS_VALUE_GET_TAG(v_held) != JS_TAG_INT)
            return 0;
        int32_t st = JS_VALUE_GET_INT(v_state);
        if ((st & JS_VALUE_GET_INT(v_held)) != 0) {
            *out_res = JS_TRUE;
            return 1;
        }
        if (!cl_resolve_global(ctx, &e->sh_g2, &e->sh_g2_alt, &e->slot_g2, &e->glob2_which, e->a2,
                               &v_susp) ||
            JS_VALUE_GET_TAG(v_susp) != JS_TAG_INT)
            return 0;
        *out_res = js_bool(st == JS_VALUE_GET_INT(v_susp));
        return 1;
    }

    if (e->kind == CL_SELECT_DIR) {
        JSShape *tsh = this_obj->shape;
        JSValue v_dir, v_out;
        int way = 0;
        if (likely(tsh && e->sh0 == tsh && e->slot0 < (uint32_t)tsh->prop_size &&
                   get_shape_prop(tsh)[e->slot0].atom == e->a0 &&
                   (get_shape_prop(tsh)[e->slot0].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
            way = 0;
            v_dir = this_obj->prop[e->slot0].u.value;
            if (JS_VALUE_GET_TAG(v_dir) != JS_TAG_INT)
                return 0;
        } else if (likely(tsh && e->sh0_alt == tsh && e->slot0_alt < (uint32_t)tsh->prop_size &&
                          get_shape_prop(tsh)[e->slot0_alt].atom == e->a0 &&
                          (get_shape_prop(tsh)[e->slot0_alt].flags & JS_PROP_TMASK) ==
                              JS_PROP_NORMAL)) {
            way = 1;
            v_dir = this_obj->prop[e->slot0_alt].u.value;
            if (JS_VALUE_GET_TAG(v_dir) != JS_TAG_INT)
                return 0;
        } else {
            JSProperty *pr = NULL;
            JSShapeProperty *ps = find_own_property(&pr, this_obj, e->a0);
            if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL ||
                JS_VALUE_GET_TAG(pr->u.value) != JS_TAG_INT)
                return 0;
            v_dir = pr->u.value;
            uint32_t s0 = (uint32_t)(pr - this_obj->prop);
            if (!e->sh0 || e->sh0 == tsh) {
                way = 0;
                e->sh0 = tsh;
                e->slot0 = s0;
                e->slot2 = UINT32_MAX;
                e->slot3 = UINT32_MAX;
            } else if (!e->sh0_alt || e->sh0_alt == tsh) {
                way = 1;
                e->sh0_alt = tsh;
                e->slot0_alt = s0;
                e->slot2_alt = UINT32_MAX;
                e->slot3_alt = UINT32_MAX;
            } else {
                e->sh0_alt = e->sh0;
                e->slot0_alt = e->slot0;
                e->slot2_alt = e->slot2;
                e->slot3_alt = e->slot3;
                way = 0;
                e->sh0 = tsh;
                e->slot0 = s0;
                e->slot2 = UINT32_MAX;
                e->slot3 = UINT32_MAX;
            }
        }
        JSValue v_glob, v_fwd;
        if (!cl_resolve_global(ctx, &e->sh_g1, &e->sh_g1_alt, &e->slot_g1, &e->glob1_which, e->a1,
                               &v_glob) ||
            JS_VALUE_GET_TAG(v_glob) != JS_TAG_OBJECT)
            return 0;
        if (!cl_read_own_normal_slot(JS_VALUE_GET_OBJ(v_glob), &e->sh1, &e->slot1, e->a2, &v_fwd) ||
            JS_VALUE_GET_TAG(v_fwd) != JS_TAG_INT)
            return 0;
        int take_then = (JS_VALUE_GET_INT(v_dir) == JS_VALUE_GET_INT(v_fwd));
        JSAtom pick = take_then ? e->a3 : e->a4;
        uint32_t *p_slot2 = (way == 0) ? &e->slot2 : &e->slot2_alt;
        uint32_t *p_slot3 = (way == 0) ? &e->slot3 : &e->slot3_alt;
        uint32_t cached_slot = take_then ? *p_slot2 : *p_slot3;
        if (likely(tsh && cached_slot < (uint32_t)tsh->prop_size &&
                   get_shape_prop(tsh)[cached_slot].atom == pick &&
                   (get_shape_prop(tsh)[cached_slot].flags & JS_PROP_TMASK) == JS_PROP_NORMAL)) {
            v_out = this_obj->prop[cached_slot].u.value;
        } else {
            JSProperty *pr = NULL;
            JSShapeProperty *ps = find_own_property(&pr, this_obj, pick);
            if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
                return 0;
            v_out = pr->u.value;
            uint32_t ns = (uint32_t)(pr - this_obj->prop);
            if (take_then)
                *p_slot2 = ns;
            else
                *p_slot3 = ns;
        }
        if (JS_VALUE_GET_TAG(v_out) == JS_TAG_UNINITIALIZED || JS_IsException(v_out))
            return 0;
        *out_res = js_dup(v_out);
        return 1;
    }

    return -1;
}
