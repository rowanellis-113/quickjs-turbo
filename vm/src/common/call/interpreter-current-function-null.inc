/* Exact original THIS_FUNC and NULL_PROTO cases, quickjs.c; MIT. */
CASE(OP_special_object) : switch (*pc++)
{
case OP_SPECIAL_OBJECT_THIS_FUNC:
    *sp++ = js_dup(sf->cur_func);
    break;
case OP_SPECIAL_OBJECT_NULL_PROTO:
    *sp++ = JS_NewObjectProtoClass(ctx, JS_NULL, JS_CLASS_OBJECT);
    if (unlikely(JS_IsException(sp[-1])))
        goto exception;
    break;
default:
    JS_ThrowInternalError(ctx, "unsupported explicit-frame special object");
    goto exception;
}
BREAK;
