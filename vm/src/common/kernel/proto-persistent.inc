/* Persistent cold second level. Original CD fill is byte-for-byte retained.
 * Shared fields are atomic; no coherent multi-field snapshot is required.
 * Native try validates one captured atom_slot against the current holder and
 * promotes CURRENT pc/holder plus that snapshot into the private table.
 * No cache pointer is dereferenced; no refs, allocations or GC/free hooks. */
typedef struct JSFrameProtoPersistentHint {
    uintptr_t pc, holder;
    uint64_t atom_slot;
    int marker;
    uint32_t reserved;
} JSFrameProtoPersistentHint;
_Static_assert(sizeof(JSFrameProtoPersistentHint) == 32 &&
                   offsetof(JSFrameProtoPersistentHint, marker) == 24 &&
                   offsetof(JSObject, shape) == QJS_ABI_OFF_JSObject_shape &&
                   offsetof(JSShape, prop_count) == QJS_ABI_OFF_JSShape_prop_count &&
                   sizeof(JSShapeProperty) == 8 &&
                   sizeof(JSFunctionBytecode) == QJS_ABI_SIZE_JSFunctionBytecode &&
                   sizeof(JSValue) == QJS_ABI_SIZE_JSValue && __atomic_always_lock_free(8, 0) &&
                   __atomic_always_lock_free(4, 0),
               "persistent native snapshot ABI");
#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(offsetof(JSShape, hash_table) == QJS_ABI_OFF_JSShape_hash_table,
               "trailing shape buckets");
#else
_Static_assert(offsetof(JSShape, prop) == QJS_ABI_OFF_JSShape_prop, "inline shape properties");
#endif
JSFrameProtoPersistentHint JS_FrameProtoPersistentHints[128]
    __attribute__((section(".qjspmet$hints"), aligned(8))) = {0};
unsigned char JS_FrameProtoPersistentNext[64] __attribute__((section(".qjspmet$next"))) = {0};
volatile unsigned char JS_FrameProtoPersistControl __attribute__((section(".qjspmet$control"))) = 0;
extern int JS_FrameProtoLoadFill(void *);
extern volatile unsigned char JS_FrameProtoLoadControl;

PROTO_PERSIST_CODE int JS_FrameProtoPersistentFill(void *opaque)
{
    int status = JS_FrameProtoLoadFill(opaque);
    unsigned char persist, primary;
    unsigned char *state = opaque, *sites;
    const uint8_t *pc;
    JSValue *sp;
    void *frame;
    JSFunctionBytecode *b;
    JSObject *holder;
    JSFrameProtoPersistentHint h, first, second;
    uint32_t atom, slot;
    uintptr_t key, bucket, pb, p0, p1;
    JSFrameProtoPersistentHint *p;
    /* Platform aligned byte read + compiler memory barrier implements acquire.
     * Explicit RIP-relative data avoids GCC .refptr COMDAT addresses when this
     * isolated object is routed late. No absolute pointer relocation. */
    QJS_PROTO_LOAD_PRIMARY(primary);
    if (!status || primary != 1)
        return status;
    persist = __atomic_load_n(&JS_FrameProtoPersistControl, __ATOMIC_ACQUIRE);
    if (!persist) {
        unsigned char expected = 0, desired = getenv("QJS_DISABLE_PROTO_LOAD_PERSIST") ? 2 : 1;
        __atomic_compare_exchange_n(&JS_FrameProtoPersistControl, &expected, desired, 0,
                                    __ATOMIC_RELEASE, __ATOMIC_RELAXED);
        persist = __atomic_load_n(&JS_FrameProtoPersistControl, __ATOMIC_ACQUIRE);
    }
    if (persist != 1)
        return status;
    memcpy(&pc, state + 16, sizeof(pc));
    memcpy(&sp, state + 24, sizeof(sp));
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    memcpy(&sites, state + 2280, sizeof(sites));
#else
    memcpy(&sites, state + 144, sizeof(sites));
#endif
    memcpy(&atom, pc + 1, sizeof(atom));
    if (JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_OBJECT)
        holder = JS_VALUE_GET_OBJ(sp[-1])->shape->proto;
    else if (JS_VALUE_GET_TAG(sp[-1]) == JS_TAG_STRING) {
        memcpy(&frame, state, sizeof(frame));
        memcpy(&b, (unsigned char *)frame + 80, sizeof(b));
        if (JS_VALUE_GET_TAG(b->realm->class_proto[JS_CLASS_STRING]) != JS_TAG_OBJECT)
            return status;
        holder = JS_VALUE_GET_OBJ(b->realm->class_proto[JS_CLASS_STRING]);
    } else
        return status;
    if (!holder || !sites)
        return status;
    key = (uintptr_t)pc;
    bucket = (key ^ (key >> 6) ^ (key >> 12)) & 7;
    sites += bucket * 64;
    memcpy(&first, sites, sizeof(first));
    memcpy(&second, sites + 32, sizeof(second));
    if (first.pc == key && first.marker == -1 && first.holder == (uintptr_t)holder &&
        (uint32_t)(first.atom_slot >> 32) == atom)
        h = first;
    else if (second.pc == key && second.marker == -1 && second.holder == (uintptr_t)holder &&
             (uint32_t)(second.atom_slot >> 32) == atom)
        h = second;
    else
        return status;
    slot = (uint32_t)h.atom_slot;
    if (slot >= holder->shape->prop_count)
        return status;
#if QJS_ABI_HAS_PREFIX_RC
    JSShapeProperty *props =
        (JSShapeProperty *)(holder->shape->hash_table + holder->shape->prop_hash_mask + 1);
#else
    JSShapeProperty *props = holder->shape->prop;
#endif
    if (props[slot].atom != atom || (props[slot].flags & JS_PROP_TMASK))
        return status;
    pb = (key ^ (key >> 6) ^ (key >> 12)) & 63;
    p = JS_FrameProtoPersistentHints + pb * 2;
    p0 = __atomic_load_n(&p[0].pc, __ATOMIC_RELAXED);
    p1 = __atomic_load_n(&p[1].pc, __ATOMIC_RELAXED);
    int way;
    if (p0 == key && __atomic_load_n(&p[0].holder, __ATOMIC_RELAXED) == (uintptr_t)holder &&
        (uint32_t)(__atomic_load_n(&p[0].atom_slot, __ATOMIC_RELAXED) >> 32) == atom)
        way = 0;
    else if (p1 == key && __atomic_load_n(&p[1].holder, __ATOMIC_RELAXED) == (uintptr_t)holder &&
             (uint32_t)(__atomic_load_n(&p[1].atom_slot, __ATOMIC_RELAXED) >> 32) == atom)
        way = 1;
    else if (!p0)
        way = 0;
    else if (!p1)
        way = 1;
    else
        way = __atomic_fetch_xor(&JS_FrameProtoPersistentNext[pb], 1, __ATOMIC_RELAXED) & 1;
    p += way;
    __atomic_store_n(&p->holder, h.holder, __ATOMIC_RELAXED);
    __atomic_store_n(&p->atom_slot, h.atom_slot, __ATOMIC_RELAXED);
    __atomic_store_n(&p->marker, -1, __ATOMIC_RELAXED);
    __atomic_store_n(&p->pc, key, __ATOMIC_RELEASE);
    return status;
}
