/* Compiler proof for fixed-width position sets. MIT.
 * Every admitted path must consume the proved number of forward characters.
 * Alternatives are unioned; unsupported operations shorten the proof, and
 * exhausted bounds decline it. No captures, counters or ordering are changed.
 */
static int re_insert_search_lookahead(REParseState *s)
{
    struct {
        int pc;
        unsigned depth;
    } pending[128];
    uint8_t maps[RE_SEARCH_LOOKAHEAD_POSITIONS][RE_SEARCH_LOOKAHEAD_MAP_BYTES] = {{0}};
    uint8_t encoded[RE_SEARCH_LOOKAHEAD_BASE +
                    RE_SEARCH_LOOKAHEAD_POSITIONS * RE_SEARCH_LOOKAHEAD_MAP_BYTES] = {0};
    const uint8_t *code = s->byte_code.buf + RE_HEADER_LEN;
    int code_len = s->byte_code.size - RE_HEADER_LEN;
    unsigned count = 1, limit = RE_SEARCH_LOOKAHEAD_POSITIONS, best = 0, from = 0, to = 0;
    int prefix = re_search_prefix_len(code, code_len), budget = 512;
    uint32_t max_char = s->is_unicode ? 0x10ffff : 0xffff;
    size_t first_skip = 0;
    unsigned length, i, j;

    if (!prefix)
        return 0;
    re_start_filter(code + prefix, code_len - prefix, &first_skip);
    pending[0].pc = prefix + first_skip;
    pending[0].depth = 0;
    while (count) {
        int pc = pending[--count].pc;
        unsigned depth = pending[count].depth;
        while (depth < limit) {
            uint8_t atom[RE_SEARCH_LOOKAHEAD_MAP_BYTES] = {0};
            int opcode, size;
            bool consumes = true, reachable = false;
            if (!budget-- || pc < 0 || pc >= code_len)
                return 0;
            opcode = code[pc];
            if (opcode >= REOP_COUNT)
                return 0;
            size = reopcode_info[opcode].size;
            if (size > code_len - pc)
                return 0;
            switch (opcode) {
            case REOP_save_start:
            case REOP_save_end:
            case REOP_save_reset:
            case REOP_line_start:
            case REOP_line_start_m:
            case REOP_line_end:
            case REOP_line_end_m:
            case REOP_word_boundary:
            case REOP_word_boundary_i:
            case REOP_not_word_boundary:
            case REOP_not_word_boundary_i:
            case REOP_set_i32:
            case REOP_set_char_pos:
                consumes = false;
                break;
            case REOP_split_goto_first:
            case REOP_split_next_first:
            case REOP_split_guard_goto_first:
            case REOP_split_guard_next_first: {
                int64_t target = (int64_t)pc + size + (int32_t)get_u32(code + pc + 1);
                if (count == countof(pending) || target < 0 || target >= code_len)
                    return 0;
                pending[count].pc = target;
                pending[count++].depth = depth;
                consumes = false;
            } break;
            case REOP_goto: {
                int64_t target = (int64_t)pc + size + (int32_t)get_u32(code + pc + 1);
                if (target < 0 || target >= code_len)
                    return 0;
                pc = target;
                continue;
            }
            case REOP_char:
            case REOP_char32: {
                uint32_t c = opcode == REOP_char ? get_u16(code + pc + 1) : get_u32(code + pc + 1);
                if (c <= max_char) {
                    re_search_map_add(atom, c);
                    reachable = true;
                }
            } break;
            case REOP_range:
            case REOP_range32: {
                unsigned n = get_u16(code + pc + 1);
                unsigned stride = opcode == REOP_range ? 4 : 8;
                if (n > (unsigned)(code_len - pc - size) / stride)
                    return 0;
                for (i = 0; i < n; i++) {
                    const uint8_t *range = code + pc + size + i * stride;
                    uint32_t low = stride == 4 ? get_u16(range) : get_u32(range);
                    uint32_t high = stride == 4 ? get_u16(range + 2) : get_u32(range + 4);
                    if (stride == 4 && i + 1 == n && high == 0xffff)
                        high = max_char;
                    high = min_uint32(high, max_char);
                    if (low <= high) {
                        reachable = true;
                        if (high - low >= 127)
                            memset(atom, 0xff, sizeof(atom));
                        else
                            for (; low <= high; low++)
                                re_search_map_add(atom, low);
                    }
                }
                size += n * stride;
            } break;
            case REOP_any:
            case REOP_dot:
            case REOP_space:
            case REOP_not_space:
                /* A universal map is a safe over-approximation of these
                 * classes over the wide domain; later positions can still
                 * provide a worthwhile interval. */
                memset(atom, 0xff, sizeof(atom));
                reachable = true;
                break;
            default:
                /* Nullable ends, lookaround, backrefs, counter loops and
                 * unexpanded folding are not assumed to consume a fixed-width character. */
                limit = depth;
                consumes = false;
                break;
            }
            if (depth >= limit)
                break;
            if (consumes) {
                if (!reachable)
                    break;
                for (i = 0; i < RE_SEARCH_LOOKAHEAD_MAP_BYTES; i++)
                    maps[depth][i] |= atom[i];
                depth++;
            }
            pc += size;
        }
    }
    if (limit < 2)
        return 0;
    for (i = 0; i < limit; i++) {
        uint8_t combined[RE_SEARCH_LOOKAHEAD_MAP_BYTES] = {0};
        for (j = i; j < limit; j++) {
            unsigned distinct = 0, k;
            for (k = 0; k < RE_SEARCH_LOOKAHEAD_MAP_BYTES; k++) {
                uint8_t bits = combined[k] |= maps[j][k];
                while (bits) {
                    distinct++;
                    bits &= bits - 1;
                }
            }
            if (j > i && distinct < 96 && (j - i + 1) * (128 - distinct) > best) {
                best = (j - i + 1) * (128 - distinct);
                from = i;
                to = j;
            }
        }
    }
    /* Avoid adding per-exec metadata for short or nearly universal prefixes. */
    if (best < 256)
        return 0;
    encoded[0] = REOP_search_lookahead;
    encoded[1] = limit | RE_SEARCH_LOOKAHEAD_WIDE;
    encoded[2] = from;
    encoded[3] = to;
    for (i = 0; i < limit; i++) {
        memcpy(encoded + RE_SEARCH_LOOKAHEAD_BASE + i * RE_SEARCH_LOOKAHEAD_MAP_BYTES, maps[i],
               RE_SEARCH_LOOKAHEAD_MAP_BYTES);
        if (i >= from && i <= to)
            for (j = 0; j < RE_SEARCH_LOOKAHEAD_MAP_BYTES; j++)
                encoded[RE_SEARCH_LOOKAHEAD_HEADER + j] |= maps[i][j];
    }
    length = RE_SEARCH_LOOKAHEAD_BASE + limit * RE_SEARCH_LOOKAHEAD_MAP_BYTES;
    if (dbuf_insert(&s->byte_code, RE_HEADER_LEN + prefix, length))
        return -1;
    memcpy(s->byte_code.buf + RE_HEADER_LEN + prefix, encoded, length);
    return 1;
}
