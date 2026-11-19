/* Original OP_special_object THIS_FUNC semantic owner, quickjs.c. The
 * function validator admits this one subopcode before any frame executes. */
CASE(OP_special_object) : if (unlikely(*pc++ != OP_SPECIAL_OBJECT_THIS_FUNC))
{
    JS_ThrowInternalError(ctx, "unsupported explicit-frame special object");
    goto exception;
}
*sp++ = js_dup(sf->cur_func);
BREAK;
