/* RegExp.prototype.test: validate R, ToString(S), then RegExpExec(R, S).
 * Keep the converted string owned across getters, reentry and GC. Flat and
 * rope strings are already language strings; duplicating either is ToString.
 * The complete original exec protocol, matcher and result cleanup remain.
 */
JSValue JS_FrameRegExpTest(JSContext *ctx, JSValueConst this_val, int argc, JSValueConst *argv)
{
    JSValue str, val;
    bool ret;

    if (!JS_IsObject(this_val))
        return JS_ThrowTypeErrorNotAnObject(ctx);
    str = JS_IsString(argv[0]) ? js_dup(argv[0]) : JS_ToString(ctx, argv[0]);
    if (JS_IsException(str))
        return JS_EXCEPTION;
    val = JS_RegExpExec(ctx, this_val, str);
    JS_FreeValue(ctx, str);
    if (JS_IsException(val))
        return JS_EXCEPTION;
    ret = !JS_IsNull(val);
    JS_FreeValue(ctx, val);
    return js_bool(ret);
}
