JSON_INLINE unsigned frame_json_hash(FrameJSONText *t, size_t start, unsigned n)
{
    unsigned h = 2166136261u, i;
    for (i = 0; i < n; i++)
        h = (h ^ frame_json_char(t, start + i)) * 16777619u;
    return h ^ n;
}
JSON_INLINE int frame_json_equal(FrameJSONText *t, size_t a, size_t b, unsigned n)
{
    return t->wide ? !memcmp(t->p16 + a, t->p16 + b, (size_t)n * 2)
                   : !memcmp(t->p8 + a, t->p8 + b, n);
}
JSON_INLINE int frame_json_hex(unsigned c)
{
    if (c >= '0' && c <= '9')
        return (int)c - '0';
    if (c >= 'a' && c <= 'f')
        return (int)c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
        return (int)c - 'A' + 10;
    return -1;
}
static JSValue frame_json_string(FrameJSONParser *p, int key, JSAtom *atom)
{
    FrameJSONText *t = &p->text;
    size_t start = ++t->pos, end = start;
    unsigned c, h = 0, n, slot = 0, use_cache = !(p->mode & JSON_NO_CACHE);
    JSValue v;
    StringBuffer b;
    if (t->wide)
        end += frame_json_scan16(t->p16 + start, t->length - start, !(p->mode & JSON_NO_SIMD), 0);
    else
        end += frame_json_scan8(t->p8 + start, t->length - start, !(p->mode & JSON_NO_SIMD));
    if (frame_json_char(t, end) == '"') {
        n = (unsigned)(end - start);
        t->pos = end + 1;
        if (use_cache && n <= 27) {
            h = frame_json_hash(t, start, n);
            slot = h & 15;
            if (key && (p->names_used & (1u << slot))) {
                FrameJSONName *e = &p->names[slot];
                if (e->hash == h && e->len == n && frame_json_equal(t, e->start, start, n)) {
                    *atom = frame_json_dup_atom(p->ctx, e->atom);
                    return JS_UNDEFINED;
                }
            } else if (!key && (p->strings_used & (1u << slot))) {
                FrameJSONString *e = &p->strings[slot];
                if (e->hash == h && e->len == n && frame_json_equal(t, e->start, start, n))
                    return js_dup(e->value);
            }
        }
        v = t->wide ? js_new_string16_len(p->ctx, t->p16 + start, n)
                    : js_new_string8_len(p->ctx, (const char *)t->p8 + start, n);
        if (JS_IsException(v)) {
            p->error = 2;
            return v;
        }
        if (key) {
            *atom = JS_ValueToAtom(p->ctx, v);
            JS_FreeValue(p->ctx, v);
            if (*atom == JS_ATOM_NULL) {
                p->error = 2;
                return JS_EXCEPTION;
            }
            if (use_cache && n <= 27) {
                FrameJSONName *e = &p->names[slot];
                if (p->names_used & (1u << slot))
                    JS_FreeAtom(p->ctx, e->atom);
                e->start = start;
                e->len = n;
                e->hash = h;
                e->atom = frame_json_dup_atom(p->ctx, *atom);
                p->names_used |= 1u << slot;
            }
            return JS_UNDEFINED;
        }
        if (use_cache && n <= 27) {
            FrameJSONString *e = &p->strings[slot];
            if (p->strings_used & (1u << slot))
                JS_FreeValue(p->ctx, e->value);
            e->start = start;
            e->len = n;
            e->hash = h;
            e->value = js_dup(v);
            p->strings_used |= 1u << slot;
        }
        return v;
    }
    if (string_buffer_init(p->ctx, &b, 32)) {
        p->error = 2;
        return JS_EXCEPTION;
    }
    t->pos = start;
    while (t->pos < t->length) {
        c = frame_json_char(t, t->pos++);
        if (c == '"') {
            v = string_buffer_end(&b);
            if (JS_IsException(v)) {
                p->error = 2;
                return v;
            }
            if (key) {
                *atom = JS_ValueToAtom(p->ctx, v);
                JS_FreeValue(p->ctx, v);
                if (*atom == JS_ATOM_NULL) {
                    p->error = 2;
                    return JS_EXCEPTION;
                }
                return JS_UNDEFINED;
            }
            return v;
        }
        if (c < 0x20)
            goto invalid;
        if (c == '\\') {
            c = frame_json_char(t, t->pos++);
            switch (c) {
            case 'b':
                c = '\b';
                break;
            case 'f':
                c = '\f';
                break;
            case 'n':
                c = '\n';
                break;
            case 'r':
                c = '\r';
                break;
            case 't':
                c = '\t';
                break;
            case '"':
            case '\\':
            case '/':
                break;
            case 'u': {
                unsigned j;
                int x;
                c = 0;
                for (j = 0; j < 4; j++) {
                    x = frame_json_hex(frame_json_char(t, t->pos++));
                    if (x < 0)
                        goto invalid;
                    c = (c << 4) | (unsigned)x;
                }
                break;
            }
            default:
                goto invalid;
            }
        }
        if (string_buffer_putc(&b, c)) {
            p->error = 2;
            string_buffer_free(&b);
            return JS_EXCEPTION;
        }
    }
invalid:
    p->error = 1;
    string_buffer_free(&b);
    return JS_UNDEFINED;
}
static JSValue frame_json_number(FrameJSONParser *p)
{
    FrameJSONText *t = &p->text;
    size_t start = t->pos, first, end, n, i;
    unsigned neg = 0, c, integer = 1, acc = 0;
    double value;
    char local[128], *buf = local;
    if (frame_json_char(t, t->pos) == '-') {
        neg = 1;
        t->pos++;
    }
    first = t->pos;
    c = frame_json_char(t, t->pos);
    if (c < '0' || c > '9')
        goto invalid;
    do {
        if (t->pos - first < 9)
            acc = acc * 10 + (c - '0');
        t->pos++;
        c = frame_json_char(t, t->pos);
    } while (c >= '0' && c <= '9');
    if (frame_json_char(t, first) == '0' && t->pos - first > 1)
        goto invalid;
    end = t->pos;
    if (c == '.') {
        integer = 0;
        t->pos++;
        c = frame_json_char(t, t->pos);
        if (c < '0' || c > '9')
            goto invalid;
        do {
            t->pos++;
            c = frame_json_char(t, t->pos);
        } while (c >= '0' && c <= '9');
    }
    if (c == 'e' || c == 'E') {
        integer = 0;
        t->pos++;
        c = frame_json_char(t, t->pos);
        if (c == '+' || c == '-') {
            t->pos++;
            c = frame_json_char(t, t->pos);
        }
        if (c < '0' || c > '9')
            goto invalid;
        do {
            t->pos++;
            c = frame_json_char(t, t->pos);
        } while (c >= '0' && c <= '9');
    }
    if (integer && end - first <= 9 && !(p->mode & JSON_NO_NUMBER)) {
        value = (double)acc;
        if (neg)
            value = -value;
        return js_float64(value); /* Preserve the upstream FLOAT64 tag and -0. */
    }
    n = t->pos - start;
    if (n >= sizeof(local)) {
        buf = js_malloc(p->ctx, n + 1);
        if (!buf) {
            p->error = 2;
            return JS_EXCEPTION;
        }
    }
    for (i = 0; i < n; i++)
        buf[i] = (char)frame_json_char(t, start + i);
    buf[n] = 0;
    value = strtod(buf, NULL);
    if (buf != local)
        js_free(p->ctx, buf);
    return js_float64(value);
invalid:
    p->error = 1;
    return JS_UNDEFINED;
}
static int frame_json_property(FrameJSONParser *p, JSValueConst value, JSAtom atom, JSValue child)
{
    JSObject *o = JS_VALUE_GET_OBJ(value);
    JSShape *old = o->shape;
    JSShapeProperty *sp;
    JSProperty *prop;
    unsigned slot = (unsigned)(((uintptr_t)old >> 4) ^ atom) & 15;
    int cache = !(p->mode & JSON_NO_CACHE) && old->is_hashed;
    if (p->mode & JSON_NO_BUILD)
        return JS_DefinePropertyValue(p->ctx, value, atom, child, JS_PROP_C_W_E);
    if (cache && (p->transitions_used & (1u << slot))) {
        FrameJSONTransition *e = &p->transitions[slot];
        if (e->from == old && e->atom == atom) {
            if (e->to->prop_size != old->prop_size) {
                prop = js_realloc(p->ctx, o->prop, sizeof(JSProperty) * (size_t)e->to->prop_size);
                if (!prop) {
                    JS_FreeValue(p->ctx, child);
                    return -1;
                }
                o->prop = prop;
            }
            o->shape = js_dup_shape(e->to);
            js_free_shape(p->ctx->rt, old);
            o->prop[e->to->prop_count - 1].u.value = child;
            return 1;
        }
    }
    sp = find_own_property(&prop, o, atom);
    if (sp) {
        /* Parser-created objects have only ordinary CWEs, including __proto__. */
        JS_FreeValue(p->ctx, prop->u.value);
        prop->u.value = child;
        return 1;
    }
    if (cache)
        js_dup_shape(old); /* Hold the original identity across add/GC. */
    prop = add_property(p->ctx, o, atom, JS_PROP_C_W_E);
    if (!prop) {
        if (cache)
            js_free_shape(p->ctx->rt, old);
        JS_FreeValue(p->ctx, child);
        return -1;
    }
    prop->u.value = child;
    if (cache && o->shape->is_hashed && o->shape != old) {
        FrameJSONTransition *e = &p->transitions[slot];
        if (p->transitions_used & (1u << slot)) {
            js_free_shape(p->ctx->rt, e->from);
            js_free_shape(p->ctx->rt, e->to);
        }
        e->from = old;
        e->to = js_dup_shape(o->shape);
        e->atom = atom;
        p->transitions_used |= 1u << slot;
    } else if (cache)
        js_free_shape(p->ctx->rt, old);
    return 1;
}
