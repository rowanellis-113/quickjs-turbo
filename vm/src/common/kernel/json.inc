/* Bounded native JSON paths. MIT. Private types/helpers are generated from
 * the selected upstream source. Caches own references for one parse only. */
#include "qjs-json-simd.h"
#include <stdatomic.h>
#ifdef _MSC_VER
/* @QJS_MSC_INTRIN@ */
#define JSON_CODE __declspec(code_seg(".qjs$zzjson")) __declspec(noinline)
#define JSON_INLINE static __forceinline
#else
#define JSON_CODE __attribute__((section(".qjsjson"), noipa))
#define JSON_INLINE static inline __attribute__((always_inline))
#endif
enum {
    JSON_NO_NUMBER = 1,
    JSON_NO_BUILD = 2,
    JSON_NO_CACHE = 4,
    JSON_NO_STRINGIFY = 8,
    JSON_NO_DIRECT = 16,
    JSON_NO_SIMD = 32,
    JSON_NO_CALLBACK = 64
};
#ifdef _MSC_VER
/* The generator appends this byte to the retained register control section.
 * It never introduces an earlier CPP data contribution into that group. */
extern _Atomic unsigned char JS_FrameJSONControl;
/* Generated native leaf helpers implement an indivisible byte read and locked
 * CAS. Their owned late code/unwind entries avoid adding volatile metadata
 * before the inherited dispatch table or retaining unused CRT COMDAT copies. */
extern unsigned char JS_FrameJSONLoad8(const unsigned char *);
extern _Bool JS_FrameJSONCAS8(unsigned char *, unsigned char *, unsigned char);
#define FRAME_JSON_CONTROL (&JS_FrameJSONControl)
#else
_Atomic unsigned char JS_FrameJSONControl __attribute__((section(".qjscbmt$zzjson")));
JSON_INLINE _Atomic unsigned char *frame_json_control_slot(void)
{
    _Atomic unsigned char *p;
    QJS_CONTROL_SLOT_ADDR(p, JS_FrameJSONControl);
    return p;
}
#define FRAME_JSON_CONTROL (frame_json_control_slot())
#endif
#ifdef _MSC_VER
JSON_INLINE unsigned frame_json_mode(void)
{
    _Atomic unsigned char *control = FRAME_JSON_CONTROL;
    unsigned char state;
    const char *s;
    unsigned result = 0;
#ifdef _MSC_VER
    state = JS_FrameJSONLoad8((const unsigned char *)control);
#else
    state = atomic_load_explicit(control, memory_order_relaxed);
#endif
    if (state)
        return state - 1;
    s = getenv("QJS_JSON_MODE");
    if (s)
        while (*s >= '0' && *s <= '9' && result < 64)
            result = result * 10 + (unsigned)(*s++ - '0');
    result &= 63;
#ifdef _MSC_VER
    {
        unsigned char expected = 0;
        if (!JS_FrameJSONCAS8((unsigned char *)control, &expected, (unsigned char)(result + 1)))
            return expected - 1;
    }
#else
    {
        unsigned char expected = 0;
        if (!atomic_compare_exchange_strong_explicit(control, &expected,
                                                     (unsigned char)(result + 1),
                                                     memory_order_relaxed, memory_order_relaxed))
            return expected - 1;
    }
#endif
    return result;
}
#else
JSON_INLINE unsigned frame_json_mode(void)
{
    _Atomic unsigned char *control = FRAME_JSON_CONTROL;
    unsigned char state;
    const char *s;
    unsigned result = 0;
#ifdef _MSC_VER
    state = JS_FrameJSONLoad8((const unsigned char *)control);
#else
    state = atomic_load_explicit(control, memory_order_relaxed);
#endif
    if (state)
        return state - 1;
    s = getenv("QJS_JSON_MODE");
    if (s)
        while (*s >= '0' && *s <= '9' && result < 128)
            result = result * 10 + (unsigned)(*s++ - '0');
    result &= 127;
#ifdef _MSC_VER
    {
        unsigned char expected = 0;
        if (!JS_FrameJSONCAS8((unsigned char *)control, &expected, (unsigned char)(result + 1)))
            return expected - 1;
    }
#else
    {
        unsigned char expected = 0;
        if (!atomic_compare_exchange_strong_explicit(control, &expected,
                                                     (unsigned char)(result + 1),
                                                     memory_order_relaxed, memory_order_relaxed))
            return expected - 1;
    }
#endif
    return result;
}
#endif
extern JSValue JS_FrameJSONReviver(JSContext *, JSValueConst, int, JSValueConst *);
extern JSValue JS_FrameJSONCallbackStringify(JSContext *, JSValueConst, JSValueConst, JSValueConst);

