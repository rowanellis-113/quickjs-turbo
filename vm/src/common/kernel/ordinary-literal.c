#include "src/common/call/interpreter-retained-context.inc"

#include <stdatomic.h>
extern void qjs_literal_core_js_free_shape0(JSRuntime *, JSShape *);
extern JSValue qjs_literal_core_JS_NewObjectFromShape(JSContext *, JSShape *, JSClassID,
                                                      JSProperty *);
extern int JS_FrameIteratorLiteralEnter(JSFrameRegisterState *);
extern int JS_FrameSlowDirectSelect(JSFrameRegisterState *);
#define ORD_ACTIVE(s)                                                                              \
    (((unsigned char *)(s))[offsetof(JSFrameRegisterState, direct_host_calls) + sizeof(bool)])
#define ORD_LAZY(s)                                                                                \
    (((unsigned char *)(s))[offsetof(JSFrameRegisterState, direct_host_calls) + sizeof(bool) + 1])
_Static_assert(sizeof(JSFrameRegisterState) == FRAME_REGISTER_STATE_BYTES &&
                   offsetof(JSFrameRegisterState, direct_host_calls) ==
                       FRAME_REGISTER_STATE_EXCEPTION + 1 &&
                   offsetof(JSFrameRegisterState, iterator_checkpoint_depth) ==
                       FRAME_REGISTER_STATE_EXCEPTION + 4,
               "owned state profile padding");
_Static_assert(offsetof(JSStackFrame, cur_sp) == QJS_ABI_OFF_JSStackFrame_cur_sp &&
                   offsetof(JSRuntime, current_stack_frame) ==
                       QJS_ABI_OFF_JSRuntime_current_stack_frame &&
                   offsetof(JSFrame, bytecode) == 80 && JS_PROP_INITIAL_SIZE == 2,
               "frozen VM and property ABI");
typedef struct {
    uintptr_t site, bytecode;
    JSShape *old_shape, *new_shape;
    JSAtom atom;
    uint32_t slot;
} OrdSite;
typedef struct {
    uint8_t cache_next[8];
    OrdSite literals[8];
    uint8_t next[4];
} OrdLegacy;
typedef struct OrdRecord {
    OrdSite site;
    struct OrdRecord *next;
} OrdRecord;
typedef struct OrdChunk {
    struct OrdChunk *next;
    unsigned used;
    OrdRecord records[16];
} OrdChunk;
typedef struct {
    OrdLegacy legacy;
    OrdRecord *bucket[64];
    OrdChunk *chunks;
    unsigned count;
} OrdScope;
_Static_assert(sizeof(OrdSite) == 40 && sizeof(OrdLegacy) == 336 &&
                   offsetof(OrdScope, legacy) == 0 && sizeof(OrdScope) < 1024,
               "old prefix and bounded root stack");
_Atomic unsigned JS_FrameOrdinaryLiteralMode __attribute__((section(".qjzzpm"), aligned(4))) = 0;
/* observe-only counters: roots, allocated records, allocation fails, object
   hits/misses, transition hits/misses, fallback, chunks, cleanup records. */
