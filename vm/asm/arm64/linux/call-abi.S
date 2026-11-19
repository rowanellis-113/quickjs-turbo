/* Typed AAPCS64 C-call bridges. The register VM is not implemented here. */
#include "qjs-aarch64-abi-values.h"
#if !defined(__aarch64__) || !defined(__linux__) || !defined(__LP64__)
#error Linux AArch64 LP64 required
#endif
#if QJS_AARCH64_SIZE_JSValue != 16 || QJS_AARCH64_OFF_JSValue_tag != 8
#error Unsupported measured JSValue ABI
#endif
#if (defined(__ARM_FEATURE_BTI_DEFAULT) && __ARM_FEATURE_BTI_DEFAULT) || (defined(__ARM_FEATURE_PAC_DEFAULT) && __ARM_FEATURE_PAC_DEFAULT)
#error The current AArch64 foundation requires a baseline without BTI/PAC
#endif
#include "asm/arm64/common/call-frame.inc"
.text
.macro QJS_AARCH64_FRAME_SAVED
.cfi_def_cfa_offset 16
.cfi_offset 29, -16
.cfi_offset 30, -8
.endm
.macro QJS_AARCH64_FRAME_ESTABLISHED
.cfi_def_cfa_register 29
.endm
.macro QJS_AARCH64_FRAME_RESTORED
.cfi_restore 29
.cfi_restore 30
.cfi_def_cfa sp, 0
.endm
.macro QJS_FUNCTION_BEGIN name
.p2align 2
.global \name
.hidden \name
.type \name, %function
\name:
.cfi_startproc
    QJS_AARCH64_FRAME_ENTER
.endm
.macro QJS_FUNCTION_END name
    QJS_AARCH64_FRAME_LEAVE
.cfi_endproc
.global \name\()_end
.hidden \name\()_end
\name\()_end:
.size \name, .-\name
.endm

    QJS_FUNCTION_BEGIN qjs_aarch64_call_generic
    mov x9, x0
    mov x0, x1
    mov x1, x2
    mov x2, x3
    mov w3, w4
    mov x4, x5
    blr x9
    QJS_FUNCTION_END qjs_aarch64_call_generic

    QJS_FUNCTION_BEGIN qjs_aarch64_call_magic
    mov x9, x0
    mov x0, x1
    mov x1, x2
    mov x2, x3
    mov w3, w4
    mov x4, x5
    mov w5, w6
    blr x9
    QJS_FUNCTION_END qjs_aarch64_call_magic

    QJS_FUNCTION_BEGIN qjs_aarch64_call_data
    mov x9, x0
    mov x0, x1
    mov x1, x2
    mov x2, x3
    mov w3, w4
    mov x4, x5
    mov w5, w6
    mov x6, x7
    blr x9
    QJS_FUNCTION_END qjs_aarch64_call_data

    QJS_FUNCTION_BEGIN qjs_aarch64_call_double
    blr x0
    QJS_FUNCTION_END qjs_aarch64_call_double

/* Exact core-call type is generated and checked against JS_CallInternal.
    Adding the callback pointer spills incoming argc/argv/flags to the stack. */
.p2align 2
.global qjs_aarch64_call_internal
.hidden qjs_aarch64_call_internal
.type qjs_aarch64_call_internal, %function
qjs_aarch64_call_internal:
.cfi_startproc
    sub sp, sp, #32
.cfi_def_cfa_offset 32
    stp x29, x30, [sp, #16]
.cfi_offset 29, -16
.cfi_offset 30, -8
    add x29, sp, #16
.cfi_def_cfa 29, 16
    mov x9, x0
    ldr w10, [sp, #32]
    ldr x11, [sp, #40]
    ldr w12, [sp, #48]
    str x11, [sp]
    str x12, [sp, #8]
    mov x0, x1
    mov x1, x2
    mov x2, x3
    mov x3, x4
    mov x4, x5
    mov x5, x6
    mov x6, x7
    mov w7, w10
    blr x9
    ldp x29, x30, [sp, #16]
    add sp, sp, #32
.cfi_restore 29
.cfi_restore 30
.cfi_def_cfa sp, 0
    ret
.cfi_endproc
.global qjs_aarch64_call_internal_end
.hidden qjs_aarch64_call_internal_end
qjs_aarch64_call_internal_end:
.size qjs_aarch64_call_internal, .-qjs_aarch64_call_internal
.section .note.GNU-stack,"",%progbits
