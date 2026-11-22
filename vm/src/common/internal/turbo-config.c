/* Process-wide explicit configuration defaults and fallback diagnostics. */
#include "src/common/internal/turbo-config.h"
#include "src/common/internal/interpreter-env.h"
#include <stdlib.h>
#include <string.h>

#if !defined(__STDC_NO_ATOMICS__)
#include <stdatomic.h>
#define QJS_TURBO_ATOMIC_I32 _Atomic(int32_t)
#define QJS_TURBO_ATOMIC_PTR(T) _Atomic(T)
#define QJS_TURBO_LOAD_I32(p) atomic_load_explicit((p), memory_order_acquire)
#define QJS_TURBO_STORE_I32(p, v) atomic_store_explicit((p), (v), memory_order_release)
#define QJS_TURBO_LOAD_PTR(p) atomic_load_explicit((p), memory_order_acquire)
#define QJS_TURBO_STORE_PTR(p, v) atomic_store_explicit((p), (v), memory_order_release)
#elif defined(_WIN32)
#include <windows.h>
#define QJS_TURBO_ATOMIC_I32 volatile LONG
#define QJS_TURBO_ATOMIC_PTR(T) T volatile
#define QJS_TURBO_LOAD_I32(p) ((int32_t)InterlockedCompareExchange((LONG *)(p), 0, 0))
#define QJS_TURBO_STORE_I32(p, v) ((void)InterlockedExchange((LONG *)(p), (LONG)(v)))
#define QJS_TURBO_LOAD_PTR(p) (InterlockedCompareExchangePointer((PVOID volatile *)(p), NULL, NULL))
#define QJS_TURBO_STORE_PTR(p, v)                                                                  \
    ((void)InterlockedExchangePointer((PVOID volatile *)(p), (PVOID)(v)))
#else
#define QJS_TURBO_ATOMIC_I32 volatile int32_t
#define QJS_TURBO_ATOMIC_PTR(T) T volatile
#define QJS_TURBO_LOAD_I32(p) (*(p))
#define QJS_TURBO_STORE_I32(p, v) (*(p) = (v))
#define QJS_TURBO_LOAD_PTR(p) (*(p))
#define QJS_TURBO_STORE_PTR(p, v) (*(p) = (v))
#endif

static QJS_TURBO_ATOMIC_I32 g_own_bytecode_tail = QJS_TURBO_DEFAULT;
static QJS_TURBO_ATOMIC_I32 g_property_ic = QJS_TURBO_DEFAULT;
static QJS_TURBO_ATOMIC_I32 g_property_ic_warmup = -1;
static QJS_TURBO_ATOMIC_I32 g_frame_backend = QJS_TURBO_DEFAULT;
static QJS_TURBO_ATOMIC_I32 g_hybrid_gc = QJS_TURBO_DEFAULT;
static QJS_TURBO_ATOMIC_I32 g_binding_cell = QJS_TURBO_DEFAULT;

static QJS_TURBO_ATOMIC_PTR(qjs_turbo_tail_apply_fn) g_tail_apply_hook = NULL;
static QJS_TURBO_ATOMIC_PTR(qjs_turbo_tail_query_fn) g_tail_query_hook = NULL;

void qjs_turbo_register_own_bytecode_hooks(qjs_turbo_tail_apply_fn apply_fn,
                                           qjs_turbo_tail_query_fn query_fn)
{
    int32_t tail_pref;
    QJS_TURBO_STORE_PTR(&g_tail_apply_hook, apply_fn);
    QJS_TURBO_STORE_PTR(&g_tail_query_hook, query_fn);
    tail_pref = QJS_TURBO_LOAD_I32(&g_own_bytecode_tail);
    if (apply_fn && tail_pref != QJS_TURBO_DEFAULT)
        apply_fn(tail_pref != QJS_TURBO_OFF);
}

static int valid_tristate(int32_t v)
{
    return v == QJS_TURBO_DEFAULT || v == QJS_TURBO_OFF || v == QJS_TURBO_ON;
}

int qjs_turbo_own_bytecode_tail_disabled(void)
{
    int32_t v = QJS_TURBO_LOAD_I32(&g_own_bytecode_tail);
    if (v == QJS_TURBO_OFF)
        return 1;
    if (v == QJS_TURBO_ON)
        return 0;
    return getenv("QJS_DISABLE_OWN_BYTECODE_TAIL") != NULL;
}

int qjs_turbo_own_bytecode_tail_active(void)
{
    qjs_turbo_tail_query_fn fn = (qjs_turbo_tail_query_fn)QJS_TURBO_LOAD_PTR(&g_tail_query_hook);
    if (fn)
        return fn() != 0;
    return 0;
}

int qjs_turbo_default_property_ic_mode(void)
{
    int32_t v = QJS_TURBO_LOAD_I32(&g_property_ic);
    if (v == QJS_TURBO_OFF)
        return 2;
    if (v == QJS_TURBO_ON)
        return 1;
    return getenv("QJS_DISABLE_PROPERTY_IC") != NULL ? 2 : 1;
}

uint32_t qjs_turbo_default_property_ic_warmup(void)
{
    int32_t v = QJS_TURBO_LOAD_I32(&g_property_ic_warmup);
    if (v >= 0) {
        uint32_t u = (uint32_t)v;
        return u > QJS_TURBO_PROPERTY_IC_WARMUP_MAX ? QJS_TURBO_PROPERTY_IC_WARMUP_MAX : u;
    }
    const char *env = getenv("QJS_PROPERTY_IC_WARMUP");
    if (env && *env) {
        char *end = NULL;
        unsigned long parsed = strtoul(env, &end, 10);
        if (end && end != env && *end == '\0') {
            if (parsed > QJS_TURBO_PROPERTY_IC_WARMUP_MAX)
                parsed = QJS_TURBO_PROPERTY_IC_WARMUP_MAX;
            return (uint32_t)parsed;
        }
    }
    return 0u;
}