uint64_t JS_FrameOrdinaryLiteralStats[34] __attribute__((section(".qjzzpm"), aligned(8)));
static FRAME_INLINE void ord_count(unsigned mode, unsigned n)
{
    if (mode & 4)
        __atomic_fetch_add(&JS_FrameOrdinaryLiteralStats[n], 1, __ATOMIC_RELAXED);
}
static FRAME_INLINE unsigned ord_mode(void)
{
    unsigned m = atomic_load_explicit(&JS_FrameOrdinaryLiteralMode, memory_order_relaxed);
    if (!m) {
        unsigned expected = 0;
        m = (getenv("QJS_DISABLE_FRAME_ORDINARY_LITERAL") ||
             getenv("QJS_DISABLE_FRAME_ITERATOR_LITERAL_SHAPES"))
                ? 2
                : 1;
        if (getenv("QJS_OBSERVE_FRAME_ORDINARY_LITERAL"))
            m |= 4;
        if (getenv("QJS_DISABLE_FRAME_ORDINARY_LITERAL_TRANSITION") ||
            getenv("QJS_DISABLE_FRAME_ITERATOR_LITERAL_TRANSITION"))
            m |= 8;
        if (getenv("QJS_ORDINARY_LITERAL_FAIL_CACHE_ALLOC"))
            m |= 16;
        if (getenv("QJS_DISABLE_FRAME_LITERAL_VM_HIT"))
            m |= 128;
        if (getenv("QJS_DISABLE_FRAME_LITERAL_LAZY"))
            m |= 256;
        if (getenv("QJS_LITERAL_LAZY_FAIL_ALLOC"))
            m |= 512;
        if (getenv("QJS_DISABLE_FRAME_LITERAL_REPEAT_GUARD"))
            m |= 1024;
        if (getenv("QJS_DISABLE_FRAME_LITERAL_SPARE"))
            m |= 2048;
        if (getenv("QJS_DISABLE_FRAME_STACK_INSERT"))
            m |= 4096;
        if (getenv("QJS_DISABLE_FRAME_TYPEOF"))
            m |= 8192;
        if (getenv("QJS_DISABLE_FRAME_PREDICATE"))
            m |= 16384;
        if (getenv("QJS_DISABLE_FRAME_TRUTHINESS"))
            m |= 32768;
        if (getenv("QJS_DISABLE_FRAME_NUMBER_TRUTH"))
            m |= 65536;
        JSObject ext = {.extensible = 1}, proto = {.is_prototype = 1}, exotic = {.is_exotic = 1};
        if (((unsigned char *)&ext)[QJS_ABI_BIT_JSObject_extensible_BYTE] !=
                QJS_ABI_BIT_JSObject_extensible_MASK ||
            ((unsigned char *)&proto)[QJS_ABI_BIT_JSObject_is_prototype_BYTE] !=
                QJS_ABI_BIT_JSObject_is_prototype_MASK ||
            ((unsigned char *)&exotic)[QJS_ABI_BIT_JSObject_is_exotic_BYTE] !=
                QJS_ABI_BIT_JSObject_is_exotic_MASK)
            m |= 128;
        if (!atomic_compare_exchange_strong_explicit(&JS_FrameOrdinaryLiteralMode, &expected, m,
                                                     memory_order_relaxed, memory_order_relaxed))
            m = expected;
    }
    return m;
}
static FRAME_INLINE void ord_release(JSRuntime *rt, JSShape *sh)
{
#ifdef QJS_PROPERTY_IC
    extern void js_property_ic_release_shape_ref(JSRuntime *, JSShape *);
    js_property_ic_release_shape_ref(rt, sh);
#else
    if (sh && --JS_REF_COUNT(sh) <= 0)
        qjs_literal_core_js_free_shape0(rt, sh);
#endif
}
static FRAME_INLINE void ord_clear(JSRuntime *rt, OrdSite *e)
{
    JSShape *a = e->old_shape, *b = e->new_shape;
    e->old_shape = e->new_shape = NULL;
    ord_release(rt, a);
    ord_release(rt, b);
}
static FRAME_INLINE void ord_publish(JSFrameRegisterState *s, JSValue *sp, uint8_t *pc)
{
    s->sp = sp;
    s->frame->saved_sp = sp;
    s->frame->sf.cur_sp = sp;
    s->frame->sf.cur_pc = pc;
    s->rt->current_stack_frame = &s->frame->sf;
}
static FRAME_INLINE OrdSite *ord_site(JSFrameRegisterState *s, unsigned mode)
{
    OrdScope *scope = (OrdScope *)s->cache_next;
    uintptr_t key = (uintptr_t)s->pc, bc = (uintptr_t)s->frame->bytecode;
    unsigned h = (key ^ (key >> 5) ^ (key >> 11)) & 63;
    for (OrdRecord *r = scope->bucket[h]; r; r = r->next)
        if (r->site.site == key && r->site.bytecode == bc)
            return &r->site;
    OrdChunk *c = scope->chunks;
    if (!c || c->used == 16) {
        if (scope->count == 16)
            return NULL;
        /* Optional storage never throws or triggers GC. A failure simply retains
     the original opcode path. Nodes never move until this VM root exits. */
        c = (mode & 16) ? NULL : js_malloc_rt(s->rt, sizeof(*c));
        if (!c) {
            ord_count(mode, 2);
            return NULL;
        }
        memset(c, 0, sizeof(*c));
        c->next = scope->chunks;
        scope->chunks = c;
        scope->count++;
        ord_count(mode, 8);
    }
    OrdRecord *r = &c->records[c->used++];
    r->site.site = key;
    r->site.bytecode = bc;
    r->next = scope->bucket[h];
    scope->bucket[h] = r;
    ord_count(mode, 1);
    return &r->site;
}

