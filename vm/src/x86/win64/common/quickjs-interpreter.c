/* Experimental explicit-frame executor, isolated from the legacy core. */
#include "quickjs-interpreter-private.h"

/* The adapter preserves the original public API under this name. Keeping the
 * fallback here preserves its compiler specialization and linker reachability. */
extern JSValue JS_LegacyCall(JSContext *ctx, JSValueConst func_obj, JSValueConst this_obj, int argc,
                             JSValueConst *argv);
#include "src/common/call/quickjs-interpreter-loop.inc"
#include "src/common/call/quickjs-interpreter-shared.inc"

#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
/* The leaf gateway uses existing private fields and one zeroed padding byte.
 * It creates no frame, changes no quota and tails the original C interpreter. */
_Static_assert(
    JS_CLASS_C_FUNCTION == 12 &&
        offsetof(JSStackFrame, cur_func) == QJS_ABI_OFF_JSStackFrame_cur_func &&
        offsetof(JSFunctionBytecode, byte_code_len) ==
            QJS_ABI_OFF_JSFunctionBytecode_byte_code_len &&
        offsetof(JSFunctionBytecode, var_count) == QJS_ABI_OFF_JSFunctionBytecode_var_count &&
        offsetof(JSFunctionBytecode, stack_size) == QJS_ABI_OFF_JSFunctionBytecode_stack_size &&
        offsetof(JSFunctionBytecode, var_ref_count) == QJS_ABI_OFF_JSFunctionBytecode_var_ref_count,
    "legacy C to small JS gateway fields");
_Static_assert(offsetof(JSRuntime, module_normalize_has_attr) ==
                       QJS_ABI_OFF_JSRuntime_module_normalize_has_attr &&
                   offsetof(JSRuntime, normalize_u) == QJS_ABI_OFF_JSRuntime_normalize_u,
               "legacy child mode at1348 is original runtime padding");
_Static_assert(offsetof(JSRuntime, module_normalize_has_attr) + sizeof(bool) <=
                       QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 5 &&
                   offsetof(JSRuntime, normalize_u) >
                       QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 5,
               "native slot store mode at1349 is original runtime padding");
_Static_assert(JS_TAG_STRING == -7 && JS_TAG_STRING_ROPE == -6 && JS_TAG_OBJECT == -1 &&
                   JS_TAG_EXCEPTION == 6 &&
                   offsetof(JSRuntime, normalize_u) >
                       QJS_ABI_OFF_JSRuntime_module_normalize_has_attr + 7,
               "primitive concat tags; add/zero modes at1350/1351 use padding");
_Static_assert(offsetof(JSRuntime, module_loader_has_attr) ==
                       QJS_ABI_OFF_JSRuntime_module_loader_has_attr &&
                   offsetof(JSRuntime, u) == QJS_ABI_OFF_JSRuntime_u &&
                   offsetof(JSVarRef, pvalue) == QJS_ABI_OFF_JSVarRef_pvalue &&
                   offsetof(JSVarRef, is_const) == QJS_ABI_OFF_JSVarRef_is_const &&
                   offsetof(JSObject, u.func.var_refs) == QJS_ABI_OFF_JSObject_u_func_var_refs,
               "pure child leaf mode at1361, live external integer slot fields");
_Static_assert(offsetof(JSFunctionBytecode, closure_var_count) ==
                   QJS_ABI_OFF_JSFunctionBytecode_closure_var_count,
               "external closure count is separate from the callee var-ref table");
#endif

#if defined(QJS_INTERP_FRAME_TAIL_ENTRY) || defined(QJS_INTERP_FRAME_INTERNAL_ENTRY)
/* Shared by the MASM and GAS entry. No argument, result or nonvolatile register
 * belongs to the selector: it returns BEFORE the selected entry executes. */
_Static_assert(offsetof(JSContext, rt) == QJS_ABI_OFF_JSContext_rt, "tail entry context offset");
_Static_assert(offsetof(JSRuntime, current_stack_frame) - 1 ==
                   QJS_ABI_OFF_JSRuntime_current_stack_frame - 1,
               "tail entry mode offset");
#if defined(_MSC_VER)
#define FRAME_ENTRY_CODE __declspec(code_seg(".text$zzqjsentry")) no_inline
#else
#define FRAME_ENTRY_CODE __attribute__((section(".text$zzqjsentry"), noipa))
#endif

FRAME_ENTRY_CODE int JS_FrameResolveCall(JSContext *ctx, const JSValue *func)
{
    if (unlikely(!FRAME_STATE(ctx->rt)))
        FRAME_STATE(ctx->rt) =
            !qjs_internal_interp_frame_disabled() && getenv("QJS_DISABLE_MIN_CALL_FRAME") == NULL
                ? 1
                : 2;
    if (FRAME_STATE(ctx->rt) != 1)
        return 0;
#ifdef ENABLE_DUMPS
    if (check_dump_flag(ctx->rt, JS_DUMP_BYTECODE_STEP))
        return 0;
#endif
    return js_frame_target(*func) != NULL;
}

#ifdef QJS_INTERP_FRAME_INTERNAL_ENTRY
FRAME_ENTRY_CODE int JS_FrameResolveInternal(JSContext *ctx, const JSValue *func)
{
    if (unlikely(!FRAME_INTERNAL_STATE(ctx->rt)))
        FRAME_INTERNAL_STATE(ctx->rt) = !qjs_internal_interp_internal_disabled() ? 1 : 2;
    if (FRAME_INTERNAL_STATE(ctx->rt) != 1)
        return 0;
    return JS_FrameResolveCall(ctx, func);
}

FRAME_ENTRY_CODE JSValue JS_FrameRunInternal(JSContext *ctx, JSValueConst func,
                                             JSValueConst this_obj, JSValueConst new_target,
                                             int argc, JSValueConst *argv, int flags)
{
#ifdef QJS_INTERP_FRAME_DIAGNOSTICS
    if (qjs_internal_interp_trace_enabled())
        fprintf(stderr, "ENTRY flags=%d argc=%d copy=%d\n", flags, argc,
                (flags & JS_CALL_FLAG_COPY_ARGV) != 0);
#endif
    return JS_FrameCallEntryDispatch(ctx, func, this_obj, new_target, argc, argv, flags);
}
#endif
#endif

#if defined(QJS_INTERP_FRAME_TAIL_ENTRY)
/* Identical ABI to public JS_Call, including the hidden 16-byte result buffer.
 * Keep the established C entry/selector stack shape on the positive path.
 * The assembly selector has already returned; no extra activation remains. */
JS_EXTERN JSValue JS_FrameRunCall(JSContext *ctx, JSValueConst func, JSValueConst this_obj,
                                  int argc, JSValueConst *argv)
{
    return JS_FrameCallEntryDispatch(ctx, func, this_obj, JS_UNDEFINED, argc, argv,
                                     JS_CALL_FLAG_COPY_ARGV);
}
#else
JS_EXTERN JSValue JS_Call(JSContext *ctx, JSValueConst func_obj, JSValueConst this_obj, int argc,
                          JSValueConst *argv)
{
    return JS_FrameCallEntryDispatch(ctx, func_obj, this_obj, JS_UNDEFINED, argc, argv,
                                     JS_CALL_FLAG_COPY_ARGV);
}
#endif
#undef FRAME_ENTRY_CODE
