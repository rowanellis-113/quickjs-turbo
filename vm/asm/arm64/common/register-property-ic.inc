/* Bytecode-owned by-id PIC hits over actual target types. MIT.
* x0 receiver,x5 way,x6 predecessor,x7 slot/holder,x8/x16 value,w17 kind.
* No call,allocation,last release or new frame. Misses preserve PC/SP/owners.
* Primary+three secondary ways,epoch/shape proofs and weak transition edges
* follow the accepted property_ic_native.py and common C cache lifetime. */
#if ARM_HAS_PROPERTY_IC
.Lget_field:
    mov w17, #1
    ldp x0, x1, [x21, #-16]
    b .Lproperty_probe
.Lget_field2:
    mov w17, #2
    ldp x0, x1, [x21, #-16]
    b .Lproperty_probe
.Lput_field:
    mov w17, #3
    ldp x0, x1, [x21, #-32]
.Lproperty_probe:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #11, .Lproperty_method_legacy
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lproperty_method_legacy
    cmp w17, #2
    b.eq .Lproperty_receiver_ready
    cmp w17, #4
    b.eq .Lproperty_receiver_ready
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lproperty_pic_slow
.Lproperty_receiver_ready:
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lproperty_method_legacy
    ldr x2, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x3, [x2, #ARM_OFF_JSFunctionBytecode_property_ic]
    cmp x3, #4095
    b.ls .Lproperty_ic_cold
    ldr x4, [x2, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    sub x4, x20, x4
    lsr x4, x4, #2
    add x3, x3, #ARM_OFF_JSPropertyIC_map
    ldr x5, [x3, x4, lsl #3]
    ldr x6, [x0, #ARM_OFF_JSObject_shape]
    cbz x5, .Lproperty_method_legacy
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_shape]
    mov w2, #0
    cmp x7, x6
    b.ne .Lproperty_site_miss
.Lproperty_matched:
    cmp w17, #3
    b.eq .Lproperty_put
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w10, #ARM_CONST_JS_IC_OWN
    b.ne .Lproperty_non_own
.Lproperty_own:
    mov x7, x0
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #40]
    add x15, x15, #1
    str x15, [x14, #40]
#endif
.Lproperty_load:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x7, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    ldp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    tbz x16, #63, .Lproperty_get_commit
    ldur w9, [x8, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    stur w9, [x8, #ARM_REF_COUNT_OFFSET]
.Lproperty_get_commit:
    cbz w2, .Lproperty_get_primary
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
#endif
.Lproperty_get_primary:
    cmp w17, #2
    b.eq .Lproperty_method_commit
    cmp w17, #4
    b.eq .Lproperty_borrow_commit
    ldur w9, [x0, #ARM_REF_COUNT_OFFSET]
    sub w9, w9, #1
    stur w9, [x0, #ARM_REF_COUNT_OFFSET]
    stp x8, x16, [x21, #-16]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #0]
    add x15, x15, #1
    str x15, [x14, #0]
#endif
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.Lproperty_method_commit:
    stp x8, x16, [x21], #16
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #8]
    add x15, x15, #1
    str x15, [x14, #8]
#endif
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.Lproperty_borrow_commit:
    stp x8, x16, [x21], #16
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14]
    add x15, x15, #1
    str x15, [x14]
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_hint_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_hint_counters
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
#endif
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.Lproperty_non_own:
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x9, #ARM_OFF_JSRuntime_property_ic_epoch]
    cbz x11, .Lproperty_pic_slow
    ldr x12, [x5, #ARM_OFF_JSPropertyICWay_epoch]
    cmp x11, x12
    b.ne .Lproperty_pic_slow
    cmp w10, #ARM_CONST_JS_IC_PROTO
    b.ne .Lproperty_check_unset
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_holder]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #48]
    add x15, x15, #1
    str x15, [x14, #48]
#endif
    b .Lproperty_load
.Lproperty_check_unset:
    cmp w10, #ARM_CONST_JS_IC_UNSET
    b.ne .Lproperty_check_getter
.Lproperty_unset:
    mov x8, #0
    mov x16, #ARM_CONST_JS_TAG_UNDEFINED
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #56]
    add x15, x15, #1
    str x15, [x14, #56]
#endif
    b .Lproperty_get_commit
.Lproperty_check_getter:
    ldr x11, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x11, [x11, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    cmp w9, #2
    b.le .Lproperty_pic_slow
    cmp w10, #7
    b.ne .Lproperty_check_getter_bool
    sub w9, w9, #1
    str w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    mov x7, x0
    b .Lproperty_load
.Lproperty_check_getter_bool:
    cmp w10, #8
    b.ne .Lproperty_pic_slow
    sub w9, w9, #1
    str w9, [x11, #ARM_OFF_JSContext_interrupt_counter]
    ldr w8, [x5, #ARM_OFF_JSPropertyICWay_slot]
    mov x16, #1
    b .Lproperty_get_commit
.Lproperty_put:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_kind]
    cmp w10, #ARM_CONST_JS_IC_REPLACE
    b.ne .Lproperty_transition
.Lproperty_replace:
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x0, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    ldp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    tbz x16, #63, .Lproperty_replace_safe
    ldur w12, [x8, #ARM_REF_COUNT_OFFSET]
    cmp w12, #1
    b.le .Lproperty_pic_slow
    cmp x8, x0
    b.ne .Lproperty_replace_nonlast
    cmp w12, #2
    b.le .Lproperty_pic_slow
.Lproperty_replace_nonlast:
    sub w12, w12, #1
    stur w12, [x8, #ARM_REF_COUNT_OFFSET]
.Lproperty_replace_safe:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #16]
    add x15, x15, #1
    str x15, [x14, #16]
#endif
.Lproperty_store:
    ldp x8, x16, [x21, #-16]
    stp x8, x16, [x7, #ARM_OFF_JSProperty_u_value]
    ldur w12, [x0, #ARM_REF_COUNT_OFFSET]
    sub w12, w12, #1
    stur w12, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #32
    cbz w2, .Lproperty_put_primary
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #32]
    add x15, x15, #1
    str x15, [x14, #32]
#endif
.Lproperty_put_primary:
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.Lproperty_transition:
    cmp w10, #ARM_CONST_JS_IC_TRANSITION
    b.ne .Lproperty_pic_slow
    ldrb w10, [x0, #ARM_BIT_JSObject_extensible_BYTE]
    tst w10, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lproperty_pic_slow
    ldrb w10, [x0, #ARM_BIT_JSObject_is_prototype_BYTE]
    tst w10, #ARM_BIT_JSObject_is_prototype_MASK
    b.ne .Lproperty_pic_slow
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x11, [x9, #ARM_OFF_JSRuntime_property_ic_epoch]
    cbz x11, .Lproperty_pic_slow
    ldr x12, [x5, #ARM_OFF_JSPropertyICWay_epoch]
    cmp x11, x12
    b.ne .Lproperty_pic_slow
    ldr x7, [x5, #ARM_OFF_JSPropertyICWay_transition]
    ldrb w13, [x7, #ARM_OFF_JSShape_is_hashed]
    tst w13, #ARM_CONST_JS_IC_PROTO_WEAK
    b.eq .Lproperty_successor_active
    bic w13, w13, #ARM_CONST_JS_IC_PROTO_WEAK
    strb w13, [x7, #ARM_OFF_JSShape_is_hashed]
    ldr x11, [x7, #ARM_OFF_JSShape_proto]
    ldur w12, [x11, #ARM_REF_COUNT_OFFSET]
    add w12, w12, #1
    stur w12, [x11, #ARM_REF_COUNT_OFFSET]
.Lproperty_successor_active:
    ldur w12, [x7, #ARM_REF_COUNT_OFFSET]
    add w12, w12, #1
    stur w12, [x7, #ARM_REF_COUNT_OFFSET]
    str x7, [x0, #ARM_OFF_JSObject_shape]
    ldur w12, [x6, #ARM_REF_COUNT_OFFSET]
    sub w12, w12, #1
    stur w12, [x6, #ARM_REF_COUNT_OFFSET]
    ldr w11, [x9, #ARM_OFF_JSRuntime_property_ic_gc_mode]
    tst w11, #ARM_CONST_JS_IC_RETAIN_ORPHANS
    b.ne .Lproperty_transition_committed
    ldr w13, [x6, #ARM_OFF_JSShape_is_hashed]
    lsr w13, w13, #8
    cmp w12, w13
    b.ne .Lproperty_transition_committed
    ldr x11, [x6, #ARM_OFF_JSShape_proto]
    cbz x11, .Lproperty_transition_committed
    ldrb w13, [x6, #ARM_OFF_JSShape_is_hashed]
    orr w13, w13, #ARM_CONST_JS_IC_PROTO_WEAK
    strb w13, [x6, #ARM_OFF_JSShape_is_hashed]
// The successor owns the same prototype before weakening the predecessor.
// This decrement cannot release its last reference or execute a callback.
    ldur w12, [x11, #ARM_REF_COUNT_OFFSET]
    sub w12, w12, #1
    stur w12, [x11, #ARM_REF_COUNT_OFFSET]
.Lproperty_transition_committed:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_property_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_property_counters
    ldr x15, [x14, #24]
    add x15, x15, #1
    str x15, [x14, #24]
#endif
    ldr w10, [x5, #ARM_OFF_JSPropertyICWay_slot]
    ldr x7, [x0, #ARM_OFF_JSObject_prop]
    add x7, x7, x10, lsl #4
    b .Lproperty_store
.Lproperty_site_miss:
    ldrb w9, [x5, #ARM_OFF_JSPropertyICSite_megamorphic]
    cbnz w9, .Lproperty_method_legacy
    ldr x7, [x5, #ARM_OFF_JSPropertyICSite_secondary]
    cbz x7, .Lproperty_no_cache
    ldr x9, [x7, #ARM_OFF_JSPropertyICWay_shape]
    cmp x9, x6
    b.eq .Lproperty_secondary
    add x7, x7, #ARM_SIZE_JSPropertyICWay
    ldr x9, [x7, #ARM_OFF_JSPropertyICWay_shape]
    cmp x9, x6
    b.eq .Lproperty_secondary
    add x7, x7, #ARM_SIZE_JSPropertyICWay
    ldr x9, [x7, #ARM_OFF_JSPropertyICWay_shape]
    cmp x9, x6
    b.ne .Lproperty_no_cache
.Lproperty_secondary:
    mov x5, x7
    mov w2, #1
    b .Lproperty_matched
.Lproperty_ic_cold:
    cmp x3, #1
    b.eq .Lproperty_method_legacy
.Lproperty_no_cache:
// An active cache must learn its first hashed shape through original C.
// Core-IC OFF retains the original live method path,independent of PICs.
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr w9, [x9, #ARM_OFF_JSRuntime_property_ic_mode]
    cmp w9, #1
    b.ne .Lproperty_method_legacy
    ldr x9, [x0, #ARM_OFF_JSObject_shape]
    ldrb w9, [x9, #ARM_OFF_JSShape_is_hashed]
    cbz w9, .Lproperty_method_legacy
    b .Lproperty_pic_slow
#else
.Lput_field:
    b .Lproperty_own_put
.Lget_field:
    mov w17, #1
    b .Lproperty_own_try
.Lget_field2:
    mov w17, #2
    b .Lproperty_own_try
#endif
