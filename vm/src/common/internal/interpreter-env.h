/* Environment compatibility for the renamed native interpreter. */
#ifndef QJS_INTERPRETER_ENV_H
#define QJS_INTERPRETER_ENV_H

#include <stdlib.h>

/* Preserve the previous public environment spellings without retaining the
 * retired backend terminology as an identifier in the current interface. */
#define QJS_INTERP_PREVIOUS_MARKER                                                                 \
    "L"                                                                                            \
    "LINT"

static inline int js_interp_env_is_set(const char *current, const char *previous)
{
    return getenv(current) != NULL || getenv(previous) != NULL;
}

int qjs_internal_interp_frame_disabled(void);
int qjs_internal_interp_internal_disabled(void);
int qjs_internal_interp_register_disabled(void);
#if defined(QJS_INTERP_FRAME_REGISTER_ABI)
int qjs_internal_interp_register_current_disabled(void);
#endif
int qjs_internal_interp_trace_enabled(void);

#endif