int qjs_turbo_default_frame_backend_disabled(void)
{
    int32_t v = QJS_TURBO_LOAD_I32(&g_frame_backend);
    if (v == QJS_TURBO_OFF)
        return 1;
    if (v == QJS_TURBO_ON)
        return 0;
    return -1; /* defer to environment variable check */
}

int qjs_turbo_default_hybrid_gc_disabled(void)
{
    int32_t v = QJS_TURBO_LOAD_I32(&g_hybrid_gc);
    if (v == QJS_TURBO_OFF)
        return 1;
    if (v == QJS_TURBO_ON)
        return 0;
    return getenv("QJS_DISABLE_HYBRID_GC") != NULL;
}

int qjs_turbo_default_binding_cell_disabled(void)
{
    int32_t v = QJS_TURBO_LOAD_I32(&g_binding_cell);
    if (v == QJS_TURBO_OFF)
        return 1;
    if (v == QJS_TURBO_ON)
        return 0;
    return getenv("QJS_DISABLE_FRAME_BINDING_CELL") != NULL;
}

JS_EXTERN int QJS_SetTurboDefaults(const QJSTurboOptions *opts)
{
    if (!opts)
        return -1;
    if (opts->struct_size != 0 && opts->struct_size != sizeof(*opts))
        return -1;
    if (!valid_tristate(opts->own_bytecode_tail) || !valid_tristate(opts->property_ic) ||
        !valid_tristate(opts->frame_backend) || !valid_tristate(opts->hybrid_gc) ||
        !valid_tristate(opts->binding_cell))
        return -1;

    if (opts->own_bytecode_tail != QJS_TURBO_DEFAULT) {
        qjs_turbo_tail_apply_fn fn;
        QJS_TURBO_STORE_I32(&g_own_bytecode_tail, opts->own_bytecode_tail);
        fn = (qjs_turbo_tail_apply_fn)QJS_TURBO_LOAD_PTR(&g_tail_apply_hook);
        if (fn)
            fn(opts->own_bytecode_tail != QJS_TURBO_OFF);
    }
    if (opts->property_ic != QJS_TURBO_DEFAULT)
        QJS_TURBO_STORE_I32(&g_property_ic, opts->property_ic);
    if (opts->property_ic_warmup >= 0) {
        int32_t clamped = opts->property_ic_warmup;
        if ((uint32_t)clamped > QJS_TURBO_PROPERTY_IC_WARMUP_MAX)
            clamped = (int32_t)QJS_TURBO_PROPERTY_IC_WARMUP_MAX;
        QJS_TURBO_STORE_I32(&g_property_ic_warmup, clamped);
    }
    if (opts->frame_backend != QJS_TURBO_DEFAULT)
        QJS_TURBO_STORE_I32(&g_frame_backend, opts->frame_backend);
    if (opts->hybrid_gc != QJS_TURBO_DEFAULT)
        QJS_TURBO_STORE_I32(&g_hybrid_gc, opts->hybrid_gc);
    if (opts->binding_cell != QJS_TURBO_DEFAULT)
        QJS_TURBO_STORE_I32(&g_binding_cell, opts->binding_cell);
    return 0;
}

JS_EXTERN void QJS_GetTurboDefaults(QJSTurboOptions *opts)
{
    if (!opts)
        return;
    QJS_TurboOptionsInit(opts);
    opts->own_bytecode_tail = QJS_TURBO_LOAD_I32(&g_own_bytecode_tail);
    opts->property_ic = QJS_TURBO_LOAD_I32(&g_property_ic);
    opts->property_ic_warmup = QJS_TURBO_LOAD_I32(&g_property_ic_warmup);
    opts->frame_backend = QJS_TURBO_LOAD_I32(&g_frame_backend);
    opts->hybrid_gc = QJS_TURBO_LOAD_I32(&g_hybrid_gc);
    opts->binding_cell = QJS_TURBO_LOAD_I32(&g_binding_cell);
}

#ifdef QJS_TURBO_NO_CORE_OVERLAY
/* Fallback definitions when built without the declared core overlay. */
JS_EXTERN int JS_SetRuntimeTurboOptions(JSRuntime *rt, const QJSTurboOptions *opts)
{
    if (!rt || !opts)
        return -1;
    if (opts->struct_size != 0 && opts->struct_size != sizeof(*opts))
        return -1;
    return 0;
}

JS_EXTERN size_t JS_PurgePropertyIC(JSRuntime *rt)
{
    (void)rt;
    return 0;
}

JS_EXTERN int QJS_GetTurboInfo(JSRuntime *rt, QJSTurboInfo *info)
{
    (void)rt;
    if (!info)
        return -1;
    memset(info, 0, sizeof(*info));
    info->struct_size = (uint32_t)sizeof(*info);
    info->api_version = QJS_TURBO_API_VERSION;
    info->backend = (QJSTurboBackend)QJS_TURBO_BACKEND_ID;
    info->backend_name = QJS_TURBO_BACKEND_NAME;
    info->native_vm_compiled = (QJS_TURBO_BACKEND_ID != 0) ? 1u : 0u;
    info->pregenerated_asm = (QJS_TURBO_PREGEN_ASM != 0) ? 1u : 0u;
    return 0;
}
#endif
