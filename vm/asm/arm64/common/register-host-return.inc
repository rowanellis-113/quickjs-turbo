/* Standard AAPCS64 JSValue result x0/x1. Original finish_call releases the
* receiver/callee/arguments in ascending address order. Never change that order.
* x23 cursor,x24 end,x28 pending flags are callee-saved while typed Free runs;
* locals/args reload from the actual current data frame after cleanup. MIT. */
.Lhost_return:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #10, .Lcall_host_finish_c
    cmp x1, #ARM_CONST_JS_TAG_EXCEPTION
    b.eq .Lcall_host_finish_c
    ldrh w28, [x22, #ARM_OFF_JSFrame_pending]
    and w9, w28, #0x7fff
    cbz w9, .Lcall_host_finish_c
    ldr x24, [x22, #ARM_OFF_JSFrame_saved_sp]
    sub x23, x24, x9, lsl #4
// Establish the exact source interval before changing ownership. A miss
// leaves every slot,PC/SP,pending bit and owner intact for original C.
    ldr x10, [x22, #ARM_OFF_JSFrame_bytecode]
    ldrh w10, [x10, #ARM_OFF_JSFunctionBytecode_var_count]
    ldr x11, [x22, #ARM_OFF_JSStackFrame_var_buf]
    add x11, x11, x10, lsl #4
    cmp x23, x11
    b.lo .Lhost_return_guard_miss
    cmp x24, x21
    b.ne .Lhost_return_guard_miss
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x9, tpidr_el0
    add x9, x9, :tprel_hi12:qjs_aarch64_host_return_counters
    add x9, x9, :tprel_lo12_nc:qjs_aarch64_host_return_counters
    ldr x10, [x9]
    add x10, x10, #1
    str x10, [x9]
#endif
    mov x21, x23
    ldr x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
.Lhost_return_release:
    cmp x23, x24
    b.eq .Lhost_return_released
    ldp x10, x11, [x23]
    mov x12, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x12, [x23], #16
    tbz x11, #63, .Lhost_return_release
    ldur w12, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w12, #1
    b.le .Lhost_return_final
    sub w12, w12, #1
    stur w12, [x10, #ARM_REF_COUNT_OFFSET]
    b .Lhost_return_release
.Lhost_return_final:
// The owning return survives legal finalizer/cross-runtime/realm reentry
// in the existing result spill. Detach before release and never rewrite it
// after reentry. State/frame PC/SP keep the original live top with holes.
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    mov x2, x10
    mov x3, x11
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x9, tpidr_el0
    add x9, x9, :tprel_hi12:qjs_aarch64_host_return_counters
    add x9, x9, :tprel_lo12_nc:qjs_aarch64_host_return_counters
    ldr x10, [x9, #16]
    add x10, x10, #1
    str x10, [x9, #16]
#endif
    ldr x1, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x1, [x1, #ARM_OFF_JSFunctionBytecode_realm]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameInterpFree
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    ldp x0, x1, [x9]
    b .Lhost_return_release
.Lhost_return_released:
    strh wzr, [x22, #ARM_OFF_JSFrame_pending]
    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]
    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]
    tbnz w28, #15, .Lhost_return_tail
    stp x0, x1, [x21], #16
    b .Ldispatch
.Lhost_return_tail:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x9, tpidr_el0
    add x9, x9, :tprel_hi12:qjs_aarch64_host_return_counters
    add x9, x9, :tprel_lo12_nc:qjs_aarch64_host_return_counters
    ldr x10, [x9, #8]
    add x10, x10, #1
    str x10, [x9, #8]
#endif
// Call operands are already consumed. Reuse the existing guarded return
// or its exact consumed-parent C continuation;never replay the tail call.
    mov x2, x21
    mov w28, #1
    b .Lreturn_prepare
.Lhost_return_guard_miss:
    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]
    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]
    b .Lcall_host_finish_c
