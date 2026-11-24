/* Source-owned reference-slot final release and generic writable own hash.
* No new stack reservation. Commit incoming ownership/slot/PC/SP before the
* original typed Free owner;never rewrite a live slot after reentry. MIT. */
.Lslot_last:
// x12 live destination,x10/x11 incoming,x14/x15 old,w17 keep,x13 width.
    cbz w17, .Lslot_last_incoming_ready
    tbz x11, #63, .Lslot_last_incoming_ready
    ldur w16, [x10, #ARM_REF_COUNT_OFFSET]
    add w16, w16, #1
    stur w16, [x10, #ARM_REF_COUNT_OFFSET]
.Lslot_last_incoming_ready:
    mov x2, x14
    mov x3, x15
    stp x10, x11, [x12]
    cbnz w17, .Lslot_last_kept
    sub x21, x21, #16
.Lslot_last_kept:
    add x20, x20, x13
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x4, tpidr_el0
    add x4, x4, :tprel_hi12:qjs_aarch64_store_counters
    add x4, x4, :tprel_lo12_nc:qjs_aarch64_store_counters
    ldr x5, [x4, #8]
    add x5, x5, #1
    str x5, [x4, #8]
#endif
    ldr x1, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x1, [x1, #ARM_OFF_JSFunctionBytecode_realm]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameInterpFree
    ARM_DISPATCH_NEXT 1

.Lproperty_own_put:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #15, .Lslow
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lslow
    ldur w8, [x20, #1]
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldr w4, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    movz x10, #0x83eb
    movk x10, #0x80b5, lsl #16
    movk x10, #0x8646, lsl #32
    movk x10, #0x61c8, lsl #48
    uxtw x9, w8
    mul x9, x9, x10
    lsr x9, x9, #32
    add x11, x4, #1
    mul x9, x9, x11
    lsr x9, x9, #32
    add x5, x2, w4, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    sub x9, x5, x9, lsl #2
    ldur w4, [x9, #-4]
.Lproperty_own_put_bucket:
    cbz w4, .Lslow
    sub w6, w4, #1
    add x6, x5, x6, lsl #3
    ldr w7, [x6, #ARM_OFF_JSShapeProperty_atom]
    cmp w7, w8
    b.eq .Lproperty_own_put_found
    ldr w4, [x6]
    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lproperty_own_put_bucket
.Lproperty_own_put_found:
    ldr w7, [x6]
    mov w8, #ARM_PROPERTY_DESC_WRITE_MASK
    and w7, w7, w8
    mov w8, #ARM_PROPERTY_DESC_WRITABLE
    cmp w7, w8
    b.ne .Lslow
    sub w4, w4, #1
    ldr x2, [x0, #ARM_OFF_JSObject_prop]
    add x2, x2, x4, lsl #4
    ldp x10, x11, [x2, #ARM_OFF_JSProperty_u_value]
// The accepted GNU generic hash retains C for referenced old values.
// The separate four-way PIC already owns its qualified nonlast route.
    tbnz x11, #63, .Lslow
    ldp x10, x11, [x21, #-16]
    stp x10, x11, [x2, #ARM_OFF_JSProperty_u_value]
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    sub w9, w9, #1
    stur w9, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #32
    add x20, x20, #5
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x4, tpidr_el0
    add x4, x4, :tprel_hi12:qjs_aarch64_store_counters
    add x4, x4, :tprel_lo12_nc:qjs_aarch64_store_counters
    ldr x5, [x4, #16]
    add x5, x5, #1
    str x5, [x4, #16]
#endif
    ARM_DISPATCH_NEXT 1
