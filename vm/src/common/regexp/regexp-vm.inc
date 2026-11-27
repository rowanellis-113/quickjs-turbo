/* Shared NG regular-expression VM body, extracted without algorithm changes.
 * FRAME_RE_CBUF_TYPE optionally fixes only the already-admitted character width.
 * Capture undo, stack ownership, bounds, Unicode, polling and errors are shared.
 * Original MIT license and attribution are retained in libregexp.c.
 */
/* Native GNU token-threaded execution; other compilers/platforms and dump builds
 * use the same switch body. Keep the VM out of the entry wrapper.
 * Decode remains at the opcode boundary, preserving existing fault/poll order.
 */
#if defined(__GNUC__) && !defined(_MSC_VER) && !defined(DUMP_EXEC) &&                              \
    !defined(QJS_REGEXP_SWITCH_DISPATCH)
#define RE_VM_THREADED 1
#define RE_VM_CASE(id) re_vm_##id:
#define RE_VM_SWITCH(opcode)
#define RE_VM_DEFAULT                                                                              \
    re_vm_bad_opcode:                                                                              \
    re_vm_invalid:
#define RE_VM_NEXT()                                                                               \
    do {                                                                                           \
        opcode = *pc++;                                                                            \
        if (unlikely(opcode >= REOP_COUNT))                                                        \
            goto re_vm_bad_opcode;                                                                 \
        goto *re_vm_targets[opcode];                                                               \
    } while (0)
#else
#define RE_VM_THREADED 0
#define RE_VM_CASE(id) case REOP_##id:
#define RE_VM_SWITCH(opcode) switch (opcode)
#define RE_VM_DEFAULT default:
#define RE_VM_NEXT() break
#endif