/* This small stack owner survives precisely one physical VM entry. The first
   eight bytes remain the ordinary call-cache replacement counters. No shape
   or bytecode pointer survives its return. Larger metadata is lazy. */
typedef struct {
    uint8_t cache_next[8];
    OrdScope *scope;
    uint64_t seen;
} OrdLazy;
_Static_assert(sizeof(OrdLazy) == 24 && sizeof(OrdScope) == 864,
               "small owner and index-free shape scope");
static FRAME_INLINE void ord_destroy(JSRuntime *rt, OrdScope *scope, unsigned mode)
{
    for (unsigned i = 0; i < 8; i++)
        ord_clear(rt, &scope->legacy.literals[i]);
    for (OrdChunk *c = scope->chunks; c;) {
        OrdChunk *next = c->next;
        for (unsigned i = 0; i < c->used; i++) {
            ord_clear(rt, &c->records[i].site);
            ord_count(mode, 9);
        }
        js_free_rt(rt, c);
        c = next;
    }
}
FRAME_CODE int JS_FrameOrdinaryLiteralLazyEnter(JSFrameRegisterState *s)
{
    /* Fresh root padding is not assumed initialized by old assembly builders.
    Only the full 336-byte legacy prefix may have nonzero byte162. */
    ORD_LAZY(s) = 0;
    unsigned mode = atomic_load_explicit(&JS_FrameOrdinaryLiteralMode, memory_order_relaxed);
    if (!mode) {
        js_frame_begin_c(s);
        mode = ord_mode();
        js_frame_finish_c(s);
    }
    if (!(mode & 1) || (mode & 256) || ORD_ACTIVE(s) || !s->cache_next || !s->sites)
        return JS_FrameInterp(s);
    OrdLazy lazy;
    lazy.scope = NULL;
    lazy.seen = 0;
    uint8_t *previous = s->cache_next;
    memcpy(lazy.cache_next, previous, 8);
    s->cache_next = lazy.cache_next;
    ORD_LAZY(s) = 1;
    ord_count(mode, 17);
    int event = JS_FrameInterp(s);
    memcpy(previous, s->cache_next, 8);
    s->cache_next = previous;
    ORD_ACTIVE(s) = 0;
    ORD_LAZY(s) = 0;
    /* A completed frame may no longer exist. Only use state/runtime and the
    owning metadata, after restoring the caller's cache counter pointer. */
    if (lazy.scope) {
        js_frame_begin_c(s);
        ord_destroy(s->rt, lazy.scope, mode);
        js_free_rt(s->rt, lazy.scope);
        ord_count(mode, 19);
        js_frame_finish_c(s);
    } else
        ord_count(mode, 21);
    return event;
}
FRAME_CODE int JS_FrameOrdinaryLiteralEnter(JSFrameRegisterState *s)
{
    ORD_LAZY(s) = 0;
    /* At a root boundary the caller owns published PC/SP. Preserve decoded PC. */
    js_frame_begin_c(s);
    unsigned mode = ord_mode();
    js_frame_finish_c(s);
    if (!(mode & 1) || !s->cache_next || !s->sites)
        return JS_FrameIteratorLiteralEnter(s);
    OrdScope scope;
    memset(&scope, 0, sizeof(scope));
    uint8_t *previous = s->cache_next;
    unsigned char active = ORD_ACTIVE(s);
    memcpy(scope.legacy.cache_next, previous, 8);
    s->cache_next = scope.legacy.cache_next;
    ORD_ACTIVE(s) = 4;
    ord_count(mode, 0);
    int event = JS_FrameInterp(s);
    memcpy(previous, scope.legacy.cache_next, 8);
    s->cache_next = previous;
    ORD_ACTIVE(s) = active;
    /* VM has restored the root's caller and exception/return owners. Do not
    dereference a completed frame here. The metadata are external GC roots. */
    js_frame_begin_c(s);
    ord_destroy(s->rt, &scope, mode);
    js_frame_finish_c(s);
    return event;
}
static FRAME_INLINE bool ord_object(JSObject *p)
{
    return p->class_id == JS_CLASS_OBJECT && p->extensible && !p->is_exotic && !p->is_prototype &&
           p->shape->is_hashed && !p->shape->deleted_prop_count;
}
static FRAME_INLINE bool ord_transition(JSShape *a, JSShape *b, JSAtom atom)
{
    if (!a || !b || !a->is_hashed || !b->is_hashed || a->deleted_prop_count ||
        b->deleted_prop_count || a->proto != b->proto || a->prop_size != b->prop_size ||
        b->prop_count != a->prop_count + 1)
        return false;
    JSShapeProperty *ap = get_shape_prop(a);
    JSShapeProperty *bp = get_shape_prop(b);
    for (unsigned i = 0; i < a->prop_count; i++)
        if (ap[i].atom != bp[i].atom || ap[i].flags != bp[i].flags)
            return false;
    return bp[a->prop_count].atom == atom && bp[a->prop_count].flags == JS_PROP_C_W_E;
}

