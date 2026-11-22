/* Private, platform-neutral property-site metadata. Public ABI is unchanged. */
#ifndef QJS_PROPERTY_IC_H
#define QJS_PROPERTY_IC_H
#ifdef QJS_PROPERTY_IC
#include "src/common/internal/turbo-config.h"

enum {
    JS_IC_EMPTY,
    JS_IC_OWN,
    JS_IC_PROTO,
    JS_IC_UNSET,
    JS_IC_REPLACE,
    JS_IC_TRANSITION,
    JS_IC_TRANSITION_RESIZE
};
enum { JS_IC_INLINE_WAYS = 4, JS_IC_MAX_WAYS = 16, JS_IC_MAX_BYTES = 1024 * 1024 };
enum {
    JS_IC_GC_SCAN = 1u,
    JS_IC_RETAIN_ORPHANS = 4u,
    JS_IC_PROTO_WEAK = 0x40u,
    JS_IC_MAX_SHAPE_REFS = 0xffffffu,
    JS_IC_SHAPE_REFS_VALID = 0x80u,
    JS_IC_WARMUP_MAX = 2047u
};

#define JS_IC_DISABLED ((struct JSPropertyIC *)(uintptr_t)1)
#define JS_IC_TAG_MAX ((uintptr_t)4095)

static inline bool js_property_ic_is_ptr(const struct JSPropertyIC *ic)
{
    return (uintptr_t)ic > JS_IC_TAG_MAX;
}

static inline uint32_t js_property_ic_warmup_count(const struct JSPropertyIC *ic)
{
    uintptr_t v = (uintptr_t)ic;
    return (v > 1u && (v & 1u)) ? (uint32_t)(v >> 1) : 0u;
}

static inline struct JSPropertyIC *js_property_ic_encode_warmup(uint32_t count)
{
    if (count > JS_IC_WARMUP_MAX)
        count = JS_IC_WARMUP_MAX;
    return (struct JSPropertyIC *)(((uintptr_t)count << 1) | 1u);
}

/* The high bit preserves is_hashed's boolean meaning and indicates that the
 * padding count is initialized. Independent shape producers set is_hashed to
 * 0/1; clones clear it. Never read their otherwise unspecified padding. */
static inline uint32_t js_property_ic_shape_refs(const JSShape *shape)
{
    const uint8_t *p = shape->property_ic_refs;
    if (!(shape->is_hashed & JS_IC_SHAPE_REFS_VALID))
        return 0;
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16);
}
static inline void js_property_ic_set_shape_refs(JSShape *shape, uint32_t refs)
{
    uint8_t *p = shape->property_ic_refs;
    assert(refs <= JS_IC_MAX_SHAPE_REFS && (shape->is_hashed & 1));
    p[0] = (uint8_t)refs;
    p[1] = (uint8_t)(refs >> 8);
    p[2] = (uint8_t)(refs >> 16);
    shape->is_hashed =
        (shape->is_hashed & (1u | JS_IC_PROTO_WEAK)) | (refs ? JS_IC_SHAPE_REFS_VALID : 0u);
}

/* An ordinary shape acquisition restores exactly one prototype edge. The
 * prototype-free hook removes every weak IC before that object can be reused. */
static inline JSShape *js_property_ic_acquire_shape_ref(JSShape *shape)
{
    if (shape->is_hashed & JS_IC_PROTO_WEAK) {
        assert(shape->proto && shape->proto->header.ref_count > 0);
        shape->is_hashed &= ~JS_IC_PROTO_WEAK;
        shape->proto->header.ref_count++;
    }
    shape->header.ref_count++;
    return shape;
}

typedef struct JSPropertyICWay {
    JSShape *shape; /* owned hashed shape: immutable while shared */
    uint32_t slot;
    uint32_t kind;
    JSObject *holder; /* borrowed; reachable under shape + epoch */
    uint64_t epoch;
    JSShape *transition; /* owned hashed successor; native only if same capacity */
} JSPropertyICWay;

typedef struct JSPropertyICSite {
    JSPropertyICWay primary;
    JSPropertyICWay *secondary; /* native probes first3; C may grow to15 */
    uint32_t churn;
    uint8_t count, next, megamorphic, capacity;
    uint64_t reserved2;
} JSPropertyICSite;

typedef struct JSPropertyIC {
    JSPropertyICSite *sites;
    uint32_t map_count, site_count;
    size_t bytes;
    JSContext *binding_realm;  /* borrowed from owner->realm;cells invalidated before mutation */
    JSFunctionBytecode *owner; /* weak: owner unlinks before freeing this slab */
    struct JSPropertyIC *next, *prev;
    JSPropertyICSite *map[]; /* floor(PC/4): owned by-id site or borrowed tagged value cell */
} JSPropertyIC;

