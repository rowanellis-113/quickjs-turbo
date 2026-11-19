/* AAPCS64 bool(ctx=x0,object=x1,uint32 index=w2,result=x3).
* Ordinary shape-backed array own-data leaf; every miss tail-calls the exact
* typed original helper with all four arguments intact. MIT.
*/
#include "interpreter-aarch64-values.h"
#if ARM_HAS_ARRAY_OWN
.macro ARRAY_OWN_COUNT offset
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_array_own_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_array_own_counters
    ldr x15, [x14, #\offset]
    add x15, x15, #1
    str x15, [x14, #\offset]
#endif
.endm
.section .text.qjs_arm_array_own,"ax",%progbits
.p2align 2
.global JS_AArch64FastArrayOwnGet
.hidden JS_AArch64FastArrayOwnGet, JS_AArch64FastArrayOwnFallback
.type JS_AArch64FastArrayOwnGet,%function
JS_AArch64FastArrayOwnGet:
.cfi_startproc
    ARRAY_OWN_COUNT 0
    ldrh w4, [x1, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Larray_own_fallback
    ldrb w4, [x1, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w4, #ARM_BIT_JSObject_fast_array_MASK
    b.ne .Larray_own_fallback
    tbnz w2, #31, .Larray_own_fallback
    ldr x4, [x1, #ARM_OFF_JSObject_shape]
    ldr w5, [x4, #ARM_OFF_JSShape_prop_hash_mask]
    and w5, w2, w5
    neg x5, x5
    sub x6, x4, #4
    ldr w5, [x6, x5, lsl #2]
    add x4, x4, #ARM_OFF_JSShape_prop
    orr w6, w2, #0x80000000
.Larray_own_probe:
    cbz w5, .Larray_own_fallback
    add x7, x4, w5, uxtw #3
    ldur w8, [x7, #-4]
    cmp w8, w6
    b.eq .Larray_own_found
    ldur w5, [x7, #-8]
    and w5, w5, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Larray_own_probe
.Larray_own_found:
    ldur w8, [x7, #-8]
    tst w8, #ARM_PROPERTY_DESC_TMASK
    b.ne .Larray_own_fallback
    sub w5, w5, #1
    ldr x7, [x1, #ARM_OFF_JSObject_prop]
    add x7, x7, w5, uxtw #4
    ldp x4, x5, [x7]
    tbz w5, #31, .Larray_own_value
    ldr w6, [x4, #ARM_REF_COUNT_OFFSET]
    add w6, w6, #1
    str w6, [x4, #ARM_REF_COUNT_OFFSET]
.Larray_own_value:
    stp x4, x5, [x3]
    ARRAY_OWN_COUNT 8
    mov w0, #1
    ret
.Larray_own_fallback:
    ARRAY_OWN_COUNT 16
    b JS_AArch64FastArrayOwnFallback
.cfi_endproc
.size JS_AArch64FastArrayOwnGet,.-JS_AArch64FastArrayOwnGet
#endif
.section .note.GNU-stack,"",%progbits
