/* Epoch-guarded monomorphic getter/length cache for OP_get_field. */
__attribute__((visibility("hidden"), noipa)) int JS_FastTypedArrayLenProve(JSContext *ctx,
                                                                           JSObject *obj)
{
    JSRuntime *rt = ctx->rt;
    JSProperty *pr = NULL;
    JSShapeProperty *ps;
    if (!obj || !is_typed_array(obj->class_id) || rt->property_ic_mode != 1 ||
        !rt->property_ic_epoch)
        return 0;
    if (find_own_property(&pr, obj, JS_ATOM_length))
        return 0;
    JSObject *cur = obj->shape ? obj->shape->proto : NULL;
    for (int depth = 0; depth < 8 && cur; depth++) {
        if (cur->is_exotic || !cur->is_prototype)
            return 0;
        ps = find_own_property(&pr, cur, JS_ATOM_length);
        if (ps) {
            if ((ps->flags & JS_PROP_TMASK) != JS_PROP_GETSET)
                return 0;
            JSObject *g = pr->u.getset.getter;
            if (!g || g->class_id != JS_CLASS_C_FUNCTION || g->u.cfunc.cproto != JS_CFUNC_getter ||
                g->u.cfunc.realm != ctx ||
                g->u.cfunc.c_function.getter != js_typed_array_get_length)
                return 0;
            return 1;
        }
        cur = cur->shape ? cur->shape->proto : NULL;
    }
    return 0;
}

enum {
    FG_KIND_THIS_FIELD = 1,
    FG_KIND_THIS_FIELD_LEN = 2,
    FG_KIND_THIS_FIELD_FIELD = 3,
    FG_KIND_CONST = 4,
    FG_KIND_TA_LEN = 5,
    FG_KIND_TA_BYTELEN = 6,
    FG_KIND_DV_BYTELEN = 7,
    FG_KIND_AB_BYTELEN = 8,
};

typedef struct FastGetFieldCache {
    JSShape *shape;
    uint64_t epoch;
    JSContext *ctx;
    JSAtom atom;
    uint8_t kind;
    int ab_class_id;
    JSAtom field1;
    JSAtom field2;
    JSValue const_val;
} FastGetFieldCache;

static FastGetFieldCache fg_cache[32];

extern int JS_FrameInterpProperty_get_field(JSFrameRegisterState *state);

static inline int fg_fallback(JSFrameRegisterState *state)
{
    if (state->rt->current_stack_frame != &state->frame->sf)
        state->rt->current_stack_frame = &state->frame->sf;
    return JS_FrameInterpProperty_get_field(state);
}

