/* Internal process-wide defaults and hook registry for QuickJS-Turbo. */
#ifndef QJS_TURBO_CONFIG_H
#define QJS_TURBO_CONFIG_H

#include <stddef.h>
#include <stdint.h>
#include "quickjs-turbo.h"

#ifndef QJS_TURBO_BACKEND_ID
#define QJS_TURBO_BACKEND_ID 0
#endif

#ifndef QJS_TURBO_BACKEND_NAME
#define QJS_TURBO_BACKEND_NAME "C_FALLBACK"
#endif

#ifndef QJS_TURBO_PREGEN_ASM
#define QJS_TURBO_PREGEN_ASM 0
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*qjs_turbo_tail_apply_fn)(int tail_enabled);
typedef int (*qjs_turbo_tail_query_fn)(void);

void qjs_turbo_register_own_bytecode_hooks(qjs_turbo_tail_apply_fn apply_fn,
                                           qjs_turbo_tail_query_fn query_fn);

/* Effective defaults combining explicit C API overrides and environment fallbacks. */
int qjs_turbo_own_bytecode_tail_disabled(void);
int qjs_turbo_own_bytecode_tail_active(void);
int qjs_turbo_default_property_ic_mode(void);
uint32_t qjs_turbo_default_property_ic_warmup(void);
int qjs_turbo_default_frame_backend_disabled(void);
int qjs_turbo_default_hybrid_gc_disabled(void);
int qjs_turbo_default_binding_cell_disabled(void);

#ifdef __cplusplus
}
#endif

#endif /* QJS_TURBO_CONFIG_H */
