/* Actual AAPCS64 int(state=x0),single-wrapper primitive native producer. MIT.
* x0..x17 volatile;no nested call,SP change or callee-saved use. The caller's
* separately reserved32 bytes are [sp,sp+32),not a shadow register home area.
* General owned/readonly/missing producers use measured private continuations.
* Prepared/deep producers retain the complete C normalizer until migrated.
*/
#include "interpreter-aarch64-values.h"
#if ARM_HAS_FORWARDING
.section .text.qjs_arm_forward,"ax",%progbits
.p2align 2
.global JS_AArch64ForwardProbe
.hidden JS_AArch64ForwardProbe,JS_FrameVarargsForwardTry,JS_FrameCallForwardNativeCold
.type JS_AArch64ForwardProbe,%function
JS_AArch64ForwardProbe:
.cfi_startproc
#if ARM_HAS_ARGUMENTS
// Source GNU argument .call filter,actual target constants. The complete
// C owner below retains logical wrappers,realm polls and rollback.
    adrp x9, JS_FrameArgumentsMode
    ldr w9, [x9, :lo12:JS_FrameArgumentsMode]
    tbnz w9, #1, .Lforward_original_probe
    tbnz w9, #8, .Lforward_original_probe
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldrb w10, [x9]
    cmp w10, #ARM_OP_call_method
    b.eq .Larguments_forward_method
    cmp w10, #ARM_OP_tail_call_method
    b.ne .Lforward_original_probe
