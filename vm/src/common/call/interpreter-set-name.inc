/* Original pinned set_name operation, included only by supported executors. */
CASE(OP_set_name) :
{
    int ret;
    JSAtom atom;
    atom = get_u32(pc);
    pc += 4;

    ret = JS_DefineObjectName(ctx, sp[-1], atom, JS_PROP_CONFIGURABLE);
    if (unlikely(ret < 0))
        goto exception;
}
BREAK;