/* Only a simple value push followed by define_field contributes to the hint.
   Stop at the first complex initializer, control flow, or nested literal. */
static FRAME_INLINE unsigned ord_literal_value_op_size(unsigned op)
{
    switch (op) {
    case OP_push_minus1:
    case OP_push_0:
    case OP_push_1:
    case OP_push_2:
    case OP_push_3:
    case OP_push_4:
    case OP_push_5:
    case OP_push_6:
    case OP_push_7:
    case OP_push_empty_string:
    case OP_undefined:
    case OP_null:
    case OP_push_false:
    case OP_push_true:
    case OP_get_loc0:
    case OP_get_loc1:
    case OP_get_loc2:
    case OP_get_loc3:
    case OP_get_arg0:
    case OP_get_arg1:
    case OP_get_arg2:
    case OP_get_arg3:
    case OP_get_var_ref0:
    case OP_get_var_ref1:
    case OP_get_var_ref2:
    case OP_get_var_ref3:
        return 1;
    case OP_push_i8:
    case OP_push_const8:
    case OP_get_loc8:
        return 2;
    case OP_push_i16:
    case OP_get_loc:
    case OP_get_loc_check:
    case OP_get_arg:
    case OP_get_var_ref:
    case OP_get_var_ref_check:
        return 3;
    case OP_push_i32:
    case OP_push_const:
    case OP_push_atom_value:
        return 5;
    default:
        return 0;
    }
}

static FRAME_INLINE uint32_t ord_shape_initial_hash(JSObject *proto)
{
    uint32_t h = hash32(1u + (uint32_t)(uintptr_t)proto);
    if (sizeof(proto) > 4)
        h = hash32(h + (uint32_t)((uint64_t)(uintptr_t)proto >> 32));
    return h;
}

