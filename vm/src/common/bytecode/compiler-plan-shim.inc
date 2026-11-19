/* The core TU projects fields only; all analysis lives in a separate C TU. */
#include "src/common/bytecode/compiler-plan-view.h"
#if defined(_MSC_VER)
#define COMPILER_SHIM_CODE __declspec(noinline) __declspec(code_seg(".qjzzec$zzcompilerShim"))
#elif defined(_WIN32) && defined(__GNUC__)
#define COMPILER_SHIM_CODE __attribute__((noinline, section(".qjscmp$S")))
#else
#define COMPILER_SHIM_CODE __attribute__((noinline))
#endif
static COMPILER_SHIM_CODE void js_compiler_bytecode_plan(JSContext *ctx, JSFunctionDef *fd)
{
    if (!fd->vars || !fd->var_count || fd->func_kind || fd->is_derived_class_constructor ||
        !fd->byte_code.size || fd->byte_code.size > 196608 ||
        js_check_stack_overflow(ctx->rt, QJS_COMPILER_PLAN_STACK_RESERVE))
        return;
    uint64_t mask = 0;
    for (unsigned i = 0; i < fd->var_count && i < 64; i++)
        if (fd->vars[i].is_lexical && !fd->vars[i].is_captured)
            mask |= UINT64_C(1) << i;
    /* resolve_labels initializes these slots in its own prologue. They never
     * rely on the entry-undefined proof, including lexical argument bindings.
     */
    const int prologue[] = {
        fd->home_object_var_idx, fd->this_active_func_var_idx, fd->new_target_var_idx,
        fd->this_var_idx,        fd->arguments_var_idx,        fd->arguments_arg_idx,
        fd->func_var_idx,        fd->var_object_idx,           fd->arg_var_object_idx};
    for (unsigned i = 0; i < sizeof(prologue) / sizeof(prologue[0]); i++)
        if (prologue[i] >= 0 && prologue[i] < 64)
            mask &= ~(UINT64_C(1) << prologue[i]);
    if (!mask)
        return;
    uint8_t sizes[OP_TEMP_END], formats[OP_TEMP_END];
    for (unsigned i = 0; i < OP_TEMP_END; i++) {
        sizes[i] = opcode_info[i].size;
        formats[i] = opcode_info[i].fmt;
    }
    _Static_assert(sizeof(((LabelSlot *)0)->pos2) == sizeof(int32_t),
                   "compiler label position width");
    QJSCompilerCode view = {{fd->byte_code.buf, fd->byte_code.size},
                            fd->var_count,
                            fd->label_count,
                            mask,
                            fd->label_slots,
                            sizeof(*fd->label_slots),
                            offsetof(LabelSlot, pos2),
                            sizes,
                            formats,
                            OP_TEMP_END};
    JS_CompilerBytecodePlan(&view);
    fd->byte_code.size = view.byte_code.size;
}
#undef COMPILER_SHIM_CODE
