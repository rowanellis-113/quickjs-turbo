/* Property IC variant routing resize transitions through inline property storage. */
#define JS_IC_MAX_SITES 1024
#define JS_IC_DISABLED ((JSPropertyIC *)(uintptr_t)1)
#define JS_IC_GC_SHAPE 0x100u
#define JS_IC_GC_TARGET 0x200u
#define JS_IC_KIND_MASK 0xffu
#include "src/common/property/global-binding-cell.inc"
static const uint8_t js_ic_opcode_sizes[] = {
#define DEF(id, size, n_pop, n_push, fmt) size,
#define def(id, size, n_pop, n_push, fmt)
#include "quickjs-opcode.h"
#undef DEF
#undef def
};

static JSPropertyICSite *js_ic_site(JSContext *ctx, JSFunctionBytecode *b, const uint8_t *pc)
{
    JSPropertyIC *ic = b->property_ic;
    uint32_t pos, count, n, map_count, index;
    size_t map_bytes, bytes;
    if (ctx->rt->property_ic_mode != 1 || ic == JS_IC_DISABLED)
        return NULL;
    if (!ic) {
        count = 0;
        for (pos = 0; pos < (uint32_t)b->byte_code_len; pos += n) {
            uint32_t op = b->byte_code_buf[pos];
            if (op >= OP_COUNT)
                return NULL;
            n = js_ic_opcode_sizes[op];
            if (!n || n > (uint32_t)b->byte_code_len - pos)
                return NULL;
            if (op == OP_get_field || op == OP_get_field2 || op == OP_put_field)
                count++;
        }
        if (!count || count > JS_IC_MAX_SITES) {
            b->property_ic = JS_IC_DISABLED;
            return NULL;
        }
        map_count = ((uint32_t)b->byte_code_len + 3) / 4;
        map_bytes = (size_t)map_count * sizeof(JSPropertyICSite *);
        map_bytes = (map_bytes + 7) & ~(size_t)7;
        bytes = sizeof(*ic) + map_bytes + (size_t)count * sizeof(JSPropertyICSite);
        if (bytes > JS_IC_MAX_BYTES) {
            b->property_ic = JS_IC_DISABLED;
            return NULL;
        }
        ic = js_calloc_rt(ctx->rt, 1, bytes);
        if (!ic) {
            b->property_ic = JS_IC_DISABLED;
            return NULL;
        }
        ic->sites = (JSPropertyICSite *)((uint8_t *)(ic + 1) + map_bytes);
        ic->map_count = map_count;
        ic->site_count = count;
        ic->bytes = bytes;
        assert(!((uintptr_t)b->byte_code_buf & 3));
        bool bind_globals = b->realm == ctx && !getenv("QJS_DISABLE_FRAME_BINDING_CELL");
        index = 0;
        for (pos = 0; pos < (uint32_t)b->byte_code_len;
             pos += js_ic_opcode_sizes[b->byte_code_buf[pos]]) {
            uint32_t op = b->byte_code_buf[pos];
            if (op == OP_get_field || op == OP_get_field2 || op == OP_put_field)
                ic->map[pos / 4] = &ic->sites[index++];
            else if (bind_globals && (op == OP_get_var || op == OP_get_var_undef)) {
                assert(!ic->map[pos / 4]);
                uintptr_t binding =
                    js_global_binding_cell_resolve(ctx, ic, get_u32(b->byte_code_buf + pos + 1));
                if (binding != 2)
                    ic->map[pos / 4] = (JSPropertyICSite *)binding;
            }
        }
        ic->owner = b;
        ic->next = ctx->rt->property_ic_list;
        if (ic->next)
            ic->next->prev = ic;
        ctx->rt->property_ic_list = ic;
        b->property_ic = ic;
    }
    pos = (uint32_t)(pc - b->byte_code_buf) / 4;
    if (pos >= ic->map_count)
        return NULL;
    return ic->map[pos];
}

static void js_ic_release_way(JSRuntime *rt, JSPropertyICWay *way)
{
    JSPropertyICWay old = *way;
    memset(way, 0, sizeof(*way));
    js_property_ic_release_cached_shape(rt, old.transition);
    js_property_ic_release_cached_shape(rt, old.shape);
}

