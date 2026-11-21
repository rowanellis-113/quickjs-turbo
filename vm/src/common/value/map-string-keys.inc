/* Same code-unit hash for flat, interned, and rope strings. A string can
 * subsequently be atomized as a Symbol description, so its atom hash is
 * reusable only for ordinary string atoms. Zero is the uncached sentinel. */
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

static no_inline JSMapRecord *js_map_find_string_record(JSContext *ctx, struct list_head *bucket,
                                                        JSValueConst key, uint32_t hash)
{
    JSString *query = JS_VALUE_GET_STRING(key);
    struct list_head *el;
    list_for_each(el, bucket)
    {
        JSMapRecord *record = list_entry(el, JSMapRecord, hash_link);
        if (JS_VALUE_GET_TAG(record->key) == JS_TAG_STRING) {
            JSString *stored = JS_VALUE_GET_STRING(record->key);
            if (stored == query ||
                (stored->len == query->len && js_map_flat_string_hash(stored) == hash &&
                 js_string_memcmp(stored, query, query->len) == 0))
                return record;
        } else if (JS_VALUE_GET_TAG(record->key) == JS_TAG_STRING_ROPE &&
                   js_same_value_zero(ctx, record->key, key)) {
            return record;
        }
    }
    return NULL;
}