/* Called only at structural mutation boundaries, never for value replacement.
 * An epoch reaching zero disables prototype-dependent caching permanently.
 * Each runtime executes on one host thread at a time, like the upstream VM. */
void js_property_ic_binding_invalidate(JSRuntime *, JSObject *);
static inline void js_property_ic_invalidate_proto(JSContext *ctx, JSObject *p)
{
    if (p->is_prototype) {
        /* Also covers foreign-realm globals:the cold helper compares the
         * actual object with each metadata owner's retained realm. */
        js_property_ic_binding_invalidate(ctx->rt, p);
        if (ctx->rt->property_ic_epoch)
            ctx->rt->property_ic_epoch++;
    }
}

JSValue JS_FrameGlobalBindingCellGet(JSContext *, JSFunctionBytecode *, const uint8_t *, JSAtom,
                                     bool);
JSValue js_property_ic_get(JSContext *, JSFunctionBytecode *, const uint8_t *, JSValueConst,
                           JSAtom);
int js_property_ic_put(JSContext *, JSFunctionBytecode *, const uint8_t *, JSValueConst, JSAtom,
                       JSValue);
void js_property_ic_free(JSRuntime *, JSFunctionBytecode *);
void js_property_ic_shape_released(JSRuntime *, JSShape *);
void js_property_ic_release_shape_ref(JSRuntime *, JSShape *);
void js_property_ic_release_cached_shape(JSRuntime *, JSShape *);
void js_property_ic_prototype_free(JSRuntime *, JSObject *);
bool js_property_ic_extend_site(JSContext *, JSPropertyIC *, JSPropertyICSite *);
void js_property_ic_mark(JSRuntime *, JSFunctionBytecode *, JS_MarkFunc *);
/* Private qualification aid; reports installed ways, not sampled hit counts. */
int js_property_ic_inspect(JSValueConst, uint32_t counts[7]);
bool js_property_ic_gc_propagate(JSRuntime *, JS_MarkFunc *);
void js_property_ic_gc_restore(JSRuntime *);
void js_property_ic_gc_prune(JSRuntime *);
size_t js_property_ic_memory_size(JSFunctionBytecode *, int *);
size_t js_property_ic_purge(JSRuntime *);
void js_property_ic_stats(JSRuntime *, uint32_t *, size_t *);

#if UINTPTR_MAX == UINT64_MAX
_Static_assert(sizeof(JSPropertyICWay) == 40 && sizeof(JSPropertyICSite) == 64 &&
                   offsetof(JSPropertyIC, map) == 56 && offsetof(JSPropertyICWay, slot) == 8 &&
                   offsetof(JSPropertyICWay, kind) == 12 &&
                   offsetof(JSPropertyICWay, holder) == 16 &&
                   offsetof(JSPropertyICWay, epoch) == 24 &&
                   offsetof(JSPropertyICWay, transition) == 32,
               "property IC C/native metadata contract");
_Static_assert(offsetof(JSPropertyICSite, megamorphic) == 54 &&
                   offsetof(JSPropertyICSite, capacity) == 55 &&
                   offsetof(JSPropertyIC, binding_realm) == 24 &&
                   offsetof(JSShape, is_hashed) == sizeof(JSGCObjectHeader),
               "property IC native fallback fields");
_Static_assert(JS_IC_INLINE_WAYS == 4 && JS_IC_MAX_WAYS == 16,
               "four native ways; bounded power-of-two C growth");
_Static_assert(offsetof(JSShape, property_ic_refs) == offsetof(JSShape, is_hashed) + 1 &&
                   sizeof(((JSShape *)0)->property_ic_refs) == 3 &&
                   offsetof(JSShape, property_ic_refs) + 3 == offsetof(JSShape, hash),
               "property IC reference count occupies only the original shape padding");
_Static_assert(JS_IC_OWN == 1 && JS_IC_PROTO == 2 && JS_IC_UNSET == 3 && JS_IC_REPLACE == 4 &&
                   JS_IC_TRANSITION == 5 && JS_IC_TRANSITION_RESIZE == 6,
               "property IC C/native mode encoding");
_Static_assert(JS_IC_PROTO_WEAK == 64 && JS_IC_RETAIN_ORPHANS == 4 && JS_IC_SHAPE_REFS_VALID == 128,
               "property IC C/native prototype ownership bits");
#endif
#endif
#endif