static JSPropertyICWay *js_ic_way(JSPropertyICSite *site, unsigned index)
{
    return index ? &site->secondary[index - 1] : &site->primary;
}

#ifndef QJS_PROPERTY_IC_LIFETIME_MODULE
#include "src/common/property/property-ic-lifetime.inc"
#endif

void js_property_ic_shape_released(JSRuntime *rt, JSShape *shape)
{
    if (!shape->proto || (shape->is_hashed & JS_IC_PROTO_WEAK) ||
        (rt->property_ic_gc_mode & (JS_IC_GC_SCAN | JS_IC_RETAIN_ORPHANS)))
        return;
    shape->is_hashed |= JS_IC_PROTO_WEAK;
    JS_FreeValueRT(rt, JS_MKPTR(JS_TAG_OBJECT, shape->proto));
}

void js_property_ic_release_shape_ref(JSRuntime *rt, JSShape *shape)
{
    if (shape)
        js_free_shape(rt, shape);
}

static void js_ic_install(JSContext *ctx, JSFunctionBytecode *b, JSPropertyICSite *site,
                          JSPropertyICWay *fresh)
{
    unsigned index;
    JSPropertyICWay old;
    if (!site || site->megamorphic)
        return;
    if (js_property_ic_shape_refs(fresh->shape) == JS_IC_MAX_SHAPE_REFS ||
        (fresh->transition && js_property_ic_shape_refs(fresh->transition) == JS_IC_MAX_SHAPE_REFS))
        return;
    assert(!fresh->transition || fresh->transition->proto == fresh->shape->proto);
    assert(!(fresh->shape->is_hashed & JS_IC_PROTO_WEAK));
    if (fresh->shape->proto)
        fresh->shape->proto->is_prototype = true;
    for (index = 0; index < site->count; index++)
        if (js_ic_way(site, index)->shape == fresh->shape)
            break;
    if (index == site->count) {
        if (site->count < JS_IC_INLINE_WAYS ||
            js_property_ic_extend_site(ctx, b->property_ic, site)) {
            if (site->count == 1 && !site->secondary) {
                site->secondary = js_calloc_rt(ctx->rt, 3, sizeof(JSPropertyICWay));
                if (!site->secondary)
                    return;
                site->capacity = JS_IC_INLINE_WAYS;
            }
            site->count++;
        } else {
            if (++site->churn >= 12) {
                site->megamorphic = 1;
                for (index = 0; index < site->count; index++)
                    js_ic_release_way(ctx->rt, js_ic_way(site, index));
                site->count = 0;
                return;
            }
            index = site->next++ & (site->count - 1);
        }
    }
    old = *js_ic_way(site, index);
    fresh->shape = js_dup_shape(fresh->shape);
    js_property_ic_set_shape_refs(fresh->shape, js_property_ic_shape_refs(fresh->shape) + 1);
    if (fresh->transition) {
        fresh->transition = js_dup_shape(fresh->transition);
        js_property_ic_set_shape_refs(fresh->transition,
                                      js_property_ic_shape_refs(fresh->transition) + 1);
    }
    *js_ic_way(site, index) = *fresh;
    if (index) {
        JSPropertyICWay swap = site->primary;
        site->primary = *js_ic_way(site, index);
        *js_ic_way(site, index) = swap;
    }
    js_property_ic_release_cached_shape(ctx->rt, old.transition);
    js_property_ic_release_cached_shape(ctx->rt, old.shape);
}

static JSPropertyICWay *js_ic_match(JSRuntime *rt, JSPropertyICSite *site, JSShape *shape)
{
    unsigned i;
    if (!site || site->megamorphic)
        return NULL;
    for (i = 0; i < site->count; i++) {
        JSPropertyICWay *way = js_ic_way(site, i);
        if (way->shape != shape)
            continue;
        if (way->kind != JS_IC_OWN && way->kind != JS_IC_REPLACE &&
            (!rt->property_ic_epoch || way->epoch != rt->property_ic_epoch))
            continue;
        if (i) {
            JSPropertyICWay swap = site->primary;
            site->primary = *way;
            *way = swap;
        }
        return &site->primary;
    }
    return NULL;
}

