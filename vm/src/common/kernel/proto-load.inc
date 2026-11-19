/* Interp-inspired ProtoLoad using the existing two-way activation table.
 * Entries are weak hints, never roots and never dereferenced cached pointers.
 * The ASM lane checks live receiver absence, live prototype, descriptor and
 * current value. No JS allocation/hook occurs in fill or a cache hit. MIT. */
typedef struct JSFrameProtoHint {
    uintptr_t pc;
    uintptr_t holder;
    uint64_t atom_slot;
    int marker;
    uint32_t reserved;
} JSFrameProtoHint;
_Static_assert(sizeof(JSFrameProtoHint) == 32 && offsetof(JSFrameProtoHint, marker) == 24 &&
                   sizeof(uintptr_t) == 8 && sizeof(JSValue) == QJS_ABI_SIZE_JSValue &&
                   sizeof(JSProperty) == QJS_ABI_SIZE_JSProperty && sizeof(JSShapeProperty) == 8 &&
                   offsetof(JSShapeProperty, atom) == QJS_ABI_OFF_JSShapeProperty_atom &&
                   offsetof(JSShape, prop_hash_mask) == QJS_ABI_OFF_JSShape_prop_hash_mask &&
                   offsetof(JSShape, prop_count) == QJS_ABI_OFF_JSShape_prop_count &&
                   offsetof(JSShape, proto) == QJS_ABI_OFF_JSShape_proto &&
                   offsetof(JSObject, shape) == QJS_ABI_OFF_JSObject_shape &&
                   offsetof(JSObject, prop) == QJS_ABI_OFF_JSObject_prop &&
                   offsetof(JSContext, class_proto) == QJS_ABI_OFF_JSContext_class_proto &&
                   sizeof(JSStackFrame) == QJS_ABI_SIZE_JSStackFrame &&
                   offsetof(JSFunctionBytecode, realm) == QJS_ABI_OFF_JSFunctionBytecode_realm &&
                   JS_CLASS_ARRAY == 2 && JS_CLASS_STRING == 5 && JS_TAG_OBJECT == -1 &&
                   JS_TAG_STRING == -7 && JS_PROP_TMASK == 48,
               "native live prototype hint ABI");
#if QJS_ABI_HAS_PREFIX_RC
_Static_assert(offsetof(JSShape, hash_table) == QJS_ABI_OFF_JSShape_hash_table,
               "trailing shape buckets");
#else
_Static_assert(offsetof(JSShape, prop) == QJS_ABI_OFF_JSShape_prop,
               "leading shape buckets and inline properties");
#endif
volatile unsigned char JS_FrameProtoLoadControl
    __attribute__((section(".data$zzzzzzzzzzprotoload"))) = 0;

/* All table access is memcpy: the existing table's effective C type remains
 * JSFrameCallSite. argc==-1 cannot match any real C call cache argc. */
PROTO_LOAD_CODE int JS_FrameProtoLoadFill(void *opaque)
{
    unsigned char *state = opaque;
    void *frame;
    const uint8_t *pc;
    JSValue *sp;
    JSFunctionBytecode *b;
    unsigned char *sites, *next;
    JSFrameProtoHint hint, first, second;
    JSObject *receiver, *holder;
    JSShape *shape;
    JSShapeProperty *props;
    uint32_t atom, slot = UINT32_MAX;
    uintptr_t index, bucket, key;
    int tag, way;
    unsigned char control = __atomic_load_n(&JS_FrameProtoLoadControl, __ATOMIC_ACQUIRE);
    if (!control) {
        unsigned char expected = 0;
        unsigned char desired = getenv("QJS_DISABLE_PROTO_LOAD_CACHE") ? 2 : 1;
        __atomic_compare_exchange_n(&JS_FrameProtoLoadControl, &expected, desired, 0,
                                    __ATOMIC_RELEASE, __ATOMIC_RELAXED);
        control = __atomic_load_n(&JS_FrameProtoLoadControl, __ATOMIC_ACQUIRE);
    }
    if (control != 1)
        return 0;
    memcpy(&frame, state, sizeof(frame));
    memcpy(&pc, state + 16, sizeof(pc));
    memcpy(&sp, state + 24, sizeof(sp));
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    memcpy(&sites, state + 2280, sizeof(sites));
    memcpy(&next, state + 2288, sizeof(next));
#else
    memcpy(&sites, state + 144, sizeof(sites));
    memcpy(&next, state + 152, sizeof(next));
#endif
    memcpy(&atom, pc + 1, sizeof(atom));
    if (!sites || !next || (atom & 0x80000000u))
        return 0;
    tag = JS_VALUE_GET_TAG(sp[-1]);
    if (tag == JS_TAG_OBJECT) {
        receiver = JS_VALUE_GET_OBJ(sp[-1]);
        if (receiver->is_exotic && receiver->class_id != JS_CLASS_ARRAY)
            return 0;
        holder = receiver->shape->proto;
    } else if (tag == JS_TAG_STRING && atom != JS_ATOM_length) {
        memcpy(&b, (unsigned char *)frame + 80, sizeof(b));
        if (JS_VALUE_GET_TAG(b->realm->class_proto[JS_CLASS_STRING]) != JS_TAG_OBJECT)
            return 0;
        holder = JS_VALUE_GET_OBJ(b->realm->class_proto[JS_CLASS_STRING]);
    } else
        return 0;
    if (!holder)
        return 0;
    shape = holder->shape;
    /* Exact selected-source find_own_property1 formula. */
#if QJS_ABI_HAS_PREFIX_RC
    index = hash_uintptr(atom) >> (1 + clz_uintptr(shape->prop_hash_mask + 1));
    props = (JSShapeProperty *)(shape->hash_table + shape->prop_hash_mask + 1);
    index = ((uint32_t *)props)[-(intptr_t)index - 1];
#else
    props = shape->prop;
    index = ((uint32_t *)shape)[-(intptr_t)(atom & shape->prop_hash_mask) - 1];
#endif
    while (index) {
        if (props[index - 1].atom == atom) {
            slot = (uint32_t)index - 1;
            break;
        }
        index = props[index - 1].hash_next;
    }
    key = (uintptr_t)pc;
    bucket = (key ^ (key >> 6) ^ (key >> 12)) & 7;
    sites += bucket * 64;
    memcpy(&first, sites, sizeof(first));
    memcpy(&second, sites + 32, sizeof(second));
    if (first.pc == key && first.marker == -1 && first.holder == (uintptr_t)holder &&
        (uint32_t)(first.atom_slot >> 32) == atom)
        way = 0;
    else if (second.pc == key && second.marker == -1 && second.holder == (uintptr_t)holder &&
             (uint32_t)(second.atom_slot >> 32) == atom)
        way = 1;
    else if (!first.pc) {
        way = 0;
        next[bucket] = 1;
    } else if (!second.pc) {
        way = 1;
        next[bucket] = 0;
    } else {
        way = next[bucket] & 1;
        next[bucket] ^= 1;
    }
    hint.pc = key;
    hint.holder = (uintptr_t)holder;
    hint.atom_slot = ((uint64_t)atom << 32) | slot;
    hint.marker = -1;
    hint.reserved = 0;
    memcpy(sites + way * 32, &hint, sizeof(hint));
    return 1;
}
