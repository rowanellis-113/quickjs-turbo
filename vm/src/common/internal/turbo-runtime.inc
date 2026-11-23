/* Runtime-level QuickJS-Turbo configuration, IC purge, and diagnostic API.
 * Included in the overlaid core TU so it has direct access to JSRuntime fields. */
#include "src/common/internal/turbo-config.h"
#include "src/common/internal/interpreter-env.h"

#ifndef QJS_TURBO_FRAME_STATE_PTR
#define QJS_TURBO_FRAME_STATE_PTR(rt_)                                                             \
    (((unsigned char *)(rt_)) + offsetof(JSRuntime, current_stack_frame) - 1)
#endif

static int qjs_turbo_valid_tristate_rt(int32_t v)
{
    return v == QJS_TURBO_DEFAULT || v == QJS_TURBO_OFF || v == QJS_TURBO_ON;
}

JS_EXTERN int JS_SetRuntimeTurboOptions(JSRuntime *rt, const QJSTurboOptions *opts)
{
    if (!rt || !opts)
        return -1;
    if (opts->struct_size != 0 && opts->struct_size != sizeof(*opts))
        return -1;
    if (!qjs_turbo_valid_tristate_rt(opts->own_bytecode_tail) ||
        !qjs_turbo_valid_tristate_rt(opts->property_ic) ||
        !qjs_turbo_valid_tristate_rt(opts->frame_backend) ||
        !qjs_turbo_valid_tristate_rt(opts->hybrid_gc) ||
        !qjs_turbo_valid_tristate_rt(opts->binding_cell))
        return -1;

    if (opts->own_bytecode_tail != QJS_TURBO_DEFAULT) {
        QJSTurboOptions tail_only;
        QJS_TurboOptionsInit(&tail_only);
        tail_only.own_bytecode_tail = opts->own_bytecode_tail;
        QJS_SetTurboDefaults(&tail_only);
    }

#ifdef QJS_PROPERTY_IC
    if (opts->property_ic == QJS_TURBO_OFF) {
        rt->property_ic_mode = 2;
    } else if (opts->property_ic == QJS_TURBO_ON) {
        rt->property_ic_mode = 1;
    }
    if (opts->property_ic_warmup >= 0) {
        uint32_t w = (uint32_t)opts->property_ic_warmup;
        if (w > QJS_TURBO_PROPERTY_IC_WARMUP_MAX)
            w = QJS_TURBO_PROPERTY_IC_WARMUP_MAX;
        rt->property_ic_warmup = w;
    }
#endif

    if (opts->frame_backend == QJS_TURBO_OFF) {
        *QJS_TURBO_FRAME_STATE_PTR(rt) = 2;
    } else if (opts->frame_backend == QJS_TURBO_ON) {
        *QJS_TURBO_FRAME_STATE_PTR(rt) = (QJS_TURBO_BACKEND_ID != 0) ? 1 : 0;
    }

#ifdef QJS_HYBRID_GC_OVERLAY
    if (opts->hybrid_gc == QJS_TURBO_OFF) {
        js_hybrid_unlink_boundary(rt);
        rt->hybrid_gc_mode = 0;
        rt->drc_ok = 0;
    } else if (opts->hybrid_gc == QJS_TURBO_ON) {
        rt->hybrid_gc_mode = JS_HYBRID_MODE_PARTIAL | JS_HYBRID_MODE_FAST_RC;
        rt->drc_ok = 1;
    }
#endif

    return 0;
}

JS_EXTERN size_t JS_PurgePropertyIC(JSRuntime *rt)
{
#ifdef QJS_PROPERTY_IC
    return js_property_ic_purge(rt);
#else
    (void)rt;
    return 0;
#endif
}

JS_EXTERN int QJS_GetTurboInfo(JSRuntime *rt, QJSTurboInfo *info)
{
    int native_compiled;
    if (!info)
        return -1;
    memset(info, 0, sizeof(*info));
    native_compiled = (QJS_TURBO_BACKEND_ID != 0) ? 1 : 0;
    info->struct_size = (uint32_t)sizeof(*info);
    info->api_version = QJS_TURBO_API_VERSION;
    info->backend = (QJSTurboBackend)QJS_TURBO_BACKEND_ID;
    info->backend_name = QJS_TURBO_BACKEND_NAME;
    info->native_vm_compiled = (uint8_t)native_compiled;
    if (native_compiled) {
        if (rt) {
            unsigned char rt_state = *QJS_TURBO_FRAME_STATE_PTR(rt);
            if (rt_state == 2)
                info->native_vm_active = 0;
            else if (rt_state == 1)
                info->native_vm_active = 1;
            else
                info->native_vm_active = qjs_internal_interp_frame_disabled() ? 0u : 1u;
        } else {
            info->native_vm_active = qjs_internal_interp_frame_disabled() ? 0u : 1u;
        }
    }
    info->own_bytecode_tail_on = (uint8_t)(qjs_turbo_own_bytecode_tail_active() ? 1u : 0u);
#ifdef QJS_PROPERTY_IC
    info->property_ic_compiled = 1u;
    if (rt) {
        info->property_ic_enabled = (rt->property_ic_mode == 1) ? 1u : 0u;
        info->property_ic_warmup = rt->property_ic_warmup;
        js_property_ic_stats(rt, &info->property_ic_slab_count, &info->property_ic_bytes);
    } else {
        info->property_ic_enabled = (qjs_turbo_default_property_ic_mode() == 1) ? 1u : 0u;
        info->property_ic_warmup = qjs_turbo_default_property_ic_warmup();
    }
#endif
#ifdef QJS_HYBRID_GC_OVERLAY
    info->hybrid_gc_compiled = 1u;
#endif
    info->pregenerated_asm = (QJS_TURBO_PREGEN_ASM != 0) ? 1u : 0u;
    return 0;
}