typedef struct FrameJSONText {
    const uint8_t *p8;
    const uint16_t *p16;
    size_t length, pos;
    unsigned wide;
} FrameJSONText;
typedef struct FrameJSONName {
    size_t start;
    unsigned len, hash;
    JSAtom atom;
} FrameJSONName;
typedef struct FrameJSONString {
    size_t start;
    unsigned len, hash;
    JSValue value;
} FrameJSONString;
typedef struct FrameJSONTransition {
    JSShape *from, *to;
    JSAtom atom;
} FrameJSONTransition;
typedef struct FrameJSONParser {
    JSContext *ctx;
    FrameJSONText text;
    unsigned mode, depth, error, names_used, strings_used, transitions_used;
    FrameJSONName names[16];
    FrameJSONString strings[16];
    FrameJSONTransition transitions[16];
} FrameJSONParser;
/* error=1 means unsupported/invalid: release all partial values and use the
 * original parser for its diagnostics. error=2 preserves an allocation error. */
JSON_INLINE unsigned frame_json_char(FrameJSONText *t, size_t i)
{
    return i < t->length ? (t->wide ? t->p16[i] : t->p8[i]) : UINT_MAX;
}
JSON_INLINE void frame_json_space(FrameJSONText *t)
{
    unsigned c;
    while ((c = frame_json_char(t, t->pos)) == ' ' || c == '\t' || c == '\n' || c == '\r')
        t->pos++;
}
JSON_INLINE unsigned frame_json_first_lane(unsigned mask)
{
    /* Only called for a nonzero mask from a fully bounded SSE2 load. */
#ifdef _MSC_VER
    unsigned long lane;
    _BitScanForward(&lane, mask);
    return (unsigned)lane;
#else
    return (unsigned)__builtin_ctz(mask);
#endif
}
/* Internal eight-bit parser strings are Latin-1. Unsigned saturation
 * rejects controls without rejecting high bytes. Each vector load is bounded;
 * JS_ParseJSON keeps its existing UTF-8 guard before reaching this path. */
JSON_INLINE size_t frame_json_scan8(const uint8_t *p, size_t n, unsigned simd)
{
    size_t i = 0;
    if (simd) {
        qjs_vec128_t q = qjs_vec_set1_epi8('"'), b = qjs_vec_set1_epi8('\\'),
                     limit = qjs_vec_set1_epi8(0x1f), zero = qjs_vec_setzero_si128();
        while (n - i >= 16) {
            qjs_vec128_t v = qjs_vec_loadu_si128((const qjs_vec128_t *)(p + i));
            qjs_vec128_t bad = qjs_vec_or_si128(
                qjs_vec_or_si128(qjs_vec_cmpeq_epi8(v, q), qjs_vec_cmpeq_epi8(v, b)),
                qjs_vec_cmpeq_epi8(qjs_vec_subs_epu8(v, limit), zero));
            unsigned mask = (unsigned)qjs_vec_movemask_epi8(bad);
            if (mask)
                return i + frame_json_first_lane(mask);
            i += 16;
        }
    }
    while (i < n && p[i] >= 0x20 && p[i] != '"' && p[i] != '\\')
        i++;
    return i;
}
JSON_INLINE size_t frame_json_scan16(const uint16_t *p, size_t n, unsigned simd, unsigned quote)
{
    size_t i = 0;
    if (simd) {
        qjs_vec128_t q = qjs_vec_set1_epi16('"'), b = qjs_vec_set1_epi16('\\'),
                     low = qjs_vec_set1_epi16(0x20);
        while (n - i >= 8) {
            qjs_vec128_t v = qjs_vec_loadu_si128((const qjs_vec128_t *)(p + i));
            qjs_vec128_t bad = qjs_vec_or_si128(
                qjs_vec_or_si128(qjs_vec_cmpeq_epi16(v, q), qjs_vec_cmpeq_epi16(v, b)),
                qjs_vec_cmpeq_epi16(
                    qjs_vec_subs_epu16(v, qjs_vec_sub_epi16(low, qjs_vec_set1_epi16(1))),
                    qjs_vec_setzero_si128()));
            if (quote)
                bad = qjs_vec_or_si128(
                    bad, qjs_vec_cmpeq_epi16(qjs_vec_and_si128(v, qjs_vec_set1_epi16(0xf800)),
                                             qjs_vec_set1_epi16(0xd800)));
            unsigned mask = (unsigned)qjs_vec_movemask_epi8(bad);
            if (mask)
                return i + (frame_json_first_lane(mask) >> 1);
            i += 8;
        }
    }
    while (i < n && p[i] >= 0x20 && p[i] != '"' && p[i] != '\\' &&
           !(quote && p[i] >= 0xd800 && p[i] <= 0xdfff))
        i++;
    return i;
}
#include "src/common/json/json_values.inc"
JSON_INLINE int frame_json_parser_stack_overflow(FrameJSONParser *p)
{
    QJS_JSON_STACK_CHECK(p->ctx->rt->stack_limit, p->ctx->rt);
}
#include "src/common/json/json_parser.inc"
typedef struct FrameJSONWriter {
    JSContext *ctx;
    StringBuffer buffer;
    JSObject *ancestors[128];
    unsigned depth, mode, plans_used;
    /* A plan owns its shape, which owns the names and prototype chain. The
     * native attempt invokes no JS callbacks; all plans die before any legacy
     * callback/fallback, and no metadata survives this stringify. No eviction:
     * recursive children cannot overwrite their parent's active plan. */
    struct FrameJSONPlan {
        JSShape *shape;
        unsigned count;
        struct FrameJSONPlanKey {
            JSString *name;
            unsigned index, length;
            uint8_t text[30];
        } keys[8];
    } plans[4];
} FrameJSONWriter;
/* Internal eight-bit JSStrings are Latin-1. The only unsafe byte values
 * are JSON controls, quote and backslash; high bytes need no scalar rescan.
 * All SSE2 loads remain fully inside the supplied span. Public UTF-8 parsing
 * is unchanged, as are the parser TU and the well-formed UTF-16 path. */