static FRAME_CODE JSValue ord_literal_new(JSContext *ctx, JSObject *proto,
                                          const JSFunctionBytecode *b, const uint8_t *pc)
{
#if QJS_ABI_HAS_PREFIX_RC
    (void)proto;
    (void)b;
    (void)pc;
    return JS_NewObject(ctx);
#else
    const uint8_t *end = b->byte_code_buf + b->byte_code_len;
    unsigned fields = 0;
    while (fields < 16 && pc < end) {
        unsigned size = ord_literal_value_op_size(*pc);
        if (!size || end - pc < (ptrdiff_t)(size + 5u) || pc[size] != OP_define_field)
            break;
        pc += size + 5u;
        fields++;
    }
    if (fields <= JS_PROP_INITIAL_SIZE)
        return JS_NewObject(ctx);

    unsigned reserve = fields <= 4 ? 4 : (fields <= 8 ? 8 : 16);
    JSRuntime *rt = ctx->rt;
    /* Separate reserve families before exposing the shape. For equal ordered
       properties each transition extends the seed by a bijective hash step,
       so neither the empty seed nor its descendants match ordinary lookup. */
    uint32_t hash = ord_shape_initial_hash(proto) ^ hash32(reserve);
    uint32_t bucket = hash >> (32 - rt->shape_hash_bits);
    for (JSShape *sh = rt->shape_hash[bucket]; sh != NULL; sh = sh->shape_hash_next) {
        if (sh->hash == hash && sh->proto == proto && sh->prop_count == 0 &&
            sh->prop_size == (int)reserve && sh->prop_hash_mask == reserve - 1) {
            return qjs_literal_core_JS_NewObjectFromShape(ctx, js_dup_shape(sh), JS_CLASS_OBJECT,
                                                          NULL);
        }
    }

    if (2 * (rt->shape_hash_count + 1) > rt->shape_hash_size && rt->shape_hash_bits < 30) {
        int new_bits = rt->shape_hash_bits + 1;
        int new_size = 1 << new_bits;
        JSShape **new_table = js_malloc_rt(rt, sizeof(new_table[0]) * (size_t)new_size);
        if (new_table) {
            memset(new_table, 0, sizeof(new_table[0]) * (size_t)new_size);
            for (int i = 0; i < rt->shape_hash_size; i++) {
                for (JSShape *s1 = rt->shape_hash[i], *next; s1 != NULL; s1 = next) {
                    next = s1->shape_hash_next;
                    uint32_t h1 = s1->hash >> (32 - new_bits);
                    s1->shape_hash_next = new_table[h1];
                    new_table[h1] = s1;
                }
            }
            js_free_rt(rt, rt->shape_hash);
            rt->shape_hash_bits = new_bits;
            rt->shape_hash_size = new_size;
            rt->shape_hash = new_table;
            bucket = hash >> (32 - new_bits);
        }
    }

    size_t hash_bytes = (size_t)reserve * sizeof(uint32_t);
    void *sh_alloc =
        js_malloc(ctx, hash_bytes + sizeof(JSShape) + (size_t)reserve * sizeof(JSShapeProperty));
    if (!sh_alloc)
        return JS_EXCEPTION;
    memset(sh_alloc, 0, hash_bytes + sizeof(JSShape));
    JSShape *shape = (JSShape *)(void *)((uint32_t *)sh_alloc + reserve);
    JS_REF_COUNT(shape) = 1;
    add_gc_object(rt, &shape->header, JS_GC_OBJ_TYPE_SHAPE);
    if (proto)
        js_dup(JS_MKPTR(JS_TAG_OBJECT, proto));
    shape->proto = proto;
    shape->prop_hash_mask = reserve - 1;
    shape->prop_size = (int)reserve;
    shape->hash = hash;
    shape->is_hashed = true;
    shape->shape_hash_next = rt->shape_hash[bucket];
    rt->shape_hash[bucket] = shape;
    rt->shape_hash_count++;
    /* The constructor consumes the factory reference on both success and OOM.
       The ordinary site takes its existing independent reference on success. */
    return qjs_literal_core_JS_NewObjectFromShape(ctx, shape, JS_CLASS_OBJECT, NULL);
#endif
}

