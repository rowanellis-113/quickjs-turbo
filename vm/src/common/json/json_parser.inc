static JSValue frame_json_value(FrameJSONParser *p)
{
    FrameJSONText *t = &p->text;
    JSValue value = JS_UNDEFINED, child;
    JSAtom atom;
    unsigned c, close;
    uint32_t idx = 0;
    const char *word;
    size_t n, i;
    frame_json_space(t);
    c = frame_json_char(t, t->pos);
    if (++p->depth > 512 || frame_json_parser_stack_overflow(p)) {
        p->error = 1;
        goto done;
    }
    if (c == '"') {
        value = frame_json_string(p, 0, NULL);
        goto done;
    }
    if (c == '-' || (c >= '0' && c <= '9')) {
        value = frame_json_number(p);
        goto done;
    }
    if (c == '{' || c == '[') {
        close = c == '{' ? '}' : ']';
        t->pos++;
        value = c == '{' ? JS_NewObject(p->ctx) : JS_NewArray(p->ctx);
        if (JS_IsException(value)) {
            p->error = 2;
            goto done;
        }
        frame_json_space(t);
        if (frame_json_char(t, t->pos) == close) {
            t->pos++;
            goto done;
        }
        for (;;) {
            atom = JS_ATOM_NULL;
            if (c == '{') {
                if (frame_json_char(t, t->pos) != '"')
                    goto invalid;
                frame_json_string(p, 1, &atom);
                if (p->error)
                    goto invalid;
                frame_json_space(t);
                if (frame_json_char(t, t->pos++) != ':') {
                    JS_FreeAtom(p->ctx, atom);
                    goto invalid;
                }
            }
            child = frame_json_value(p);
            if (p->error) {
                JS_FreeAtom(p->ctx, atom);
                JS_FreeValue(p->ctx, child);
                goto invalid;
            }
            if (c == '{') {
                i = frame_json_property(p, value, atom, child);
                JS_FreeAtom(p->ctx, atom);
            } else if (p->mode & JSON_NO_BUILD) {
                i = JS_DefinePropertyValueUint32(p->ctx, value, idx++, child, JS_PROP_C_W_E);
            } else {
                i = add_fast_array_element(p->ctx, JS_VALUE_GET_OBJ(value), child, JS_PROP_THROW);
                idx++;
            }
            if ((int)i < 0) {
                p->error = 2;
                goto invalid;
            }
            frame_json_space(t);
            if (frame_json_char(t, t->pos) == close) {
                t->pos++;
                goto done;
            }
            if (frame_json_char(t, t->pos++) != ',')
                goto invalid;
            frame_json_space(t);
        }
    }
    if (c == 't') {
        word = "true";
        n = 4;
        value = JS_TRUE;
    } else if (c == 'f') {
        word = "false";
        n = 5;
        value = JS_FALSE;
    } else if (c == 'n') {
        word = "null";
        n = 4;
        value = JS_NULL;
    } else
        goto invalid;
    for (i = 0; i < n; i++)
        if (frame_json_char(t, t->pos++) != (unsigned char)word[i])
            goto invalid;
    goto done;
invalid:
    if (!p->error)
        p->error = 1;
    JS_FreeValue(p->ctx, value);
    value = JS_UNDEFINED;
done:
    p->depth--;
    return value;
}
JSON_CODE static JSValue frame_json_parse_text(JSContext *ctx, FrameJSONText text, unsigned mode,
                                               int *error)
{
    FrameJSONParser p;
    JSValue value;
    unsigned i;
    p.ctx = ctx;
    p.text = text;
    p.mode = mode | (text.length < 128 ? JSON_NO_CACHE : 0);
    p.depth = 0;
    p.error = 0;
    p.names_used = p.strings_used = p.transitions_used = 0;
    value = frame_json_value(&p);
    frame_json_space(&p.text);
    if (!p.error && p.text.pos != p.text.length)
        p.error = 1;
    for (i = 0; i < 16; i++) {
        if (p.names_used & (1u << i))
            JS_FreeAtom(ctx, p.names[i].atom);
        if (p.strings_used & (1u << i))
            JS_FreeValue(ctx, p.strings[i].value);
        if (p.transitions_used & (1u << i)) {
            js_free_shape(ctx->rt, p.transitions[i].from);
            js_free_shape(ctx->rt, p.transitions[i].to);
        }
    }
    *error = p.error;
    if (p.error) {
        JS_FreeValue(ctx, value);
        return p.error == 2 ? JS_EXCEPTION : JS_UNDEFINED;
    }
    return value;
}
/* Keep callable reviver parsing/source records on the upstream path for now.
 * Conversion of a non-string input happens exactly once in either path. */
JSON_CODE JSValue JS_FrameJSONParse(JSContext *ctx, JSValueConst this_val, int argc,
                                    JSValueConst *argv)
{
    JSString *s;
    JSValue result, input;
    FrameJSONText text;
    unsigned mode = frame_json_mode();
    int error;
    if ((mode & JSON_NO_DIRECT) || (argc > 1 && JS_IsFunction(ctx, argv[1])))
        return js_json_parse(ctx, this_val, argc, argv);
    input = JS_ToString(ctx, argv[0]);
    if (JS_IsException(input))
        return input;
    s = JS_VALUE_GET_STRING(input);
    text.length = s->len;
    text.pos = 0;
    text.wide = s->is_wide_char;
    text.p8 = text.wide ? NULL : str8(s);
    text.p16 = text.wide ? str16(s) : NULL;
    result = frame_json_parse_text(ctx, text, mode, &error);
    if (error == 1)
        result = js_json_parse(ctx, this_val, 1, (JSValueConst *)&input);
    JS_FreeValue(ctx, input);
    return result;
}
/* Public UTF-8 API: ASCII borrows the caller's bounded buffer. Non-ASCII keeps
 * the original UTF-8 validation/diagnostics instead of treating it as Latin-1. */
extern JSValue JS_LegacyParseJSON(JSContext *, const char *, size_t, const char *);
JSON_CODE JSValue JS_ParseJSON(JSContext *ctx, const char *buf, size_t len, const char *filename)
{
    FrameJSONText text;
    JSValue result;
    size_t i;
    unsigned mode = frame_json_mode();
    int error;
    if (mode & JSON_NO_DIRECT)
        goto original;
    for (i = 0; i < len; i++)
        if ((unsigned char)buf[i] >= 128)
            goto original;
    text.p8 = (const uint8_t *)buf;
    text.p16 = NULL;
    text.wide = 0;
    text.length = len;
    text.pos = 0;
    result = frame_json_parse_text(ctx, text, mode, &error);
    if (!error || error == 2)
        return result;
original:
    return JS_LegacyParseJSON(ctx, buf, len, filename);
}