JSValue js_property_ic_get(JSContext *ctx, JSFunctionBytecode *b, const uint8_t *pc,
                           JSValueConst obj, JSAtom atom)
{
    JSPropertyICSite *site;
    JSPropertyICWay fresh = {0}, *way;
    JSObject *receiver, *p;
    JSProperty *pr;
    JSShapeProperty *prs;
    uint32_t depth = 0;
    bool cacheable;
    if (JS_VALUE_GET_TAG(obj) != JS_TAG_OBJECT)
        return JS_GetPropertyInternal(ctx, obj, atom, obj, false);
    receiver = JS_VALUE_GET_OBJ(obj);
    site = js_ic_site(ctx, b, pc);
    way = js_ic_match(ctx->rt, site, receiver->shape);
    if (way && way->kind != JS_IC_OWN && receiver->is_exotic)
        way = NULL;
    if (way) {
        if (way->kind == JS_IC_UNSET)
            return JS_UNDEFINED;
        p = way->kind == JS_IC_OWN ? receiver : way->holder;
        return js_dup(p->prop[way->slot].u.value);
    }
    cacheable =
        site && !site->megamorphic && receiver->shape->is_hashed && !__JS_AtomIsTaggedInt(atom);
    p = receiver;
    for (;;) {
        if (cacheable && p != receiver)
            p->is_prototype = true;
        prs = find_own_property(&pr, p, atom);
        if (prs) {
            if (prs->flags & JS_PROP_TMASK)
                break;
            if (cacheable && (p == receiver || ctx->rt->property_ic_epoch)) {
                fresh.shape = receiver->shape;
                fresh.slot = (uint32_t)(pr - p->prop);
                fresh.kind = p == receiver ? JS_IC_OWN : JS_IC_PROTO;
                fresh.holder = p == receiver ? NULL : p;
                fresh.epoch = ctx->rt->property_ic_epoch;
                JSValue result = js_dup(pr->u.value);
                js_ic_install(ctx, b, site, &fresh);
                return result;
            }
            return js_dup(pr->u.value);
        }
        if (p->is_exotic)
            break;
        if (++depth > 32)
            cacheable = false;
        p = p->shape->proto;
        if (!p) {
            if (cacheable && ctx->rt->property_ic_epoch) {
                fresh.shape = receiver->shape;
                fresh.kind = JS_IC_UNSET;
                fresh.epoch = ctx->rt->property_ic_epoch;
                js_ic_install(ctx, b, site, &fresh);
            }
            return JS_UNDEFINED;
        }
    }
    return JS_GetPropertyInternal(ctx, obj, atom, obj, false);
}

static bool js_ic_can_transition(JSContext *ctx, JSObject *receiver, JSAtom atom)
{
    JSObject *p = receiver->shape->proto;
    JSProperty *pr;
    JSShapeProperty *prs;
    unsigned depth = 0;
    if (!ctx->rt->property_ic_epoch || !receiver->extensible || receiver->is_exotic ||
        receiver->is_prototype || !receiver->shape->is_hashed || __JS_AtomIsTaggedInt(atom))
        return false;
    while (p) {
        p->is_prototype = true;
        if (++depth > 32)
            return false;
        prs = find_own_property(&pr, p, atom);
        if (prs)
            return (prs->flags & (JS_PROP_TMASK | JS_PROP_WRITABLE | JS_PROP_LENGTH)) ==
                   JS_PROP_WRITABLE;
        if (p->is_exotic)
            return false;
        p = p->shape->proto;
    }
    return true;
}

