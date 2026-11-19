/* Actual AAPCS64 int(ctx=x0,sp=x1,is_neq=w2),pure nonlast identity. MIT. */
#include "interpreter-aarch64-values.h"
#if ARM_HAS_COMPARISONS
.section .text.qjs_arm_comparison_leaf,"ax",%progbits
.p2align 2
.global JS_LinuxStrictIdentityLeaf
.hidden JS_LinuxStrictIdentityLeaf
.type JS_LinuxStrictIdentityLeaf,%function
JS_LinuxStrictIdentityLeaf:
.cfi_startproc
    ldp x3, x4, [x1, #-32]
    ldp x5, x6, [x1, #-16]
    cmp x4, x6
    b.ne .Lidentity_fallback
    cmp x4, #ARM_CONST_JS_TAG_SYMBOL
    b.eq .Lidentity_reference
    cmp x4, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lidentity_fallback
.Lidentity_reference:
    ldr w4, [x3, #ARM_REF_COUNT_OFFSET]
    cmp x3, x5
    b.ne .Lidentity_distinct
    cmp w4, #2
    b.le .Lidentity_fallback
    mov w7, #1
    b .Lidentity_release
.Lidentity_distinct:
    cmp w4, #1
    b.le .Lidentity_fallback
    ldr w6, [x5, #ARM_REF_COUNT_OFFSET]
    cmp w6, #1
    b.le .Lidentity_fallback
    mov w7, #0
.Lidentity_release:
    sub w4, w4, #1
    str w4, [x3, #ARM_REF_COUNT_OFFSET]
    ldr w6, [x5, #ARM_REF_COUNT_OFFSET]
    sub w6, w6, #1
    str w6, [x5, #ARM_REF_COUNT_OFFSET]
    and w2, w2, #1
    eor w7, w7, w2
    mov x6, #ARM_CONST_JS_TAG_BOOL
    stp x7, x6, [x1, #-32]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_compare_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_compare_counters
    ldr x15, [x14, #112]
    add x15, x15, #1
    str x15, [x14, #112]
#endif
    mov w0, #0
    ret
.Lidentity_fallback:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_compare_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_compare_counters
    ldr x15, [x14, #120]
    add x15, x15, #1
    str x15, [x14, #120]
#endif
    b JS_LinuxStrictIdentityFallback
.cfi_endproc
.size JS_LinuxStrictIdentityLeaf,.-JS_LinuxStrictIdentityLeaf
#endif
.section .note.GNU-stack,"",%progbits
