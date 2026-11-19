/* Shared prepared .call descriptor,leaf and owned constructors,AAPCS64. MIT.
* x0 state,x1 targetBC,x2 originalargv,w3 nativeargc,x4 targetslot,w5 depth.
* Caller lease32:0 targetBC,8 packed depth/argc,16 originalargv,24 scratch.
* No call,SP change,callee-saved write or observer after commitment.
*/
#include "interpreter-aarch64-values.h"
#if ARM_HAS_FORWARDING
.section .text.qjs_arm_forward_prepared,"ax",%progbits
.p2align 2
.hidden JS_FrameCallPrepareData,JS_FrameVarargsForwardTry,JS_FrameCallPrepareCold
.hidden JS_FrameCallPrepareCommit,qjs_aarch64_core_js_function_call

/* Original explicit-observation counters remain process-global and atomic. */
.macro PREPARE_ATOMIC_INC address
.Latomic_\@:
    ldxr x14, [\address]
    add x14, x14, #1
    stxr w15, x14, [\address]
    cbnz w15, .Latomic_\@
.endm
.macro PREPARE_TLS offset
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_forward_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_forward_counters
    ldr x15, [x14, #\offset]
    add x15, x15, #1
    str x15, [x14, #\offset]
#endif
.endm
/* x9 is complete hypothetical child+logical bytes. Preserve leaf x6/x7. */
.macro PREPARE_QUOTA fallback
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x11, [x10, #ARM_OFF_JSFrameSegment_capacity]
    ldr x10, [x10, #ARM_OFF_JSFrameSegment_used]
    sub x11, x11, x10
    cmp x9, x11
    b.hi \fallback
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x9, x9, x10
    b.cs \fallback
    mov x10, #5280
    adds x9, x9, x10
    b.cs \fallback
    mov x10, sp
    subs x10, x10, x9
    b.lo \fallback
    ldr x11, [x0, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cmp x10, x11
    b.lo \fallback
.endm
/* Source order:caller,argv[-1] wrapper,argv[-2] wrapper,argv[0]... .
* Refund precisely the successful prefix on a near poll,including aliases.
*/
.macro PREPARE_POLLS fallback
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x9, #ARM_OFF_JSFrame_bytecode]
    ldr x10, [x9, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    cmp w11, #1
    b.le \fallback
    sub w11, w11, #1
    str w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    mov w8, #0
.Lpoll_wrapper_\@:
    cbz w8, .Lpoll_first_\@
    cmp w8, #1
    b.eq .Lpoll_second_\@
    sub w9, w8, #2
    add x9, x2, x9, lsl #4
    b .Lpoll_address_\@
.Lpoll_first_\@:
    sub x9, x2, #16
    b .Lpoll_address_\@
.Lpoll_second_\@:
    sub x9, x2, #32
.Lpoll_address_\@:
    ldr x9, [x9]
    ldr x10, [x9, #ARM_OFF_JSObject_u_cfunc_realm]
    ldr w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    cmp w11, #1
    b.le .Lpoll_refund_\@
    sub w11, w11, #1
    str w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    add w8, w8, #1
    cmp w8, w5
    b.lo .Lpoll_wrapper_\@
    b .Lpoll_ready_\@
.Lpoll_refund_\@:
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x9, #ARM_OFF_JSFrame_bytecode]
    ldr x10, [x9, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    add w11, w11, #1
    str w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    mov w12, #0
    cbz w8, .Lpoll_refunded_\@
.Lrefund_wrapper_\@:
    cbz w12, .Lrefund_first_\@
    cmp w12, #1
    b.eq .Lrefund_second_\@
    sub w9, w12, #2
    add x9, x2, x9, lsl #4
    b .Lrefund_address_\@
.Lrefund_first_\@:
    sub x9, x2, #16
    b .Lrefund_address_\@
.Lrefund_second_\@:
    sub x9, x2, #32
.Lrefund_address_\@:
    ldr x9, [x9]
    ldr x10, [x9, #ARM_OFF_JSObject_u_cfunc_realm]
    ldr w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    add w11, w11, #1
    str w11, [x10, #ARM_OFF_JSContext_interrupt_counter]
    add w12, w12, #1
    cmp w12, w8
    b.lo .Lrefund_wrapper_\@
.Lpoll_refunded_\@:
    b \fallback
.Lpoll_ready_\@:
.endm

.global JS_AArch64CallPrepareOne
.hidden JS_AArch64CallPrepareOne
.type JS_AArch64CallPrepareOne,%function
JS_AArch64CallPrepareOne:
.cfi_startproc
    adrp x9, JS_FrameCallPrepareData
    ldrb w9, [x9, :lo12:JS_FrameCallPrepareData]
    and w9, w9, #3
    cmp w9, #1
    b.eq .Lprepare_one_ready
    cmp w9, #2
    b.eq .Lprepare_one_C
    b JS_FrameCallPrepareCold
.Lprepare_one_ready:
    sub x4, x2, #32
    mov w5, #1
    b JS_AArch64CallPrepareExecute
.Lprepare_one_C:
    b JS_FrameVarargsForwardTry
.cfi_endproc
.size JS_AArch64CallPrepareOne,.-JS_AArch64CallPrepareOne

.p2align 2
.global JS_AArch64CallPrepareDeep
.hidden JS_AArch64CallPrepareDeep
.type JS_AArch64CallPrepareDeep,%function
JS_AArch64CallPrepareDeep:
.cfi_startproc
    adrp x9, JS_FrameCallPrepareData
    ldrb w9, [x9, :lo12:JS_FrameCallPrepareData]
    and w9, w9, #3
    cmp w9, #1
    b.eq .Lprepare_deep_ready
    cmp w9, #2
    b.eq .Lprepare_deep_C
    b JS_FrameCallPrepareCold
.Lprepare_deep_ready:
    sub x4, x2, #32
    mov w5, #1
.Lprepare_unwrap:
    ldr x9, [x4, #8]
    cmn x9, #1
    b.ne .Lprepare_deep_C
    ldr x9, [x4]
    ldrh w10, [x9, #ARM_OFF_JSObject_class_id]
    cmp w10, #ARM_CONST_JS_CLASS_BYTECODE_FUNCTION
    b.eq .Lprepare_target
    cmp w10, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lprepare_deep_C
    ldr x10, [x9, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x11, qjs_aarch64_core_js_function_call
    add x11, x11, :lo12:qjs_aarch64_core_js_function_call
    cmp x10, x11
    b.ne .Lprepare_deep_C
    ldrb w10, [x9, #ARM_OFF_JSObject_u_cfunc_cproto]
    cbnz w10, .Lprepare_deep_C
    ldrh w10, [x9, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w10, .Lprepare_deep_C
    ldrb w10, [x9, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w10, #1
    b.ne .Lprepare_deep_C
    cmp w5, #64
    b.hs .Lprepare_deep_C
    cmp w3, w5
    b.lo .Lprepare_deep_C
    sub w10, w5, #1
    add x4, x2, x10, lsl #4
    add w5, w5, #1
    b .Lprepare_unwrap
.Lprepare_target:
    ldr x1, [x9, #ARM_OFF_JSObject_u_func_function_bytecode]
    ldrb w9, [x1, #ARM_FRAME_KIND_OFFSET]
    tbz w9, #0, .Lprepare_deep_C
    b JS_AArch64CallPrepareExecute
.Lprepare_deep_C:
    b JS_FrameVarargsForwardTry
.cfi_endproc
.size JS_AArch64CallPrepareDeep,.-JS_AArch64CallPrepareDeep

.p2align 2
.global JS_AArch64CallPrepareExecute
.hidden JS_AArch64CallPrepareExecute
.type JS_AArch64CallPrepareExecute,%function
JS_AArch64CallPrepareExecute:
.cfi_startproc
    str x1, [sp]
    orr w9, w3, w5, lsl #16
    str x9, [sp, #8]
    str x2, [sp, #16]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x9, #ARM_OFF_JSFrame_bytecode]
    ldrb w9, [x9, #ARM_FORWARD_MODE_OFFSET]
    cmp w9, #1
    b.ne .Lprepare_commit
    ldrh w9, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    cbnz w9, .Lprepare_commit
    ldrh w9, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_closure_var_count]
    orr w9, w9, w10
    cbnz w9, .Lprepare_commit
    ldrh w9, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    cmp w9, #2
    b.hi .Lprepare_commit
    ldr w9, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    ldr x10, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    cmp w9, #1
    b.eq .Lprepare_return_undefined
    cmp w9, #2
    b.eq .Lprepare_return_value
    cmp w9, #4
    b.ne .Lprepare_commit
    ldrb w9, [x10, #2]
    cmp w9, #ARM_OP_add
    b.ne .Lprepare_commit
    ldrb w9, [x10, #3]
    cmp w9, #ARM_OP_return
    b.ne .Lprepare_commit
    ldrb w9, [x10]
    sub w9, w9, #ARM_OP_get_arg0
    cmp w9, #3
    b.hi .Lprepare_commit
    add w9, w9, w5
    cmp w9, w3
    b.hs .Lprepare_commit
    add x9, x2, x9, lsl #4
    ldr w11, [x9, #8]
    cbnz w11, .Lprepare_commit
    ldr w6, [x9]
    str w6, [sp, #24]
    ldrb w9, [x10, #1]
    sub w9, w9, #ARM_OP_push_minus1
    cmp w9, #8
    b.ls .Lprepare_add_short
    ldrb w9, [x10, #1]
    sub w9, w9, #ARM_OP_get_arg0
    cmp w9, #3
    b.hi .Lprepare_commit
    add w9, w9, w5
    cmp w9, w3
    b.hs .Lprepare_commit
    add x9, x2, x9, lsl #4
    ldr w11, [x9, #8]
    cbnz w11, .Lprepare_commit
    ldr w6, [x9]
    b .Lprepare_add_value
.Lprepare_add_short:
    sub w6, w9, #1
.Lprepare_add_value:
    ldr w9, [sp, #24]
    adds w6, w6, w9
    b.vs .Lprepare_commit
    mov x7, #0
    b .Lprepare_leaf_quota
.Lprepare_return_undefined:
    ldrb w9, [x10]
    cmp w9, #ARM_OP_return_undef
    b.ne .Lprepare_commit
    b .Lprepare_undefined
.Lprepare_return_value:
    ldrb w9, [x10, #1]
    cmp w9, #ARM_OP_return
    b.ne .Lprepare_commit
    ldrb w9, [x10]
    sub w9, w9, #ARM_OP_push_minus1
    cmp w9, #8
    b.ls .Lprepare_small_integer
    ldrb w9, [x10]
    sub w9, w9, #ARM_OP_get_arg0
    cmp w9, #3
    b.ls .Lprepare_argument
    ldrb w9, [x10]
    cmp w9, #ARM_OP_undefined
    b.eq .Lprepare_undefined
    cmp w9, #ARM_OP_null
    b.eq .Lprepare_null
    cmp w9, #ARM_OP_push_false
    b.eq .Lprepare_false
    cmp w9, #ARM_OP_push_true
    b.ne .Lprepare_commit
    mov x6, #1
    b .Lprepare_boolean
.Lprepare_false:
    mov x6, #0
.Lprepare_boolean:
    mov x7, #ARM_CONST_JS_TAG_BOOL
    b .Lprepare_leaf_quota
.Lprepare_null:
    mov x6, #0
    mov x7, #ARM_CONST_JS_TAG_NULL
    b .Lprepare_leaf_quota
.Lprepare_undefined:
    mov x6, #0
    mov x7, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lprepare_leaf_quota
.Lprepare_small_integer:
    sub w6, w9, #1
    mov x7, #0
    b .Lprepare_leaf_quota
.Lprepare_argument:
    add w9, w9, w5
    cmp w9, w3
    b.hs .Lprepare_undefined
    add x9, x2, x9, lsl #4
    ldp x6, x7, [x9]
.Lprepare_leaf_quota:
    subs w9, w3, w5
    csel w9, w9, wzr, hs
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w9, w10
    csel w9, w9, w10, hs
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    add w9, w9, w10
    lsl x9, x9, #4
    add x9, x9, #ARM_FRAME_HEADER_BYTES
    mov x10, #80
    madd x9, x5, x10, x9
    PREPARE_QUOTA .Lprepare_leaf_C
    PREPARE_POLLS .Lprepare_leaf_C
// Own a returned heap value before any argument cleanup/finalizer.
    mov w9, #-9
    cmp w7, w9
    b.lo .Lprepare_no_dup
    ldr w9, [x6, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x6, #ARM_REF_COUNT_OFFSET]
.Lprepare_no_dup:
    add x9, x0, #ARM_OFF_JSFrameRegisterState_result
    stp x6, x7, [x9]
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    str x9, [x10, #ARM_OFF_JSStackFrame_cur_sp]
    str x9, [x10, #ARM_OFF_JSFrame_saved_sp]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldr w11, [sp, #8]
    and w11, w11, #65535
    add w11, w11, #2
    ldrb w12, [x9]
    cmp w12, #ARM_OP_tail_call_method
    b.ne .Lprepare_not_tail
    orr w11, w11, #0x8000
.Lprepare_not_tail:
    strh w11, [x10, #ARM_OFF_JSFrame_pending]
    add x9, x9, #3
    str x9, [x10, #ARM_OFF_JSStackFrame_cur_pc]
    str x9, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    adrp x13, JS_FrameCallPrepareData
    add x13, x13, :lo12:JS_FrameCallPrepareData
    ldrb w9, [x13]
    tbz w9, #2, .Lprepare_leaf_unobserved
    add x13, x13, #8
    PREPARE_ATOMIC_INC x13
    adrp x13, JS_FrameCallPrepareData
    add x13, x13, :lo12:JS_FrameCallPrepareData
    add x13, x13, #24
    add x13, x13, x5, lsl #3
    PREPARE_ATOMIC_INC x13
.Lprepare_leaf_unobserved:
    PREPARE_TLS 64
    mov w0, #2
    ret
.Lprepare_commit:
    adrp x13, JS_FrameCallPrepareData
    add x13, x13, :lo12:JS_FrameCallPrepareData
    ldrb w9, [x13]
    tbz w9, #2, .Lprepare_commit_unobserved
    add x13, x13, #16
    PREPARE_ATOMIC_INC x13
    adrp x13, JS_FrameCallPrepareData
    add x13, x13, :lo12:JS_FrameCallPrepareData
    add x13, x13, #24
    ldr w9, [sp, #8]
    lsr w9, w9, #16
    add x13, x13, x9, lsl #3
    PREPARE_ATOMIC_INC x13
.Lprepare_commit_unobserved:
    b JS_AArch64CallPrepareOwned
.Lprepare_leaf_C:
    b JS_FrameVarargsForwardTry
.cfi_endproc
.size JS_AArch64CallPrepareExecute,.-JS_AArch64CallPrepareExecute

.p2align 2
.global JS_AArch64CallPrepareOwned
.hidden JS_AArch64CallPrepareOwned
.type JS_AArch64CallPrepareOwned,%function
JS_AArch64CallPrepareOwned:
.cfi_startproc
    adrp x9, JS_FrameCallPrepareData
    add x9, x9, :lo12:JS_FrameCallPrepareData
    ldrb w9, [x9, #1]
    cmp w9, #1
    b.ne .Lprepare_owned_C
    ldr x1, [sp]
    ldr w3, [sp, #8]
    lsr w5, w3, #16
    and w3, w3, #65535
    ldr x2, [sp, #16]
    subs w9, w3, w5
    csel w9, w9, wzr, hs
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w9, w10
    csel w9, w9, w10, hs
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    add w9, w9, w10
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    add w9, w9, w10
    lsl x9, x9, #4
    add x9, x9, #ARM_FRAME_HEADER_BYTES
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    lsl x10, x10, #3
    add x10, x10, #15
    and x10, x10, #-16
    add x9, x9, x10
    str x9, [sp, #24]
    mov x10, #80
    madd x9, x5, x10, x9
    PREPARE_QUOTA .Lprepare_owned_C
    PREPARE_POLLS .Lprepare_owned_C
// All failing checks are complete. Build every slot before publication.
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x8, [x9, #ARM_OFF_JSFrameSegment_data]
    ldr x10, [x9, #ARM_OFF_JSFrameSegment_used]
    add x8, x8, x10
    str x9, [x8, #ARM_OFF_JSFrame_segment]
    str x1, [x8, #ARM_OFF_JSFrame_bytecode]
    ldr x9, [sp, #24]
    str w9, [x8, #ARM_OFF_JSFrame_frame_bytes]
    cmp w5, #1
    b.ne .Lprepare_owned_target_later
    sub x4, x2, #32
    b .Lprepare_owned_target_slot
.Lprepare_owned_target_later:
    sub w9, w5, #2
    add x4, x2, x9, lsl #4
.Lprepare_owned_target_slot:
    ldp x10, x11, [x4]
    stp x10, x11, [x8, #ARM_OFF_JSStackFrame_cur_func]
    subs w9, w3, w5
    csel w9, w9, wzr, hs
    ldrh w10, [x1, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w9, w10
    csel w9, w9, w10, hs
    strh w9, [x8, #ARM_OFF_JSStackFrame_arg_count]
    strh w9, [x8, #ARM_OFF_JSFrame_owned_args]
    strh wzr, [x8, #ARM_OFF_JSFrame_pending]
    add x10, x8, #ARM_FRAME_HEADER_BYTES
    str x10, [x8, #ARM_OFF_JSStackFrame_arg_buf]
    add x10, x10, x9, lsl #4
    str x10, [x8, #ARM_OFF_JSStackFrame_var_buf]
    ldrh w9, [x1, #ARM_OFF_JSFunctionBytecode_var_count]
    add x10, x10, x9, lsl #4
    str x10, [x8, #ARM_OFF_JSStackFrame_cur_sp]
    str x10, [x8, #ARM_OFF_JSFrame_saved_sp]
    ldrh w9, [x1, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    strh w9, [x8, #ARM_OFF_JSStackFrame_var_ref_count]
    str xzr, [x8, #ARM_OFF_JSStackFrame_var_refs]
    cbz w9, .Lprepare_owned_refs_done
    ldrh w11, [x1, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x10, x10, x11, lsl #4
    str x10, [x8, #ARM_OFF_JSStackFrame_var_refs]
.Lprepare_owned_zero_refs:
    str xzr, [x10], #ARM_VAR_REF_POINTER_BYTES
    subs w9, w9, #1
    b.ne .Lprepare_owned_zero_refs
.Lprepare_owned_refs_done:
    str xzr, [x8, #ARM_OFF_JSStackFrame_cur_pc]
    str xzr, [x8, #(ARM_OFF_JSFrame_bytecode-8)]
    ldrb w9, [x1, #ARM_STRICT_BYTE]
    and w9, w9, #ARM_STRICT_MASK
    lsr w9, w9, #ARM_STRICT_SHIFT
    strb w9, [x8, #ARM_OFF_JSStackFrame_is_strict_mode]
    strb wzr, [x8, #61]
    mov w9, #2
    strh w9, [x8, #ARM_FRAME_ROOT_OFFSET]
    cmp w3, w5
    b.lo .Lprepare_owned_undefined_this
    sub w9, w5, #1
    add x9, x2, x9, lsl #4
    ldp x10, x11, [x9]
    b .Lprepare_owned_this_done
.Lprepare_owned_undefined_this:
    mov x10, #0
    mov x11, #ARM_CONST_JS_TAG_UNDEFINED
.Lprepare_owned_this_done:
    stp x10, x11, [x8, #ARM_OFF_JSFrame_this_value]
    subs w16, w3, w5
    csel w16, w16, wzr, hs
    sub w9, w3, w16
    add x10, x2, x9, lsl #4
    ldr x9, [x8, #ARM_OFF_JSStackFrame_arg_buf]
    cbz w16, .Lprepare_owned_pad_start
.Lprepare_owned_copy_args:
    ldp x12, x13, [x10], #16
    stp x12, x13, [x9], #16
    mov w14, #-9
    cmp w13, w14
    b.lo .Lprepare_owned_no_dup
    ldr w14, [x12, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    str w14, [x12, #ARM_REF_COUNT_OFFSET]
.Lprepare_owned_no_dup:
    subs w16, w16, #1
    b.ne .Lprepare_owned_copy_args
.Lprepare_owned_pad_start:
    ldr x10, [x8, #ARM_OFF_JSStackFrame_var_buf]
    mov x11, #ARM_CONST_JS_TAG_UNDEFINED
    cmp x9, x10
    b.eq .Lprepare_owned_vars_start
.Lprepare_owned_pad_args:
    stp xzr, x11, [x9], #16
    cmp x9, x10
    b.lo .Lprepare_owned_pad_args
.Lprepare_owned_vars_start:
    ldr x10, [x8, #ARM_OFF_JSFrame_saved_sp]
    cmp x9, x10
    b.eq .Lprepare_owned_vars_done
.Lprepare_owned_zero_vars:
    stp xzr, x11, [x9], #16
    cmp x9, x10
    b.lo .Lprepare_owned_zero_vars
.Lprepare_owned_vars_done:
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    str x9, [x8, #ARM_OFF_JSStackFrame_prev_frame]
    ldr x2, [sp, #16]
    ldr w3, [sp, #8]
    lsr w5, w3, #16
    and w3, w3, #65535
    ldp x10, x11, [x2, #-16]
    ldp x12, x13, [x2, #-32]
    ldr x9, [sp, #24]
    add x9, x8, x9
.Lprepare_owned_logical_loop:
    ldr x14, [x8, #ARM_OFF_JSStackFrame_prev_frame]
    str x14, [x9, #ARM_OFF_JSStackFrame_prev_frame]
    str x9, [x8, #ARM_OFF_JSStackFrame_prev_frame]
    stp x10, x11, [x9, #ARM_OFF_JSStackFrame_cur_func]
    mov x14, x2
    mov w15, w3
    cbnz w3, .Lprepare_owned_logical_count
    add x14, x8, #ARM_OFF_JSFrame_this_value
    mov w15, #1
.Lprepare_owned_logical_count:
    str x14, [x9, #ARM_OFF_JSStackFrame_arg_buf]
    strh w15, [x9, #ARM_OFF_JSStackFrame_arg_count]
    strh wzr, [x9, #ARM_OFF_JSStackFrame_var_ref_count]
    strh wzr, [x9, #ARM_OFF_JSStackFrame_is_strict_mode]
    mov w14, #50944
    strh w14, [x9, #ARM_FRAME_ROOT_OFFSET]
    str xzr, [x9, #ARM_OFF_JSStackFrame_var_buf]
    str xzr, [x9, #ARM_OFF_JSStackFrame_var_refs]
    str xzr, [x9, #ARM_OFF_JSStackFrame_cur_pc]
    str xzr, [x9, #ARM_OFF_JSStackFrame_cur_sp]
    str xzr, [x9, #72]
    add x9, x9, #80
    subs w5, w5, #1
    b.eq .Lprepare_owned_logical_done
    mov x10, x12
    mov x11, x13
    ldp x12, x13, [x2], #16
    sub w3, w3, #1
    b .Lprepare_owned_logical_loop
.Lprepare_owned_logical_done:
    ldr x1, [sp]
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    str x9, [x10, #ARM_OFF_JSStackFrame_cur_sp]
    str x9, [x10, #ARM_OFF_JSFrame_saved_sp]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldr w11, [sp, #8]
    and w11, w11, #65535
    add w11, w11, #2
    ldrb w12, [x9]
    cmp w12, #ARM_OP_tail_call_method
    b.ne .Lprepare_owned_not_tail
    orr w11, w11, #0x8000
.Lprepare_owned_not_tail:
    strh w11, [x10, #ARM_OFF_JSFrame_pending]
    add x9, x9, #3
    str x9, [x10, #ARM_OFF_JSStackFrame_cur_pc]
    ldr w9, [sp, #8]
    lsr w9, w9, #16
    mov x10, #80
    mul x9, x9, x10
    ldr x10, [sp, #24]
    add x9, x9, x10
    ldr x10, [x0, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x11, [x10, #ARM_OFF_JSFrameSegment_used]
    add x11, x11, x9
    str x11, [x10, #ARM_OFF_JSFrameSegment_used]
    ldr x11, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x11, x11, x9
    str x11, [x0, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adrp x13, JS_FrameCallPrepareData
    add x13, x13, :lo12:JS_FrameCallPrepareData
    ldrb w9, [x13]
    tbz w9, #2, .Lprepare_owned_unobserved
    add x13, x13, #24
    PREPARE_ATOMIC_INC x13
.Lprepare_owned_unobserved:
    PREPARE_TLS 80
    str x8, [x0, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x9, [x1, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    str x9, [x0, #ARM_OFF_JSFrameRegisterState_pc]
    ldr x9, [x8, #ARM_OFF_JSFrame_saved_sp]
    str x9, [x0, #ARM_OFF_JSFrameRegisterState_sp]
    ldr x9, [x0, #ARM_OFF_JSFrameRegisterState_rt]
    str x8, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
    mov w0, #1
    ret
.Lprepare_owned_C:
    b JS_AArch64CallPrepareFallback
.cfi_endproc
.size JS_AArch64CallPrepareOwned,.-JS_AArch64CallPrepareOwned

.p2align 2
.global JS_AArch64CallPrepareFallback
.hidden JS_AArch64CallPrepareFallback
.type JS_AArch64CallPrepareFallback,%function
JS_AArch64CallPrepareFallback:
.cfi_startproc
    PREPARE_TLS 72
    ldr w3, [sp, #8]
    ldr x2, [sp, #16]
    lsr w9, w3, #16
    cmp w9, #1
    b.ne .Lprepare_fallback_later
    sub x1, x2, #32
    b JS_FrameCallPrepareCommit
.Lprepare_fallback_later:
    sub w9, w9, #2
    add x1, x2, x9, lsl #4
    b JS_FrameCallPrepareCommit
.cfi_endproc
.size JS_AArch64CallPrepareFallback,.-JS_AArch64CallPrepareFallback
.purgem PREPARE_ATOMIC_INC
.purgem PREPARE_TLS
.purgem PREPARE_QUOTA
.purgem PREPARE_POLLS
#endif
.section .note.GNU-stack,"",%progbits
