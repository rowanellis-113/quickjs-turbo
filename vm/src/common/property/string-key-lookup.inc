/* Atomless string-key dynamic property lookup, own writable overwrite, and 'in' fast paths.
 * Strictly guards against exotic receivers/prototypes (except ordinary Array for non-index
 * lookups in GetPropertyValue), numeric array-index strings, and accessor/varref/autoinit slots. */
#ifdef CONFIG_ATOMICS
static _Atomic unsigned char js_string_key_lookup_mode;
static inline bool js_string_key_lookup_enabled(void)
{
    unsigned char m = atomic_load_explicit(&js_string_key_lookup_mode, memory_order_relaxed);
    if (unlikely(!m)) {
        m = getenv("QJS_DISABLE_STRING_KEY_FAST") ? 2 : 1;
        atomic_store_explicit(&js_string_key_lookup_mode, m, memory_order_relaxed);
    }
    return m == 1;
}
#else
static inline bool js_string_key_lookup_enabled(void)
{
    return getenv("QJS_DISABLE_STRING_KEY_FAST") == NULL;
}
#endif

typedef struct StrKeySlotCache {
    uintptr_t rt_id;
    uintptr_t shape_id;
    uint32_t hash;
    uint32_t atom;
    uint32_t slot;
    uint32_t len;
} StrKeySlotCache;

static _Thread_local StrKeySlotCache js_str_key_cache[256];

static inline bool js_str_eq_fast(JSString *a, JSString *b)
{
    if (a->len != b->len)
        return false;
    if (likely(!a->is_wide_char && !b->is_wide_char))
        return a->len == 0 || memcmp(str8(a), str8(b), a->len) == 0;
    return js_string_memcmp(a, b, a->len) == 0;
}

static inline JSAtom js_find_existing_string_atom(JSRuntime *rt, JSString *str,
                                                  bool *may_be_numeric)
{
    uint32_t h, i;
    JSAtomStruct *p;
    if (str->atom_type == JS_ATOM_TYPE_STRING) {
        *may_be_numeric = false;
        return js_get_atom_index(rt, str);
    }
    if (unlikely(str->atom_type != 0)) {
        *may_be_numeric = true;
        return JS_ATOM_NULL;
    }
    if (str->len > 0) {
        uint32_t c0 = str->is_wide_char ? str16(str)[0] : str8(str)[0];
        if (c0 >= '0' && c0 <= '9') {
            uint32_t n;
            if (is_num_string(&n, str) && n <= JS_ATOM_MAX_INT) {
                *may_be_numeric = true;
                return __JS_AtomFromUInt32(n);
            }
        }
    }
    *may_be_numeric = false;
    h = str->hash;
    if (!h) {
        h = hash_string(str, JS_ATOM_TYPE_STRING) & JS_ATOM_HASH_MASK;
        str->hash = h;
    }
    i = rt->atom_hash[h & (rt->atom_hash_size - 1)];
    while (i != 0) {
        p = rt->atom_array[i];
        if (p->hash == h && p->atom_type == JS_ATOM_TYPE_STRING && js_str_eq_fast(p, str)) {
            return i;
        }
        i = p->hash_next;
    }
    return JS_ATOM_NULL;
}

