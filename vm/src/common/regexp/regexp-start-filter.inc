/* Necessary first-character proof and an ordinary-bytecode encoding. MIT.
 * Unknown/nullable/large expressions retain the existing backtracking path.
 * The encoded lookahead is independently correct when executed normally;
 * the executor may hoist its pure test outside candidate-position retries.
 */
#define RE_START_FILTER_RANGES 32

static int re_search_prefix_len(const uint8_t *code, size_t len)
{
    return len >= 11 && code[0] == REOP_split_goto_first && get_u32(code + 1) == 6 &&
                   code[5] == REOP_any && code[6] == REOP_goto && get_u32(code + 7) == (uint32_t)-11
               ? 11
               : 0;
}

/* 1 = proved nonnullable, 0 = decline, -1 = allocation failure. */
static int re_first_character_set(REParseState *s, CharRange *set, const uint8_t *code, int len)
{
    int pending[128], count = 1, budget = 512;
    pending[0] = 0;
    while (count) {
        int pc = pending[--count];
        for (;;) {
            int op, size;
            if (--budget < 0 || pc < 0 || pc >= len)
                return 0;
            op = code[pc];
            if (op >= REOP_COUNT)
                return 0;
            size = reopcode_info[op].size;
            if (size > len - pc)
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
                pc += size;
                continue;
            case REOP_split_goto_first:
            case REOP_split_next_first:
            case REOP_split_guard_goto_first:
            case REOP_split_guard_next_first:
                if (count == countof(pending))
                    return 0;
                {
                    int64_t target = (int64_t)pc + size + (int32_t)get_u32(code + pc + 1);
                    if (target < 0 || target >= len)
                        return 0;
                    pending[count++] = (int)target;
                }
                pc += size;
                continue;
            case REOP_goto: {
                int64_t target = (int64_t)pc + size + (int32_t)get_u32(code + pc + 1);
                if (target < 0 || target >= len)
                    return 0;
                pc = (int)target;
            }
                continue;
            case REOP_char:
            case REOP_char32:
            case REOP_char_i:
            case REOP_char32_i: {
                uint32_t c = (op == REOP_char || op == REOP_char_i) ? get_u16(code + pc + 1)
                                                                    : get_u32(code + pc + 1);
                if (op == REOP_char_i || op == REOP_char32_i) {
#ifdef QJS_FRAME_REGEXP_PRIVATE_UNICODE
                    int n, i;
                    const uint32_t *members = qjs_frame_regexp_fold_char(c, s->is_unicode, &n);
                    for (i = 0; i < n; i++)
                        if (cr_union_interval(set, members[i], members[i]))
                            return -1;
                    if (n)
                        break;
#else
                    return 0;
#endif
                }
                if (c <= 0x10ffff && cr_union_interval(set, c, c))
                    return -1;
            } break;
            case REOP_range:
            case REOP_range32:
            case REOP_range_i:
            case REOP_range32_i: {
                unsigned i, n = get_u16(code + pc + 1);
                unsigned stride = (op == REOP_range || op == REOP_range_i) ? 4 : 8;
                CharRange folded, expanded;
                int result = 0;
                if (n > (unsigned)(len - pc - size) / stride)
                    return 0;
                cr_init(&folded, s->opaque, lre_realloc);
                cr_init(&expanded, s->opaque, lre_realloc);
                for (i = 0; i < n; i++) {
                    const uint8_t *p = code + pc + size + stride * i;
                    uint32_t low = stride == 4 ? get_u16(p) : get_u32(p);
                    uint32_t high = stride == 4 ? get_u16(p + 2) : get_u32(p + 4);
                    if (stride == 4 && i + 1 == n && high == 0xffff)
                        high = 0x10ffff;
                    high = min_uint32(high, 0x10ffff);
                    if (low <= high && cr_add_interval(&folded, low, high + 1)) {
                        result = -1;
                        break;
                    }
                }
                if (!result && (op == REOP_range_i || op == REOP_range32_i)) {
#ifdef QJS_FRAME_REGEXP_PRIVATE_UNICODE
                    result = qjs_frame_regexp_expand_ranges(&expanded, &folded, s->is_unicode);
                    if (!result)
                        result = cr_op1(set, expanded.points, expanded.len, CR_OP_UNION);
#else
                    cr_free(&folded);
                    cr_free(&expanded);
                    return 0;
#endif
                } else if (!result) {
                    result = cr_op1(set, folded.points, folded.len, CR_OP_UNION);
                }
                cr_free(&folded);
                cr_free(&expanded);
                if (result)
                    return -1;
            } break;
            default:
                /* Includes match (nullable), lookaround, backwards reads,
                   unknown folded atoms, backrefs, consuming loops and dot. */
                return 0;
            }
            if (set->len > RE_START_FILTER_RANGES * 2)
                return 0;
            break;
        }
    }
    return set->len != 0;
}