FRAME_CODE int JS_FrameOrdinaryLiteralStep(JSFrameRegisterState *s)
{
    unsigned mode = atomic_load_explicit(&JS_FrameOrdinaryLiteralMode, memory_order_relaxed),
             op = *s->pc;
    JSValue *sp = s->sp;
    uint8_t *pc = s->pc;
    JSFrame *frame = s->frame;
    JSContext *ctx = frame->bytecode->realm;
    JSObject *p = NULL;
    JSShape *old = NULL;
    /* All C boundaries, including fallback, see the actual owning SP. */
    ord_publish(s, sp, pc);
    if (ORD_LAZY(s) == 1 && ORD_ACTIVE(s) == 0 && !s->iterator_checkpoint_depth &&
        !s->exception_pending && (mode & 1) && (op == OP_object || op == OP_define_field)) {
        /* A define-only entry may target an existing object. Do not allocate
     metadata for operations the current two-slot cache cannot accelerate. */
        JSObject *candidate =
            op == OP_define_field && JS_IsObject(sp[-2]) ? JS_VALUE_GET_OBJ(sp[-2]) : NULL;
        bool eligible = op == OP_object ||
                        (!(mode & 8) && candidate && ord_object(candidate) &&
                         candidate->shape->prop_count < candidate->shape->prop_size &&
                         (!(mode & 2048) || candidate->shape->prop_size == JS_PROP_INITIAL_SIZE));
        if (!(mode & 1024)) {
            /* A collision may admit metadata early, never skip semantic guards.
      Define operations in a one-shot object do not train this predictor.
      No bytecode/shape pointer is retained and there is no warmup dependence. */
            eligible = false;
            if (op == OP_object) {
                OrdLazy *lazy = (OrdLazy *)s->cache_next;
                uintptr_t key = (uintptr_t)pc;
                uint64_t bit = UINT64_C(1) << ((key ^ (key >> 5) ^ (key >> 11)) & 63);
                eligible = (lazy->seen & bit) != 0;
                lazy->seen |= bit;
                if (!eligible)
                    ord_count(mode, 22);
            }
        }
        if (eligible) {
            OrdLazy *lazy = (OrdLazy *)s->cache_next;
            ord_publish(s, sp, pc + (op == OP_object ? 1 : 5));
            js_frame_begin_c(s);
            OrdScope *scope = (mode & (16 | 512)) ? NULL : js_malloc_rt(s->rt, sizeof(*scope));
            if (scope) {
                memset(scope, 0, sizeof(*scope));
                memcpy(scope->legacy.cache_next, lazy->cache_next, 8);
                lazy->scope = scope;
                s->cache_next = scope->legacy.cache_next;
                ORD_ACTIVE(s) = 4;
                ORD_LAZY(s) = 2;
                ord_count(mode, 0);
                ord_count(mode, 18);
            } else {
                /* Sticky only for this physical entry; generic opcode remains exact. */
                ORD_LAZY(s) = 3;
                ord_count(mode, 2);
                ord_count(mode, 20);
            }
            js_frame_finish_c(s);
        }
    }
    if (ORD_ACTIVE(s) != 4 || s->iterator_checkpoint_depth || s->exception_pending || !(mode & 1) ||
        (op != OP_object && op != OP_define_field))
        return JS_FrameSlowDirectSelect(s);
    if (op == OP_define_field) {
        p = JS_IsObject(sp[-2]) ? JS_VALUE_GET_OBJ(sp[-2]) : NULL;
        old = p ? p->shape : NULL;
        if ((mode & 8) || !p || !ord_object(p) || old->prop_count >= old->prop_size ||
            ((mode & 2048) && old->prop_size != JS_PROP_INITIAL_SIZE)) {
            ord_count(mode, 7);
            return JS_FrameSlowDirectSelect(s);
        }
    }
    /* Publish decoded PC before allocations, core calls, or shape releases. */
    ord_publish(s, sp, pc + (op == OP_object ? 1 : 5));
    js_frame_begin_c(s);
    OrdSite *entry = ord_site(s, mode);
    if (!entry) {
        ord_count(mode, 7);
        js_frame_finish_c(s);
        return JS_FrameSlowDirectSelect(s);
    }
    int ret = 0;
    if (op == OP_object) {
        JSShape *sh = entry->new_shape;
        JSValue proto = ctx->class_proto[JS_CLASS_OBJECT], v;
        JSObject *prototype = JS_IsObject(proto) ? JS_VALUE_GET_OBJ(proto) : NULL;
        if (sh && sh->is_hashed && sh->prop_count == 0 && sh->proto == prototype) {
            ord_count(mode, 3);
            JS_REF_COUNT(sh)++;
            v = qjs_literal_core_JS_NewObjectFromShape(ctx, sh, JS_CLASS_OBJECT, NULL);
        } else {
            ord_count(mode, 4);
            if (!entry->new_shape && !(mode & (8 | 2048)))
                v = ord_literal_new(ctx, prototype, frame->bytecode, pc + 1);
            else
                v = JS_NewObject(ctx);
            if (!JS_IsException(v) && !entry->new_shape) {
                sh = JS_VALUE_GET_OBJ(v)->shape;
                JS_REF_COUNT(sh)++;
                entry->new_shape = sh;
            }
        }
        *sp++ = v;
        pc++;
        ret = JS_IsException(v) ? -1 : 0;
    } else {
        JSAtom atom = get_u32(pc + 1);
        JSShape *next = entry->new_shape;
        if (entry->old_shape == old && entry->atom == atom && next && next->is_hashed &&
            next->prop_count == old->prop_count + 1 && next->prop_size == old->prop_size) {
            ord_count(mode, 5);
            if (old->prop_size > JS_PROP_INITIAL_SIZE)
                ord_count(mode, 23);
            JS_REF_COUNT(next)++;
            p->shape = next;
            p->prop[entry->slot].u.value = sp[-1];
            JS_REF_COUNT(old)--;
            /* old is still owned by this cache; the decrement cannot finalize. */
            --sp;
            *sp = JS_UNDEFINED;
        } else {
            ord_count(mode, 6);
            bool fill = !entry->new_shape;
            if (fill)
                JS_REF_COUNT(old)++;
            /* The core consumes RHS, including on failure. Remove the VM stack's
      owner before callbacks/GC can see a freed stale value in that slot. */
            JSValue value = sp[-1];
            --sp;
            *sp = JS_UNDEFINED;
            ord_publish(s, sp, pc + 5);
            ret = JS_DefinePropertyValue(ctx, sp[-1], atom, value, JS_PROP_C_W_E | JS_PROP_THROW);
            if (fill) {
                next = p->shape;
                if (ret >= 0 && ord_object(p) && ord_transition(old, next, atom)) {
                    JS_REF_COUNT(next)++;
                    entry->old_shape = old;
                    entry->new_shape = next;
                    entry->atom = atom;
                    entry->slot = old->prop_count;
                } else
                    ord_release(s->rt, old);
            }
        }
        pc += 5;
    }
    s->pc = pc;
    ord_publish(s, sp, pc);
    js_frame_finish_c(s);
    if (ret < 0) {
        s->exception_pending = true;
        return JS_FrameSlowDirectSelect(s);
    }
    return 0;
}

