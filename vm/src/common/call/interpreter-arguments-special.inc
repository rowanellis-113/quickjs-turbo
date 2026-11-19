/* Original full argument-frame objects and retained ordinary special cases. MIT. */
CASE(OP_special_object) :
{
    unsigned special = *pc++;
    JSValue object;
    if (FRAME_KIND(b) == 2 && FRAME_ITERATOR_KIND(b) == 128)
        object = JS_AArch64ArgumentsObject(frame, special);
    else if (special == OP_SPECIAL_OBJECT_THIS_FUNC)
        object = js_dup(sf->cur_func);
    else if (special == OP_SPECIAL_OBJECT_NULL_PROTO)
        object = JS_NewObjectProtoClass(ctx, JS_NULL, JS_CLASS_OBJECT);
    else
        object = JS_ThrowInternalError(ctx, "unsupported explicit-frame special object");
    *sp++ = object;
    if (unlikely(JS_IsException(sp[-1])))
        goto exception;
}
BREAK;
