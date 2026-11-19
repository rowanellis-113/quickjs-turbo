/* Necessary-character proof across a bounded nullable prefix. MIT.
 * Every explored path must reach a selective atom within eight forward
 * characters. Its possible positions and character sets are unioned. This
 * is a necessary assertion only; the unchanged VM verifies every candidate.
 * Exhausted bounds, nullable success and unsupported control flow decline.
 */
static int re_insert_search_window(REParseState *s)
{
    struct {
        int pc;
        unsigned depth;
    } pending[128];
    uint8_t encoded[RE_SEARCH_LOOKAHEAD_BASE] = {0};
    const uint8_t *code = s->byte_code.buf + RE_HEADER_LEN;
    int code_len = s->byte_code.size - RE_HEADER_LEN;
    int prefix = re_search_prefix_len(code, code_len), budget = 512;
    unsigned count = 1, from = RE_SEARCH_LOOKAHEAD_POSITIONS, to = 0, paths = 0, i;
    size_t first_skip = 0;

    if (!prefix || code_len <= prefix || code[prefix] == REOP_search_lookahead)
        return 0;
    re_start_filter(code + prefix, code_len - prefix, &first_skip);
    pending[0].pc = prefix + first_skip;
    pending[0].depth = 0;
    while (count) {
        int pc = pending[--count].pc;
        unsigned depth = pending[count].depth;
        for (;;) {
            uint8_t atom[RE_SEARCH_LOOKAHEAD_MAP_BYTES] = {0};
            unsigned distinct = 0;
            int op, size;
            bool consumes = true;
            if (!budget-- || pc < 0 || pc >= code_len || depth >= RE_SEARCH_LOOKAHEAD_POSITIONS)
                return 0;
            op = code[pc];
            if (op >= REOP_COUNT)
                return 0;
            size = reopcode_info[op].size;
            if (size > code_len - pc)
                return 0;
            switch (op) {
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
                pending[count].pc = (int)target;
                pending[count++].depth = depth;
                consumes = false;
            } break;
            case REOP_goto: {
                int64_t target = (int64_t)pc + size + (int32_t)get_u32(code + pc + 1);
                if (target < 0 || target >= code_len)
                    return 0;
                pc = (int)target;
                continue;
            }
            case REOP_char:
            case REOP_char32:
                re_search_map_add(atom, op == REOP_char ? get_u16(code + pc + 1)
                                                        : get_u32(code + pc + 1));
                break;
            case REOP_range:
            case REOP_range32: {
                unsigned n = get_u16(code + pc + 1), j;
                unsigned stride = op == REOP_range ? 4 : 8;
                if (n > (unsigned)(code_len - pc - size) / stride)
                    return 0;
                for (j = 0; j < n; j++) {
                    const uint8_t *p = code + pc + size + stride * j;
                    uint32_t low = stride == 4 ? get_u16(p) : get_u32(p);
                    uint32_t high = stride == 4 ? get_u16(p + 2) : get_u32(p + 4);
                    if (stride == 4 && j + 1 == n && high == 0xffff)
                        high = 0x10ffff;
                    high = min_uint32(high, 0x10ffff);
                    if (low <= high) {
                        if (high - low >= 127)
                            memset(atom, 0xff, sizeof(atom));
                        else
                            for (; low <= high; low++)
                                re_search_map_add(atom, low);
                    }
                }
                size += stride * n;
            } break;
            case REOP_range_i:
            case REOP_range32_i: {
                unsigned n = get_u16(code + pc + 1);
                unsigned stride = op == REOP_range_i ? 4 : 8;
                if (n > (unsigned)(code_len - pc - size) / stride)
                    return 0;
                size += stride * n;
                memset(atom, 0xff, sizeof(atom));
            } break;
            case REOP_char_i:
            case REOP_char32_i:
            case REOP_any:
            case REOP_dot:
            case REOP_space:
            case REOP_not_space:
                /* Over-approximate folded/broad atoms as consuming any one
                 * fixed-width unit. Unicode-wide execution ignores metadata. */
                memset(atom, 0xff, sizeof(atom));
                break;
            default:
                return 0;
            }
            if (consumes) {
                for (i = 0; i < RE_SEARCH_LOOKAHEAD_MAP_BYTES; i++) {
                    unsigned bits = atom[i];
                    while (bits) {
                        distinct++;
                        bits &= bits - 1;
                    }
                }
                if (distinct && distinct <= 32) {
                    for (i = 0; i < RE_SEARCH_LOOKAHEAD_MAP_BYTES; i++)
                        encoded[RE_SEARCH_LOOKAHEAD_HEADER + i] |= atom[i];
                    if (depth < from)
                        from = depth;
                    if (depth > to)
                        to = depth;
                    paths++;
                    break;
                }
                depth++;
            }
            pc += size;
        }
    }
    /* Position zero alone is already covered by the existing first filter.
     * Decline broadly unioned alternatives rather than burdening each exec. */
    if (!paths || !to)
        return 0;
    encoded[0] = REOP_search_lookahead;
    encoded[1] = 1 | RE_SEARCH_LOOKAHEAD_WIDE | RE_SEARCH_LOOKAHEAD_WINDOW;
    encoded[2] = from;
    encoded[3] = to;
    if (!re_search_lookahead_size(encoded, sizeof(encoded), true))
        return 0;
    if (dbuf_insert(&s->byte_code, RE_HEADER_LEN + prefix, sizeof(encoded)))
        return -1;
    memcpy(s->byte_code.buf + RE_HEADER_LEN + prefix, encoded, sizeof(encoded));
    return 1;
}
