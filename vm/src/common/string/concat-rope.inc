/* The caller admits only shared flat prefixes that the original helper
 * would copy. Platform control supplies js_frame_shared_concat_mode().
 * Existing rope operands keep NG's coalescing/depth rules. No mutation of
 * a shared string or inferred local ownership is permitted. */
JSValue JS_FrameSharedConcatRope(JSContext *ctx, JSValue left, JSValue right)
{
    unsigned char mode = js_frame_shared_concat_mode();
    if (mode != 1)
        return JS_ConcatString(ctx, left, right);
    assert(JS_VALUE_GET_TAG(left) == JS_TAG_STRING && JS_VALUE_GET_TAG(right) == JS_TAG_STRING);
    assert(JS_REF_COUNT(JS_VALUE_GET_STRING(left)) > 1);
    assert(JS_VALUE_GET_STRING(left)->len > JS_STRING_ROPE_SHORT_LEN &&
           JS_VALUE_GET_STRING(left)->len <= JS_STRING_ROPE_SHORT2_LEN);
    assert(JS_VALUE_GET_STRING(right)->len &&
           JS_VALUE_GET_STRING(right)->len <= JS_STRING_ROPE_SHORT_LEN);
    /* At most8192+512 characters, so neither length overflow nor depth
       rebalance is possible for this new two-flat-leaf node. Both inputs
       are consumed by the original constructor, including OOM cleanup. */
    return js_new_string_rope(ctx, left, right);
}