static no_inline intptr_t FRAME_RE_EXEC_NAME(REExecContext *s, uint8_t **capture, const uint8_t *pc,
                                             const uint8_t *cptr)
{
    int opcode;
#if RE_VM_THREADED
    static const void *const re_vm_targets[REOP_COUNT] = {
#define DEF(id, size) &&re_vm_##id,
#include "libregexp-opcode.h"
#undef DEF
    };
#endif
#ifdef FRAME_RE_CBUF_TYPE
    const int cbuf_type = FRAME_RE_CBUF_TYPE;
#else
    int cbuf_type;
#endif
    uint32_t val, c, idx;
    const uint8_t *cbuf_end;
    StackElem *sp, *bp, *stack_end;
#ifdef DUMP_EXEC
    const uint8_t *pc_start = pc; /* TEST */
#endif
#ifndef FRAME_RE_CBUF_TYPE
    cbuf_type = s->cbuf_type;
#endif
    cbuf_end = s->cbuf_end;

    sp = s->stack_buf;
    bp = s->stack_buf;
    stack_end = s->stack_buf + s->stack_size;

#define CHECK_STACK_SPACE(n)                                                                       \
    if (unlikely((stack_end - sp) < (n))) {                                                        \
        size_t saved_sp = sp - s->stack_buf;                                                       \
        size_t saved_bp = bp - s->stack_buf;                                                       \
        if (stack_realloc(s, sp - s->stack_buf + (n)))                                             \
            return LRE_RET_MEMORY_ERROR;                                                           \
        stack_end = s->stack_buf + s->stack_size;                                                  \
        sp = s->stack_buf + saved_sp;                                                              \
        bp = s->stack_buf + saved_bp;                                                              \
    }

    /* XXX: could test if the value was saved to reduce the stack size
       but slower */
#define SAVE_CAPTURE(idx, value)                                                                   \
    {                                                                                              \
        CHECK_STACK_SPACE(2);                                                                      \
        sp[0].val = idx;                                                                           \
        sp[1].ptr = capture[idx];                                                                  \
        sp += 2;                                                                                   \
        capture[idx] = (value);                                                                    \
    }

    /* avoid saving the previous value if already saved */
#define SAVE_CAPTURE_CHECK(idx, value)                                                             \
    {                                                                                              \
        StackElem *sp1;                                                                            \
        sp1 = sp;                                                                                  \
        for (;;) {                                                                                 \
            if (sp1 > bp) {                                                                        \
                if (sp1[-2].val == idx)                                                            \
                    break;                                                                         \
                sp1 -= 2;                                                                          \
            } else {                                                                               \
                CHECK_STACK_SPACE(2);                                                              \
                sp[0].val = idx;                                                                   \
                sp[1].ptr = capture[idx];                                                          \
                sp += 2;                                                                           \
                break;                                                                             \
            }                                                                                      \
        }                                                                                          \
        capture[idx] = (value);                                                                    \
    }

#ifdef DUMP_EXEC
    printf("%5s %5s %5s %5s %s\n", "PC", "CP", "BP", "SP", "OPCODE");
#endif
    for (;;) {
#if RE_VM_THREADED
        RE_VM_NEXT();
#else
        opcode = *pc++;
#endif
#ifdef DUMP_EXEC
        printf("%5ld %5ld %5ld %5ld %s\n", pc - 1 - pc_start,
               cbuf_type == 0 ? cptr - s->cbuf : (cptr - s->cbuf) / 2, bp - s->stack_buf,
               sp - s->stack_buf, reopcode_info[opcode].name);
#endif
        RE_VM_SWITCH(opcode)
        {
            RE_VM_CASE(literal_hint)
            pc += 4;
            RE_VM_NEXT();
            RE_VM_CASE(search_lookahead)
            {
                const uint8_t *meta = pc - 1;
                int length = re_test_search_lookahead(s, meta, cptr);
                if (length < 0)
                    return length;
                if (!length)
                    goto no_match;
                pc = meta + length;
            }
            RE_VM_NEXT();
            RE_VM_CASE(match)
            return 1;
        no_match:
            for (;;) {
                REExecStateEnum type;
                if (bp == s->stack_buf)
                    return 0;
                /* undo the modifications to capture[] */
                while (sp > bp) {
                    capture[sp[-2].val] = sp[-1].ptr;
                    sp -= 2;
                }

                pc = sp[-3].ptr;
                cptr = sp[-2].ptr;
                type = sp[-1].bp.type;
                bp = s->stack_buf + sp[-1].bp.val;
                sp -= 3;
                if (type != RE_EXEC_STATE_LOOKAHEAD)
                    break;
            }
            if (lre_poll_timeout(s))
                return LRE_RET_TIMEOUT;
            RE_VM_NEXT();
            RE_VM_CASE(lookahead_match)
            /* pop all the saved states until reaching the start of
               the lookahead and keep the updated captures and
               variables and the corresponding undo info. */
            {
                StackElem *sp1, *sp_top, *next_sp;
                REExecStateEnum type;

                sp_top = sp;
                for (;;) {
                    sp1 = sp;
                    sp = bp;
                    pc = sp[-3].ptr;
                    cptr = sp[-2].ptr;
                    type = sp[-1].bp.type;
                    bp = s->stack_buf + sp[-1].bp.val;
                    sp[-1].ptr = (void *)sp1; /* save the next value for the copy step */
                    sp -= 3;
                    if (type == RE_EXEC_STATE_LOOKAHEAD)
                        break;
                }
                if (sp != s->stack_buf) {
                    /* keep the undo info if there is a saved state */
                    sp1 = sp;
                    while (sp1 < sp_top) {
                        next_sp = (void *)sp1[2].ptr;
                        sp1 += 3;
                        while (sp1 < next_sp)
                            *sp++ = *sp1++;
                    }
                }
            }
            RE_VM_NEXT();
            RE_VM_CASE(negative_lookahead_match)
            /* pop all the saved states until reaching start of the negative lookahead */
            for (;;) {
                REExecStateEnum type;
                type = bp[-1].bp.type;
                /* undo the modifications to capture[] */
                while (sp > bp) {
                    capture[sp[-2].val] = sp[-1].ptr;
                    sp -= 2;
                }
                pc = sp[-3].ptr;
                cptr = sp[-2].ptr;
                type = sp[-1].bp.type;
                bp = s->stack_buf + sp[-1].bp.val;
                sp -= 3;
                if (type == RE_EXEC_STATE_NEGATIVE_LOOKAHEAD)
                    break;
            }
            goto no_match;
            RE_VM_CASE(char32)
            RE_VM_CASE(char32_i)
            val = get_u32(pc);
            pc += 4;
            goto test_char;
            RE_VM_CASE(char)
            RE_VM_CASE(char_i)
            val = get_u16(pc);
            pc += 2;
        test_char:
            if (cptr >= cbuf_end)
                goto no_match;
            GET_CHAR(c, cptr, cbuf_end, cbuf_type);
            if (opcode == REOP_char_i || opcode == REOP_char32_i) {
                c = lre_canonicalize(c, s->is_unicode);
            }
            if (val != c)
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(split_guard_goto_first)
            RE_VM_CASE(split_guard_next_first)
            {
                const uint8_t *retry;
                bool possible = false;
                int atom;
                val = get_u32(pc);
                pc += 4;
                if (opcode == REOP_split_guard_next_first) {
                    retry = pc + (int32_t)val;
                } else {
                    retry = pc;
                    pc += (int32_t)val;
                }
                atom = retry[0];
                if (cptr < cbuf_end) {
                    PEEK_CHAR(c, cptr, cbuf_end, cbuf_type);
                    if (atom == REOP_range || atom == REOP_range32) {
                        unsigned n = get_u16(retry + 1);
                        const uint8_t *ranges = retry + 3;
                        if (atom == REOP_range && n <= 2) {
                            uint32_t low = get_u16(ranges);
                            uint32_t high = get_u16(ranges + 2);
                            if (n == 1 && high == 0xffff)
                                high = UINT32_MAX;
                            if (c >= low && c <= high) {
                                possible = true;
                            } else if (n == 2) {
                                low = get_u16(ranges + 4);
                                high = get_u16(ranges + 6);
                                if (high == 0xffff)
                                    high = UINT32_MAX;
                                possible = c >= low && c <= high;
                            }
                        } else {
                            possible =
                                lre_range_contains_sorted(ranges, n, c, atom == REOP_range32);
                        }
                    } else {
                        uint32_t expected = (atom == REOP_char || atom == REOP_char_i)
                                                ? get_u16(retry + 1)
                                                : get_u32(retry + 1);
                        if (atom == REOP_char_i || atom == REOP_char32_i)
                            c = lre_canonicalize(c, s->is_unicode);
                        possible = c == expected;
                    }
                }
                if (!possible) {
                    /* Keep bounded interrupt response while bypassing a
                       future failed character test and its backtrack. */
                    if (lre_poll_timeout(s))
                        return LRE_RET_TIMEOUT;
                    RE_VM_NEXT();
                }
                CHECK_STACK_SPACE(3);
                sp[0].ptr = (uint8_t *)retry;
                sp[1].ptr = (uint8_t *)cptr;
                sp[2].bp.val = bp - s->stack_buf;
                sp[2].bp.type = RE_EXEC_STATE_SPLIT;
                sp += 3;
                bp = sp;
            }
            RE_VM_NEXT();
            RE_VM_CASE(split_goto_first)
            RE_VM_CASE(split_next_first)
            {
                const uint8_t *pc1;

                val = get_u32(pc);
                pc += 4;
#if defined(FRAME_RE_CBUF_TYPE) && FRAME_RE_CBUF_TYPE == 0
                if ((int)val > 0 && cptr < cbuf_end) {
                    const uint8_t *probe = (opcode == REOP_split_next_first) ? pc : (pc + (int)val);
                    if (probe + 2 < s->bytecode_end && probe[0] == REOP_save_start)
                        probe += 2;
                    if (probe + 3 <= s->bytecode_end && probe[0] == REOP_char) {
                        if (get_u16(probe + 1) != *cptr) {
                            if (opcode == REOP_split_next_first)
                                pc += (int)val;
                            RE_VM_NEXT();
                        }
                    }
                } else if (opcode == REOP_split_goto_first && (int)val < 0 &&
                           pc + 3 <= s->bytecode_end && pc[0] == REOP_save_end &&
                           pc[1] < (uint32_t)s->capture_count && pc[2] == REOP_match) {
                    const uint8_t *target = pc + (int)val;
                    int handled = 0;
                    cptr = lre_greedy_tail_scan8(s, target, pc, cptr, cbuf_end, &handled);
                    if (handled != 0) {
                        if (handled < 0)
                            return handled;
                        RE_VM_NEXT();
                    }
                    if (bp > s->stack_buf && sp == bp && bp[-3].ptr == pc &&
                        bp[-1].bp.type == RE_EXEC_STATE_SPLIT) {
                        bp[-2].ptr = (uint8_t *)cptr;
                        pc = target;
                        if (lre_poll_timeout(s))
                            return LRE_RET_TIMEOUT;
                        RE_VM_NEXT();
                    }
                }
#endif
                if (opcode == REOP_split_next_first) {
                    pc1 = pc + (int)val;
                } else {
                    pc1 = pc;
                    pc = pc + (int)val;
                }
                CHECK_STACK_SPACE(3);
                sp[0].ptr = (uint8_t *)pc1;
                sp[1].ptr = (uint8_t *)cptr;
                sp[2].bp.val = bp - s->stack_buf;
                sp[2].bp.type = RE_EXEC_STATE_SPLIT;
                sp += 3;
                bp = sp;
            }
            RE_VM_NEXT();
            RE_VM_CASE(lookahead)
            RE_VM_CASE(negative_lookahead)
            val = get_u32(pc);
            pc += 4;
            CHECK_STACK_SPACE(3);
            sp[0].ptr = (uint8_t *)(pc + (int)val);
            sp[1].ptr = (uint8_t *)cptr;
            sp[2].bp.val = bp - s->stack_buf;
            sp[2].bp.type = RE_EXEC_STATE_LOOKAHEAD + opcode - REOP_lookahead;
            sp += 3;
            bp = sp;
            RE_VM_NEXT();
            RE_VM_CASE(goto)
            val = get_u32(pc);
            pc += 4 + (int)val;
            if (lre_poll_timeout(s))
                return LRE_RET_TIMEOUT;
            RE_VM_NEXT();
            RE_VM_CASE(line_start)
            RE_VM_CASE(line_start_m)
            if (cptr == s->cbuf)
                RE_VM_NEXT();
            if (opcode == REOP_line_start)
                goto no_match;
            PEEK_PREV_CHAR(c, cptr, s->cbuf, cbuf_type);
            if (!is_line_terminator(c))
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(line_end)
            RE_VM_CASE(line_end_m)
            if (cptr == cbuf_end)
                RE_VM_NEXT();
            if (opcode == REOP_line_end)
                goto no_match;
            PEEK_CHAR(c, cptr, cbuf_end, cbuf_type);
            if (!is_line_terminator(c))
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(dot)
            if (cptr == cbuf_end)
                goto no_match;
            GET_CHAR(c, cptr, cbuf_end, cbuf_type);
            if (is_line_terminator(c))
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(any)
            if (cptr == cbuf_end)
                goto no_match;
            GET_CHAR(c, cptr, cbuf_end, cbuf_type);
            RE_VM_NEXT();
            RE_VM_CASE(space)
            if (cptr == cbuf_end)
                goto no_match;
            GET_CHAR(c, cptr, cbuf_end, cbuf_type);
            if (!lre_is_space(c))
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(not_space)
            if (cptr == cbuf_end)
                goto no_match;
            GET_CHAR(c, cptr, cbuf_end, cbuf_type);
            if (lre_is_space(c))
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(save_start)
            RE_VM_CASE(save_end)
            val = *pc++;
            if (val >= (uint32_t)s->capture_count)
                return LRE_RET_BYTECODE_ERROR;
            idx = 2 * val + opcode - REOP_save_start;
            SAVE_CAPTURE(idx, (uint8_t *)cptr);
            RE_VM_NEXT();
            RE_VM_CASE(save_reset)
            {
                uint32_t val2;
                val = pc[0];
                val2 = pc[1];
                pc += 2;
                if (val2 >= (uint32_t)s->capture_count)
                    return LRE_RET_BYTECODE_ERROR;
                CHECK_STACK_SPACE(2 * (val2 - val + 1));
                while (val <= val2) {
                    idx = 2 * val;
                    SAVE_CAPTURE(idx, NULL);
                    idx = 2 * val + 1;
                    SAVE_CAPTURE(idx, NULL);
                    val++;
                }
            }
            RE_VM_NEXT();
            RE_VM_CASE(set_i32)
            idx = 2 * s->capture_count + pc[0];
            val = get_u32(pc + 1);
            pc += 5;
            SAVE_CAPTURE_CHECK(idx, (void *)(uintptr_t)val);
            RE_VM_NEXT();
            RE_VM_CASE(loop)
            {
                uint32_t val2;
                idx = 2 * s->capture_count + pc[0];
                val = get_u32(pc + 1);
                pc += 5;

                val2 = (uintptr_t)capture[idx] - 1;
                SAVE_CAPTURE_CHECK(idx, (void *)(uintptr_t)val2);
                if (val2 != 0) {
                    pc += (int)val;
                    if (lre_poll_timeout(s))
                        return LRE_RET_TIMEOUT;
                }
            }
            RE_VM_NEXT();
            RE_VM_CASE(loop_split_goto_first)
            RE_VM_CASE(loop_split_next_first)
            RE_VM_CASE(loop_check_adv_split_goto_first)
            RE_VM_CASE(loop_check_adv_split_next_first)
            {
                const uint8_t *pc1;
                uint32_t val2, limit;
                idx = 2 * s->capture_count + pc[0];
                limit = get_u32(pc + 1);
                val = get_u32(pc + 5);
                pc += 9;

                /* decrement the counter */
                val2 = (uintptr_t)capture[idx] - 1;
                SAVE_CAPTURE_CHECK(idx, (void *)(uintptr_t)val2);

                if (val2 > limit) {
                    /* normal loop if counter > limit */
                    pc += (int)val;
                    if (lre_poll_timeout(s))
                        return LRE_RET_TIMEOUT;
                } else {
                    /* check advance */
                    if ((opcode == REOP_loop_check_adv_split_goto_first ||
                         opcode == REOP_loop_check_adv_split_next_first) &&
                        capture[idx + 1] == cptr && val2 != limit) {
                        goto no_match;
                    }

                    /* otherwise conditional split */
                    if (val2 != 0) {
                        if (opcode == REOP_loop_split_next_first ||
                            opcode == REOP_loop_check_adv_split_next_first) {
                            pc1 = pc + (int)val;
                        } else {
                            pc1 = pc;
                            pc = pc + (int)val;
                        }
                        CHECK_STACK_SPACE(3);
                        sp[0].ptr = (uint8_t *)pc1;
                        sp[1].ptr = (uint8_t *)cptr;
                        sp[2].bp.val = bp - s->stack_buf;
                        sp[2].bp.type = RE_EXEC_STATE_SPLIT;
                        sp += 3;
                        bp = sp;
                    }
                }
            }
            RE_VM_NEXT();
            RE_VM_CASE(set_char_pos)
            idx = 2 * s->capture_count + pc[0];
            pc++;
            SAVE_CAPTURE_CHECK(idx, (uint8_t *)cptr);
            RE_VM_NEXT();
            RE_VM_CASE(check_advance)
            idx = 2 * s->capture_count + pc[0];
            pc++;
            if (capture[idx] == cptr)
                goto no_match;
            RE_VM_NEXT();
            RE_VM_CASE(word_boundary)
            RE_VM_CASE(word_boundary_i)
            RE_VM_CASE(not_word_boundary)
            RE_VM_CASE(not_word_boundary_i)
            {
                bool v1, v2;
                int ignore_case =
                    (opcode == REOP_word_boundary_i || opcode == REOP_not_word_boundary_i);
                bool is_boundary = (opcode == REOP_word_boundary || opcode == REOP_word_boundary_i);
                /* char before */
                if (cptr == s->cbuf) {
                    v1 = false;
                } else {
                    PEEK_PREV_CHAR(c, cptr, s->cbuf, cbuf_type);
                    if (c < 256) {
                        v1 = (lre_is_word_byte(c) != 0);
                    } else {
                        v1 = ignore_case && (c == 0x017f || c == 0x212a);
                    }
                }
                /* current char */
                if (cptr >= cbuf_end) {
                    v2 = false;
                } else {
                    PEEK_CHAR(c, cptr, cbuf_end, cbuf_type);
                    if (c < 256) {
                        v2 = (lre_is_word_byte(c) != 0);
                    } else {
                        v2 = ignore_case && (c == 0x017f || c == 0x212a);
                    }
                }
                if (v1 ^ v2 ^ is_boundary)
                    goto no_match;
            }
            RE_VM_NEXT();
            RE_VM_CASE(back_reference)
            RE_VM_CASE(back_reference_i)
            RE_VM_CASE(backward_back_reference)
            RE_VM_CASE(backward_back_reference_i)
            {
                const uint8_t *cptr1, *cptr1_end, *cptr1_start;
                const uint8_t *pc1;
                uint32_t c1, c2;
                int i, n;

                n = *pc++;
                pc1 = pc;
                pc += n;

                for (i = 0; i < n; i++) {
                    val = pc1[i];
                    if (val >= s->capture_count)
                        goto no_match;
                    cptr1_start = capture[2 * val];
                    cptr1_end = capture[2 * val + 1];
                    /* test the first not empty capture */
                    if (cptr1_start && cptr1_end) {
                        if (opcode == REOP_back_reference || opcode == REOP_back_reference_i) {
                            cptr1 = cptr1_start;
                            while (cptr1 < cptr1_end) {
                                if (cptr >= cbuf_end)
                                    goto no_match;
                                GET_CHAR(c1, cptr1, cptr1_end, cbuf_type);
                                GET_CHAR(c2, cptr, cbuf_end, cbuf_type);
                                if (opcode == REOP_back_reference_i) {
                                    c1 = lre_canonicalize(c1, s->is_unicode);
                                    c2 = lre_canonicalize(c2, s->is_unicode);
                                }
                                if (c1 != c2)
                                    goto no_match;
                            }
                        } else {
                            cptr1 = cptr1_end;
                            while (cptr1 > cptr1_start) {
                                if (cptr == s->cbuf)
                                    goto no_match;
                                GET_PREV_CHAR(c1, cptr1, cptr1_start, cbuf_type);
                                GET_PREV_CHAR(c2, cptr, s->cbuf, cbuf_type);
                                if (opcode == REOP_backward_back_reference_i) {
                                    c1 = lre_canonicalize(c1, s->is_unicode);
                                    c2 = lre_canonicalize(c2, s->is_unicode);
                                }
                                if (c1 != c2)
                                    goto no_match;
                            }
                        }
                        break;
                    }
                }
            }
            RE_VM_NEXT();
            RE_VM_CASE(range)
            RE_VM_CASE(range_i)
            {
                int n;
                uint32_t low, high, idx_min, idx_max, idx;

                n = get_u16(pc); /* n must be >= 1 */
                pc += 2;
                if (cptr >= cbuf_end)
                    goto no_match;
                GET_CHAR(c, cptr, cbuf_end, cbuf_type);
                if (opcode == REOP_range_i) {
                    c = lre_canonicalize(c, s->is_unicode);
                }
                if (n <= 2) {
                    /* Yarr's cased-character pair has no binary-search
                       machinery. The same interval test also handles small
                       ordinary classes, without adding a bytecode format. */
                    low = get_u16(pc);
                    high = get_u16(pc + 2);
                    if (n == 1 && high == 0xffff)
                        high = UINT32_MAX;
                    if (c >= low && c <= high)
                        goto range_match;
                    if (n == 2) {
                        low = get_u16(pc + 4);
                        high = get_u16(pc + 6);
                        if (high == 0xffff)
                            high = UINT32_MAX;
                        if (c >= low && c <= high)
                            goto range_match;
                    }
                    goto no_match;
                }
                idx_min = 0;
#if defined(FRAME_RE_CBUF_TYPE) && FRAME_RE_CBUF_TYPE == 0
                {
                    int lim = n < 8 ? n : 8;
                    for (int ri = 0; ri < lim; ri++) {
                        low = get_u16(pc + ri * 4);
                        if (c < low)
                            goto no_match;
                        high = get_u16(pc + ri * 4 + 2);
                        if (c <= high)
                            goto range_match;
                    }
                    if (n <= 8)
                        goto no_match;
                    idx_min = 8;
                }
#else
                low = get_u16(pc + 0 * 4);
                if (c < low)
                    goto no_match;
#endif
                idx_max = n - 1;
                high = get_u16(pc + idx_max * 4 + 2);
                /* 0xffff in for last value means +infinity */
                if (unlikely(c >= 0xffff) && high == 0xffff)
                    goto range_match;
                if (c > high)
                    goto no_match;
                while (idx_min <= idx_max) {
                    idx = (idx_min + idx_max) / 2;
                    low = get_u16(pc + idx * 4);
                    high = get_u16(pc + idx * 4 + 2);
                    if (c < low)
                        idx_max = idx - 1;
                    else if (c > high)
                        idx_min = idx + 1;
                    else
                        goto range_match;
                }
                goto no_match;
            range_match:
                pc += 4 * n;
            }
            RE_VM_NEXT();
            RE_VM_CASE(range32)
            RE_VM_CASE(range32_i)
            {
                int n;
                uint32_t low, high, idx_min, idx_max, idx;

                n = get_u16(pc); /* n must be >= 1 */
                pc += 2;
                if (cptr >= cbuf_end)
                    goto no_match;
                GET_CHAR(c, cptr, cbuf_end, cbuf_type);
                if (opcode == REOP_range32_i) {
                    c = lre_canonicalize(c, s->is_unicode);
                }
                idx_min = 0;
#if defined(FRAME_RE_CBUF_TYPE) && FRAME_RE_CBUF_TYPE == 0
                {
                    int lim = n < 8 ? n : 8;
                    for (int ri = 0; ri < lim; ri++) {
                        low = get_u32(pc + ri * 8);
                        if (c < low)
                            goto no_match;
                        high = get_u32(pc + ri * 8 + 4);
                        if (c <= high)
                            goto range32_match;
                    }
                    if (n <= 8)
                        goto no_match;
                    idx_min = 8;
                }
#else
                low = get_u32(pc + 0 * 8);
                if (c < low)
                    goto no_match;
#endif
                idx_max = n - 1;
                high = get_u32(pc + idx_max * 8 + 4);
                if (c > high)
                    goto no_match;
                while (idx_min <= idx_max) {
                    idx = (idx_min + idx_max) / 2;
                    low = get_u32(pc + idx * 8);
                    high = get_u32(pc + idx * 8 + 4);
                    if (c < low)
                        idx_max = idx - 1;
                    else if (c > high)
                        idx_min = idx + 1;
                    else
                        goto range32_match;
                }
                goto no_match;
            range32_match:
                pc += 8 * n;
            }
            RE_VM_NEXT();
            RE_VM_CASE(prev)
            /* go to the previous char */
            if (cptr == s->cbuf)
                goto no_match;
            PREV_CHAR(cptr, s->cbuf, cbuf_type);
            RE_VM_NEXT();
            RE_VM_DEFAULT
#ifdef DUMP_EXEC
            printf("unknown opcode pc=%ld\n", pc - 1 - pc_start);
#endif
            abort();
        }
    }
}

#undef CHECK_STACK_SPACE
#undef SAVE_CAPTURE
#undef SAVE_CAPTURE_CHECK

#undef RE_VM_THREADED
#undef RE_VM_CASE
#undef RE_VM_SWITCH
#undef RE_VM_DEFAULT
#undef RE_VM_NEXT
