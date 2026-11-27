/* Same code-unit hash for flat, interned, and rope strings. A string can
 * subsequently be atomized as a Symbol description, so its atom hash is
 * reusable only for ordinary string atoms. Zero is the uncached sentinel. */
static uint32_t map_hash_key(JSContext *ctx, JSValueConst key);

static inline uint32_t js_map_flat_string_hash(JSString *str)
{
    uint32_t hash = str->hash;
    unsigned atom_type = str->atom_type;
    if (atom_type == JS_ATOM_TYPE_STRING || (!atom_type && hash))
        return hash;
    hash = hash_string(str, JS_ATOM_TYPE_STRING) & JS_ATOM_HASH_MASK;
    if (!atom_type)
        str->hash = hash;
    return hash;
}

static inline uint32_t js_map_ptr_hash(JSContext *ctx, const void *ptr, uint32_t tag)
{
#ifdef QJS_MAP_POINTER_HASH
    return ((uint32_t)(((uint64_t)((uintptr_t)ptr ^ tag) * UINT64_C(0x61C8864680B583EB)) >> 32)) ^
           ctx->hash_seed;
#else
    return ((uint32_t)((uintptr_t)ptr * 3163)) ^ ctx->hash_seed ^ hash32(tag);
#endif
}

static inline uint32_t js_map_int_hash(JSContext *ctx, int32_t iv)
{
    JSFloat64Union u;
    u.d = (double)iv;
#ifdef QJS_MAP_POINTER_HASH
    u.u64 = ((u.u64 ^ (u.u64 >> 33)) ^ (uint64_t)(uint32_t)JS_TAG_FLOAT64) *
            UINT64_C(0xff51afd7ed558ccd);
    return ((uint32_t)(((u.u64 ^ (u.u64 >> 33)) * UINT64_C(0xc4ceb9fe1a85ec53)) >> 32)) ^
           ctx->hash_seed;
#else
    return ((u.u32[0] ^ u.u32[1]) * 3163) ^ ctx->hash_seed ^ hash32((uint32_t)JS_TAG_FLOAT64);
#endif
}

static inline uint32_t js_map_hash_key_fast(JSContext *ctx, JSValueConst key)
{
    int tag = JS_VALUE_GET_TAG(key);
    if (tag == JS_TAG_STRING)
        return js_map_flat_string_hash(JS_VALUE_GET_STRING(key)) ^ ctx->hash_seed ^
               hash32((uint32_t)JS_TAG_STRING);
    if (tag == JS_TAG_OBJECT)
        return js_map_ptr_hash(ctx, JS_VALUE_GET_OBJ(key), (uint32_t)JS_TAG_OBJECT);
    if (tag == JS_TAG_INT)
        return js_map_int_hash(ctx, JS_VALUE_GET_INT(key));
    if (tag == JS_TAG_SYMBOL)
        return js_map_ptr_hash(ctx, JS_VALUE_GET_PTR(key), (uint32_t)JS_TAG_SYMBOL);
    return map_hash_key(ctx, key);
}

static inline JSMapRecord *js_map_find_record_hash(JSContext *ctx, JSMapState *s, JSValueConst key,
                                                   uint32_t *out_hash)
{
    int tag = JS_VALUE_GET_TAG(key);
    uint32_t mask = s->hash_size - 1;
    struct list_head *bucket, *el;

    if (tag == JS_TAG_STRING) {
        JSString *query = JS_VALUE_GET_STRING(key);
        uint32_t sh = js_map_flat_string_hash(query);
        uint32_t h = sh ^ ctx->hash_seed ^ hash32((uint32_t)JS_TAG_STRING);
        *out_hash = h;
        bucket = &s->hash_table[h & mask];
        list_for_each(el, bucket)
        {
            JSMapRecord *record = list_entry(el, JSMapRecord, hash_link);
            int ktag = JS_VALUE_GET_TAG(record->key);
            if (likely(ktag == JS_TAG_STRING)) {
                JSString *stored = JS_VALUE_GET_STRING(record->key);
                if (stored == query ||
                    (stored->len == query->len && js_map_flat_string_hash(stored) == sh &&
                     js_string_memcmp(stored, query, query->len) == 0))
                    return record;
            } else if (unlikely(ktag == JS_TAG_STRING_ROPE) &&
                       js_same_value_zero(ctx, record->key, key)) {
                return record;
            }
        }
        return NULL;
    }
    if (tag == JS_TAG_OBJECT) {
        JSObject *obj = JS_VALUE_GET_OBJ(key);
        uint32_t h = js_map_ptr_hash(ctx, obj, (uint32_t)JS_TAG_OBJECT);
        *out_hash = h;
        bucket = &s->hash_table[h & mask];
        list_for_each(el, bucket)
        {
            JSMapRecord *record = list_entry(el, JSMapRecord, hash_link);
            if (likely(JS_VALUE_GET_TAG(record->key) == JS_TAG_OBJECT) &&
                JS_VALUE_GET_OBJ(record->key) == obj)
                return record;
        }
        return NULL;
    }
    if (tag == JS_TAG_INT) {
        int32_t iv = JS_VALUE_GET_INT(key);
        double d = (double)iv;
        uint32_t h = js_map_int_hash(ctx, iv);
        *out_hash = h;
        bucket = &s->hash_table[h & mask];
        list_for_each(el, bucket)
        {
            JSMapRecord *record = list_entry(el, JSMapRecord, hash_link);
            int ktag = JS_VALUE_GET_TAG(record->key);
            if (likely(ktag == JS_TAG_INT)) {
                if (JS_VALUE_GET_INT(record->key) == iv)
                    return record;
            } else if (JS_TAG_IS_FLOAT64(ktag) && JS_VALUE_GET_FLOAT64(record->key) == d) {
                return record;
            }
        }
        return NULL;
    }
    if (tag == JS_TAG_SYMBOL) {
        void *sym = JS_VALUE_GET_PTR(key);
        uint32_t h = js_map_ptr_hash(ctx, sym, (uint32_t)JS_TAG_SYMBOL);
        *out_hash = h;
        bucket = &s->hash_table[h & mask];
        list_for_each(el, bucket)
        {
            JSMapRecord *record = list_entry(el, JSMapRecord, hash_link);
            if (likely(JS_VALUE_GET_TAG(record->key) == JS_TAG_SYMBOL) &&
                JS_VALUE_GET_PTR(record->key) == sym)
                return record;
        }
        return NULL;
    }
    {
        uint32_t h = map_hash_key(ctx, key);
        *out_hash = h;
        bucket = &s->hash_table[h & mask];
        list_for_each(el, bucket)
        {
            JSMapRecord *record = list_entry(el, JSMapRecord, hash_link);
            if (js_same_value_zero(ctx, record->key, key))
                return record;
        }
        return NULL;
    }
}