JSON_INLINE size_t frame_json_scan_latin8(const uint8_t *p, size_t n, unsigned simd)
{
    size_t i = 0;
    if (simd) {
        qjs_vec128_t q = qjs_vec_set1_epi8('"'), b = qjs_vec_set1_epi8('\\'),
                     limit = qjs_vec_set1_epi8(0x1f), zero = qjs_vec_setzero_si128();
        while (n - i >= 16) {
            qjs_vec128_t v = qjs_vec_loadu_si128((const qjs_vec128_t *)(p + i));
            qjs_vec128_t bad = qjs_vec_or_si128(
                qjs_vec_or_si128(qjs_vec_cmpeq_epi8(v, q), qjs_vec_cmpeq_epi8(v, b)),
                qjs_vec_cmpeq_epi8(qjs_vec_subs_epu8(v, limit), zero));
            unsigned mask = (unsigned)qjs_vec_movemask_epi8(bad);
            if (mask)
                return i + frame_json_first_lane(mask);
            i += 16;
        }
    }
    while (i < n && p[i] >= 0x20 && p[i] != '"' && p[i] != '\\')
        i++;
    return i;
}
/* Copy and validate a safe prefix directly into an already-wide output.
 * Reserve the unescaped remainder plus closing quote once. Vector stores may
 * touch uncommitted characters, but stay inside that capacity; only the safe
 * prefix advances len. The existing escaper overwrites the rest. No source
 * or output pointer survives allocation, and no user callback is invoked.
 * Narrow output keeps the existing width-selection/storage policy. */
/* Compiler ablation of the specialized quote workers. Legacy retains the
 * f95p predicates and dispatch; the GCC path specializes immutable input
 * width/mode. The quote implementation retains the f95q compiler selection;
 * shape-plan changes must independently preserve inherited core/parser RX. One shared
 * escaping body keeps this selection maintainable across source upgrades. */
