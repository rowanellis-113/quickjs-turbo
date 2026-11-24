/* Native prepared child frames, MIT. No allocation or C call on admission.
* Callee and argv remain owned by the paused caller until finish_call.
* Every rejection leaves PC/SP, interrupt counter and ownership unchanged. */
.Lcall_short:
#ifdef QJS_AARCH64_CALL_LEAVES
    mov x28, #0
#endif
    sub w0, w9, #ARM_OP_call0
    add x1, x20, #1
    mov w17, #0
    b .Lcall_prepare
.Lcall_wide:
#ifdef QJS_AARCH64_CALL_LEAVES
    mov x28, #0
#endif
    ldurh w0, [x20, #1]
    add x1, x20, #3
    mov w17, #0
    cmp w9, #ARM_OP_call_method
    b.eq .Lcall_method_flag
    cmp w9, #ARM_OP_tail_call_method
    b.ne .Lcall_tail_flag
.Lcall_method_flag:
    mov w17, #1
.Lcall_tail_flag:
    cmp w9, #ARM_OP_tail_call
    b.eq .Lcall_is_tail
    cmp w9, #ARM_OP_tail_call_method
    b.ne .Lcall_prepare
.Lcall_is_tail:
    orr w17, w17, #2
.Lcall_prepare:
    sub x2, x21, x0, lsl #4
    ldp x3, x4, [x2, #-16]
    cmn x4, #1
    b.ne .Lslow
    ldrh w12, [x3, #ARM_OFF_JSObject_class_id]
    cmp w12, #ARM_CONST_JS_CLASS_BYTECODE_FUNCTION
    b.ne .Lcall_host
    ldr x7, [x3, #ARM_OFF_JSObject_u_func_function_bytecode]
#if ARM_HAS_ARGUMENTS
    b .Larguments_guard
#endif
.Lcall_original_kind:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    and w12, w12, #7
    mov w16, #0
    cmp w12, #3
    b.eq .Lcall_kind_ready
    cmp w12, #1
    b.eq .Lcall_owned_kind
    cmp w12, #5
#if ARM_HAS_FORWARDING
    b.eq .Lcall_captured_owned_kind
    cmp w12, #7
    b.ne .Lslow
// Exact bounded proof permits readonly argument capture windows.
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #7, .Lslow
    b .Lcall_kind_ready
.Lcall_captured_owned_kind:
#else
    b.ne .Lslow
#endif
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #7, .Lslow
.Lcall_owned_kind:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #4, .Lslow
    ldrh w16, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
.Lcall_kind_ready:
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    cbz w12, .Lcall_capture_ready
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #7, .Lslow
.Lcall_capture_ready:
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    mov x5, #0
    mov x6, #0
    cmp w0, w12
    b.hs .Lcall_arity_ready
    cbz w16, .Lcall_missing_readonly
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #8, .Lslow
    b .Lcall_arity_ready
.Lcall_missing_readonly:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
#if ARM_HAS_FORWARDING
    tbz w14, #6, .Lcall_captured_missing_owned
#else
    tbz w14, #6, .Lslow
#endif
// Match js_frame_pad_window: only the last frame on its own segment may
// extend, and a capture table after the operand stack must remain intact.
    ldrh w14, [x22, #ARM_OFF_JSStackFrame_var_ref_count]
#if ARM_HAS_FORWARDING
    cbnz w14, .Lcall_captured_missing_owned
#else
    cbnz w14, .Lslow
#endif
    ldr x6, [x22, #ARM_OFF_JSFrame_segment]
    ldr x14, [x6, #ARM_OFF_JSFrameSegment_data]
    ldr w15, [x22, #ARM_OFF_JSFrame_frame_bytes]
    sub x11, x22, x14
    add x11, x11, x15
    ldr x15, [x6, #ARM_OFF_JSFrameSegment_used]
    cmp x11, x15
#if ARM_HAS_FORWARDING
    b.ne .Lcall_captured_missing_owned
#else
    b.ne .Lslow
#endif
    sub x11, x2, x14
    add x11, x11, x12, lsl #4
    ldr x14, [x6, #ARM_OFF_JSFrameSegment_capacity]
    cmp x11, x14
#if ARM_HAS_FORWARDING
    b.hi .Lcall_captured_missing_owned
#else
    b.hi .Lslow
#endif
    subs x5, x11, x15
    csel x5, x5, xzr, hi
#if ARM_HAS_FORWARDING
    b .Lcall_arity_ready
.Lcall_captured_missing_owned:
    ldrb w14, [x7, #ARM_FRAME_KIND_OFFSET]
    and w14, w14, #7
    cmp w14, #7
    b.ne .Lslow
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #4, .Lslow
    tbz w14, #8, .Lslow
    ldrh w16, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    mov x5, #0
    mov x6, #0
    b .Lcall_arity_ready
#endif
.Lcall_arity_ready:
    ldrh w13, [x7, #ARM_OFF_JSFunctionBytecode_var_count]
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x9, x13, x14
    add x9, x9, x16
    lsl x9, x9, #4
    add x9, x9, #ARM_FRAME_HEADER_BYTES
// The actual C builder places an align16 local pointer table after the
// declared operand area. Reserve it before any quota/capacity commitment.
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    mov x15, #ARM_VAR_REF_POINTER_BYTES
    mul x12, x12, x15
    add x12, x12, #15
    and x12, x12, #-16
    add x9, x9, x12
    ldr x8, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x10, [x8, #ARM_OFF_JSFrameSegment_used]
    cmp x8, x6
    csel x12, x5, xzr, eq
    add x10, x10, x12
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_capacity]
    subs x12, x12, x10
    b.lo .Lslow
    cmp x12, x9
    b.lo .Lslow
// Retain C-boundary stack reserve. The cached limit excludes only this
// activation's deferred data-frame charges; zero is the unlimited sentinel.
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x12, .Lcall_quota_ready
    ldr x15, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x15, x15, x5
    b.cs .Lslow
    adds x15, x15, x9
    b.cs .Lslow
    adds x12, x12, x15
    b.cs .Lslow
    adds x12, x12, #4096
    b.cs .Lslow
    mov x15, sp
    cmp x15, x12
    b.lo .Lslow
.Lcall_quota_ready:
#ifdef QJS_AARCH64_CALL_LEAVES
#include "interpreter-aarch64-leaf-bridge.inc"
#endif
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_data]
    add x10, x10, x12
// The original call entry polls the caller realm before publishing child.
    ldr x15, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x15, [x15, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    subs w12, w12, #1
    b.le .Lslow
    str w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
// Commit begins here. There are no remaining fallbacks or calls to C.
    cbz x6, .Lcall_window_ready
#ifdef QJS_AARCH64_VM_INSTRUMENT
// Observe the actual successful route, using the existing save area's
// spare word. No new frame/state field and no C call during admission.
    ldr x12, [sp, #(ARM_VM_POLICY_OFF+8)]
    orr x12, x12, #1
    cbz x5, .Lcall_window_observe_owner
    orr x12, x12, #2
.Lcall_window_observe_owner:
    cmp x8, x6
    b.eq .Lcall_window_observe_done
    orr x12, x12, #4
.Lcall_window_observe_done:
    str x12, [sp, #(ARM_VM_POLICY_OFF+8)]
#endif
    cbz x5, .Lcall_window_padding
    str x11, [x6, #ARM_OFF_JSFrameSegment_used]
    ldr w12, [x22, #ARM_OFF_JSFrame_frame_bytes]
    add w12, w12, w5
    str w12, [x22, #ARM_OFF_JSFrame_frame_bytes]
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x12, x12, x5
    str x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
.Lcall_window_padding:
    add x12, x2, x0, lsl #4
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    sub w14, w14, w0
    mov x15, #ARM_CONST_JS_TAG_UNDEFINED
.Lcall_pad_missing:
    stp xzr, x15, [x12], #16
    subs w14, w14, #1
    b.ne .Lcall_pad_missing
.Lcall_window_ready:
    str x1, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    and w12, w17, #1
    add w12, w12, w0
    add w12, w12, #1
    tbz w17, #1, .Lcall_pending_ready
    orr w12, w12, #0x8000
.Lcall_pending_ready:
    strh w12, [x22, #ARM_OFF_JSFrame_pending]
    str x22, [x10, #ARM_OFF_JSStackFrame_prev_frame]
    add x12, x10, #ARM_OFF_JSStackFrame_cur_func
    stp x3, x4, [x12]
    add x23, x10, #ARM_FRAME_HEADER_BYTES
    mov x24, x2
    cbz w16, .Lcall_arguments_ready
    mov x24, x23
    add x23, x23, x16, lsl #4
.Lcall_arguments_ready:
    str x24, [x10, #ARM_OFF_JSStackFrame_arg_buf]
    str x23, [x10, #ARM_OFF_JSStackFrame_var_buf]
    str xzr, [x10, #ARM_OFF_JSStackFrame_var_refs]
    strh wzr, [x10, #ARM_OFF_JSStackFrame_var_ref_count]
    ldrh w12, [x7, #ARM_OFF_JSFunctionBytecode_arg_count]
    cmp w16, #0
    b.ne .Lcall_visible_arity
    cmp w0, w12
    csel w12, w0, w12, hs
.Lcall_visible_arity:
    strh w12, [x10, #ARM_OFF_JSStackFrame_arg_count]
    ldrb w12, [x7, #ARM_STRICT_BYTE]
    and w12, w12, #ARM_STRICT_MASK
    lsr w12, w12, #ARM_STRICT_SHIFT
    str w12, [x10, #ARM_OFF_JSStackFrame_is_strict_mode]
    str xzr, [x10, #ARM_OFF_JSStackFrame_cur_pc]
    stp xzr, xzr, [x10, #ARM_OFF_JSStackFrame_cur_sp]
    str x7, [x10, #ARM_OFF_JSFrame_bytecode]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    tbz w17, #0, .Lcall_this_ready
    ldp x5, x6, [x2, #-32]
.Lcall_this_ready:
    add x12, x10, #ARM_OFF_JSFrame_this_value
    stp x5, x6, [x12]
    str xzr, [x10, #ARM_OFF_JSFrame_saved_sp]
    str x8, [x10, #ARM_OFF_JSFrame_segment]
    str w9, [x10, #ARM_OFF_JSFrame_frame_bytes]
    strh w16, [x10, #ARM_OFF_JSFrame_owned_args]
    strh wzr, [x10, #ARM_OFF_JSFrame_pending]
    cbz w16, .Lcall_owned_ready
    mov x12, x24
    mov x14, x2
    cmp w0, w16
    csel w15, w0, w16, lo
    cbz w15, .Lcall_owned_padding
.Lcall_copy_owned:
    ldp x5, x6, [x14], #16
    tbz x6, #63, .Lcall_copy_store
    ldur w11, [x5, #ARM_REF_COUNT_OFFSET]
    add w11, w11, #1
    stur w11, [x5, #ARM_REF_COUNT_OFFSET]
.Lcall_copy_store:
    stp x5, x6, [x12], #16
    subs w15, w15, #1
    b.ne .Lcall_copy_owned
.Lcall_owned_padding:
    cmp w0, w16
    b.hs .Lcall_owned_ready
    sub w15, w16, w0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
.Lcall_owned_pad_loop:
    stp xzr, x6, [x12], #16
    subs w15, w15, #1
    b.ne .Lcall_owned_pad_loop
.Lcall_owned_ready:
    mov x12, x23
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    cbz w13, .Lcall_locals_ready
.Lcall_init_locals:
    stp xzr, x14, [x12], #16
    subs w13, w13, #1
    b.ne .Lcall_init_locals
.Lcall_locals_ready:
    mov x21, x12
    ldrh w13, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    strh w13, [x10, #ARM_OFF_JSStackFrame_var_ref_count]
    cbz w13, .Lcall_capture_initialized
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x14, x12, x14, lsl #4
    str x14, [x10, #ARM_OFF_JSStackFrame_var_refs]
.Lcall_zero_capture:
    str xzr, [x14], #ARM_VAR_REF_POINTER_BYTES
    subs w13, w13, #1
    b.ne .Lcall_zero_capture
.Lcall_capture_initialized:
    ldr x20, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_used]
    add x12, x12, x9
    str x12, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x12, x12, x9
    str x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    str x10, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x10, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    mov x22, x10
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x12, [sp, #96]
    add x12, x12, #1
    str x12, [sp, #96]
    tbz w17, #1, .Lcall_observed
    ldr x12, [sp, #112]
    add x12, x12, #1
    str x12, [sp, #112]
.Lcall_observed:
#endif
    ARM_DISPATCH_NEXT 1

// Existing typed C host bridge, reached without a C interpreter-step frame.
// The bridge owns polling, padding, realm, visible SF and exact quota sync.
.Lcall_host:
#if ARM_HAS_FORWARDING
    b .Lcall_forward_guard
#endif
.Lcall_host_original:
    ldrb w14, [x19, #ARM_OFF_JSFrameRegisterState_direct_host_calls]
    cbz w14, .Lslow
    mov w16, #0
    cmp w12, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lcall_class_host
    ldrb w12, [x3, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w12, #ARM_CONST_JS_CFUNC_generic
    b.eq .Lcall_host_ready
    cmp w12, #ARM_CONST_JS_CFUNC_generic_magic
    b.eq .Lcall_host_ready
.Lcall_class_host:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #5, .Lslow
    mov w16, #1
.Lcall_host_ready:
    str x1, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    and w12, w17, #1
    add w12, w12, w0
    add w12, w12, #1
    tbz w17, #1, .Lcall_host_pending
    orr w12, w12, #0x8000
.Lcall_host_pending:
    strh w12, [x22, #ARM_OFF_JSFrame_pending]
    str x1, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov w3, w17
    and w3, w3, #1
    mov w4, w0
    mov x1, x2
    mov w2, w4
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    cbnz w16, .Lcall_original_host
    bl JS_FrameAArch64HostDirectValue
    b .Lcall_host_finish
.Lcall_original_host:
    bl JS_FrameAArch64HostValue
.Lcall_host_finish:
    b .Lhost_return
.Lcall_host_finish_c:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x9, tpidr_el0
    add x9, x9, :tprel_hi12:qjs_aarch64_host_return_counters
    add x9, x9, :tprel_lo12_nc:qjs_aarch64_host_return_counters
    ldr x10, [x9, #24]
    add x10, x10, #1
    str x10, [x9, #24]
#endif
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameAArch64FinishCall
    cbz w0, .Lreload
    b .Ldone

/* Native cleanup never invokes a destructor. Read-only guards precede all decrements.
* Keep the original RC>total-cells sufficient bound. Lower-RC references may
* also proceed when RC>1 and a collision-free64-bit mask proves uniqueness
* across BOTH ranges. Any collision retains C; there are no false admissions.
* Every committed decrement leaves a live owner. Other returns retain C. */
.Lreturn:
    mov w28, #0
    sub x2, x21, #16
    ldp x0, x1, [x2]
    b .Lreturn_prepare
.Lreturn_undef:
    mov w28, #0
    mov x2, x21
    mov x0, #0
    mov x1, #ARM_CONST_JS_TAG_UNDEFINED
.Lreturn_prepare:
    cmp x1, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lreturn_fallback
#if ARM_HAS_CONSTRUCTORS
    ldrb w9, [x22, #ARM_FRAME_ROOT_OFFSET]
    cmp w9, #3
    b.eq .Lconstruct_return
#endif
    ldrh w9, [x22, #ARM_OFF_JSStackFrame_var_ref_count]
    cbnz w9, .Lreturn_fallback
    ldrh w9, [x22, #ARM_OFF_JSFrame_owned_args]
    sub x3, x23, x9, lsl #4
    sub x8, x2, x3
    lsr x8, x8, #4
    mov x4, #0
    mov x6, #0
    mov x7, #0
    mov w17, #0
    ldrb w9, [x22, #ARM_FRAME_ROOT_OFFSET]
#if ARM_HAS_FORWARDING
    cmp w9, #2
    b.ne .Lreturn_root_classified
    ldr x4, [x22, #ARM_OFF_JSStackFrame_prev_frame]
.Lreturn_forward_parent:
    ldr x9, [x4, #ARM_OFF_JSStackFrame_var_buf]
    cbnz x9, .Lreturn_parent_pending
    ldrb w9, [x4, #63]
    cmp w9, #199
    b.ne .Lreturn_parent_pending
    ldr x4, [x4, #ARM_OFF_JSStackFrame_prev_frame]
    b .Lreturn_forward_parent
.Lreturn_root_classified:
#endif
    cbnz w9, .Lreturn_ranges_ready
    ldr x4, [x22, #ARM_OFF_JSStackFrame_prev_frame]
.Lreturn_parent_pending:
    ldrh w5, [x4, #ARM_OFF_JSFrame_pending]
    lsr w17, w5, #15
    and w5, w5, #0x7fff
    ldr x6, [x4, #ARM_OFF_JSFrame_saved_sp]
    sub x7, x6, x5, lsl #4
    add x8, x8, x5
.Lreturn_ranges_ready:
    cmp x8, #32
    b.hi .Lreturn_fallback
// The original caller pending count is dead. This register-only mask is
// shared across both read-only guard ranges, including Dirty phase splits.
    mov x5, #0
    mov x9, x3
    mov x10, x2
    mov w16, #0
.Lreturn_guard:
    cmp x9, x10
    b.eq .Lreturn_guard_range_done
    ldp x11, x12, [x9], #16
    tbz x12, #63, .Lreturn_guard
    ldur w13, [x11, #ARM_REF_COUNT_OFFSET]
    cmp w13, w8
    b.gt .Lreturn_guard
// Only low-RC references need distinctness. Equal pointers have the same
// unchanged RC, so a high-RC reference cannot hide a low-RC alias. A repeated
// hash bit declines before ANY decrement; no collision proves all remaining
// pointers unique, and RC>1 then proves every release nonlast.
    cmp w13, #1
    b.le .Lreturn_fallback
    eor x15, x11, x11, lsr #6
    lsr x15, x15, #4
    mov x14, #1
    lsl x14, x14, x15
    tst x5, x14
    b.ne .Lreturn_fallback
    orr x5, x5, x14
    b .Lreturn_guard
.Lreturn_guard_range_done:
    cbnz w16, .Lreturn_commit
    mov w16, #1
    mov x9, x7
    mov x10, x6
    b .Lreturn_guard
.Lreturn_commit:
    mov x9, x3
    mov x10, x2
    mov w16, #0
.Lreturn_release:
    cmp x9, x10
    b.eq .Lreturn_release_range_done
    ldp x11, x12, [x9], #16
    tbz x12, #63, .Lreturn_release
    ldur w13, [x11, #ARM_REF_COUNT_OFFSET]
    sub w13, w13, #1
    stur w13, [x11, #ARM_REF_COUNT_OFFSET]
    b .Lreturn_release
.Lreturn_release_range_done:
    cbnz w16, .Lreturn_pop
    mov w16, #1
    mov x9, x7
    mov x10, x6
    b .Lreturn_release
.Lreturn_pop:
    cbnz w28, .Lreturn_counted
    add x26, x26, #1
.Lreturn_counted:
    ldr x9, [x22, #ARM_OFF_JSFrame_segment]
    ldr x10, [x9, #ARM_OFF_JSFrameSegment_data]
    sub x10, x22, x10
    str x10, [x9, #ARM_OFF_JSFrameSegment_used]
    str x9, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr w10, [x22, #ARM_OFF_JSFrame_frame_bytes]
#if ARM_HAS_FORWARDING
    ldrb w12, [x22, #ARM_FRAME_ROOT_OFFSET]
    cmp w12, #2
    b.ne .Lreturn_no_forward_tail
// No observer/last release remains. Match shared forward_take only now.
    ldr x12, [x22, #ARM_OFF_JSStackFrame_prev_frame]
.Lreturn_take_forward_tail:
    ldr x14, [x12, #ARM_OFF_JSStackFrame_var_buf]
    cbnz x14, .Lreturn_forward_tail_done
    ldrb w14, [x12, #63]
    cmp w14, #199
    b.ne .Lreturn_forward_tail_done
    add x10, x10, #80
    ldr x12, [x12, #ARM_OFF_JSStackFrame_prev_frame]
    b .Lreturn_take_forward_tail
.Lreturn_forward_tail_done:
    str x12, [x22, #ARM_OFF_JSStackFrame_prev_frame]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_forward_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_forward_counters
    ldr x15, [x14, #24]
    add x15, x15, #1
    str x15, [x14, #24]
#endif
.Lreturn_no_forward_tail:
#endif
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    sub x11, x11, x10
    str x11, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x12, [x22, #ARM_OFF_JSStackFrame_prev_frame]
    str x12, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
    str x4, [x19, #ARM_OFF_JSFrameRegisterState_frame]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x10, [sp, #104]
    add x10, x10, #1
    str x10, [sp, #104]
#endif
    cbz x4, .Lreturn_root
    mov x22, x4
    strh wzr, [x22, #ARM_OFF_JSFrame_pending]
    ldr x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]
    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]
    cbnz w17, .Lreturn_tail_parent
    stp x0, x1, [x7]
    add x21, x7, #16
    b .Ldispatch
.Lreturn_tail_parent:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x9, [sp, #120]
    add x9, x9, #1
    str x9, [sp, #120]
#endif
    mov x21, x7
    mov x2, x7
    mov w28, #1
    b .Lreturn_prepare
.Lreturn_root:
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x2, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    b .Ldone
.Lreturn_fallback:
// Once a tail parent has been consumed, its opcode cannot be replayed.
// Resume exactly at the shared C return label with the owning value spill.
    cbz w28, .Lslow
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x2, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameAArch64Return
    cbz w0, .Lreload
    b .Ldone
