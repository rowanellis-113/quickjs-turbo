/* Private Unicode dependencies of the retained regexp engine. MIT.
 * Prefix every Unicode entry, including inline helpers: the pinned engine
 * continues to use its own libunicode implementation and public API. */
#ifndef QJS_FRAME_REGEXP_UNICODE_H
#define QJS_FRAME_REGEXP_UNICODE_H

#define lre_case_conv qjs_frame_regexp_lre_case_conv
#define lre_canonicalize qjs_frame_regexp_lre_canonicalize
#define lre_is_cased qjs_frame_regexp_lre_is_cased
#define lre_is_case_ignorable qjs_frame_regexp_lre_is_case_ignorable
#define cr_init qjs_frame_regexp_cr_init
#define cr_free qjs_frame_regexp_cr_free
#define cr_realloc qjs_frame_regexp_cr_realloc
#define cr_copy qjs_frame_regexp_cr_copy
#define cr_add_point qjs_frame_regexp_cr_add_point
#define cr_add_interval qjs_frame_regexp_cr_add_interval
#define cr_op1 qjs_frame_regexp_cr_op1
#define cr_union_interval qjs_frame_regexp_cr_union_interval
#define cr_op qjs_frame_regexp_cr_op
#define cr_invert qjs_frame_regexp_cr_invert
#define cr_regexp_canonicalize qjs_frame_regexp_cr_regexp_canonicalize
#define lre_is_id_start qjs_frame_regexp_lre_is_id_start
#define lre_is_id_continue qjs_frame_regexp_lre_is_id_continue
#define lre_is_white_space qjs_frame_regexp_lre_is_white_space
#define unicode_normalize qjs_frame_regexp_unicode_normalize
#define unicode_script qjs_frame_regexp_unicode_script
#define unicode_general_category qjs_frame_regexp_unicode_general_category
#define unicode_prop qjs_frame_regexp_unicode_prop
#define unicode_sequence_prop qjs_frame_regexp_unicode_sequence_prop
#define lre_ctype_bits qjs_frame_regexp_lre_ctype_bits
#define lre_is_space_byte qjs_frame_regexp_lre_is_space_byte
#define lre_is_id_start_byte qjs_frame_regexp_lre_is_id_start_byte
#define lre_is_id_continue_byte qjs_frame_regexp_lre_is_id_continue_byte
#define lre_is_word_byte qjs_frame_regexp_lre_is_word_byte
#define lre_is_space_non_ascii qjs_frame_regexp_lre_is_space_non_ascii
#define lre_is_space qjs_frame_regexp_lre_is_space

#include "libunicode.h"

/* Compile-time preimages, using this dependency's exact canonicalization. */
const uint32_t *qjs_frame_regexp_fold_char(uint32_t canonical, bool is_unicode, int *count);
int qjs_frame_regexp_expand_ranges(CharRange *result, const CharRange *folded, bool is_unicode);
#endif
