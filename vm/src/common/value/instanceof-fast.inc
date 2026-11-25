/* Epoch-guarded inline cache for native OP_instanceof fast path. */
#if defined(_MSC_VER)
#define QJS_FAST_INSTOF_TLS __declspec(thread)
#else
#define QJS_FAST_INSTOF_TLS _Thread_local
#endif

typedef struct {
    JSObject *ctor;
    JSShape *ctor_shape;
    uint32_t ctor_prop_count;
    uint32_t holder_prop_count;
    uint64_t epoch;
    JSContext *ctx;
    JSObject *holder;
    JSShape *holder_shape;
    JSObject *method;
    uint32_t has_inst_slot;
    uint32_t proto_slot;
    uint8_t holder_depth;
    uint8_t has_proto;
} FastInstOfEntry;

static QJS_FAST_INSTOF_TLS FastInstOfEntry fast_instof_cache[64];

static inline bool fast_instof_holder_live(JSObject *ctor, const JSObject *holder)
{
    JSObject *cur = ctor;
    for (unsigned d = 0; cur && d < 16; d++, cur = cur->shape->proto) {
        if (cur->is_exotic)
            return false;
        if (cur == holder)
            return true;
    }
    return false;
}

static inline int js_fast_instanceof_impl(JSContext *ctx, JSRuntime *rt, JSValue *sp)
{
#ifdef QJS_FAST_INSTANCEOF_NO_DIRECT_DATA
    unsigned mode = 1;
#else
    unsigned mode = __atomic_load_n(&JS_FrameSlowDirectData.mode, __ATOMIC_RELAXED);
    if ((mode & (3 | 64 | 128)) != 1)
        return 0;
#endif
    uint64_t epoch = rt->property_ic_epoch;
    if (ctx->interrupt_counter <= 1 || rt->dump_flags || rt->property_ic_mode != 1 || !epoch)
        return 0;
    JSValue v_val = sp[-2];
    JSValue c_val = sp[-1];
    if (!JS_IsObject(c_val))
        return 0;
    JSObject *ctor = JS_VALUE_GET_OBJ(c_val);
    if ((ctor->class_id != JS_CLASS_BYTECODE_FUNCTION && ctor->class_id != JS_CLASS_C_FUNCTION) ||
        ctor->is_exotic)
        return 0;
    int v_has_rc = JS_VALUE_HAS_REF_COUNT(v_val);
    int v_is_obj = JS_IsObject(v_val);
    JSObject *vobj = v_is_obj ? JS_VALUE_GET_OBJ(v_val) : NULL;
    void *vptr = (!v_is_obj && v_has_rc) ? JS_VALUE_GET_PTR(v_val) : NULL;
    if (vobj == ctor) {
        if (JS_REF_COUNT(ctor) <= 2)
            return 0;
    } else if (v_is_obj) {
        if (JS_REF_COUNT(vobj) <= 1 || JS_REF_COUNT(ctor) <= 1)
            return 0;
    } else if (vptr) {
        if (JS_REF_COUNT(vptr) <= 1 || JS_REF_COUNT(ctor) <= 1)
            return 0;
    } else {
        if (JS_REF_COUNT(ctor) <= 1)
            return 0;
    }

    FastInstOfEntry *e = &fast_instof_cache[(((uintptr_t)ctor >> 4) ^ ((uintptr_t)ctor >> 10) ^
                                             ((uintptr_t)ctor >> 16)) &
                                            63u];
    if (unlikely(!(e->ctor == ctor && e->ctor_shape == ctor->shape &&
                   e->ctor_prop_count == (uint32_t)ctor->shape->prop_count && e->epoch == epoch &&
                   e->ctx == ctx && e->holder &&
                   (e->holder_depth == 0u
                        ? (e->holder == ctor)
                        : (e->holder_depth == 1u
                               ? (ctor->shape->proto == e->holder && !e->holder->is_exotic)
                               : (e->holder_depth == 2u
                                      ? (ctor->shape->proto && !ctor->shape->proto->is_exotic &&
                                         ctor->shape->proto->shape->proto == e->holder &&
                                         !e->holder->is_exotic)
                                      : fast_instof_holder_live(ctor, e->holder)))) &&
                   e->holder->shape == e->holder_shape &&
                   e->holder_prop_count == (uint32_t)e->holder->shape->prop_count &&
                   e->has_inst_slot < e->holder_prop_count &&
                   get_shape_prop(e->holder->shape)[e->has_inst_slot].atom ==
                       JS_ATOM_Symbol_hasInstance &&
                   !(get_shape_prop(e->holder->shape)[e->has_inst_slot].flags & JS_PROP_TMASK) &&
                   JS_IsObject(e->holder->prop[e->has_inst_slot].u.value) &&
                   JS_VALUE_GET_OBJ(e->holder->prop[e->has_inst_slot].u.value) == e->method))) {
        JSObject *walk = ctor;
        JSShapeProperty *sh_hi = NULL;
        JSProperty *pr_hi = NULL;
        unsigned depth;
        for (depth = 0; walk && depth < 16; depth++, walk = walk->shape->proto) {
            if (walk->is_exotic || (walk->class_id != JS_CLASS_OBJECT &&
                                    walk->class_id != JS_CLASS_BYTECODE_FUNCTION &&
                                    walk->class_id != JS_CLASS_C_FUNCTION))
                return 0;
            walk->is_prototype = true;
            sh_hi = find_own_property(&pr_hi, walk, JS_ATOM_Symbol_hasInstance);
            if (sh_hi)
                break;
        }
        if (!walk || depth == 16 || !sh_hi || (sh_hi->flags & JS_PROP_TMASK) ||
            !JS_IsObject(pr_hi->u.value))
            return 0;
        JSObject *method = JS_VALUE_GET_OBJ(pr_hi->u.value);
        if (method->class_id != JS_CLASS_C_FUNCTION || method->u.cfunc.cproto != JS_CFUNC_generic ||
            method->u.cfunc.magic != 0 || method->u.cfunc.length != 1 ||
            method->u.cfunc.c_function.generic != &js_function_hasInstance)
            return 0;
        JSProperty *pr_proto = NULL;
        JSShapeProperty *sh_proto = find_own_property(&pr_proto, ctor, JS_ATOM_prototype);
        uint8_t has_p = 0;
        uint32_t p_slot = 0;
        if (sh_proto && !(sh_proto->flags & JS_PROP_TMASK)) {
            has_p = 1;
            p_slot = (uint32_t)(pr_proto - ctor->prop);
        }
        e->ctor = ctor;
        e->ctor_shape = ctor->shape;
        e->ctor_prop_count = (uint32_t)ctor->shape->prop_count;
        e->epoch = epoch;
        e->ctx = ctx;
        e->holder = walk;
        e->holder_shape = walk->shape;
        e->holder_prop_count = (uint32_t)walk->shape->prop_count;
        e->holder_depth = (uint8_t)depth;
        e->method = method;
        e->has_inst_slot = (uint32_t)(pr_hi - walk->prop);
        e->proto_slot = p_slot;
        e->has_proto = has_p;
    }

    int result = 0;
    if (v_is_obj) {
        if (!e->has_proto || e->proto_slot >= e->ctor_prop_count ||
            get_shape_prop(ctor->shape)[e->proto_slot].atom != JS_ATOM_prototype ||
            (get_shape_prop(ctor->shape)[e->proto_slot].flags & JS_PROP_TMASK))
            return 0;
        JSValue pv = ctor->prop[e->proto_slot].u.value;
        if (!JS_IsObject(pv))
            return 0;
        JSObject *target = JS_VALUE_GET_OBJ(pv);
        JSObject *w = vobj;
        unsigned d;
        for (d = 0; d < 32; d++) {
            if (unlikely(w->class_id == JS_CLASS_PROXY))
                return 0;
            w = w->shape->proto;
            if (!w) {
                result = 0;
                break;
            }
            if (w == target) {
                result = 1;
                break;
            }
        }
        if (d == 32)
            return 0;
    }

    --ctx->interrupt_counter;
    if (vobj == ctor) {
        JS_REF_COUNT(ctor) -= 2;
    } else {
        if (v_is_obj) {
            --JS_REF_COUNT(vobj);
        } else if (vptr) {
            --JS_REF_COUNT(vptr);
        }
        --JS_REF_COUNT(ctor);
    }
    sp[-2] = JS_MKVAL(JS_TAG_BOOL, result);
#ifndef QJS_FAST_INSTANCEOF_NO_DIRECT_DATA
    if (mode & 4)
        __atomic_fetch_add(&JS_FrameSlowDirectData.hits, 1, __ATOMIC_RELAXED);
#else
    (void)mode;
#endif
    return 1;
}

#ifdef QJS_FAST_INSTANCEOF_STATE_ENTRY
__attribute__((visibility("hidden"), section(".text.qjs_frame"),
               noipa)) int JS_FastInstanceOf(JSFrameRegisterState *state, JSValue *sp)
{
    return js_fast_instanceof_impl(state->frame->bytecode->realm, state->rt, sp);
}
#endif

#ifdef QJS_FAST_INSTANCEOF_CTX_ENTRY
static inline int JS_FastInstanceOfContext(JSContext *ctx, JSValue *sp)
{
    return js_fast_instanceof_impl(ctx, ctx->rt, sp);
}
#endif