_Static_assert(OP_define_field == 75 && JS_TAG_OBJECT == -1 && JS_TAG_UNDEFINED == 3 &&
                   JS_CLASS_OBJECT == 1 && sizeof(JSProperty) == QJS_ABI_SIZE_JSProperty &&
                   offsetof(JSObject, class_id) == QJS_ABI_OFF_JSObject_class_id &&
                   offsetof(JSObject, shape) == QJS_ABI_OFF_JSObject_shape &&
                   offsetof(JSObject, prop) == QJS_ABI_OFF_JSObject_prop &&
                   offsetof(JSShape, is_hashed) == QJS_ABI_OFF_JSShape_is_hashed &&
                   offsetof(JSShape, prop_size) == QJS_ABI_OFF_JSShape_prop_size &&
                   offsetof(JSShape, prop_count) == QJS_ABI_OFF_JSShape_prop_count &&
                   offsetof(JSShape, deleted_prop_count) ==
                       QJS_ABI_OFF_JSShape_deleted_prop_count &&
                   offsetof(OrdScope, bucket) == 336 && sizeof(OrdRecord) == 48 &&
                   offsetof(OrdRecord, next) == 40 && offsetof(OrdSite, old_shape) == 16 &&
                   offsetof(OrdSite, new_shape) == 24 && offsetof(OrdSite, atom) == 32 &&
                   offsetof(OrdSite, slot) == 36 &&
                   offsetof(JSFrameRegisterState, exception_pending) ==
                       FRAME_REGISTER_STATE_EXCEPTION,
               "index-free VM shape and ownership ABI");

