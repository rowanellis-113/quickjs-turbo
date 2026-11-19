/* QuickJS-NG 60984dc's primitive arithmetic classifier (MIT).
 * This helper has no allocation, coercion, reference-count or private-layout
 * access. Keep the accepted opcode fast path on the older 0.15.1 core. */
static inline bool js_arith_to_float64(JSValue v, double *pd)
{
    uint32_t tag = JS_VALUE_GET_TAG(v);
    if (JS_TAG_IS_FLOAT64(tag))
        *pd = JS_VALUE_GET_FLOAT64(v);
    else if (tag == JS_TAG_INT)
        *pd = JS_VALUE_GET_INT(v);
    else
        return false;
    return true;
}
