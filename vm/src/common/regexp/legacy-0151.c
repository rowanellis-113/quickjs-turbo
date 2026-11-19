/* Preserve the pinned 0.15.1 bytecode format at serialization boundaries.
 * The normal compiler/executor remains the optimized retained engine. Reuse
 * the untouched original source here, with every definition namespaced. MIT. */
#include "legacy-0151.h"
#include <stdbool.h>
#include <stdint.h>

extern void *lre_realloc(void *, void *, size_t);
extern bool lre_check_stack_overflow(void *, size_t);
extern int lre_check_timeout(void *);

typedef struct {
    void *opaque;
    size_t allocation_limit;
} FrameLegacyRegExpCompiler;

void *qjs_frame_legacy_lre_realloc(void *opaque, void *ptr, size_t size)
{
    FrameLegacyRegExpCompiler *compiler = opaque;
    if (size > compiler->allocation_limit)
        return NULL;
    return lre_realloc(compiler->opaque, ptr, size);
}
bool qjs_frame_legacy_lre_check_stack_overflow(void *opaque, size_t size)
{
    return lre_check_stack_overflow(((FrameLegacyRegExpCompiler *)opaque)->opaque, size);
}
int qjs_frame_legacy_lre_check_timeout(void *opaque)
{
    return lre_check_timeout(((FrameLegacyRegExpCompiler *)opaque)->opaque);
}

#define lre_compile qjs_frame_legacy_lre_compile
#define lre_exec qjs_frame_legacy_lre_exec
#define lre_parse_escape qjs_frame_legacy_lre_parse_escape
#define lre_is_space qjs_frame_legacy_lre_is_space
#define lre_get_capture_count qjs_frame_legacy_lre_get_capture_count
#define lre_get_flags qjs_frame_legacy_lre_get_flags
#define lre_get_groupnames qjs_frame_legacy_lre_get_groupnames
#define lre_id_start_table_ascii qjs_frame_legacy_lre_id_start_table_ascii
#define lre_id_continue_table_ascii qjs_frame_legacy_lre_id_continue_table_ascii
#define lre_realloc qjs_frame_legacy_lre_realloc
#define lre_check_stack_overflow qjs_frame_legacy_lre_check_stack_overflow
#define lre_check_timeout qjs_frame_legacy_lre_check_timeout
#include "../../../../libregexp.c"

uint8_t *qjs_frame_regexp_legacy_compile(int *length, char *error, int error_size,
                                         const char *pattern, size_t pattern_length, int flags,
                                         void *opaque, size_t runtime_bytecode_length)
{
    FrameLegacyRegExpCompiler compiler;
    compiler.opaque = opaque;
    /* Do not reintroduce the old compiler's exponential copies on export.
       If it needs much more storage, the writer uses a distinct version that
       old readers reject before decoding. Native readers retain all features. */
    compiler.allocation_limit =
        runtime_bytecode_length > SIZE_MAX / 4 ? SIZE_MAX : runtime_bytecode_length * 4;
    if (compiler.allocation_limit < 65536)
        compiler.allocation_limit = 65536;
    return qjs_frame_legacy_lre_compile(length, error, error_size, pattern, pattern_length, flags,
                                        &compiler);
}