int js_property_ic_put(JSContext *ctx, JSFunctionBytecode *b, const uint8_t *pc, JSValueConst obj,
                       JSAtom atom, JSValue value)
{
    JSPropertyICSite *site;
    JSPropertyICWay fresh = {0}, *way;
    JSObject *p;
    JSShape *old;
    JSProperty *pr;
    JSShapeProperty *prs;
    int slot;
    if (JS_VALUE_GET_TAG(obj) != JS_TAG_OBJECT)
        return JS_SetPropertyInternal2(ctx, obj, atom, value, obj, JS_PROP_THROW_STRICT);
    p = JS_VALUE_GET_OBJ(obj);
    site = js_ic_site(ctx, b, pc);
    way = js_ic_match(ctx->rt, site, p->shape);
    if (way) {
        if (way->kind == JS_IC_REPLACE) {
            set_value(ctx, &p->prop[way->slot].u.value, value);
            return true;
        }
        if ((way->kind == JS_IC_TRANSITION || way->kind == JS_IC_TRANSITION_RESIZE) &&
            p->extensible && !p->is_exotic && !p->is_prototype) {
            if (way->kind == JS_IC_TRANSITION_RESIZE) {
                JSProperty *props = qjs_inline_property_realloc(
                    ctx, p, (size_t)way->transition->prop_size * sizeof(p->prop[0]));
                if (!props) {
                    JS_FreeValue(ctx, value);
                    return -1;
                }
                p->prop = props;
            }
            old = p->shape;
            p->shape = js_dup_shape(way->transition);
            p->prop[way->slot].u.value = value;
            js_free_shape(ctx->rt, old);
            return true;
        }
    }
    prs = find_own_property(&pr, p, atom);
    if (prs) {
        if ((prs->flags & (JS_PROP_TMASK | JS_PROP_WRITABLE | JS_PROP_LENGTH)) ==
            JS_PROP_WRITABLE) {
            slot = (int)(pr - p->prop);
            if (site && p->shape->is_hashed && !__JS_AtomIsTaggedInt(atom)) {
                fresh.shape = p->shape;
                fresh.slot = slot;
                fresh.kind = JS_IC_REPLACE;
                js_ic_install(ctx, b, site, &fresh);
                pr = &p->prop[slot];
            }
            set_value(ctx, &pr->u.value, value);
            return true;
        }
    } else if (site && !site->megamorphic && js_ic_can_transition(ctx, p, atom)) {
        old = js_dup_shape(p->shape);
        slot = old->prop_count;
        pr = add_property(ctx, p, atom, JS_PROP_C_W_E);
        if (!pr) {
            js_free_shape(ctx->rt, old);
            JS_FreeValue(ctx, value);
            return -1;
        }
        pr->u.value = value;
        if (p->shape->is_hashed && p->shape->prop_count == slot + 1) {
            fresh.shape = old;
            fresh.slot = slot;
            fresh.kind =
                p->shape->prop_size == old->prop_size ? JS_IC_TRANSITION : JS_IC_TRANSITION_RESIZE;
            fresh.epoch = ctx->rt->property_ic_epoch;
            fresh.transition = p->shape;
            js_ic_install(ctx, b, site, &fresh);
        }
        js_free_shape(ctx->rt, old);
        return true;
    }
    return JS_SetPropertyInternal2(ctx, obj, atom, value, obj, JS_PROP_THROW_STRICT);
}

void js_property_ic_mark(JSRuntime *rt, JSFunctionBytecode *b, JS_MarkFunc *mark)
{
    JSPropertyIC *ic = b->property_ic;
    uint32_t i, j;
    if (!ic || ic == JS_IC_DISABLED)
        return;
    if (rt->property_ic_gc_mode & JS_IC_GC_SCAN)
        return;
    for (i = 0; i < ic->site_count; i++) {
        JSPropertyICSite *site = &ic->sites[i];
        for (j = 0; j < site->count; j++) {
            JSPropertyICWay *way = js_ic_way(site, j);
            if (way->shape)
                mark(rt, &way->shape->header);
            if (way->transition)
                mark(rt, &way->transition->header);
        }
    }
}

void js_property_ic_free(JSRuntime *rt, JSFunctionBytecode *b)
{
    JSPropertyIC *ic = b->property_ic;
    uint32_t i, j;
    b->property_ic = NULL;
    if (!ic || ic == JS_IC_DISABLED)
        return;
    if (ic->prev)
        ic->prev->next = ic->next;
    else
        rt->property_ic_list = ic->next;
    if (ic->next)
        ic->next->prev = ic->prev;
    for (i = 0; i < ic->site_count; i++) {
        JSPropertyICSite *site = &ic->sites[i];
        for (j = 0; j < site->count; j++)
            js_ic_release_way(rt, js_ic_way(site, j));
        js_free_rt(rt, site->secondary);
    }
    js_free_rt(rt, ic);
}

