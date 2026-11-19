/* Cold IC-owned reference release and prototype invalidation.
 * Native object builds compile this in an ordinary C module; PORTABLE includes it in core.
 * Keep owner protection and detach-before-release ordering identical in both.
 */
bool js_property_ic_extend_site(JSContext *ctx, JSPropertyIC *ic, JSPropertyICSite *site)
{
    unsigned capacity = site->capacity ? site->capacity : JS_IC_INLINE_WAYS;
    unsigned next_capacity;
    size_t bytes;
    JSPropertyICWay *secondary;
    if (site->count >= JS_IC_MAX_WAYS)
        return false;
    if (site->count < capacity)
        return true;
    /* A fresh process control declines only additional growth. Existing four
     * native probes, ordinary learning and give-up policy remain available. */
    if (getenv("QJS_DISABLE_IC_ADAPTIVE_WAYS"))
        return false;
    next_capacity = capacity * 2;
    assert(site->count == capacity && site->secondary &&
           (capacity == JS_IC_INLINE_WAYS || capacity == 8));
    bytes = ic->bytes;
    for (unsigned i = 0; i < ic->site_count; i++) {
        JSPropertyICSite *other = &ic->sites[i];
        if (other->secondary) {
            unsigned allocated = other->capacity ? other->capacity : JS_IC_INLINE_WAYS;
            bytes += (allocated - 1) * sizeof(JSPropertyICWay);
        }
    }
    if (bytes > JS_IC_MAX_BYTES ||
        (next_capacity - capacity) * sizeof(JSPropertyICWay) > JS_IC_MAX_BYTES - bytes)
        return false;
    /* Runtime raw realloc never triggers GC or throws an exception in this
     * pinned source. Failure leaves all old ways and references untouched. */
    secondary =
        js_realloc_rt(ctx->rt, site->secondary, (next_capacity - 1) * sizeof(JSPropertyICWay));
    if (!secondary)
        return false;
    memset(secondary + capacity - 1, 0, (next_capacity - capacity) * sizeof(JSPropertyICWay));
    site->secondary = secondary;
    site->capacity = (uint8_t)next_capacity;
    return true;
}

void js_property_ic_release_cached_shape(JSRuntime *rt, JSShape *shape)
{
    uint32_t refs;
    if (!shape)
        return;
    refs = js_property_ic_shape_refs(shape);
    assert(refs != 0);
    js_property_ic_set_shape_refs(shape, refs - 1);
    js_property_ic_release_shape_ref(rt, shape);
}

static void js_ic_evict_group(JSRuntime *rt, JSObject *proto)
{
    JSPropertyIC *ic, *next;
    uint32_t i, j;
    /* Dropping a shape can destroy a prototype which owns a cached function.
     * Protect every metadata owner until the full traversal has completed.
     * No allocation, persistent root, JS call or ownership change survives it. */
    for (ic = rt->property_ic_list; ic; ic = ic->next)
        ic->owner->header.ref_count++;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        for (i = 0; i < ic->site_count; i++) {
            JSPropertyICSite *site = &ic->sites[i];
            for (j = 0; j < site->count;) {
                JSPropertyICWay *way = js_ic_way(site, j);
                JSPropertyICWay old;
                if (!way->shape || way->shape->proto != proto) {
                    j++;
                    continue;
                }
                old = *way;
                *way = *js_ic_way(site, --site->count);
                memset(js_ic_way(site, site->count), 0, sizeof(*way));
                site->churn = 0;
                site->reserved2++;
                js_property_ic_release_cached_shape(rt, old.transition);
                js_property_ic_release_cached_shape(rt, old.shape);
            }
        }
    }
    for (ic = rt->property_ic_list; ic; ic = next) {
        JSFunctionBytecode *owner = ic->owner;
        next = ic->next; /* Every not-yet-visited owner is still protected. */
        JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_FUNCTION_BYTECODE, owner));
    }
}

/* No allocation,release,GC or dereference of the borrowed cell itself.
 * owner unlinks its slab before releasing realm,so a linked realm is valid.
 * Structural hooks run before any realloc,descriptor conversion,compaction
 * or prototype change,including later-OOM paths. Free hooks run before values.
 */
void js_property_ic_binding_invalidate(JSRuntime *rt, JSObject *holder)
{
    JSPropertyIC *ic;
    uint32_t i;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        JSContext *realm = ic->binding_realm;
        if (!realm || (JS_VALUE_GET_OBJ(realm->global_var_obj) != holder &&
                       JS_VALUE_GET_OBJ(realm->global_obj) != holder))
            continue;
        ic->binding_realm = NULL;
        for (i = 0; i < ic->map_count; ++i)
            if ((uintptr_t)ic->map[i] & 1)
                ic->map[i] = NULL;
    }
}

void js_property_ic_prototype_free(JSRuntime *rt, JSObject *proto)
{
    js_property_ic_binding_invalidate(rt, proto);
    if (rt->property_ic_list && !(rt->property_ic_gc_mode & JS_IC_RETAIN_ORPHANS))
        js_ic_evict_group(rt, proto);
}
