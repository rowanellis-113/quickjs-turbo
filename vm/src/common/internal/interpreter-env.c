#include "src/common/internal/interpreter-env.h"
#include "src/common/internal/turbo-config.h"

/* Interpreter controls are inspected at mode setup or diagnostic boundaries. */
#if defined(_MSC_VER) && defined(_M_X64)
#define QJS_INTERP_ENV_COLD __declspec(code_seg(".qjscold$zzqjsenv"))
#else
#define QJS_INTERP_ENV_COLD
#endif

QJS_INTERP_ENV_COLD int qjs_internal_interp_frame_disabled(void)
{
    int pref = qjs_turbo_default_frame_backend_disabled();
    if (pref >= 0)
        return pref;
    return js_interp_env_is_set("QJS_DISABLE_INTERP_FRAME",
                                "QJS_DISABLE_" QJS_INTERP_PREVIOUS_MARKER "_FRAME");
}
QJS_INTERP_ENV_COLD int qjs_internal_interp_internal_disabled(void)
{
    return js_interp_env_is_set("QJS_DISABLE_INTERNAL_INTERP",
                                "QJS_DISABLE_INTERNAL_" QJS_INTERP_PREVIOUS_MARKER);
}
QJS_INTERP_ENV_COLD int qjs_internal_interp_register_disabled(void)
{
    return js_interp_env_is_set("QJS_DISABLE_REGISTER_INTERP",
                                "QJS_DISABLE_REGISTER_" QJS_INTERP_PREVIOUS_MARKER);
}
#if defined(QJS_INTERP_FRAME_REGISTER_ABI)
#if !defined(_MSC_VER) && defined(_WIN32) && defined(__GNUC__)
__attribute__((section(".text$zzqjsenv")))
#endif
QJS_INTERP_ENV_COLD int qjs_internal_interp_register_current_disabled(void)
{
    return getenv("QJS_DISABLE_REGISTER_INTERP") != NULL;
}
#endif
QJS_INTERP_ENV_COLD int qjs_internal_interp_trace_enabled(void)
{
    return js_interp_env_is_set("QJS_INTERP_FRAME_TRACE",
                                "QJS_" QJS_INTERP_PREVIOUS_MARKER "_FRAME_TRACE");
}
#undef QJS_INTERP_ENV_COLD

#if defined(_MSC_VER) && defined(_M_X64) && defined(_MT) && !defined(_DLL)
/* Static C runtime libraries omit the indirect import slot for getenv;
 * provide a readonly pointer slot for indirect native assembly calls. */
extern __declspec(selectany) char *(__cdecl *const __imp_getenv)(const char *) = getenv;
#endif
