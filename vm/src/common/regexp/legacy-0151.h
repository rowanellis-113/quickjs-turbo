/* Cold wire-format bridge to the pinned compiler. MIT. */
#ifndef QJS_FRAME_REGEXP_LEGACY_0151_H
#define QJS_FRAME_REGEXP_LEGACY_0151_H
#include <stddef.h>
#include <stdint.h>

uint8_t *qjs_frame_regexp_legacy_compile(int *length, char *error, int error_size,
                                         const char *pattern, size_t pattern_length, int flags,
                                         void *opaque, size_t runtime_bytecode_length);
#endif