int js_property_ic_inspect(JSValueConst func, uint32_t counts[7])
{
    JSPropertyIC *ic;
    JSObject *p;
    uint32_t i, j;
    memset(counts, 0, 7 * sizeof(*counts));
    if (JS_VALUE_GET_TAG(func) != JS_TAG_OBJECT)
        return -1;
    p = JS_VALUE_GET_OBJ(func);
    if (!js_class_has_bytecode(p->class_id))
        return -1;
    ic = p->u.func.function_bytecode->property_ic;
    if (!ic || ic == JS_IC_DISABLED)
        return 0;
    for (i = 0; i < ic->site_count; i++) {
        JSPropertyICSite *site = &ic->sites[i];
        counts[0] += site->megamorphic != 0;
        for (j = 0; j < site->count; j++)
            counts[js_ic_way(site, j)->kind & JS_IC_KIND_MASK]++;
    }
    return (int)ic->site_count;
}

bool js_property_ic_gc_propagate(JSRuntime *rt, JS_MarkFunc *mark)
{
    JSPropertyIC *ic;
    bool changed = false;
    uint32_t i, j;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        if (ic->owner->header.mark)
            continue;
        for (i = 0; i < ic->site_count; i++) {
            JSPropertyICSite *site = &ic->sites[i];
            for (j = 0; j < site->count; j++) {
                JSPropertyICWay *way = js_ic_way(site, j);
                if (!way->transition || !rt->property_ic_epoch ||
                    way->epoch != rt->property_ic_epoch)
                    continue;
                assert(way->shape->proto == way->transition->proto);
                if (!way->shape->header.mark && way->transition->header.mark) {
                    mark(rt, &way->transition->header);
                    way->kind |= JS_IC_GC_TARGET;
                    changed = true;
                } else if (way->shape->header.mark && !way->transition->header.mark) {
                    mark(rt, &way->shape->header);
                    way->kind |= JS_IC_GC_SHAPE;
                    changed = true;
                }
            }
        }
    }
    return changed;
}

void js_property_ic_gc_restore(JSRuntime *rt)
{
    JSPropertyIC *ic;
    uint32_t i, j;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        if (ic->owner->header.mark)
            continue;
        for (i = 0; i < ic->site_count; i++) {
            JSPropertyICSite *site = &ic->sites[i];
            for (j = 0; j < site->count; j++) {
                JSPropertyICWay *way = js_ic_way(site, j);
                if (way->shape && !(way->kind & JS_IC_GC_SHAPE))
                    way->shape->header.ref_count++;
                if (way->transition && !(way->kind & JS_IC_GC_TARGET))
                    way->transition->header.ref_count++;
                way->kind &= JS_IC_KIND_MASK;
            }
        }
    }
}

void js_property_ic_gc_prune(JSRuntime *rt)
{
    JSPropertyIC *ic;
    uint32_t i, j, write;
    for (ic = rt->property_ic_list; ic; ic = ic->next) {
        if (ic->owner->header.mark)
            continue;
        for (i = 0; i < ic->site_count; i++) {
            JSPropertyICSite *site = &ic->sites[i];
            for (j = 0; j < site->count; j++) {
                JSPropertyICWay *way = js_ic_way(site, j);
                if (way->shape->header.mark || (way->transition && way->transition->header.mark) ||
                    ((way->kind != JS_IC_OWN && way->kind != JS_IC_REPLACE) &&
                     (!rt->property_ic_epoch || way->epoch != rt->property_ic_epoch)))
                    js_ic_release_way(rt, way);
            }
            write = 0;
            for (j = 0; j < site->count; j++) {
                JSPropertyICWay *way = js_ic_way(site, j);
                if (!way->shape)
                    continue;
                if (write != j) {
                    *js_ic_way(site, write) = *way;
                    memset(way, 0, sizeof(*way));
                }
                write++;
            }
            site->count = (uint8_t)write;
            site->churn = 0;
        }
    }
}

size_t js_property_ic_memory_size(JSFunctionBytecode *b, int *allocations)
{
    JSPropertyIC *ic = b->property_ic;
    size_t bytes;
    uint32_t i;
    if (!ic || ic == JS_IC_DISABLED)
        return 0;
    bytes = ic->bytes;
    (*allocations)++;
    for (i = 0; i < ic->site_count; i++) {
        if (ic->sites[i].secondary) {
            unsigned capacity = ic->sites[i].capacity ? ic->sites[i].capacity : JS_IC_INLINE_WAYS;
            bytes += (capacity - 1) * sizeof(JSPropertyICWay);
            (*allocations)++;
        }
    }
    return bytes;
}