.Larguments_forward_method:
    ldurh w3, [x9, #1]
    mov w11, #32765
    cmp w3, w11
    b.hi .Lforward_original_probe
    ldr x2, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    sub x2, x2, x3, lsl #4
    ldur x10, [x2, #-24]
    cmn x10, #1
    b.ne .Lforward_original_probe
    ldur x1, [x2, #-32]
    ldrh w10, [x1, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_BYTECODE_FUNCTION
    b.eq .Larguments_forward_js
    cmp w10, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lforward_original_probe
    ldr x10, [x1, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x11, qjs_aarch64_core_js_function_call
    add x11, x11, :lo12:qjs_aarch64_core_js_function_call
    cmp x10, x11
    b.ne .Lforward_original_probe
    ldrb w10, [x1, #ARM_OFF_JSObject_u_cfunc_cproto]
    cbnz w10, .Lforward_original_probe
    ldrh w10, [x1, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w10, .Lforward_original_probe
    ldrb w10, [x1, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w10, #1
    b.ne .Lforward_original_probe
    b .Larguments_forward_try
.Larguments_forward_js:
    ldr x1, [x1, #ARM_OFF_JSObject_u_func_function_bytecode]
    ldrb w10, [x1, #ARM_FRAME_KIND_OFFSET]
    tbnz w10, #0, .Lforward_original_probe
    cmp w10, #2
    b.ne .Larguments_forward_unknown
    ldrb w10, [x1, #(ARM_OFF_JSFunctionBytecode_pc2line_len+4)]
    cmp w10, #128
    b.eq .Larguments_forward_try
    cmp w10, #64
    b.eq .Lforward_original_probe
.Larguments_forward_unknown:
    ldr w10, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w10, #2
    b.lo .Larguments_forward_negative
    cmp w10, #2048
    b.hi .Larguments_forward_negative
    cmp w10, #17
    mov w11, #17
    csel w10, w10, w11, ls
    ldr x11, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    add x12, x11, x10
.Larguments_forward_prefix:
    cmp x11, x12
    b.hs .Larguments_forward_negative
    ldrb w10, [x11], #1
    cmp w10, #ARM_OP_push_this
    b.eq .Larguments_forward_store
    cmp w10, #ARM_OP_special_object
    b.ne .Larguments_forward_negative
    cmp x11, x12
    b.hs .Larguments_forward_negative
    ldrb w10, [x11], #1
    cmp w10, #1
    b.ls .Larguments_forward_try
    cmp w10, #4
    b.hi .Larguments_forward_negative
.Larguments_forward_store:
    cmp x11, x12
    b.hs .Larguments_forward_negative
    ldrb w10, [x11], #1
    cmp w10, #ARM_OP_put_loc8
    b.eq .Larguments_forward_local8
    sub w10, w10, #ARM_OP_put_loc0
    cmp w10, #3
    b.hi .Larguments_forward_negative
    b .Larguments_forward_prefix
.Larguments_forward_local8:
    add x11, x11, #1
    b .Larguments_forward_prefix
.Larguments_forward_negative:
    ldrb w10, [x1, #ARM_FRAME_KIND_OFFSET]
    cmp w10, #2
    b.ne .Lforward_original_probe
    mov w10, #64
    strb w10, [x1, #(ARM_OFF_JSFunctionBytecode_pc2line_len+4)]
    b .Lforward_original_probe
.Larguments_forward_try:
// AAPCS64 caller-owned lease,not a Win home area. The outer probe lease
// remains untouched for a declining original native/typed producer.
    stp x0, x30, [sp, #-16]!
.cfi_adjust_cfa_offset 16
.cfi_offset 30, -8
    bl JS_FrameArgumentsForwardTry
    ldp x9, x30, [sp], #16
.cfi_adjust_cfa_offset -16
.cfi_restore 30
    cbz w0, .Larguments_forward_original
    ret
.Larguments_forward_original:
    mov x0, x9
.Lforward_original_probe:
#endif
    adrp x9, JS_FrameCallForwardNativeControl
    ldrb w9, [x9, :lo12:JS_FrameCallForwardNativeControl]
    cmp w9, #1
    b.ne .Lforward_native_control
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x9, #ARM_OFF_JSFrame_bytecode]
    ldrb w9, [x9, #ARM_FORWARD_MODE_OFFSET]
    cmp w9, #1
    b.eq .Lforward_native_warm
    cmp w9, #5
    b.ne .Lforward_native_C
.Lforward_native_warm:
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldrb w10, [x9]
    cmp w10, #ARM_OP_call_method
    b.eq .Lforward_native_method
    cmp w10, #ARM_OP_tail_call_method
    b.ne .Lforward_native_C
.Lforward_native_method:
    ldurh w3, [x9, #1]
    mov w11, #32765
    cmp w3, w11
    b.hi .Lforward_native_C
    ldr x2, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    sub x2, x2, x3, lsl #4
    ldur x10, [x2, #-24]
    cmn x10, #1
    b.ne .Lforward_native_reject
    ldur x1, [x2, #-32]
    ldrh w10, [x1, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_BYTECODE_FUNCTION
    b.eq .Lforward_native_js
    cmp w10, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.eq .Lforward_native_deep
    b .Lforward_native_reject
.Lforward_native_js:
    ldr x1, [x1, #ARM_OFF_JSObject_u_func_function_bytecode]
    ldrb w10, [x1, #ARM_FRAME_KIND_OFFSET]
    cmp w10, #2
    b.eq .Lforward_native_reject
    tbz w10, #0, .Lforward_native_C
// Reload the actual caller's leaf control after the target guards.
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x9, #ARM_OFF_JSFrame_bytecode]
    ldrb w9, [x9, #ARM_FORWARD_MODE_OFFSET]
    cmp w9, #1
    b.ne .Lforward_native_owned
    ldr w10, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w10, #2
    b.eq .Lforward_native_shape
    cmp w10, #4
    b.ne .Lforward_native_owned
.Lforward_native_shape:
    ldrh w11, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    cbnz w11, .Lforward_native_owned
    ldrh w11, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    cbnz w11, .Lforward_native_owned
    ldrh w11, [x1, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    cbnz w11, .Lforward_native_owned
    ldrh w11, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    cmp w11, #2
    b.hi .Lforward_native_owned
    ldr x9, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    cmp w10, #2
    b.eq .Lforward_native_constant
    ldrb w10, [x9]
    cmp w10, #ARM_OP_get_arg0
    b.ne .Lforward_native_owned
    ldrb w10, [x9, #2]
    cmp w10, #ARM_OP_add
    b.ne .Lforward_native_owned
    ldrb w10, [x9, #3]
    cmp w10, #ARM_OP_return
    b.ne .Lforward_native_owned
    cmp w3, #2
    b.lo .Lforward_native_general
    ldr w10, [x2, #24]
    cbnz w10, .Lforward_native_general
    ldrb w4, [x9, #1]
    sub w4, w4, #ARM_OP_push_minus1
    cmp w4, #8
    b.hi .Lforward_native_owned
    sub w4, w4, #1
    ldr w11, [x2, #16]
    adds w4, w4, w11
    b.vs .Lforward_native_general
    b .Lforward_native_value
.Lforward_native_constant:
    ldrb w10, [x9, #1]
    cmp w10, #ARM_OP_return
    b.ne .Lforward_native_owned
    ldrb w4, [x9]
    sub w4, w4, #ARM_OP_push_minus1
    cmp w4, #8
    b.hi .Lforward_native_owned
    sub w4, w4, #1
.Lforward_native_value:
    str x4, [sp]
// Same hypothetical owned child + one logical80-byte tail as the source.
    subs w5, w3, #1
    csel w5, w5, wzr, hs
    ldrh w6, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w5, w6
    csel w5, w5, w6, hs
    ldrh w6, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    add w5, w5, w6
    lsl x5, x5, #4
    add x5, x5, #(ARM_FRAME_HEADER_BYTES+80)
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x7, [x6, #ARM_OFF_JSFrameSegment_capacity]
    ldr x6, [x6, #ARM_OFF_JSFrameSegment_used]
    sub x7, x7, x6
    cmp x5, x7
    b.hi .Lforward_native_C
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x5, x5, x6
    b.cs .Lforward_native_C
    mov x6, #5280
    adds x5, x5, x6
    b.cs .Lforward_native_C
    mov x6, sp
    subs x6, x6, x5
    b.lo .Lforward_native_C
    ldr x7, [x0, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cmp x6, x7
    b.lo .Lforward_native_C
    ldr x5, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x5, [x5, #ARM_OFF_JSFrame_bytecode]
    ldr x5, [x5, #ARM_OFF_JSFunctionBytecode_realm]
    ldur x6, [x2, #-16]
    ldr x6, [x6, #ARM_OFF_JSObject_u_cfunc_realm]
    ldr w7, [x5, #ARM_OFF_JSContext_interrupt_counter]
    cmp x5, x6
    b.ne .Lforward_native_two_realms
    cmp w7, #2
    b.le .Lforward_native_C
    b .Lforward_native_commit
.Lforward_native_two_realms:
    cmp w7, #1
    b.le .Lforward_native_C
    ldr w8, [x6, #ARM_OFF_JSContext_interrupt_counter]
    cmp w8, #1
    b.le .Lforward_native_C
.Lforward_native_commit:
// All guards passed. No allocation,observer or failing operation follows.
    sub w7, w7, #1
    str w7, [x5, #ARM_OFF_JSContext_interrupt_counter]
    ldr w7, [x6, #ARM_OFF_JSContext_interrupt_counter]
    sub w7, w7, #1
    str w7, [x6, #ARM_OFF_JSContext_interrupt_counter]
    ldr x5, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x6, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    add w8, w3, #2
    ldrb w9, [x6]
    cmp w9, #ARM_OP_tail_call_method
    b.ne .Lforward_native_not_tail
    orr w8, w8, #0x8000
.Lforward_native_not_tail:
    strh w8, [x5, #ARM_OFF_JSFrame_pending]
    add x6, x6, #3
    str x6, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    str x6, [x5, #ARM_OFF_JSStackFrame_cur_pc]
    ldr x7, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    str x7, [x5, #ARM_OFF_JSStackFrame_cur_sp]
    str x7, [x5, #ARM_OFF_JSFrame_saved_sp]
    ldr x4, [sp]
    add x6, x0, #ARM_OFF_JSFrameRegisterState_result
    stp x4, xzr, [x6]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_forward_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_forward_counters
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
#endif
    mov w0, #2
    ret
.Lforward_native_deep:
    b JS_AArch64CallPrepareDeep
.Lforward_native_owned:
    b JS_AArch64ForwardOwnedTry
.Lforward_native_general:
    b JS_AArch64ForwardOwnedGeneral
.Lforward_native_C:
    b JS_FrameVarargsForwardTry
.Lforward_native_reject:
    mov w0, #0
    ret
.Lforward_native_control:
    cmp w9, #2
    b.eq .Lforward_native_C
    b JS_FrameCallForwardNativeCold
.cfi_endproc
.size JS_AArch64ForwardProbe,.-JS_AArch64ForwardProbe
#endif
.section .note.GNU-stack,"",%progbits