_Static_assert(offsetof(JSFrameRegisterState, direct_host_calls) + sizeof(bool) ==
                       FRAME_REGISTER_STATE_EXCEPTION + 2 &&
                   offsetof(JSFrameRegisterState, iterator_checkpoint_depth) ==
                       FRAME_REGISTER_STATE_EXCEPTION + 4 &&
                   sizeof(JSFrameRegisterState) == FRAME_REGISTER_STATE_BYTES,
               "literal-active and lazy ownership have separate state padding bytes");

_Static_assert(JS_TAG_FIRST == -9 && sizeof(JSValue) == QJS_ABI_SIZE_JSValue,
               "insert2 tag and value ABI");

_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   offsetof(JSFrameRegisterState, rt) == 56 &&
                   offsetof(JSRuntime, atom_array) == QJS_ABI_OFF_JSRuntime_atom_array &&
                   JS_TAG_BIG_INT == -9 && JS_TAG_SYMBOL == -8 && JS_TAG_STRING == -7 &&
                   JS_TAG_STRING_ROPE == -6 && JS_TAG_OBJECT == -1 && JS_TAG_INT == 0 &&
                   JS_TAG_BOOL == 1 && JS_TAG_NULL == 2 && JS_TAG_UNDEFINED == 3 &&
                   JS_TAG_SHORT_BIG_INT == 7 && JS_TAG_FLOAT64 == 8 && JS_ATOM_string == 76 &&
                   JS_ATOM_number == 74 && JS_ATOM_undefined == 73 && JS_ATOM_boolean == 75 &&
                   JS_ATOM_object == 77 && JS_ATOM_bigint == 149 && JS_ATOM_symbol == 78,
               "typeof leaf private ABI");

_Static_assert(JS_ATOM_object == 77, "predicate leaf atom identity");

_Static_assert(sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   sizeof(JSGCObjectHeader) == QJS_ABI_SIZE_JSGCObjectHeader &&
                   offsetof(JSObject, header) == QJS_ABI_OFF_JSObject_header &&
                   offsetof(JSObject, class_id) == QJS_ABI_OFF_JSObject_class_id &&
                   offsetof(JSString, hash_next) == QJS_ABI_OFF_JSString_hash_next &&
                   offsetof(JSStringRope, len) == QJS_ABI_OFF_JSStringRope_len &&
                   JS_TAG_OBJECT == -1 && JS_TAG_STRING == -7 && JS_TAG_STRING_ROPE == -6,
               "truthiness private ABI");

#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(offsetof(JSMallocBlockHeader, user_data) -
                       offsetof(JSMallocBlockHeader, ref_count) ==
                   4,
               "prefix reference count is measured before the value pointer");
#else
_Static_assert(QJS_ABI_REF_COUNT_OFFSET == 0 && offsetof(JSObject, header) == 0,
               "inline reference count is measured at the value pointer");
#endif

/* The existing native Number truth leaf consumes this exact ABI/mode word. */
_Static_assert(JS_TAG_FLOAT64 == 8 && sizeof(JSValue) == 16 &&
                   sizeof(JS_FrameOrdinaryLiteralMode) == 4,
               "native Number truth ABI");