static inline bool js_str_key_cache_probe(JSRuntime *rt, JSObject *obj, JSString *str,
                                          uint32_t *out_slot, uint32_t *out_idx, uint32_t *out_h)
{
    if (unlikely(obj->is_exotic || str->is_wide_char))
        return false;
    JSShape *sh = obj->shape;
    uint32_t h;
    JSAtom direct_atom = JS_ATOM_NULL;
    if (str->atom_type == JS_ATOM_TYPE_STRING) {
        direct_atom = js_get_atom_index(rt, str);
        h = (uint32_t)direct_atom;
    } else if (likely(str->atom_type == 0)) {
        if (str->len > 0) {
            uint8_t c0 = str8(str)[0];
            if (c0 >= '0' && c0 <= '9')
                return false;
        }
        h = str->hash;
        if (!h) {
            h = hash_string(str, JS_ATOM_TYPE_STRING) & JS_ATOM_HASH_MASK;
            str->hash = h;
        }
    } else {
        return false;
    }
    uint32_t idx = (uint32_t)((((uintptr_t)sh >> 5) ^ h ^ (h >> 8)) & 255u);
    *out_idx = idx;
    *out_h = h;
    StrKeySlotCache *e = &js_str_key_cache[idx];
    if (e->rt_id == (uintptr_t)rt && e->shape_id == (uintptr_t)sh && e->hash == h &&
        e->len == str->len && e->slot < (uint32_t)sh->prop_count) {
        JSAtom atom = e->atom;
        JSShapeProperty *prs = &get_shape_prop(sh)[e->slot];
        if (likely(prs->atom == atom && !(prs->flags & JS_PROP_TMASK))) {
            if (direct_atom != JS_ATOM_NULL) {
                if (likely(atom == direct_atom)) {
                    *out_slot = e->slot;
                    return true;
                }
            } else if (likely(atom > 0 && atom < (uint32_t)rt->atom_size)) {
                JSAtomStruct *ap = rt->atom_array[atom];
                if (likely(!atom_is_free(ap) && ap->atom_type == JS_ATOM_TYPE_STRING &&
                           !ap->is_wide_char && ap->len == str->len &&
                           (str->len == 0 || memcmp(str8(ap), str8(str), str->len) == 0))) {
                    *out_slot = e->slot;
                    return true;
                }
            }
        }
    }
    return false;
}

static no_inline bool js_try_get_property_string(JSContext *ctx, JSValueConst this_obj,
                                                 JSValue prop, JSValue *out)
{
    JSRuntime *rt = ctx->rt;
    JSObject *obj, *cur;
    JSString *str;
    JSAtom atom;
    bool may_num;
    uint32_t c_slot = 0, c_idx = 0, c_h = 0;
    bool can_cache = false;
    if (!js_string_key_lookup_enabled())
        return false;
    obj = JS_VALUE_GET_OBJ(this_obj);
    str = JS_VALUE_GET_STRING(prop);
    if (!obj->is_exotic && !str->is_wide_char &&
        (str->atom_type == 0 || str->atom_type == JS_ATOM_TYPE_STRING)) {
        if (js_str_key_cache_probe(rt, obj, str, &c_slot, &c_idx, &c_h)) {
            JSValue v = obj->prop[c_slot].u.value;
            if (likely(!JS_IsUninitialized(v))) {
                *out = js_dup(v);
                JS_FreeValue(ctx, prop);
                return true;
            }
        }
        can_cache = (str->atom_type == JS_ATOM_TYPE_STRING) ||
                    !(str->len > 0 && str8(str)[0] >= '0' && str8(str)[0] <= '9');
    }
    atom = js_find_existing_string_atom(rt, str, &may_num);
    if (may_num) {
        if (atom != JS_ATOM_NULL &&
            js_get_fast_array_element(ctx, obj, __JS_AtomToUInt32(atom), out)) {
            JS_FreeValue(ctx, prop);
            return true;
        }
        return false;
    }
    if (unlikely(__JS_AtomIsTaggedInt(atom)))
        return false;
    if (atom == JS_ATOM_NULL) {
        cur = obj;
        for (unsigned d = 0; d < 16 && cur; d++, cur = cur->shape->proto) {
            if (cur->is_exotic && cur->class_id != JS_CLASS_ARRAY)
                return false;
        }
        if (cur == NULL) {
            JS_FreeValue(ctx, prop);
            *out = JS_UNDEFINED;
            return true;
        }
        return false;
    }
    cur = obj;
    for (unsigned d = 0; d < 16 && cur; d++, cur = cur->shape->proto) {
        JSProperty *pr;
        JSShapeProperty *prs = find_own_property(&pr, cur, atom);
        if (prs) {
            if (likely(!(prs->flags & JS_PROP_TMASK) && !JS_IsUninitialized(pr->u.value))) {
                if (can_cache && cur == obj) {
                    StrKeySlotCache *e = &js_str_key_cache[c_idx];
                    e->rt_id = (uintptr_t)rt;
                    e->shape_id = (uintptr_t)obj->shape;
                    e->hash = c_h;
                    e->atom = atom;
                    e->slot = (uint32_t)(pr - obj->prop);
                    e->len = str->len;
                }
                *out = js_dup(pr->u.value);
                JS_FreeValue(ctx, prop);
                return true;
            }
            return false;
        }
        if (cur->is_exotic && cur->class_id != JS_CLASS_ARRAY)
            return false;
    }
    if (cur == NULL) {
        JS_FreeValue(ctx, prop);
        *out = JS_UNDEFINED;
        return true;
    }
    return false;
}

