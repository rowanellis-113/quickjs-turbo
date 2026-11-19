/* MIT. Proven nonempty literal matching without a backtracking context.
 * The original body stays present; the five-byte hint exports as goto(0).
 */
#define RE_LITERAL_LIMIT 64
#define RE_LITERAL_HINT_SIZE 5
#define RE_LITERAL_VERSION 1

typedef union RELiteralBuffer {
    uint8_t bytes[RE_LITERAL_LIMIT];
    uint16_t units[RE_LITERAL_LIMIT];
} RELiteralBuffer;

static int re_literal_prefix_len(const uint8_t *code, size_t size)
{
    return size >= 11 &&
                   (code[0] == REOP_split_goto_first || code[0] == REOP_split_guard_goto_first) &&
                   get_u32(code + 1) == 6 && code[5] == REOP_any && code[6] == REOP_goto &&
                   get_u32(code + 7) == (uint32_t)-11
               ? 11
               : 0;
}

static bool re_literal_body(const uint8_t *p, size_t size, int flags, unsigned captures,
                            unsigned registers, unsigned *count, unsigned *wide,
                            RELiteralBuffer *literal, int shift)
{
    unsigned n, has_wide = 0;
    if (captures != 1 || registers || (flags & (LRE_FLAG_IGNORECASE | LRE_FLAG_STICKY)) ||
        size < 8 || size > 5 + RE_LITERAL_LIMIT * 3 || (size - 5) % 3)
        return false;
    n = (unsigned)((size - 5) / 3);
    if (!n || n > RE_LITERAL_LIMIT || p[0] != REOP_save_start || p[1] ||
        p[size - 3] != REOP_save_end || p[size - 2] || p[size - 1] != REOP_match)
        return false;
    for (unsigned i = 0; i < n; i++) {
        const uint8_t *op = p + 2 + i * 3;
        unsigned c;
        if (op[0] != REOP_char)
            return false;
        c = get_u16(op + 1);
        /* Unicode-wide code-unit search is sound for nonsurrogate BMP atoms.
         * Astral opcodes and lone-surrogate Unicode patterns keep the VM.
         */
        if ((flags & (LRE_FLAG_UNICODE | LRE_FLAG_UNICODE_SETS)) && c >= 0xd800 && c <= 0xdfff)
            return false;
        has_wide |= c > 255;
        if (literal) {
            if (shift)
                literal->units[i] = (uint16_t)c;
            else
                literal->bytes[i] = (uint8_t)c;
        }
    }
    *count = n;
    *wide = has_wide;
    return true;
}

static int re_insert_literal_hint(REParseState *s, unsigned registers)
{
    size_t size = s->byte_code.size - RE_HEADER_LEN;
    const uint8_t *body = s->byte_code.buf + RE_HEADER_LEN;
    unsigned count, wide;
    uint8_t *hint;
    if (re_literal_prefix_len(body, size) != 11 ||
        !re_literal_body(body + 11, size - 11, s->re_flags, s->capture_count, registers, &count,
                         &wide, NULL, 0))
        return 0;
    const char *disabled = getenv("QJS_DISABLE_REGEXP_LITERAL");
    if (disabled && strcmp(disabled, "0"))
        return 0;
    if (dbuf_insert(&s->byte_code, RE_HEADER_LEN + 11, RE_LITERAL_HINT_SIZE))
        return -1;
    hint = s->byte_code.buf + RE_HEADER_LEN + 11;
    hint[0] = REOP_literal_hint;
    put_u16(hint + 1, (uint16_t)count);
    hint[3] = (uint8_t)wide;
    hint[4] = RE_LITERAL_VERSION;
    return 1;
}

static unsigned re_validate_literal_hint(const uint8_t *bc, size_t size, RELiteralBuffer *literal,
                                         int shift)
{
    const uint8_t *body = bc + RE_HEADER_LEN, *hint = body + 11;
    unsigned count, wide;
    if (size < 11 + RE_LITERAL_HINT_SIZE + 8 || re_literal_prefix_len(body, size) != 11 ||
        hint[0] != REOP_literal_hint || hint[4] != RE_LITERAL_VERSION ||
        !re_literal_body(hint + RE_LITERAL_HINT_SIZE, size - 11 - RE_LITERAL_HINT_SIZE,
                         lre_get_flags(bc), bc[RE_HEADER_CAPTURE_COUNT],
                         bc[RE_HEADER_REGISTER_COUNT], &count, &wide, literal, shift) ||
        get_u16(hint + 1) != count || hint[3] != wide)
        return 0;
    return count;
}

static inline int re_literal_poll(void *opaque, int *budget, int steps)
{
    *budget -= steps;
    if (unlikely(*budget <= 0)) {
        *budget = INTERRUPT_COUNTER_INIT;
        if (lre_check_timeout(opaque))
            return LRE_RET_TIMEOUT;
    }
    return 0;
}

/* Keep the bounded local buffer out of the ordinary nonliteral entry frame.
 * Decode before any timeout callback, retaining no bytecode pointer afterward.
 */
static no_inline int re_exec_literal_hint(uint8_t **capture, const uint8_t *bc,
                                          const uint8_t *input, int start, int length, int shift,
                                          void *opaque)
{
    size_t body_size = get_u32(bc + RE_HEADER_BYTECODE_LEN);
    RELiteralBuffer literal;
    const uint16_t *units = shift == 1 ? (const uint16_t *)input : NULL;
    const void *needle;
    unsigned count, first;
    int flags, wide, last, budget = INTERRUPT_COUNTER_INIT;
    flags = lre_get_flags(bc);
    count = re_validate_literal_hint(bc, body_size, &literal, shift);
    if (!count)
        return LRE_RET_BYTECODE_ERROR;
    wide = bc[RE_HEADER_LEN + 11 + 3];
    capture[0] = capture[1] = NULL;
    if (start < 0 || start > length || count > (unsigned)(length - start) || (!shift && wide))
        return 0;
    if (shift && (flags & (LRE_FLAG_UNICODE | LRE_FLAG_UNICODE_SETS)) && start > 0 &&
        start < length && is_lo_surrogate(units[start]) && is_hi_surrogate(units[start - 1]))
        start--;
    first = shift ? literal.units[0] : literal.bytes[0];
    needle = shift ? (const void *)literal.units : (const void *)literal.bytes;
    last = length - (int)count;
    while (start <= last) {
        int chunk = last - start + 1, found = start;
        if (chunk > 4096)
            chunk = 4096;
        if (!shift) {
            const uint8_t *p = memchr(input + start, first, chunk);
            found = p ? (int)(p - input) : start + chunk;
        } else {
            while (found < start + chunk && units[found] != first)
                found++;
        }
        if (re_literal_poll(opaque, &budget, found - start))
            return LRE_RET_TIMEOUT;
        if (found == start + chunk) {
            start = found;
            continue;
        }
        if (count == 1 ||
            !memcmp(input + ((size_t)found << shift), needle, (size_t)count << shift)) {
            capture[0] = (uint8_t *)input + ((size_t)found << shift);
            capture[1] = (uint8_t *)input + ((size_t)(found + count) << shift);
            return 1;
        }
        start = found + 1;
        if (re_literal_poll(opaque, &budget, count))
            return LRE_RET_TIMEOUT;
    }
    return 0;
}