__attribute__((visibility("hidden"), section(".text.qjs_frame"), noipa)) int
JS_FastGetField(JSFrameRegisterState *state)
{
    uint8_t *pc = state->pc;
    JSValue *sp = state->sp;
    JSValue recv = sp[-1];
    if (!JS_IsObject(recv))
        return fg_fallback(state);
    JSObject *obj = JS_VALUE_GET_OBJ(recv);
    if (obj->header.ref_count <= 1)
        return fg_fallback(state);
    JSFrame *frame = state->frame;
    JSRuntime *rt = state->rt;
    JSContext *ctx = frame->bytecode->realm;
    uint64_t epoch = rt->property_ic_epoch;
    if (ctx->interrupt_counter <= 2 || rt->dump_flags || rt->property_ic_mode != 1 || !epoch)
        return fg_fallback(state);
    JSAtom atom = get_u32(pc + 1);
    if (atom & UINT32_C(0x80000000))
        return fg_fallback(state);
    uint32_t slot = (((uint32_t)((uintptr_t)obj->shape >> 6)) ^ (uint32_t)atom) & 31u;
    FastGetFieldCache *e = &fg_cache[slot];
    if (!(e->kind && e->shape == obj->shape && e->epoch == epoch && e->ctx == ctx &&
          e->atom == atom)) {
        bool is_ta = is_typed_array(obj->class_id);
        bool is_dv = (obj->class_id == JS_CLASS_DATAVIEW);
        bool is_ab = (obj->class_id == JS_CLASS_ARRAY_BUFFER ||
                      obj->class_id == JS_CLASS_SHARED_ARRAY_BUFFER);
        if (obj->is_exotic && !is_ta && !is_dv && !is_ab)
            return fg_fallback(state);
        JSProperty *pr = NULL;
        if (find_own_property(&pr, obj, atom))
            return fg_fallback(state);
        uint8_t new_kind = 0;
        int new_ab_cid = 0;
        JSAtom f1 = 0, f2 = 0;
        JSValue cval = JS_UNDEFINED;
        JSObject *cur = obj->shape ? obj->shape->proto : NULL;
        for (int depth = 0; depth < 8 && cur; depth++) {
            if (!cur->is_prototype || cur->is_exotic)
                return fg_fallback(state);
            JSShapeProperty *ps = find_own_property(&pr, cur, atom);
            if (ps) {
                if ((ps->flags & JS_PROP_TMASK) != JS_PROP_GETSET)
                    return fg_fallback(state);
                JSObject *g = pr->u.getset.getter;
                if (!g)
                    return fg_fallback(state);
                if (g->class_id == JS_CLASS_C_FUNCTION) {
                    if (g->u.cfunc.realm != ctx)
                        return fg_fallback(state);
                    uint8_t cp = g->u.cfunc.cproto;
                    if (cp == JS_CFUNC_getter && is_ta &&
                        g->u.cfunc.c_function.getter == js_typed_array_get_length) {
                        new_kind = FG_KIND_TA_LEN;
                    } else if (cp == JS_CFUNC_getter && is_ta &&
                               g->u.cfunc.c_function.getter == js_typed_array_get_byteLength) {
                        new_kind = FG_KIND_TA_BYTELEN;
                    } else if (cp == JS_CFUNC_getter && is_dv &&
                               g->u.cfunc.c_function.getter == js_dataview_get_byteLength) {
                        new_kind = FG_KIND_DV_BYTELEN;
                    } else if (cp == JS_CFUNC_getter_magic && is_ab &&
                               g->u.cfunc.c_function.getter_magic ==
                                   js_array_buffer_get_byteLength &&
                               g->u.cfunc.magic == obj->class_id) {
                        new_kind = FG_KIND_AB_BYTELEN;
                        new_ab_cid = g->u.cfunc.magic;
                    }
                } else if (g->class_id == JS_CLASS_BYTECODE_FUNCTION && !g->is_exotic &&
                           !obj->is_exotic) {
                    JSFunctionBytecode *gb = g->u.func.function_bytecode;
                    if (gb->realm == ctx && gb->func_kind == JS_FUNC_NORMAL &&
                        !gb->is_derived_class_constructor && gb->arg_count == 0 &&
                        gb->var_ref_count == 0 && gb->closure_var_count == 0) {
                        const uint8_t *bc = gb->byte_code_buf;
                        uint32_t blen = gb->byte_code_len;
                        uint32_t off = 0;
                        if (gb->var_count == 0) {
                            if (blen == 1 && bc[0] == OP_return_undef) {
                                new_kind = FG_KIND_CONST;
                                cval = JS_UNDEFINED;
                            } else if (blen == 2 && bc[1] == OP_return) {
                                uint8_t op0 = bc[0];
                                if (op0 == OP_undefined) {
                                    new_kind = FG_KIND_CONST;
                                    cval = JS_UNDEFINED;
                                } else if (op0 == OP_null) {
                                    new_kind = FG_KIND_CONST;
                                    cval = JS_NULL;
                                } else if (op0 == OP_push_false || op0 == OP_push_true) {
                                    new_kind = FG_KIND_CONST;
                                    cval = JS_MKVAL(JS_TAG_BOOL, op0 == OP_push_true);
                                } else if (op0 >= OP_push_minus1 && op0 <= OP_push_7) {
                                    new_kind = FG_KIND_CONST;
                                    cval = js_int32((int32_t)op0 - OP_push_0);
                                }
                            } else if (blen == 3 && bc[0] == OP_push_i8 && bc[2] == OP_return) {
                                new_kind = FG_KIND_CONST;
                                cval = js_int32((int8_t)bc[1]);
                            } else if (blen == 4 && bc[0] == OP_push_i16 && bc[3] == OP_return) {
                                new_kind = FG_KIND_CONST;
                                cval = js_int32((int16_t)get_u16(bc + 1));
                            } else if (blen >= 1 && bc[0] == OP_push_this) {
                                off = 1;
                            }
                        } else if (gb->var_count == 1 && blen >= 3 && bc[0] == OP_push_this &&
                                   bc[1] == OP_put_loc0 && bc[2] == OP_get_loc0) {
                            off = 3;
                        }
                        if (!new_kind && off) {
                            if (off + 6 == blen && bc[off] == OP_get_field &&
                                bc[off + 5] == OP_return) {
                                f1 = get_u32(bc + off + 1);
                                if (!(f1 & UINT32_C(0x80000000)))
                                    new_kind = FG_KIND_THIS_FIELD;
                            } else if (off + 7 == blen && bc[off] == OP_get_field &&
                                       bc[off + 5] == OP_get_length && bc[off + 6] == OP_return) {
                                f1 = get_u32(bc + off + 1);
                                if (!(f1 & UINT32_C(0x80000000)))
                                    new_kind = FG_KIND_THIS_FIELD_LEN;
                            } else if (off + 11 == blen && bc[off] == OP_get_field &&
                                       bc[off + 5] == OP_get_field && bc[off + 10] == OP_return) {
                                f1 = get_u32(bc + off + 1);
                                f2 = get_u32(bc + off + 6);
                                if (!(f1 & UINT32_C(0x80000000)) && !(f2 & UINT32_C(0x80000000)))
                                    new_kind = FG_KIND_THIS_FIELD_FIELD;
                            }
                        }
                    }
                }
                break;
            }
            cur = cur->shape ? cur->shape->proto : NULL;
        }
        if (!new_kind)
            return fg_fallback(state);
        e->shape = obj->shape;
        e->epoch = epoch;
        e->ctx = ctx;
        e->atom = atom;
        e->kind = new_kind;
        e->ab_class_id = new_ab_cid;
        e->field1 = f1;
        e->field2 = f2;
        e->const_val = cval;
    }

    JSValue res;
    switch (e->kind) {
    case FG_KIND_TA_LEN:
        if (!is_typed_array(obj->class_id))
            return fg_fallback(state);
        res = js_int32(obj->u.array.count);
        break;
    case FG_KIND_TA_BYTELEN: {
        if (!is_typed_array(obj->class_id))
            return fg_fallback(state);
        if (typed_array_is_oob(obj)) {
            res = js_int32(0);
        } else {
            JSTypedArray *ta = obj->u.typed_array;
            if (ta->track_rab)
                return fg_fallback(state);
            res = js_uint32(ta->length);
        }
        break;
    }
    case FG_KIND_DV_BYTELEN: {
        if (obj->class_id != JS_CLASS_DATAVIEW || dataview_is_oob(obj))
            return fg_fallback(state);
        JSTypedArray *ta = obj->u.typed_array;
        if (ta->track_rab) {
            JSArrayBuffer *abuf = ta->buffer->u.array_buffer;
            res = js_uint32(abuf->byte_length - ta->offset);
        } else {
            res = js_uint32(ta->length);
        }
        break;
    }
    case FG_KIND_AB_BYTELEN:
        if (obj->class_id != e->ab_class_id)
            return fg_fallback(state);
        res = js_uint32(obj->u.array_buffer->byte_length);
        break;
    case FG_KIND_THIS_FIELD: {
        if (obj->is_exotic)
            return fg_fallback(state);
        JSProperty *pr = NULL;
        JSShapeProperty *ps = find_own_property(&pr, obj, e->field1);
        if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
            return fg_fallback(state);
        JSValue val = pr->u.value;
        if (JS_VALUE_GET_TAG(val) == JS_TAG_UNINITIALIZED || JS_IsException(val))
            return fg_fallback(state);
        res = js_dup(val);
        break;
    }
    case FG_KIND_THIS_FIELD_LEN: {
        if (obj->is_exotic)
            return fg_fallback(state);
        JSProperty *pr = NULL;
        JSShapeProperty *ps = find_own_property(&pr, obj, e->field1);
        if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
            return fg_fallback(state);
        JSValue val = pr->u.value;
        int tag = JS_VALUE_GET_TAG(val);
        if (tag == JS_TAG_STRING) {
            res = js_int32(JS_VALUE_GET_STRING(val)->len);
        } else if (tag == JS_TAG_OBJECT) {
            JSObject *sub = JS_VALUE_GET_OBJ(val);
            if (sub->class_id != JS_CLASS_ARRAY || !sub->fast_array || !sub->shape ||
                sub->shape->prop_count < 1 || sub->shape->prop[0].atom != JS_ATOM_length ||
                (sub->shape->prop[0].flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
                return fg_fallback(state);
            JSValue lv = sub->prop[0].u.value;
            int ltag = JS_VALUE_GET_TAG(lv);
            if (ltag != JS_TAG_INT && ltag != JS_TAG_FLOAT64)
                return fg_fallback(state);
            res = lv;
        } else {
            return fg_fallback(state);
        }
        break;
    }
    case FG_KIND_THIS_FIELD_FIELD: {
        if (obj->is_exotic)
            return fg_fallback(state);
        JSProperty *pr = NULL;
        JSShapeProperty *ps = find_own_property(&pr, obj, e->field1);
        if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
            return fg_fallback(state);
        JSValue sub_v = pr->u.value;
        if (!JS_IsObject(sub_v))
            return fg_fallback(state);
        JSObject *sub = JS_VALUE_GET_OBJ(sub_v);
        if (sub->is_exotic)
            return fg_fallback(state);
        ps = find_own_property(&pr, sub, e->field2);
        if (!ps || (ps->flags & JS_PROP_TMASK) != JS_PROP_NORMAL)
            return fg_fallback(state);
        JSValue val = pr->u.value;
        if (JS_VALUE_GET_TAG(val) == JS_TAG_UNINITIALIZED || JS_IsException(val))
            return fg_fallback(state);
        res = js_dup(val);
        break;
    }
    case FG_KIND_CONST:
        res = e->const_val;
        break;
    default:
        return fg_fallback(state);
    }

    sp[-1] = res;
    obj->header.ref_count--;
    pc += 5;
    state->pc = pc;
    frame->sf.cur_pc = pc;
    ctx->interrupt_counter--;
    return 2;
}
