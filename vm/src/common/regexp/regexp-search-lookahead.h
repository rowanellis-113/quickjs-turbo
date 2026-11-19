/* Fixed-width subject necessary conditions; private regexp bytecode format. MIT. */
#define RE_SEARCH_LOOKAHEAD_WIDE 0x80
#define RE_SEARCH_LOOKAHEAD_WINDOW 0x40
#define RE_SEARCH_LOOKAHEAD_COUNT(pc) ((pc)[1] & 0x3f)
#define RE_SEARCH_LOOKAHEAD_POSITIONS 8
#define RE_SEARCH_LOOKAHEAD_MAP_BYTES 16
#define RE_SEARCH_LOOKAHEAD_HEADER 4
#define RE_SEARCH_LOOKAHEAD_BASE (RE_SEARCH_LOOKAHEAD_HEADER + RE_SEARCH_LOOKAHEAD_MAP_BYTES)

/* opcode, position count, interval start, interval end, interval union map,
 * then one 128-bit map per position. Low-seven-bit collisions are permitted:
 * they only admit extra candidates. Bit 7 of the count enables fixed-width
 * UTF-16 input as well as byte input; old byte-only payloads keep that bit
 * clear. Unicode wide input retains the generic matcher. This assertion does
 * not consume input. Import validates the full tables; runtime bounds checks
 * also run for compiler-produced bytecode. Bit 6 instead denotes a necessary
 * character within the inclusive from..to input window: count must be one,
 * and only the header and union map are stored. Old readers reject this
 * private encoding. JS wire input recompiles the original pattern.
 */
static unsigned re_search_lookahead_size(const uint8_t *pc, size_t available, bool full)
{
    unsigned count, from, to, length, i, j;
    if (available < RE_SEARCH_LOOKAHEAD_HEADER)
        return 0;
    count = RE_SEARCH_LOOKAHEAD_COUNT(pc);
    from = pc[2];
    to = pc[3];
    if (pc[1] & RE_SEARCH_LOOKAHEAD_WINDOW) {
        unsigned distinct = 0;
        if (count != 1 || from > to || !to || to >= RE_SEARCH_LOOKAHEAD_POSITIONS ||
            available < RE_SEARCH_LOOKAHEAD_BASE)
            return 0;
        if (full) {
            for (i = 0; i < RE_SEARCH_LOOKAHEAD_MAP_BYTES; i++) {
                unsigned bits = pc[RE_SEARCH_LOOKAHEAD_HEADER + i];
                while (bits) {
                    distinct++;
                    bits &= bits - 1;
                }
            }
            if (!distinct || distinct > 32)
                return 0;
        }
        return RE_SEARCH_LOOKAHEAD_BASE;
    }
    if (count < 2 || count > RE_SEARCH_LOOKAHEAD_POSITIONS || from >= to || to >= count)
        return 0;
    length = RE_SEARCH_LOOKAHEAD_BASE + count * RE_SEARCH_LOOKAHEAD_MAP_BYTES;
    if (length > available)
        return 0;
    if (full) {
        for (i = 0; i < RE_SEARCH_LOOKAHEAD_MAP_BYTES; i++) {
            uint8_t bits = 0;
            for (j = from; j <= to; j++)
                bits |= pc[RE_SEARCH_LOOKAHEAD_BASE + j * RE_SEARCH_LOOKAHEAD_MAP_BYTES + i];
            if (bits != pc[RE_SEARCH_LOOKAHEAD_HEADER + i])
                return 0;
        }
    }
    return length;
}

static bool re_search_map_contains(const uint8_t *map, unsigned c)
{
    c &= 127;
    return (map[c >> 3] & (1u << (c & 7))) != 0;
}

static void re_search_map_add(uint8_t *map, unsigned c)
{
    c &= 127;
    map[c >> 3] |= 1u << (c & 7);
}
