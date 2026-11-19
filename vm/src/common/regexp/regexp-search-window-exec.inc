/* Fused necessary-character search. MIT.
 * A hit at q excludes all candidate starts before q-to. Low-seven-bit map
 * collisions only produce extra VM attempts. The original VM decides the
 * match, captures and branch ordering. A short input need not contain the
 * entire maximum window: a character at its minimum offset is sufficient.
 */
static no_inline int re_scan_search_window(REExecContext *s, const uint8_t *meta,
                                           const uint8_t **position, bool searching)
{
    const uint8_t *start = *position, *p;
    unsigned from = meta[2], to = meta[3], shift = s->cbuf_type;
    size_t remaining = (size_t)(s->cbuf_end - start) >> shift;
    if (remaining <= from)
        return 0;
    p = start + (from << shift);
    for (;;) {
        unsigned c = shift ? get_u16(p) : *p;
        size_t offset = (size_t)(p - start) >> shift;
        if (re_search_map_contains(meta + RE_SEARCH_LOOKAHEAD_HEADER, c)) {
            *position = offset > to ? p - (to << shift) : start;
            return 1;
        }
        if ((!searching && offset == to) || ((size_t)(s->cbuf_end - p) >> shift) <= 1)
            return 0;
        p += 1u << shift;
        if (lre_poll_timeout(s))
            return LRE_RET_TIMEOUT;
    }
}
