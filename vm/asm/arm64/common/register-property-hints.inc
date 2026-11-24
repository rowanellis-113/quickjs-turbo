/* Source-owned bytecode-lifetime own slots and live-slot borrowed PICs. MIT.
* Fixed VM CFA;no call,allocation,last release or safepoint. All failed
* borrowed proofs reconstruct the original owning operand before dispatch. */
.Lproperty_own_try:
    cmp w17, #4
    b.eq .Lproperty_borrow_fallback
    cmp w17, #3
    b.eq .Lproperty_own_put
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldarb w9, [x9]
    cmp w9, #1
    b.ne .Lproperty_own_original
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lproperty_method_legacy_fallback
    cmp w17, #2
    b.eq .Lproperty_hint_receiver
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lslow
.Lproperty_hint_receiver:
    ldr x2, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr w3, [x2, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w3, #2048
    b.hi .Lproperty_own_original
    add w3, w3, #3
    and w3, w3, #0xfffffffc
    add x3, x20, x3
    and x3, x3, #0xfffffffffffffffc
    ldur w8, [x20, #1]
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldr w4, [x3]
    sub w4, w4, #1
    ldr w5, [x2, #ARM_OFF_JSShape_prop_count]
    cmp w4, w5
    b.hs .Lproperty_hint_hash
    ldr w5, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x2, w5, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    add x5, x5, x4, lsl #3
    ldr w6, [x5, #ARM_OFF_JSShapeProperty_atom]
    cmp w6, w8
    b.ne .Lproperty_hint_hash
    ldr w6, [x5]
    tst w6, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lproperty_method_legacy_fallback
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_hint_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_hint_counters
    sub w13, w17, #1
    add x12, x12, x13, lsl #3
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
#endif
    b .Lproperty_hint_load
.Lproperty_own_original:
// Original no-hint native hash path:OFF and long bytecodes must not
// read a tail or lose the accepted generic own-data mechanism.
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lproperty_method_legacy_fallback
    cmp w17, #2
    b.eq .Lproperty_own_original_receiver
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lslow
.Lproperty_own_original_receiver:
    mov x3, #0
    ldur w8, [x20, #1]
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
.Lproperty_hint_hash:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_hint_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_hint_counters
    ldr x13, [x12, #24]
    add x13, x13, #1
    str x13, [x12, #24]
#endif
    ldr w4, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x2, w4, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
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
    sub x10, x5, x9, lsl #2
    ldur w4, [x10, #-4]
.Lproperty_hint_bucket:
    cbz w4, .Lproperty_hint_absent
    sub w6, w4, #1
    add x6, x5, x6, lsl #3
    ldr w7, [x6, #ARM_OFF_JSShapeProperty_atom]
    cmp w7, w8
    b.eq .Lproperty_hint_found
    ldr w4, [x6]
    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lproperty_hint_bucket
.Lproperty_hint_absent:
    cmp w17, #2
    b.eq .Lproperty_proto_object_absent
    b .Lproperty_method_legacy_fallback
.Lproperty_hint_found:
    ldr w7, [x6]
    tst w7, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lproperty_method_legacy_fallback
    cbz x3, .Lproperty_own_original_found
    str w4, [x3]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_hint_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_hint_counters
    ldr x13, [x12, #16]
    add x13, x13, #1
    str x13, [x12, #16]
#endif
.Lproperty_own_original_found:
    sub w4, w4, #1
.Lproperty_hint_load:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    cbnz x3, .Lproperty_hint_value
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_hint_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_hint_counters
    add w13, w17, #5
    add x12, x12, x13, lsl #3
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
.Lproperty_hint_value:
#endif
    ldr x2, [x0, #ARM_OFF_JSObject_prop]
    add x2, x2, x4, lsl #4
    ldp x10, x11, [x2, #ARM_OFF_JSProperty_u_value]
    tbz x11, #63, .Lproperty_hint_commit
    ldur w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    stur w9, [x10, #ARM_REF_COUNT_OFFSET]
.Lproperty_hint_commit:
    cmp w17, #2
    b.eq .Lproperty_hint_method
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    sub w9, w9, #1
    stur w9, [x0, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x21, #-16]
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.Lproperty_hint_method:
    stp x10, x11, [x21], #16
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1

.Lproperty_pic_slow:
    cmp w17, #4
    b.ne .Lslow
.Lproperty_borrow_fallback:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_hint_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_hint_counters
    ldr x13, [x12, #40]
    add x13, x13, #1
    str x13, [x12, #40]
#endif
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    stur w9, [x0, #ARM_REF_COUNT_OFFSET]
    mov x1, #ARM_CONST_JS_TAG_OBJECT
    stp x0, x1, [x21], #16
    b .Lget_field

.Lproperty_borrow_entry:
#if ARM_HAS_PROPERTY_IC
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldrb w9, [x9, #ARM_OFF_JSFrameOwnBytecodeControl_local_field]
    cmp w9, #1
    b.ne .Lproperty_borrow_fallback
    mov w17, #4
    b .Lproperty_probe
#else
    b .Lproperty_borrow_fallback
#endif
