/* By-PC resolved cells borrowed from the owning realm's current globals.
 * Low bits:1=lexical(TDZ),3=global own data,2=declined. No retained JSValue.
 * Armed global objects invalidate all cells before structural modification;
 * ordinary value replacement writes the same cell and retains original RC.
 */
static JSValue JS_GetGlobalVar(JSContext *, JSAtom, bool);
static JSPropertyICSite *js_ic_site(JSContext *, JSFunctionBytecode *, const uint8_t *);
_Static_assert(_Alignof(JSProperty) >= 4 && offsetof(JSProperty, u.value) == 0,
               "binding cell tags require aligned ordinary property values");

static uintptr_t js_global_binding_cell_resolve(JSContext *ctx, JSPropertyIC *ic, JSAtom atom)
{
    JSObject *lexical = JS_VALUE_GET_OBJ(ctx->global_var_obj);
    JSObject *global = JS_VALUE_GET_OBJ(ctx->global_obj);
    JSShapeProperty *prs;
    JSProperty *pr;
    uintptr_t kind = 1;
    /* The same mutation/free hooks must protect both ordinary global objects.
     * Exotic/global replacement extensions retain the original lookup. */
    if (lexical->class_id != JS_CLASS_OBJECT || lexical->is_exotic ||
        global->class_id != JS_CLASS_OBJECT || global->is_exotic)
        return 2;
    prs = find_own_property(&pr, lexical, atom);
    if (!prs) {
        prs = find_own_property(&pr, global, atom);
        kind = 3;
    }
    if (!prs || (prs->flags & JS_PROP_TMASK))
        return 2;
    /* Adding a lexical shadow must also invalidate cached global own data.
     * Arming is sticky,as for prototype ICs. It adds no root/reference. */
    lexical->is_prototype = true;
    global->is_prototype = true;
    ic->binding_realm = ctx;
    return (uintptr_t)&pr->u.value | kind;
}

#if defined(_MSC_VER)
#define BINDING_CELL_INLINE static __forceinline
#elif defined(__GNUC__)
#define BINDING_CELL_INLINE static inline __attribute__((always_inline))
#else
#define BINDING_CELL_INLINE static inline
#endif
BINDING_CELL_INLINE JSValue js_global_binding_cell_get(JSContext *ctx, JSFunctionBytecode *b,
                                                       const uint8_t *pc, JSAtom atom,
                                                       bool throw_ref_error)
{
    JSPropertyIC *ic = b->property_ic;
    uintptr_t entry;
    uint32_t pos;
    JSValue value;
    /* Native own-method lookup can bypass by-id IC creation entirely. Admit
     * the same bounded slab once,at an already published global slow read.
     * No-by-id/oversized functions and optional OOM retain the old lookup. */
    if (!ic && ctx->rt->property_ic_mode == 1 && ctx == b->realm) {
        (void)js_ic_site(ctx, b, pc);
        ic = b->property_ic;
    }
    if ((uintptr_t)ic <= 1 || ctx->rt->property_ic_mode != 1 || ctx != b->realm)
        return JS_GetGlobalVar(ctx, atom, throw_ref_error);
    pos = (uint32_t)(pc - b->byte_code_buf) / 4;
    if (pos >= ic->map_count)
        return JS_GetGlobalVar(ctx, atom, throw_ref_error);
    entry = (uintptr_t)ic->map[pos];
    if (!entry) {
        /* The generic read may initialize a lazy global or reenter JS. Learn
         * its current cell only afterwards,from freshly acquired metadata. */
        value = JS_GetGlobalVar(ctx, atom, throw_ref_error);
        if (JS_IsException(value))
            return value;
        ic = b->property_ic;
        if ((uintptr_t)ic > 1 && ctx->rt->property_ic_mode == 1 && pos < ic->map_count &&
            !ic->map[pos]) {
            entry = getenv("QJS_DISABLE_FRAME_BINDING_CELL")
                        ? 2
                        : js_global_binding_cell_resolve(ctx, ic, atom);
            ic->map[pos] = (JSPropertyICSite *)entry;
        }
        return value;
    }
    if (!(entry & 1))
        return JS_GetGlobalVar(ctx, atom, throw_ref_error);
    value = *(JSValue *)(entry & ~(uintptr_t)3);
    if (unlikely(JS_IsUninitialized(value)) && !(entry & 2))
        return JS_ThrowReferenceErrorUninitialized(ctx, atom);
    return js_dup(value);
}

JSValue JS_FrameGlobalBindingCellGet(JSContext *ctx, JSFunctionBytecode *b, const uint8_t *pc,
                                     JSAtom atom, bool throw_ref_error)
{
    return js_global_binding_cell_get(ctx, b, pc, atom, throw_ref_error);
}
#undef BINDING_CELL_INLINE
