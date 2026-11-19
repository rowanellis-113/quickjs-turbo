/* Isolate the retained regexp dependency; keep upstream input files intact.
 * The three adjacent libunicode files are exact, licensed upstream sources.
 * This translation unit is used only by the pinned 0.15.1 native backend. */
#include "regexp-unicode.h"
#include "libunicode.c"

typedef struct {
    uint32_t canonical;
    uint16_t first;
    uint16_t count;
} RegExpFoldClass;

#include "regexp-casefold-data.h"

const uint32_t *qjs_frame_regexp_fold_char(uint32_t canonical, bool is_unicode, int *count)
{
    const RegExpFoldClass *classes =
        is_unicode ? regexp_fold_unicode_classes : regexp_fold_legacy_classes;
    const uint32_t *members = is_unicode ? regexp_fold_unicode_members : regexp_fold_legacy_members;
    size_t low = 0, high = is_unicode ? countof(regexp_fold_unicode_classes)
                                      : countof(regexp_fold_legacy_classes);
    while (low < high) {
        size_t mid = low + (high - low) / 2;
        if (classes[mid].canonical < canonical)
            low = mid + 1;
        else if (classes[mid].canonical > canonical)
            high = mid;
        else {
            *count = classes[mid].count;
            return members + classes[mid].first;
        }
    }
    *count = 0;
    return NULL;
}

static bool regexp_fold_range_contains(const CharRange *range, uint32_t c)
{
    int low = 0, high = range->len / 2;
    while (low < high) {
        int mid = low + (high - low) / 2;
        if (c < range->points[2 * mid])
            high = mid;
        else if (c >= range->points[2 * mid + 1])
            low = mid + 1;
        else
            return true;
    }
    return false;
}

int qjs_frame_regexp_expand_ranges(CharRange *result, const CharRange *folded, bool is_unicode)
{
    const RegExpFoldClass *classes =
        is_unicode ? regexp_fold_unicode_classes : regexp_fold_legacy_classes;
    const uint32_t *members = is_unicode ? regexp_fold_unicode_members : regexp_fold_legacy_members;
    const uint32_t *domain = is_unicode ? regexp_fold_unicode_domain : regexp_fold_legacy_domain;
    size_t domain_len =
        is_unicode ? countof(regexp_fold_unicode_domain) : countof(regexp_fold_legacy_domain);
    size_t class_count =
        is_unicode ? countof(regexp_fold_unicode_classes) : countof(regexp_fold_legacy_classes);
    CharRange extra;
    size_t i, j;
    int ret = -1;

    /* For a complement, unioning aliases with folded alone is wrong: e.g.
       [^a]/iu contains 'A' in folded but must reject it after folding. Remove
       every nonidentity source first, then add exactly the accepted classes. */
    if (cr_op(result, folded->points, folded->len, domain, (int)domain_len, CR_OP_SUB))
        return -1;
    cr_init(&extra, result->mem_opaque, result->realloc_func);
    for (i = 0; i < class_count; i++) {
        if (!regexp_fold_range_contains(folded, classes[i].canonical))
            continue;
        for (j = 0; j < classes[i].count; j++) {
            uint32_t c = members[classes[i].first + j];
            if (cr_add_interval(&extra, c, c + 1))
                goto done;
        }
    }
    cr_sort_and_remove_overlap(&extra);
    ret = cr_op1(result, extra.points, extra.len, CR_OP_UNION);
done:
    cr_free(&extra);
    return ret;
}

/* 0.15.1's public regexp header declares this bool(int) helper. The retained
 * engine uses its private inline helper; preserve the original external ABI. */
#undef lre_is_space
bool lre_is_space(int c)
{
    return c >= 0 && qjs_frame_regexp_lre_is_space((uint32_t)c) != 0;
}
