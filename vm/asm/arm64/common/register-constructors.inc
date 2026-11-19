/* Ordinary construction: source-owned push and native root3 return. MIT. */
#if ARM_HAS_CONSTRUCTORS
.macro ARM_CONSTRUCT_EVENT offset
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_construct_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_construct_counters
    ldr x15, [x14, #\offset]
    add x15, x15, #1
    str x15, [x14, #\offset]
#endif
.endm
.Lconstruct_call:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_FrameInterpProperty_call_constructor
    cbz w0, .Lreload
    b .Ldone
.Lconstruct_return:
// Original child cleanup must finish before its storage can be reused.
// All fallback edges precede the first decrement or slot transfer.
    ldrh w9, [x22, #ARM_OFF_JSStackFrame_var_ref_count]
    cbnz w9, .Lreturn_fallback
    ldrh w9, [x22, #ARM_OFF_JSFrame_owned_args]
    sub x3, x23, x9, lsl #4
    sub x8, x2, x3
    lsr x8, x8, #4
    cmp x8, #32
    b.hi .Lreturn_fallback
    ldr x4, [x22, #ARM_OFF_JSStackFrame_prev_frame]
    cbz x4, .Lreturn_fallback
    ldrh w5, [x4, #ARM_OFF_JSFrame_pending]
    tbnz w5, #15, .Lreturn_fallback
    and w5, w5, #0x7fff
    cmp w5, #2
    b.lo .Lreturn_fallback
    mov x9, x3
.Lconstruct_guard:
    cmp x9, x2
    b.eq .Lconstruct_release_begin
    ldp x10, x11, [x9], #16
    tbz x11, #63, .Lconstruct_guard
    ldr w12, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w12, w8
    b.le .Lreturn_fallback
    b .Lconstruct_guard
.Lconstruct_release_begin:
    mov x9, x3
.Lconstruct_release:
    cmp x9, x2
    b.eq .Lconstruct_pop
    ldp x10, x11, [x9], #16
    tbz x11, #63, .Lconstruct_release
    ldr w12, [x10, #ARM_REF_COUNT_OFFSET]
    sub w12, w12, #1
    str w12, [x10, #ARM_REF_COUNT_OFFSET]
    b .Lconstruct_release
.Lconstruct_pop:
    cbnz w28, .Lconstruct_counted
    add x26, x26, #1
.Lconstruct_counted:
    ldr x9, [x22, #ARM_OFF_JSFrame_segment]
    ldr x10, [x9, #ARM_OFF_JSFrameSegment_data]
    sub x10, x22, x10
    str x10, [x9, #ARM_OFF_JSFrameSegment_used]
    str x9, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr w10, [x22, #ARM_OFF_JSFrame_frame_bytes]
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    sub x11, x11, x10
    str x11, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x4, [x9, #ARM_OFF_JSRuntime_current_stack_frame]
    str x4, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    mov x22, x4
    ldr x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    ldr x21, [x22, #ARM_OFF_JSFrame_saved_sp]
// The unchanged host consumer may resume in C under its independent
// policy or guard. Publish the restored parent continuation first.
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    ldr x23, [x22, #ARM_OFF_JSStackFrame_var_buf]
    ldr x24, [x22, #ARM_OFF_JSStackFrame_arg_buf]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x9, [sp, #104]
    add x9, x9, #1
    str x9, [sp, #104]
#endif
    ARM_CONSTRUCT_EVENT 8
    tbnz x1, #63, .Lconstruct_heap_return
// A primitive immediate is discarded without release. Transfer the live
// receiver owner out of its slot before the unchanged ascending consumer.
    sub x9, x21, x5, lsl #4
    ldp x0, x1, [x9]
    mov x10, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x10, [x9]
    ARM_CONSTRUCT_EVENT 16
    b .Lhost_return
.Lconstruct_heap_return:
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    stp x0, x1, [x9]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameVarargsConstructHeapReturn
    cbz w0, .Lreload
    b .Ldone
.purgem ARM_CONSTRUCT_EVENT
#endif
