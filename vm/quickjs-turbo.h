/* Public runtime configuration and diagnostics API for QuickJS-Turbo.
 * Safe to include from both C11 and C++11 consumers; upstream quickjs.h
 * remains unmodified and ABI-compatible. */
#ifndef QUICKJS_TURBO_H
#define QUICKJS_TURBO_H

#include <stddef.h>
#include <stdint.h>
#include "quickjs.h"

#ifdef __cplusplus
extern "C" {
#endif

#define QJS_TURBO_API_VERSION 1u
#define QJS_TURBO_PROPERTY_IC_WARMUP_MAX 2047u

typedef enum QJSTurboTriState {
    QJS_TURBO_DEFAULT = -1,
    QJS_TURBO_OFF = 0,
    QJS_TURBO_ON = 1,
} QJSTurboTriState;

typedef enum QJSTurboBackend {
    QJS_TURBO_BACKEND_C_FALLBACK = 0,
    QJS_TURBO_BACKEND_LINUX_X86_64 = 1,
    QJS_TURBO_BACKEND_LINUX_AARCH64 = 2,
    QJS_TURBO_BACKEND_MACOS_X86_64 = 3,
    QJS_TURBO_BACKEND_WIN_X86_64 = 4,
} QJSTurboBackend;

typedef struct QJSTurboOptions {
    uint32_t struct_size;       /* sizeof(QJSTurboOptions) or 0 */
    int32_t own_bytecode_tail;  /* QJS_TURBO_DEFAULT(-1), OFF(0 = PIC-only), ON(1) */
    int32_t property_ic;        /* QJS_TURBO_DEFAULT(-1), OFF(0), ON(1) */
    int32_t property_ic_warmup; /* <0: default; 0: eager; 1..2047: warmup threshold */
    int32_t frame_backend;      /* QJS_TURBO_DEFAULT(-1), OFF(0 = C VM), ON(1 = native if built) */
    int32_t hybrid_gc;          /* QJS_TURBO_DEFAULT(-1), OFF(0), ON(1) */
    int32_t binding_cell;       /* QJS_TURBO_DEFAULT(-1), OFF(0), ON(1) */
    uint32_t reserved[4];
} QJSTurboOptions;

typedef struct QJSTurboInfo {
    uint32_t struct_size;    /* caller sets sizeof(QJSTurboInfo) or 0 */
    uint32_t api_version;    /* QJS_TURBO_API_VERSION */
    QJSTurboBackend backend; /* effective compiled backend */
    const char *
        backend_name; /* "LINUX_X86_64", "LINUX_AARCH64", "MACOS_X86_64", "WIN_X86_64", "C_FALLBACK" */
    uint8_t native_vm_compiled; /* 1 if native ASM VM compiled in, 0 if C_FALLBACK */
    uint8_t
        native_vm_active; /* 1 if native ASM VM enabled for rt (or process default if rt==NULL) */
    uint8_t
        own_bytecode_tail_on; /* 1 if own_bytecode tail allocation is active, 0 if off/PIC-only */
    uint8_t property_ic_compiled; /* 1 if QJS_PROPERTY_IC compiled in */
    uint8_t
        property_ic_enabled; /* 1 if property_ic active for rt (or process default if rt==NULL) */
    uint8_t hybrid_gc_compiled; /* 1 if QJS_HYBRID_GC compiled in */
    uint8_t pregenerated_asm;   /* 1 if built from pre-generated assembly */
    uint8_t reserved_flags;
    uint32_t property_ic_warmup;     /* effective warmup threshold (0 = eager) */
    uint32_t property_ic_slab_count; /* live IC slabs in rt (0 if rt==NULL) */
    uint32_t reserved_u32;
    size_t property_ic_bytes; /* live bytes in IC slabs + secondary arrays in rt */
} QJSTurboInfo;

static inline void QJS_TurboOptionsInit(QJSTurboOptions *opts)
{
    if (!opts)
        return;
    opts->struct_size = (uint32_t)sizeof(*opts);
    opts->own_bytecode_tail = QJS_TURBO_DEFAULT;
    opts->property_ic = QJS_TURBO_DEFAULT;
    opts->property_ic_warmup = -1;
    opts->frame_backend = QJS_TURBO_DEFAULT;
    opts->hybrid_gc = QJS_TURBO_DEFAULT;
    opts->binding_cell = QJS_TURBO_DEFAULT;
    opts->reserved[0] = 0;
    opts->reserved[1] = 0;
    opts->reserved[2] = 0;
    opts->reserved[3] = 0;
}

/* Set/query process-wide defaults without getenv() or constructor priority races.
 * Returns 0 on success, < 0 on invalid arguments. */
JS_EXTERN int QJS_SetTurboDefaults(const QJSTurboOptions *opts);
JS_EXTERN void QJS_GetTurboDefaults(QJSTurboOptions *opts);

/* Configure per-runtime turbo options (property_ic, property_ic_warmup, frame_backend).
 * Returns 0 on success, < 0 on invalid arguments. */
JS_EXTERN int JS_SetRuntimeTurboOptions(JSRuntime *rt, const QJSTurboOptions *opts);

/* Reclaim idle Property IC slabs owned by rt; returns total bytes freed.
 * Safe to invoke when a worker is idle/hibernating (active frames are skipped). */
JS_EXTERN size_t JS_PurgePropertyIC(JSRuntime *rt);

/* Structured read-only diagnostics. rt may be NULL for process-level info.
 * Returns 0 on success, < 0 on invalid arguments. */
JS_EXTERN int QJS_GetTurboInfo(JSRuntime *rt, QJSTurboInfo *info);

#ifdef __cplusplus
}
#endif

#endif /* QUICKJS_TURBO_H */