static no_inline bool js_try_set_property_string(JSContext *ctx, JSValueConst this_obj,
                                                 JSValue prop, JSValue val, int flags, int *out_ret)
{
    JSRuntime *rt = ctx->rt;
    JSObject *obj;
    JSString *str;
    JSAtom atom;
    bool may_num;
    JSProperty *pr;
    JSShapeProperty *prs;
    uint32_t c_slot = 0, c_idx = 0, c_h = 0;
    bool can_cache = false;
    (void)flags;
    if (!js_string_key_lookup_enabled())
        return false;
    obj = JS_VALUE_GET_OBJ(this_obj);
    if (obj->is_exotic)
        return false;
    str = JS_VALUE_GET_STRING(prop);
    if (!str->is_wide_char && (str->atom_type == 0 || str->atom_type == JS_ATOM_TYPE_STRING)) {
        if (js_str_key_cache_probe(rt, obj, str, &c_slot, &c_idx, &c_h)) {
            prs = &get_shape_prop(obj->shape)[c_slot];
            if (likely((prs->flags & (JS_PROP_TMASK | JS_PROP_WRITABLE | JS_PROP_LENGTH)) ==
                       JS_PROP_WRITABLE)) {
                set_value(ctx, &obj->prop[c_slot].u.value, val);
                JS_FreeValue(ctx, prop);
                *out_ret = true;
                return true;
            }
        }
        can_cache = (str->atom_type == JS_ATOM_TYPE_STRING) ||
                    !(str->len > 0 && str8(str)[0] >= '0' && str8(str)[0] <= '9');
    }
    atom = js_find_existing_string_atom(rt, str, &may_num);
    if (may_num || atom == JS_ATOM_NULL || unlikely(__JS_AtomIsTaggedInt(atom)))
        return false;
    prs = find_own_property(&pr, obj, atom);
    if (likely(prs && (prs->flags & (JS_PROP_TMASK | JS_PROP_WRITABLE | JS_PROP_LENGTH)) ==
                          JS_PROP_WRITABLE)) {
        if (can_cache) {
            StrKeySlotCache *e = &js_str_key_cache[c_idx];
            e->rt_id = (uintptr_t)rt;
            e->shape_id = (uintptr_t)obj->shape;
            e->hash = c_h;
            e->atom = atom;
            e->slot = (uint32_t)(pr - obj->prop);
            e->len = str->len;
        }
        set_value(ctx, &pr->u.value, val);
        JS_FreeValue(ctx, prop);
        *out_ret = true;
        return true;
    }
    return false;
}

static no_inline bool js_try_has_property_string(JSContext *ctx, JSValueConst obj_val,
                                                 JSValue key_val, int *out_ret)
{
    JSObject *cur;
    JSAtom atom;
    bool may_num;
    if (!js_string_key_lookup_enabled())
        return false;
    atom = js_find_existing_string_atom(ctx->rt, JS_VALUE_GET_STRING(key_val), &may_num);
    if (may_num || unlikely(__JS_AtomIsTaggedInt(atom)))
        return false;
    cur = JS_VALUE_GET_OBJ(obj_val);
    for (unsigned d = 0; d < 16 && cur; d++, cur = cur->shape->proto) {
        if (cur->is_exotic)
            return false;
        if (atom != JS_ATOM_NULL) {
            JSProperty *pr;
            JSShapeProperty *prs = find_own_property(&pr, cur, atom);
            if (prs) {
                *out_ret = 1;
                return true;
            }
        }
    }
    if (cur == NULL) {
        *out_ret = 0;
        return true;
    }
    return false;
}
