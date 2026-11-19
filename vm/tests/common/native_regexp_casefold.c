/* Full scalar-domain validation against the retained canonicalizer. MIT. */
#include <stdio.h>
#include <stdlib.h>
#include "src/common/regexp/unicode/regexp-unicode.h"

static unsigned long checks;
static int allocations, fail_after;

static void *test_realloc(void *opaque, void *ptr, size_t size)
{
    void *result;
    (void)opaque;
    if (!size) {
        if (ptr)
            allocations--;
        free(ptr);
        return NULL;
    }
    if (fail_after > 0 && --fail_after == 0)
        return NULL;
    result = realloc(ptr, size);
    if (result && !ptr)
        allocations++;
    return result;
}

static int contains(const CharRange *range, uint32_t c)
{
    int low = 0, high = range->len / 2;
    while (low < high) {
        int mid = low + (high - low) / 2;
        if (c < range->points[2 * mid])
            high = mid;
        else if (c >= range->points[2 * mid + 1])
            low = mid + 1;
        else
            return 1;
    }
    return 0;
}

int main(void)
{
    static const uint32_t cases[][2] = {{0, 0x110000},       {'a', 'z' + 1},  {'A', 'Z' + 1},
                                        {'0', '9' + 1},      {0x3c2, 0x3c4},  {0x400, 0x500},
                                        {0x10000, 0x110000}, {0x212a, 0x212b}};
    uint32_t c;
    int mode, i, inverse, step;
    for (mode = 0; mode < 2; mode++) {
        for (c = 0; c <= 0x10ffff; c++) {
            uint32_t canonical = lre_canonicalize(c, mode != 0);
            int n, j, found = 0;
            const uint32_t *members = qjs_frame_regexp_fold_char(canonical, mode != 0, &n);
            if (!members) {
                if (canonical != c)
                    return 1;
            } else {
                for (j = 0; j < n; j++) {
                    if (lre_canonicalize(members[j], mode != 0) != canonical ||
                        (j && members[j - 1] >= members[j]))
                        return 2;
                    found |= members[j] == c;
                }
                if (!found)
                    return 3;
            }
            checks++;
        }
        for (i = 0; i < (int)(sizeof(cases) / sizeof(cases[0])); i++) {
            for (inverse = 0; inverse < 2; inverse++) {
                CharRange input, output;
                cr_init(&input, NULL, test_realloc);
                cr_init(&output, NULL, test_realloc);
                if (cr_add_interval(&input, cases[i][0], cases[i][1]))
                    return 4;
                if (inverse && cr_invert(&input))
                    return 5;
                if (qjs_frame_regexp_expand_ranges(&output, &input, mode != 0))
                    return 6;
                for (c = 0; c <= 0x10ffff; c++) {
                    if (contains(&input, lre_canonicalize(c, mode != 0)) != contains(&output, c)) {
                        fprintf(stderr, "preimage mode=%d case=%d inverse=%d U+%x\n", mode, i,
                                inverse, c);
                        return 7;
                    }
                    checks++;
                }
                cr_free(&input);
                cr_free(&output);
                if (allocations)
                    return 8;
            }
        }
    }
    for (step = 1; step < 30; step++) {
        CharRange input, output;
        cr_init(&input, NULL, test_realloc);
        cr_init(&output, NULL, test_realloc);
        if (cr_add_interval(&input, 0, 0x110000))
            return 9;
        fail_after = step;
        (void)qjs_frame_regexp_expand_ranges(&output, &input, true);
        fail_after = 0;
        cr_free(&input);
        cr_free(&output);
        if (allocations)
            return 10;
    }
    printf("REGEXP_CASEFOLD_DOMAIN_OK %lu\n", checks);
    return 0;
}
