/* Accepted single-wrapper owned/readonly/missing constructors,AAPCS64. MIT.
* Private typed continuation:x0state,x1targetBC,x2originalargv,w3nativeargc.
* No nested call,SP change orcallee-saved register use. Caller reserves32bytes:
* [sp0argv,sp8argc,sp16regularbytes,sp24target]. All misses precede commitment.
*/
#include "interpreter-aarch64-values.h"
#if ARM_HAS_FORWARDING
.section .text.qjs_arm_forward_owned,"ax",%progbits
.p2align 2

/* mode0 owns the complete prefix;mode1 borrows provided;mode2 pads onlymissing.
* Every fixed offset comes from the actual compiler's ARM contract.
*/
.macro FORWARD_CHILD mode
    str x2, [sp]
    str x3, [sp, #8]
    str x1, [sp, #24]
.if \mode == 0
    subs w4, w3, #1
    csel w4, w4, wzr, hs
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w4, w5
    csel w4, w4, w5, hs
.else
    mov w4, #0
.endif
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    add w4, w4, w5
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    add w4, w4, w5
    lsl x4, x4, #4
    add x4, x4, #ARM_FRAME_HEADER_BYTES
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    lsl x5, x5, #3
    add x5, x5, #15
    and x5, x5, #-16
    add x4, x4, x5
    str x4, [sp, #16]
    add x5, x4, #80
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x7, [x6, #ARM_OFF_JSFrameSegment_capacity]
    ldr x6, [x6, #ARM_OFF_JSFrameSegment_used]
    sub x7, x7, x6
    cmp x5, x7
    b.hi .Lff_C_\@
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x5, x5, x6
    b.cs .Lff_C_\@
    mov x6, #5280
    adds x5, x5, x6
    b.cs .Lff_C_\@
    mov x6, sp
    subs x6, x6, x5
    b.lo .Lff_C_\@
    ldr x7, [x0, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cmp x6, x7
    b.lo .Lff_C_\@
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x6, [x6, #ARM_OFF_JSFrame_bytecode]
    ldr x6, [x6, #ARM_OFF_JSFunctionBytecode_realm]
    ldur x7, [x2, #-16]
    ldr x7, [x7, #ARM_OFF_JSObject_u_cfunc_realm]
    ldr w10, [x6, #ARM_OFF_JSContext_interrupt_counter]
    cmp x6, x7
    b.ne .Lff_two_realms_\@
    cmp w10, #2
    b.le .Lff_C_\@
    b .Lff_commit_\@
.Lff_two_realms_\@:
    cmp w10, #1
    b.le .Lff_C_\@
    ldr w11, [x7, #ARM_OFF_JSContext_interrupt_counter]
    cmp w11, #1
    b.le .Lff_C_\@
.Lff_commit_\@:
// No observer,allocation,failure or fallback until complete publication.
    sub w10, w10, #1
    str w10, [x6, #ARM_OFF_JSContext_interrupt_counter]
    ldr w10, [x7, #ARM_OFF_JSContext_interrupt_counter]
    sub w10, w10, #1
    str w10, [x7, #ARM_OFF_JSContext_interrupt_counter]
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x8, [x6, #ARM_OFF_JSFrameSegment_data]
    ldr x7, [x6, #ARM_OFF_JSFrameSegment_used]
    add x8, x8, x7
    ldp x12, x13, [x2, #-32]
    stp x12, x13, [x8, #ARM_OFF_JSStackFrame_cur_func]
    str x1, [x8, #ARM_OFF_JSFrame_bytecode]
    str x6, [x8, #ARM_OFF_JSFrame_segment]
    ldr x4, [sp, #16]
    str w4, [x8, #ARM_OFF_JSFrame_frame_bytes]
    add x6, x8, x4
    str x6, [x8, #ARM_OFF_JSStackFrame_prev_frame]
.if \mode == 2
    ldrh w9, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
.else
    subs w9, w3, #1
    csel w9, w9, wzr, hs
.if \mode == 0
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w9, w10
    csel w9, w9, w10, hs
.endif
.endif
    strh w9, [x8, #ARM_OFF_JSStackFrame_arg_count]
    strh wzr, [x8, #ARM_OFF_JSFrame_pending]
    add x11, x8, #ARM_FRAME_HEADER_BYTES
.if \mode == 0
    strh w9, [x8, #ARM_OFF_JSFrame_owned_args]
    str x11, [x8, #ARM_OFF_JSStackFrame_arg_buf]
    add x11, x11, x9, lsl #4
.else
    strh wzr, [x8, #ARM_OFF_JSFrame_owned_args]
    add x10, x2, #16
    str x10, [x8, #ARM_OFF_JSStackFrame_arg_buf]
.endif
    str x11, [x8, #ARM_OFF_JSStackFrame_var_buf]
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    add x11, x11, x10, lsl #4
    str x11, [x8, #ARM_OFF_JSStackFrame_cur_sp]
    str x11, [x8, #ARM_OFF_JSFrame_saved_sp]
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    strh w10, [x8, #ARM_OFF_JSStackFrame_var_ref_count]
    str xzr, [x8, #ARM_OFF_JSStackFrame_var_refs]
    cbz w10, .Lff_refs_done_\@
    ldrh w12, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x11, x11, x12, lsl #4
    str x11, [x8, #ARM_OFF_JSStackFrame_var_refs]
.Lff_zero_refs_\@:
    str xzr, [x11], #ARM_VAR_REF_POINTER_BYTES
    subs w10, w10, #1
    b.ne .Lff_zero_refs_\@
.Lff_refs_done_\@:
    str xzr, [x8, #ARM_OFF_JSStackFrame_cur_pc]
    str xzr, [x8, #(ARM_OFF_JSFrame_bytecode-8)]
    ldrb w10, [x1, #ARM_STRICT_BYTE]
    and w10, w10, #ARM_STRICT_MASK
    lsr w10, w10, #ARM_STRICT_SHIFT
    strb w10, [x8, #ARM_OFF_JSStackFrame_is_strict_mode]
    strb wzr, [x8, #61]
    mov w10, #2
    strh w10, [x8, #ARM_FRAME_ROOT_OFFSET]
    cbz w3, .Lff_undefined_this_\@
    ldp x12, x13, [x2]
    b .Lff_this_done_\@
.Lff_undefined_this_\@:
    mov x12, #0
    mov x13, #ARM_CONST_JS_TAG_UNDEFINED
.Lff_this_done_\@:
    stp x12, x13, [x8, #ARM_OFF_JSFrame_this_value]
.if \mode == 0
    ldr x9, [x8, #ARM_OFF_JSStackFrame_arg_buf]
    subs w16, w3, #1
    csel w16, w16, wzr, hs
    add x10, x2, #16
    cbz w16, .Lff_pad_start_\@
.Lff_copy_args_\@:
    ldp x12, x13, [x10], #16
    stp x12, x13, [x9], #16
    mov w14, #-9
    cmp w13, w14
    b.lo .Lff_no_dup_\@
    ldur w14, [x12, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    stur w14, [x12, #ARM_REF_COUNT_OFFSET]
.Lff_no_dup_\@:
    subs w16, w16, #1
    b.ne .Lff_copy_args_\@
.Lff_pad_start_\@:
    ldr x10, [x8, #ARM_OFF_JSStackFrame_var_buf]
.elseif \mode == 2
    subs w16, w3, #1
    csel w16, w16, wzr, hs
    ldr x9, [x8, #ARM_OFF_JSStackFrame_arg_buf]
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    add x10, x9, x10, lsl #4
    add x9, x9, x16, lsl #4
.endif
.if \mode != 1
    mov x11, #ARM_CONST_JS_TAG_UNDEFINED
    cmp x9, x10
    b.eq .Lff_args_done_\@
.Lff_pad_args_\@:
    stp xzr, x11, [x9], #16
    cmp x9, x10
    b.lo .Lff_pad_args_\@
.Lff_args_done_\@:
.endif
    ldr x9, [x8, #ARM_OFF_JSStackFrame_var_buf]
    ldr x10, [x8, #ARM_OFF_JSFrame_saved_sp]
    mov x11, #ARM_CONST_JS_TAG_UNDEFINED
    cmp x9, x10
    b.eq .Lff_vars_done_\@
.Lff_zero_vars_\@:
    stp xzr, x11, [x9], #16
    cmp x9, x10
    b.lo .Lff_zero_vars_\@
.Lff_vars_done_\@:
    ldr x2, [sp]
    ldr w3, [sp, #8]
    ldr x4, [sp, #16]
    add x6, x8, x4
    ldr x7, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    str x7, [x6, #ARM_OFF_JSStackFrame_prev_frame]
    ldp x12, x13, [x2, #-16]
    stp x12, x13, [x6, #ARM_OFF_JSStackFrame_cur_func]
    mov x9, x2
    cbnz w3, .Lff_logical_argc_\@
    add x9, x8, #ARM_OFF_JSFrame_this_value
    mov w3, #1
.Lff_logical_argc_\@:
    str x9, [x6, #ARM_OFF_JSStackFrame_arg_buf]
    strh w3, [x6, #ARM_OFF_JSStackFrame_arg_count]
    strh wzr, [x6, #ARM_OFF_JSStackFrame_var_ref_count]
    strh wzr, [x6, #ARM_OFF_JSStackFrame_is_strict_mode]
    mov w10, #50944
    strh w10, [x6, #ARM_FRAME_ROOT_OFFSET]
    str xzr, [x6, #ARM_OFF_JSStackFrame_var_buf]
    str xzr, [x6, #ARM_OFF_JSStackFrame_var_refs]
    str xzr, [x6, #ARM_OFF_JSStackFrame_cur_pc]
    str xzr, [x6, #ARM_OFF_JSStackFrame_cur_sp]
    str xzr, [x6, #72]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    str x9, [x7, #ARM_OFF_JSStackFrame_cur_sp]
    str x9, [x7, #ARM_OFF_JSFrame_saved_sp]
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldr w3, [sp, #8]
    add w9, w3, #2
    ldrb w11, [x10]
    cmp w11, #ARM_OP_tail_call_method
    b.ne .Lff_parent_not_tail_\@
    orr w9, w9, #0x8000
.Lff_parent_not_tail_\@:
    strh w9, [x7, #ARM_OFF_JSFrame_pending]
    add x10, x10, #3
    str x10, [x7, #ARM_OFF_JSStackFrame_cur_pc]
    add x4, x4, #80
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x10, [x9, #ARM_OFF_JSFrameSegment_used]
    add x10, x10, x4
    str x10, [x9, #ARM_OFF_JSFrameSegment_used]
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x10, x10, x4
    str x10, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    str x8, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x1, [sp, #24]
    ldr x10, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    str x10, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x10, [x8, #ARM_OFF_JSFrame_saved_sp]
    str x10, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_rt]
    str x8, [x10, #ARM_OFF_JSRuntime_current_stack_frame]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_forward_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_forward_counters
    ldr x15, [x14, #(40+8*\mode)]
    add x15, x15, #1
    str x15, [x14, #(40+8*\mode)]
#endif
    mov w0, #1
    ret
.Lff_C_\@:
    b JS_FrameVarargsForwardTry
.endm

.global JS_AArch64ForwardOwnedTry,JS_AArch64ForwardOwnedGeneral,JS_AArch64ForwardOwnedCopy
.hidden JS_AArch64ForwardOwnedTry,JS_AArch64ForwardOwnedGeneral,JS_AArch64ForwardOwnedCopy
.hidden JS_FrameVarargsForwardTry,JS_FrameCallForwardOwnedCold
.type JS_AArch64ForwardOwnedTry,%function
JS_AArch64ForwardOwnedTry:
.cfi_startproc
    ldr w4, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w4, #4
    b.hi JS_AArch64ForwardOwnedGeneral
    ldrh w4, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    cbnz w4, JS_AArch64ForwardOwnedGeneral
    ldrh w4, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    orr w4, w4, w5
    cbnz w4, JS_AArch64ForwardOwnedGeneral
    ldrh w4, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    cmp w4, #2
    b.hi JS_AArch64ForwardOwnedGeneral
// Compact single-wrapper descriptors share the original prepared executor.
    b JS_AArch64CallPrepareOne
JS_AArch64ForwardOwnedGeneral:
    adrp x4, JS_FrameCallForwardOwnedControl
    ldrb w4, [x4, :lo12:JS_FrameCallForwardOwnedControl]
    cmp w4, #1
    b.eq .Lff_owned_enabled
    cmp w4, #2
    b.eq .Lff_owned_C
    b JS_FrameCallForwardOwnedCold
.Lff_owned_enabled:
    ldrb w4, [x1, #ARM_FRAME_KIND_OFFSET]
    tbnz w4, #1, .Lff_owned_borrow
JS_AArch64ForwardOwnedCopy:
    FORWARD_CHILD 0
.Lff_owned_borrow:
    b JS_AArch64ForwardBorrowTry
.Lff_owned_C:
    b JS_FrameVarargsForwardTry
.cfi_endproc
.size JS_AArch64ForwardOwnedTry,.-JS_AArch64ForwardOwnedTry

.p2align 2
.global JS_AArch64ForwardBorrowTry
.hidden JS_AArch64ForwardBorrowTry
.type JS_AArch64ForwardBorrowTry,%function
JS_AArch64ForwardBorrowTry:
.cfi_startproc
    adrp x4, JS_FrameCallForwardBorrowControl
    ldrb w4, [x4, :lo12:JS_FrameCallForwardBorrowControl]
    cmp w4, #1
    b.eq .Lff_borrow_enabled
    cmp w4, #2
    b.eq .Lff_borrow_copy
    b JS_FrameCallForwardOwnedCold
.Lff_borrow_enabled:
    cmp w3, #1
    b.lo .Lff_borrow_missing
    sub w4, w3, #1
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w4, w5
    b.lo .Lff_borrow_missing
    FORWARD_CHILD 1
.Lff_borrow_copy:
    b JS_AArch64ForwardOwnedCopy
.Lff_borrow_missing:
    b JS_AArch64ForwardBorrowMissingTry
.cfi_endproc
.size JS_AArch64ForwardBorrowTry,.-JS_AArch64ForwardBorrowTry

.p2align 2
.global JS_AArch64ForwardBorrowMissingTry
.hidden JS_AArch64ForwardBorrowMissingTry
.type JS_AArch64ForwardBorrowMissingTry,%function
JS_AArch64ForwardBorrowMissingTry:
.cfi_startproc
    adrp x4, JS_FrameCallForwardBorrowMissingControl
    ldrb w4, [x4, :lo12:JS_FrameCallForwardBorrowMissingControl]
    cmp w4, #1
    b.eq .Lff_missing_enabled
    cmp w4, #2
    b.eq .Lff_missing_copy
    b JS_FrameCallForwardOwnedCold
.Lff_missing_enabled:
    subs w4, w3, #1
    csel w4, w4, wzr, hs
    ldrh w5, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w4, w5
    b.hs .Lff_missing_copy
    add x5, x2, x5, lsl #4
    add x5, x5, #16
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x7, [x6, #ARM_OFF_JSFrame_bytecode]
    ldrh w9, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    ldr x10, [x6, #ARM_OFF_JSStackFrame_var_buf]
    add x10, x10, x9, lsl #4
    ldrh w9, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x10, x10, x9, lsl #4
    cmp x5, x10
    b.hi .Lff_missing_copy
    ldr w9, [x6, #ARM_OFF_JSFrame_frame_bytes]
    add x10, x6, x9
    cmp x5, x10
    b.hi .Lff_missing_copy
    FORWARD_CHILD 2
.Lff_missing_copy:
    b JS_AArch64ForwardOwnedCopy
.cfi_endproc
.size JS_AArch64ForwardBorrowMissingTry,.-JS_AArch64ForwardBorrowMissingTry
.purgem FORWARD_CHILD
#endif
.section .note.GNU-stack,"",%progbits