static int re_insert_start_filter(REParseState *s)
{
    CharRange first;
    int prefix, proof, n, i, position;
    unsigned distinct = 0, stride;
    uint8_t encoded[5 + 3 + RE_START_FILTER_RANGES * 8 + 1];
    size_t length;
    const uint8_t *code = s->byte_code.buf + RE_HEADER_LEN;
    int code_len = s->byte_code.size - RE_HEADER_LEN;

    prefix = re_search_prefix_len(code, code_len);
    cr_init(&first, s->opaque, lre_realloc);
    proof = re_first_character_set(s, &first, code + prefix, code_len - prefix);
    if (proof <= 0)
        goto done;
    for (i = 0; i < first.len; i += 2) {
        distinct += first.points[i + 1] - first.points[i];
        if (distinct > 4096) {
            proof = 0;
            goto done;
        }
    }
    n = first.len / 2;
    stride = first.points[first.len - 1] > 0x10000 ? 8 : 4;
    encoded[0] = REOP_lookahead;
    put_u32(encoded + 1, 3 + stride * n + 1);
    encoded[5] = stride == 4 ? REOP_range : REOP_range32;
    put_u16(encoded + 6, n);
    for (i = 0; i < n; i++) {
        uint8_t *p = encoded + 8 + stride * i;
        if (stride == 4) {
            put_u16(p, first.points[i * 2]);
            put_u16(p + 2, first.points[i * 2 + 1] - 1);
        } else {
            put_u32(p, first.points[i * 2]);
            put_u32(p + 4, first.points[i * 2 + 1] - 1);
        }
    }
    encoded[8 + stride * n] = REOP_lookahead_match;
    length = 9 + stride * n;
    position = RE_HEADER_LEN + prefix;
    if (dbuf_insert(&s->byte_code, position, length)) {
        proof = -1;
        goto done;
    }
    memcpy(s->byte_code.buf + position, encoded, length);
done:
    cr_free(&first);
    return proof < 0 ? -1 : 0;
}

/* Return a pure one-character lookahead, or NULL for normal dispatch. This
   also handles an equivalent user-authored assertion without changing it. */
static const uint8_t *re_start_filter(const uint8_t *pc, size_t len, size_t *skip)
{
    unsigned n, stride;
    size_t size;
    if (len < 13 || pc[0] != REOP_lookahead || (pc[5] != REOP_range && pc[5] != REOP_range32))
        return NULL;
    n = get_u16(pc + 6);
    stride = pc[5] == REOP_range ? 4 : 8;
    size = 9 + stride * n;
    if (!n || n > RE_START_FILTER_RANGES || size > len || get_u32(pc + 1) != size - 5 ||
        pc[size - 1] != REOP_lookahead_match)
        return NULL;
    *skip = size;
    return pc + 5;
}

static bool re_start_filter_contains(const uint8_t *atom, uint32_t c)
{
    unsigned n = get_u16(atom + 1), i;
    unsigned stride = atom[0] == REOP_range ? 4 : 8;
    const uint8_t *ranges = atom + 3;
    for (i = 0; i < n; i++) {
        uint32_t low = stride == 4 ? get_u16(ranges + stride * i) : get_u32(ranges + stride * i);
        uint32_t high =
            stride == 4 ? get_u16(ranges + stride * i + 2) : get_u32(ranges + stride * i + 4);
        if (stride == 4 && i + 1 == n && high == 0xffff)
            high = UINT32_MAX;
        if (c >= low && c <= high)
            return true;
        if (c < low)
            return false;
    }
    return false;
}
