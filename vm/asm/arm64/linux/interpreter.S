/* Experimental Linux/AAPCS64 register executor, MIT.
* x19 state, x20 opcode PC, x21 operand SP, x22 frame, x23 locals,
* x24 arguments, x25 relative dispatch table. All C calls use AAPCS64.
* Instructions commit PC/SP only after every fast-path guard succeeds.
* Prepared JS calls/guarded returns stay in this activation. Allocation,
* finalizers and unprepared boundaries retain the source-derived C owner.
*/
#include "interpreter-aarch64-values.h"
#include "src/arm64/linux/interpreter-policy.h"
#if !defined(__aarch64__) || !defined(__linux__)
#error Linux AArch64 required
#endif
#if defined(__ARM_FEATURE_BTI_DEFAULT) || defined(__ARM_FEATURE_PAC_DEFAULT)
#error BTI/PAC register executor is not qualified yet
#endif
.text
// Keep the entry and its internal dispatch layout on a 64-byte instruction line
// boundary, independent of the size of the C code linked before this object.
.p2align 6
.global JS_FrameInterp
.hidden JS_FrameInterp
.type JS_FrameInterp,%function
#ifdef QJS_AARCH64_VM_INSTRUMENT
#define ARM_VM_POLICY_OFF 128
#else
#define ARM_VM_POLICY_OFF 96
#endif
#define ARM_VM_SAVE_BYTES (ARM_VM_POLICY_OFF+16)
JS_FrameInterp:
.cfi_startproc
    stp x29, x30, [sp, #-ARM_VM_SAVE_BYTES]!
.cfi_def_cfa_offset ARM_VM_SAVE_BYTES
.cfi_offset 29, -ARM_VM_SAVE_BYTES
.cfi_offset 30, -(ARM_VM_SAVE_BYTES-8)
    mov x29, sp
    stp x19, x20, [sp, #16]
    stp x21, x22, [sp, #32]
    stp x23, x24, [sp, #48]
    stp x25, x26, [sp, #64]
    stp x27, x28, [sp, #80]
.cfi_offset 19, -(ARM_VM_SAVE_BYTES-16)
.cfi_offset 20, -(ARM_VM_SAVE_BYTES-24)
.cfi_offset 21, -(ARM_VM_SAVE_BYTES-32)
.cfi_offset 22, -(ARM_VM_SAVE_BYTES-40)
.cfi_offset 23, -(ARM_VM_SAVE_BYTES-48)
.cfi_offset 24, -(ARM_VM_SAVE_BYTES-56)
.cfi_offset 25, -(ARM_VM_SAVE_BYTES-64)
.cfi_offset 26, -(ARM_VM_SAVE_BYTES-72)
.cfi_offset 27, -(ARM_VM_SAVE_BYTES-80)
.cfi_offset 28, -(ARM_VM_SAVE_BYTES-88)
    mov x19, x0
#ifdef QJS_AARCH64_SCALAR_OPS
    bl qjs_aarch64_vm_scalar_policy
#else
    bl qjs_aarch64_vm_policy
#endif
    str w0, [sp, #ARM_VM_POLICY_OFF]
    adrp x25, .Ldispatch_table
    add x25, x25, :lo12:.Ldispatch_table
    tbz w0, #9, .Lpublication_selected
    adrp x25, qjs_aarch64_publish_clean
    add x25, x25, :lo12:qjs_aarch64_publish_clean
.Lpublication_selected:
    mov x26, #0
    mov x27, #0
    mov x28, #0
#ifdef QJS_AARCH64_VM_INSTRUMENT
    stp xzr, xzr, [sp, #96]
    stp xzr, xzr, [sp, #112]
    str xzr, [sp, #(ARM_VM_POLICY_OFF+8)]
#endif
.Lreload:
.macro ARM_DISPATCH_NEXT native_ops
    add x26, x26, #\native_ops
    ldrb w9, [x20]
    ldrsw x10, [x25, x9, lsl #2]
    add x10, x25, x10
    br x10
.endm
    ldr x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]
    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]
.Ldispatch:
    ldrb w9, [x20]
    ldrsw x10, [x25, x9, lsl #2]
    add x10, x25, x10
    br x10
.Lfast:
    add x26, x26, #1
    b .Ldispatch
.Lslow:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameInterpSlow
    cbz w0, .Lreload
.Ldone:
#ifdef QJS_AARCH64_VM_INSTRUMENT
// One observation per activation; no change to the interpreter state ABI.
    mov x1, x26
    mov x2, x27
    mov x3, sp
    mov x0, x19
    ldp x4, x5, [sp, #96]
    ldp x6, x7, [sp, #112]
    bl qjs_aarch64_vm_completed
    ldr x0, [sp, #(ARM_VM_POLICY_OFF+8)]
    bl qjs_aarch64_vm_window_observe
#endif
    mov w0, #1
.cfi_remember_state
    ldp x19, x20, [sp, #16]
    ldp x21, x22, [sp, #32]
    ldp x23, x24, [sp, #48]
    ldp x25, x26, [sp, #64]
    ldp x27, x28, [sp, #80]
.cfi_restore 19
.cfi_restore 20
.cfi_restore 21
.cfi_restore 22
.cfi_restore 23
.cfi_restore 24
.cfi_restore 25
.cfi_restore 26
.cfi_restore 27
.cfi_restore 28
    ldp x29, x30, [sp], #ARM_VM_SAVE_BYTES
.cfi_restore 29
.cfi_restore 30
.cfi_def_cfa_offset 0
    ret
.cfi_restore_state

#include "asm/arm64/common/register-ops.inc"
#include "asm/arm64/common/register-slots.inc"
#include "asm/arm64/common/register-reference-stores.inc"
#include "asm/arm64/common/register-references.inc"
#include "asm/arm64/common/register-global-bindings.inc"
#include "asm/arm64/common/register-comparisons.inc"
#include "asm/arm64/common/register-branch.inc"
#include "asm/arm64/common/register-numeric.inc"
#include "asm/arm64/common/register-forwarding.inc"
#include "asm/arm64/common/register-iterators.inc"
#include "asm/arm64/common/register-call.inc"
#include "asm/arm64/common/register-constructors.inc"
#include "asm/arm64/common/register-regexp.inc"
#include "asm/arm64/common/register-null-proto.inc"
#include "asm/arm64/common/register-arguments.inc"
#include "asm/arm64/common/register-varargs.inc"
#include "asm/arm64/common/register-indexed.inc"
#include "asm/arm64/common/register-literals.inc"
#include "asm/arm64/common/register-bigint.inc"
#include "asm/arm64/common/register-strings.inc"
#include "asm/arm64/common/register-string-append.inc"
#include "asm/arm64/common/register-stack-insert.inc"
#include "asm/arm64/common/register-host-return.inc"
#include "asm/arm64/common/register-property-ic.inc"
#include "asm/arm64/common/register-property-primitives.inc"
#include "asm/arm64/common/register-property-hints.inc"
#include "asm/arm64/common/register-property-prototypes.inc"
#include "asm/arm64/common/register-scalar-ops.inc"
#include "interpreter-aarch64-publication.inc"
.cfi_endproc
.size JS_FrameInterp, .-JS_FrameInterp
.global qjs_aarch64_vm_end
.hidden qjs_aarch64_vm_end
qjs_aarch64_vm_end:

// CALLed leaf proxies preserve x0..x8 and tail-enter the typed C boundary.
#include "interpreter-aarch64-publication-proxies.inc"

// Relative offsets require no executable-memory or absolute table relocation.
.section .rodata.qjs_aarch64_dispatch,"a",%progbits
.p2align 2
.global qjs_aarch64_publish_original
.hidden qjs_aarch64_publish_original
.type qjs_aarch64_publish_original,%object
qjs_aarch64_publish_original:
.Ldispatch_table:
#include "interpreter-aarch64-dispatch.inc"
.size qjs_aarch64_publish_original, .-qjs_aarch64_publish_original
#include "interpreter-aarch64-publication-tables.inc"
.section .note.GNU-stack,"",%progbits
