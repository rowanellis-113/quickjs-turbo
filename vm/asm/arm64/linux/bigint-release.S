/* Standard AAPCS64 void(ctx=x0,JSValue={x1,x2});no private clone ABI. MIT. */
#include "interpreter-aarch64-values.h"
#if ARM_HAS_NUMERIC_WORKERS
.macro ARM_BIG_RELEASE_COUNT offset
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_numeric_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_numeric_counters
    ldr x13, [x12, #\offset]
    add x13, x13, #1
    str x13, [x12, #\offset]
#endif
.endm
.section .text.qjs_arm_bigint_release,"ax",%progbits
.p2align 2
.global JS_FrameBigIntRelease
.hidden JS_FrameBigIntRelease,JS_FrameBigIntReleaseControl,JS_FrameBigIntReleaseSlow
.type JS_FrameBigIntRelease,%function
JS_FrameBigIntRelease:
.cfi_startproc
    adrp x9, JS_FrameBigIntReleaseControl
    ldrb w9, [x9, :lo12:JS_FrameBigIntReleaseControl]
    cmp w9, #1
    b.ne .Lbig_release_control
    mov x10, #ARM_CONST_JS_TAG_BIG_INT
    cmp x2, x10
    b.ne .Lbig_release_generic
    ldur w10, [x1, #ARM_REF_COUNT_OFFSET]
    cmp w10, #0
    b.le .Lbig_release_generic
    sub w10, w10, #1
    stur w10, [x1, #ARM_REF_COUNT_OFFSET]
    cbnz w10, .Lbig_release_return
    ARM_BIG_RELEASE_COUNT 8
    ldr x0, [x0, #ARM_OFF_JSContext_rt]
    b js_free_rt
.Lbig_release_return:
    ARM_BIG_RELEASE_COUNT 0
    ret
.Lbig_release_generic:
    ARM_BIG_RELEASE_COUNT 16
    b JS_FreeValue
.Lbig_release_control:
    cbnz w9, .Lbig_release_generic
    ARM_BIG_RELEASE_COUNT 24
    b JS_FrameBigIntReleaseSlow
.cfi_endproc
.size JS_FrameBigIntRelease,.-JS_FrameBigIntRelease
.section .rodata.qjs_arm_add_local,"a",%progbits
.global JS_FrameAddLocalDisable
.hidden JS_FrameAddLocalDisable
.type JS_FrameAddLocalDisable,%object
JS_FrameAddLocalDisable:
.asciz "QJS_DISABLE_NATIVE_ADD_LOCAL"
.size JS_FrameAddLocalDisable,.-JS_FrameAddLocalDisable
#endif
.section .note.GNU-stack,"",%progbits
