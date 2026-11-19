/* Original insert3: obj key value -> value obj key value. MIT.
* No C call/allocation/final release;incoming publication token is retained. */
#if ARM_HAS_STACK_INSERT
.Lstack_insert3:
    adrp x9, JS_FrameSlowDirectData
    add x9, x9, :lo12:JS_FrameSlowDirectData
    ldrb w9, [x9, #ARM_OFF_JSFrameSlowDirectData_mode]
    tbnz w9, #5, .Lslow
    ldp x0, x1, [x21, #-16]
    tbz x1, #63, .Lstack_insert3_copy
    ldr w6, [x0, #ARM_REF_COUNT_OFFSET]
    add w6, w6, #1
    str w6, [x0, #ARM_REF_COUNT_OFFSET]
.Lstack_insert3_copy:
    ldp x2, x3, [x21, #-32]
    ldp x4, x5, [x21, #-48]
    stp x0, x1, [x21]
    stp x2, x3, [x21, #-16]
    stp x4, x5, [x21, #-32]
    stp x0, x1, [x21, #-48]
    add x21, x21, #16
    add x20, x20, #1
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_stack_insert_counter
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_stack_insert_counter
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
#endif
    ARM_DISPATCH_NEXT 1
#endif