JSON_INLINE size_t frame_json_copy_wide(FrameJSONWriter *w, JSString *s, size_t start,
                                        unsigned wide)
{
    StringBuffer *b = &w->buffer;
    size_t i = 0, n = s->len - start, needed = (size_t)b->len + n + 1;
    uint16_t *out;
    qjs_vec128_t zero = qjs_vec_setzero_si128(), bad;
    if (needed > (size_t)b->size && string_buffer_realloc(b, (int)needed, 0))
        return SIZE_MAX;
    out = str16(b->str) + b->len;
#ifdef _MSC_VER
    if (s->is_wide_char) {
#else
    if (wide) {
#endif
        const uint16_t *p = str16(s) + start;
        qjs_vec128_t quote = qjs_vec_set1_epi16('"'), slash = qjs_vec_set1_epi16('\\'),
                     limit = qjs_vec_set1_epi16(0x1f);
        while (n - i >= 8) {
            qjs_vec128_t v = qjs_vec_loadu_si128((const qjs_vec128_t *)(p + i));
            unsigned mask;
            qjs_vec_storeu_si128((qjs_vec128_t *)(out + i), v);
            bad = qjs_vec_or_si128(
                qjs_vec_or_si128(qjs_vec_cmpeq_epi16(v, quote), qjs_vec_cmpeq_epi16(v, slash)),
                qjs_vec_cmpeq_epi16(qjs_vec_subs_epu16(v, limit), zero));
            bad = qjs_vec_or_si128(
                bad, qjs_vec_cmpeq_epi16(qjs_vec_and_si128(v, qjs_vec_set1_epi16(0xf800)),
                                         qjs_vec_set1_epi16(0xd800)));
            mask = (unsigned)qjs_vec_movemask_epi8(bad);
            if (mask) {
                i += frame_json_first_lane(mask) >> 1;
                goto done;
            }
            i += 8;
        }
        while (i < n) {
            unsigned c = p[i];
            if (c < 0x20 || c == '"' || c == '\\' || (c >= 0xd800 && c <= 0xdfff))
                break;
            out[i++] = (uint16_t)c;
        }
    } else {
        const uint8_t *p = str8(s) + start;
        qjs_vec128_t quote = qjs_vec_set1_epi8('"'), slash = qjs_vec_set1_epi8('\\'),
                     limit = qjs_vec_set1_epi8(0x1f);
        while (n - i >= 16) {
            qjs_vec128_t v = qjs_vec_loadu_si128((const qjs_vec128_t *)(p + i));
            unsigned mask;
            qjs_vec_storeu_si128((qjs_vec128_t *)(out + i), qjs_vec_unpacklo_epi8(v, zero));
            qjs_vec_storeu_si128((qjs_vec128_t *)(out + i + 8), qjs_vec_unpackhi_epi8(v, zero));
            bad = qjs_vec_or_si128(
                qjs_vec_or_si128(qjs_vec_cmpeq_epi8(v, quote), qjs_vec_cmpeq_epi8(v, slash)),
                qjs_vec_cmpeq_epi8(qjs_vec_subs_epu8(v, limit), zero));
            mask = (unsigned)qjs_vec_movemask_epi8(bad);
            if (mask) {
                i += frame_json_first_lane(mask);
                goto done;
            }
            i += 16;
        }
        while (i < n) {
            unsigned c = p[i];
            if (c < 0x20 || c == '"' || c == '\\')
                break;
            out[i++] = (uint16_t)c;
        }
    }
done:
    b->len += (int)i;
    return i;
}
/* 0=success, 1=guarded fallback, -1=allocation failure. This walker never
 * invokes a getter, Proxy trap, toJSON or replacer before a fallback. */
#ifdef _MSC_VER
static int frame_json_quote(FrameJSONWriter *w, JSString *s)
#define JSON_QUOTE_WIDE (s->is_wide_char)
#define JSON_QUOTE_SIMD (!(w->mode & JSON_NO_SIMD))
#define JSON_QUOTE_LENGTH (s->len)
#define JSON_QUOTE_COPY frame_json_copy_wide(w, s, i, 0)
#else
JSON_INLINE int frame_json_quote_chars(FrameJSONWriter *w, JSString *s, unsigned wide,
                                       unsigned simd)
#define JSON_QUOTE_WIDE wide
#define JSON_QUOTE_SIMD simd
#define JSON_QUOTE_LENGTH length
#define JSON_QUOTE_COPY frame_json_copy_wide(w, s, i, wide)
#endif
{
#ifdef _MSC_VER
    size_t i = 0, start;
#else
    size_t i = 0, start, length = s->len;
#endif
    unsigned c, next;
    char escape[6];
    static const char hex[] = "0123456789abcdef";
    if (string_buffer_putc8(&w->buffer, '"'))
        return -1;
    while (i < JSON_QUOTE_LENGTH) {
        start = i;
        if (w->buffer.is_wide_char && JSON_QUOTE_SIMD && JSON_QUOTE_LENGTH - i >= 16) {
            size_t copied = JSON_QUOTE_COPY;
            if (copied == SIZE_MAX)
                return -1;
            i += copied;
        } else {
            if (!JSON_QUOTE_WIDE) {
                i += frame_json_scan_latin8(str8(s) + i, JSON_QUOTE_LENGTH - i, JSON_QUOTE_SIMD);
            } else
                i += frame_json_scan16(str16(s) + i, JSON_QUOTE_LENGTH - i, JSON_QUOTE_SIMD, 1);
            if (i > start) {
                int r = JSON_QUOTE_WIDE
                            ? string_buffer_write16(&w->buffer, str16(s) + start, (int)(i - start))
                            : string_buffer_write8(&w->buffer, str8(s) + start, (int)(i - start));
                if (r)
                    return -1;
            }
        }
        if (i == JSON_QUOTE_LENGTH)
            break;
        c = JSON_QUOTE_WIDE ? str16(s)[i++] : str8(s)[i++];
        escape[0] = '\\';
        if (c == '"' || c == '\\')
            escape[1] = (char)c;
        else if (c == '\b')
            escape[1] = 'b';
        else if (c == '\f')
            escape[1] = 'f';
        else if (c == '\n')
            escape[1] = 'n';
        else if (c == '\r')
            escape[1] = 'r';
        else if (c == '\t')
            escape[1] = 't';
        else {
            if (c >= 0xd800 && c <= 0xdbff && i < JSON_QUOTE_LENGTH &&
                (next = str16(s)[i]) >= 0xdc00 && next <= 0xdfff) {
                if (string_buffer_putc16(&w->buffer, c) || string_buffer_putc16(&w->buffer, next))
                    return -1;
                i++;
                continue;
            }
            escape[1] = 'u';
            escape[2] = hex[(c >> 12) & 15];
            escape[3] = hex[(c >> 8) & 15];
            escape[4] = hex[(c >> 4) & 15];
            escape[5] = hex[c & 15];
            if (string_buffer_write8(&w->buffer, (const uint8_t *)escape, 6))
                return -1;
            continue;
        }
        if (string_buffer_write8(&w->buffer, (const uint8_t *)escape, 2))
            return -1;
    }
    return string_buffer_putc8(&w->buffer, '"') ? -1 : 0;
}
#undef JSON_QUOTE_WIDE
#undef JSON_QUOTE_SIMD
#undef JSON_QUOTE_LENGTH
#undef JSON_QUOTE_COPY
#ifndef _MSC_VER
/* The input width and mode cannot change during quoting. Select them once,
 * before the character loop.
 * Two native workers constant-fold the scans, prefix copy and code-unit load.
 * The scalar control has no fused-copy/output-width guard in its loop.
 * Keep workers out of line to avoid cloning their SIMD register saves into
 * the width/mode dispatcher. The shared source retains one escaping body. */
JSON_CODE static int frame_json_quote_latin8(FrameJSONWriter *w, JSString *s)
{
    return frame_json_quote_chars(w, s, 0, 1);
}
JSON_CODE static int frame_json_quote_utf16(FrameJSONWriter *w, JSString *s)
{
    return frame_json_quote_chars(w, s, 1, 1);
}
JSON_CODE static int frame_json_quote_scalar(FrameJSONWriter *w, JSString *s)
{
    return frame_json_quote_chars(w, s, s->is_wide_char, 0);
}
static int frame_json_quote(FrameJSONWriter *w, JSString *s)
{
    if (w->mode & JSON_NO_SIMD)
        return frame_json_quote_scalar(w, s);
    if (s->is_wide_char)
        return frame_json_quote_utf16(w, s);
    return frame_json_quote_latin8(w, s);
}
#endif
JSON_INLINE int frame_json_key(FrameJSONWriter *w, JSString *s)
{
    /* Short Latin-1 keys avoid the general SIMD quote frame and reserve/write
     * the two quotes and colon together. Validate before touching the buffer;
     * escaped or wide names keep the general well-formed quoting path. */
    if (!s->is_wide_char && s->len <= 27) {
        const uint8_t *data = str8(s);
        uint8_t text[30];
        unsigned i, n = s->len;
        text[0] = '"';
        for (i = 0; i < n; i++) {
            unsigned c = data[i];
            if (c < 0x20 || c == '"' || c == '\\')
                goto general;
            text[i + 1] = (uint8_t)c;
        }
        text[n + 1] = '"';
        text[n + 2] = ':';
        return string_buffer_write8(&w->buffer, text, (int)n + 3) ? -1 : 0;
    }
general:
    if (frame_json_quote(w, s))
        return -1;
    return string_buffer_putc8(&w->buffer, ':') ? -1 : 0;
}
JSON_INLINE int frame_json_no_tojson(JSObject *o)
{
    JSProperty *prop;
    unsigned depth = 0;
    for (; o; o = o->shape->proto) {
        if (++depth > 128 || (o->class_id != JS_CLASS_OBJECT && o->class_id != JS_CLASS_ARRAY) ||
            (o->is_exotic && o->class_id != JS_CLASS_ARRAY))
            return 0;
        if (find_own_property(&prop, o, JS_ATOM_toJSON))
            return 0;
    }
    return 1;
}
/* Plans pin shapes for copy-on-write and root borrowed key names through GC.
 * No native attempt invokes user code; all slots die before legacy callbacks.
 * Legacy keeps the measured eager implementation. Native prepares keys on a second
 * guarded observation, outside the hot walk. UINT_MAX marks an observed slot;
 * it owns its shape but has no readable keys until promotion completes. */
#ifdef _MSC_VER
static struct FrameJSONPlan *frame_json_plan(FrameJSONWriter *w, JSObject *o)
{
    struct FrameJSONPlan *plan = &w->plans[w->plans_used];
#else
JSON_CODE static void frame_json_plan(FrameJSONWriter *w, JSObject *o, struct FrameJSONPlan *plan)
{
#endif
    JSShapeProperty *properties = get_shape_prop(o->shape);
    unsigned i, j, n;
    plan->count = 0;
    for (i = 0; i < (unsigned)o->shape->prop_count; i++) {
        JSShapeProperty *p = &properties[i];
        struct FrameJSONPlanKey *key;
        JSString *name;
        const uint8_t *data;
        if (p->atom == JS_ATOM_NULL || !(p->flags & JS_PROP_ENUMERABLE) ||
            JS_AtomGetKind(w->ctx, p->atom) != JS_ATOM_KIND_STRING)
            continue;
        key = &plan->keys[plan->count++];
        name = w->ctx->rt->atom_array[p->atom];
        key->name = name;
        key->index = i;
        key->length = 0;
        if (name->is_wide_char || name->len > 27)
            continue;
        n = name->len;
        data = str8(name);
        key->text[0] = '"';
        for (j = 0; j < n; j++) {
            unsigned c = data[j];
            if (c < 0x20 || c == '"' || c == '\\')
                break;
            key->text[j + 1] = (uint8_t)c;
        }
        if (j != n)
            continue;
        key->text[n + 1] = '"';
        key->text[n + 2] = ':';
        key->length = n + 3;
    }
#ifdef _MSC_VER
    plan->shape = js_dup_shape(o->shape);
    w->plans_used++;
    return plan;
#endif
}
JSON_INLINE void frame_json_plans_free(FrameJSONWriter *w)
{
    unsigned i;
    for (i = 0; i < w->plans_used; i++)
        js_free_shape(w->ctx->rt, w->plans[i].shape);
}
JSON_INLINE int frame_json_omitted(JSValueConst v)
{
    int tag = JS_VALUE_GET_TAG(v);
    return tag == JS_TAG_UNDEFINED || tag == JS_TAG_SYMBOL;
}
JSON_INLINE int frame_json_writer_stack_overflow(FrameJSONWriter *w)
{
    QJS_JSON_STACK_CHECK(w->ctx->rt->stack_limit, w->ctx->rt);
}
static int frame_json_write(FrameJSONWriter *w, JSValueConst v)
{
    JSObject *o;
    JSShapeProperty *properties;
    struct FrameJSONPlan *plan = NULL;
    JSValue str;
    unsigned i, used;
    int r, tag = JS_VALUE_GET_NORM_TAG(v);
    char buf[24], *end = buf + sizeof(buf), *at = end;
    uint32_t mag, index;
    int32_t integer;
    double number;
    switch (tag) {
    case JS_TAG_STRING:
        return frame_json_quote(w, JS_VALUE_GET_STRING(v));
    case JS_TAG_INT:
        integer = JS_VALUE_GET_INT(v);
    write_integer:
        mag = integer < 0 ? 0u - (uint32_t)integer : (uint32_t)integer;
        do {
            *--at = (char)('0' + mag % 10);
            mag /= 10;
        } while (mag);
        if (integer < 0)
            *--at = '-';
        return string_buffer_write8(&w->buffer, (const uint8_t *)at, (int)(end - at)) ? -1 : 0;
    case JS_TAG_BOOL:
        return string_buffer_puts8(&w->buffer, JS_VALUE_GET_BOOL(v) ? "true" : "false") ? -1 : 0;
    case JS_TAG_NULL:
        return string_buffer_puts8(&w->buffer, "null") ? -1 : 0;
    case JS_TAG_FLOAT64:
        number = JS_VALUE_GET_FLOAT64(v);
        if (!isfinite(number))
            return string_buffer_puts8(&w->buffer, "null") ? -1 : 0;
        if (!(w->mode & JSON_NO_NUMBER) && number >= INT32_MIN && number <= INT32_MAX) {
            integer = (int32_t)number;
            if (number == (double)integer)
                goto write_integer;
        }
        str = JS_ToString(w->ctx, v);
        if (JS_IsException(str))
            return -1;
        r = string_buffer_concat_value(&w->buffer, str);
        JS_FreeValue(w->ctx, str);
        return r ? -1 : 0;
    case JS_TAG_OBJECT:
        break;
    default:
        return 1;
    }
    o = JS_VALUE_GET_OBJ(v);
    if (o->class_id != JS_CLASS_OBJECT && o->class_id != JS_CLASS_ARRAY)
        return 1;
    if (!(w->mode & JSON_NO_CACHE) && o->class_id == JS_CLASS_OBJECT && !o->is_exotic) {
        for (i = 0; i < w->plans_used; i++)
            if (w->plans[i].shape == o->shape) {
                plan = &w->plans[i];
                break;
            }
    }
    if ((!plan && !frame_json_no_tojson(o)) || w->depth >= 128 ||
        frame_json_writer_stack_overflow(w))
        return 1;
    for (i = 0; i < w->depth; i++)
        if (w->ancestors[i] == o)
            return 1;
    w->ancestors[w->depth++] = o;
    if (o->class_id == JS_CLASS_ARRAY) {
        if (!o->fast_array || JS_VALUE_GET_TAG(o->prop[0].u.value) != JS_TAG_INT ||
            JS_VALUE_GET_INT(o->prop[0].u.value) < 0 ||
            (uint32_t)JS_VALUE_GET_INT(o->prop[0].u.value) != o->u.array.count) {
            r = 1;
            goto done;
        }
        if (string_buffer_putc8(&w->buffer, '[')) {
            r = -1;
            goto done;
        }
        for (i = 0; i < o->u.array.count; i++) {
            if (i && string_buffer_putc8(&w->buffer, ',')) {
                r = -1;
                goto done;
            }
            r = frame_json_omitted(o->u.array.u.values[i])
                    ? (string_buffer_puts8(&w->buffer, "null") ? -1 : 0)
                    : frame_json_write(w, o->u.array.u.values[i]);
            if (r)
                goto done;
        }
        r = string_buffer_putc8(&w->buffer, ']') ? -1 : 0;
        goto done;
    }
    properties = get_shape_prop(o->shape);
    /* Integer keys need the engine's sorting rules. Keep that generic path. */
#ifdef _MSC_VER
    if (!plan) {
#else
    if (plan) {
        if (plan->count == UINT_MAX)
            frame_json_plan(w, o, plan);
    } else {
#endif
        for (i = 0; i < (unsigned)o->shape->prop_count; i++) {
            JSShapeProperty *p = &properties[i];
            if (p->atom == JS_ATOM_NULL || !(p->flags & JS_PROP_ENUMERABLE))
                continue;
            if (JS_AtomIsArrayIndex(w->ctx, &index, p->atom) || (p->flags & JS_PROP_TMASK)) {
                r = 1;
                goto done;
            }
        }
#ifdef _MSC_VER
        if (!(w->mode & JSON_NO_CACHE) && w->plans_used < 4 && o->shape->prop_count <= 8)
            plan = frame_json_plan(w, o);
#else
        if (!(w->mode & JSON_NO_CACHE) && w->plans_used < 4 && o->shape->prop_count <= 8) {
            struct FrameJSONPlan *observed = &w->plans[w->plans_used++];
            observed->shape = js_dup_shape(o->shape);
            observed->count = UINT_MAX;
        }
#endif
    }
    if (string_buffer_putc8(&w->buffer, '{')) {
        r = -1;
        goto done;
    }
    used = 0;
    if (plan) {
        for (i = 0; i < plan->count; i++) {
            struct FrameJSONPlanKey *key = &plan->keys[i];
            JSValueConst value = o->prop[key->index].u.value;
            if (frame_json_omitted(value))
                continue;
            if (used++ && string_buffer_putc8(&w->buffer, ',')) {
                r = -1;
                goto done;
            }
            r = key->length ? string_buffer_write8(&w->buffer, key->text, (int)key->length)
                            : frame_json_key(w, key->name);
            if (r) {
                r = -1;
                goto done;
            }
            r = frame_json_write(w, value);
            if (r)
                goto done;
        }
        r = string_buffer_putc8(&w->buffer, '}') ? -1 : 0;
        goto done;
    }
    for (i = 0; i < (unsigned)o->shape->prop_count; i++) {
        JSShapeProperty *p = &properties[i];
        if (p->atom == JS_ATOM_NULL || !(p->flags & JS_PROP_ENUMERABLE) ||
            JS_AtomGetKind(w->ctx, p->atom) != JS_ATOM_KIND_STRING ||
            frame_json_omitted(o->prop[i].u.value))
            continue;
        if (used++ && string_buffer_putc8(&w->buffer, ',')) {
            r = -1;
            goto done;
        }
        /* Array-index atoms were rejected above and the atom kind is STRING.
         * The live object's shape owns this atom throughout quoting. Buffer
         * allocation can collect cycles, but this path invokes no user code
         * and neither mutates the object nor releases its shape/atom. */
        r = frame_json_key(w, w->ctx->rt->atom_array[p->atom]);
        if (r) {
            r = -1;
            goto done;
        }
        r = frame_json_write(w, o->prop[i].u.value);
        if (r)
            goto done;
    }
    r = string_buffer_putc8(&w->buffer, '}') ? -1 : 0;
done:
    w->depth--;
    return r;
}
extern JSValue JS_LegacyJSONStringify(JSContext *, JSValueConst, JSValueConst, JSValueConst);
#ifdef _MSC_VER
JSON_CODE JSValue JS_JSONStringify(JSContext *ctx, JSValueConst obj, JSValueConst replacer,
                                   JSValueConst space)
{
    FrameJSONWriter w;
    unsigned mode = frame_json_mode();
    int r;
    if ((mode & JSON_NO_STRINGIFY) || !JS_IsUndefined(replacer) || !JS_IsUndefined(space))
        goto original;
    if (frame_json_omitted(obj))
        return JS_UNDEFINED;
    if (JS_IsObject(obj) && !frame_json_no_tojson(JS_VALUE_GET_OBJ(obj)))
        goto original;
    w.ctx = ctx;
    w.depth = 0;
    w.mode = mode;
    w.plans_used = 0;
    if (string_buffer_init(ctx, &w.buffer, 256))
        return JS_EXCEPTION;
    r = frame_json_write(&w, obj);
    frame_json_plans_free(&w);
    if (!r)
        return string_buffer_end(&w.buffer);
    string_buffer_free(&w.buffer);
    if (r < 0)
        return JS_EXCEPTION;
original:
    return JS_LegacyJSONStringify(ctx, obj, replacer, space);
}
#else
JSON_CODE JSValue JS_JSONStringify(JSContext *ctx, JSValueConst obj, JSValueConst replacer,
                                   JSValueConst space)
{
    FrameJSONWriter w;
    unsigned mode = frame_json_mode();
    int r;
    if ((mode & JSON_NO_STRINGIFY) || !JS_IsUndefined(replacer) || !JS_IsUndefined(space))
        goto original;
    if (frame_json_omitted(obj))
        return JS_UNDEFINED;
    if (JS_IsObject(obj) && !frame_json_no_tojson(JS_VALUE_GET_OBJ(obj)))
        goto original;
    w.ctx = ctx;
    w.depth = 0;
    w.mode = mode;
    w.plans_used = 0;
    if (string_buffer_init(ctx, &w.buffer, 256))
        return JS_EXCEPTION;
    r = frame_json_write(&w, obj);
    frame_json_plans_free(&w);
    if (!r)
        return string_buffer_end(&w.buffer);
    string_buffer_free(&w.buffer);
    if (r < 0)
        return JS_EXCEPTION;
original:
    if (!(mode & (JSON_NO_STRINGIFY | JSON_NO_CALLBACK)))
        return JS_FrameJSONCallbackStringify(ctx, obj, replacer, space);
    return JS_LegacyJSONStringify(ctx, obj, replacer, space);
}
#endif
#ifdef _MSC_VER
JSON_CODE JSValue JS_FrameJSONStringify(JSContext *ctx, JSValueConst this_val, int argc,
                                        JSValueConst *argv)
{
    /* Retain the exact old native entry as the real unsupported/control path.
     * Its original function-table reference is replaced by this wrapper. */
    if ((frame_json_mode() & JSON_NO_STRINGIFY) || !JS_IsUndefined(argv[1]) ||
        !JS_IsUndefined(argv[2]))
        return js_json_stringify(ctx, this_val, argc, argv);
    return JS_JSONStringify(ctx, argv[0], argv[1], argv[2]);
}
#else
JSON_CODE JSValue JS_FrameJSONStringify(JSContext *ctx, JSValueConst this_val, int argc,
                                        JSValueConst *argv)
{
    /* Retain the exact old native entry as the real unsupported/control path.
     * Its original function-table reference is replaced by this wrapper. */
    if (frame_json_mode() & JSON_NO_STRINGIFY)
        return js_json_stringify(ctx, this_val, argc, argv);
    return JS_JSONStringify(ctx, argv[0], argv[1], argv[2]);
}
#endif
