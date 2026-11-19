/* Generic/magic native ABI assertions; configuration lives in assembly. MIT. */
/* The five bytes before current_stack_frame hold shared/host/register/internal/frame modes.
 * Independent alignment padding follows module_normalize_has_attr.
 * No core type or boundary-record offset is changed. */
#define FRAME_GENERIC_MODE(rt)                                                                     \
    (((unsigned char *)(rt))[QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 1])
#define FRAME_GENERIC_WINDOW_MODE(rt)                                                              \
    (((unsigned char *)(rt))[QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 2])
_Static_assert(offsetof(JSRuntime, module_normalize_has_attr) ==
                       QJS_ABI_OFF_JSRuntime_module_normalize_has_attr &&
                   sizeof(bool) == 1 &&
                   offsetof(JSRuntime, normalize_u) == QJS_ABI_OFF_JSRuntime_normalize_u &&
                   QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 1 >=
                       offsetof(JSRuntime, module_normalize_has_attr) + sizeof(bool) &&
                   QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 2 <=
                       offsetof(JSRuntime, normalize_u),
               "generic mode consumes independent original module padding");
_Static_assert(QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 2 >=
                       offsetof(JSRuntime, module_normalize_has_attr) + sizeof(bool) &&
                   QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 3 <=
                       offsetof(JSRuntime, normalize_u),
               "generic window mode consumes a separate original padding byte");
_Static_assert(offsetof(JSObject, u.cfunc.magic) == QJS_ABI_OFF_JSObject_u_cfunc_magic &&
                   JS_TAG_EXCEPTION == 6 && JS_TAG_UNDEFINED == 3 &&
                   sizeof(JSValue) == QJS_ABI_SIZE_JSValue,
               "generic/magic native result and parameter ABI");
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
_Static_assert(offsetof(JSFrameRegisterState, direct_host_generic) == 2392 &&
                   offsetof(JSFrameRegisterState, direct_host_magic) == 2400,
               "generic diagnostic counter offsets");
#endif

/* The generic guard reads these adjacent one-byte fields as a Win64 word. */
_Static_assert(JS_CFUNC_generic == 0 && JS_CFUNC_generic_magic == 1 &&
                   offsetof(JSObject, u.cfunc.length) == QJS_ABI_OFF_JSObject_u_cfunc_length &&
                   offsetof(JSObject, u.cfunc.cproto) == QJS_ABI_OFF_JSObject_u_cfunc_cproto &&
                   sizeof(((JSObject *)0)->u.cfunc.length) == 1 &&
                   sizeof(((JSObject *)0)->u.cfunc.cproto) == 1,
               "zero-formal/zero-actual generic native guard ABI");
