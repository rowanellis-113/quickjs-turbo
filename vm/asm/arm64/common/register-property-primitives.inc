/* Source-owned live property kernels;fixed VM CFA,no allocation/last release.
* x0/x1 receiver,x2 live holder,x3 shape/slot,w8 atom,w16 mode.
* Number's once-only cold policy call uses standard void(void) AAPCS64.
* Every other miss preserves original PC/SP and all owning operands. MIT. */
.Lproperty_method_legacy:
    b .Lproperty_own_try
.Lproperty_method_legacy_fallback:
    cmp w17, #2
    b.ne .Lslow
.Lproperty_method_live:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #13, .Lslow
    ldp x0, x1, [x21, #-16]
    ldur w8, [x20, #1]
    tbnz w8, #31, .Lslow
    cmp x1, #ARM_CONST_JS_TAG_STRING
    b.eq .Lproperty_string_method
    cmp x1, #ARM_CONST_JS_TAG_INT
    b.eq .Lproperty_number_method
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .Lproperty_number_method
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.eq .Lproperty_object_live
    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lslow
.Lproperty_object_live:
    mov x2, x0
    mov w16, #1
    mov w15, #33
    b .Lproperty_live_lookup
.Lproperty_string_method:
    cmp w8, #ARM_CONST_JS_ATOM_length
    b.eq .Lslow
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #12, .Lslow
    tbnz w9, #14, .Lproperty_proto_string
    mov w16, #2
    ldr x2, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x2, [x2, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x2, [x2, #ARM_OFF_JSContext_class_proto]
    add x2, x2, #(ARM_CONST_JS_CLASS_STRING*16)
    ldp x2, x3, [x2]
    cmp x3, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    mov w15, #1
    b .Lproperty_live_lookup
.Lproperty_number_method:
    adrp x9, JS_FrameNumberPropertyControl
    add x9, x9, :lo12:JS_FrameNumberPropertyControl
    ldarb w10, [x9]
    cbz w10, .Lproperty_number_cold
    cmp w10, #1
    b.ne .Lslow
    mov w16, #3
    ldr x2, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x2, [x2, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x2, [x2, #ARM_OFF_JSContext_class_proto]
    add x2, x2, #(ARM_CONST_JS_CLASS_NUMBER*16)
    ldp x2, x3, [x2]
    cmp x3, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldrh w9, [x2, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_NUMBER
    b.eq .Lproperty_number_holder
    cmp w9, #ARM_CONST_JS_CLASS_OBJECT
    b.ne .Lslow
.Lproperty_number_holder:
    mov w15, #1
.Lproperty_live_lookup:
    ldr x3, [x2, #ARM_OFF_JSObject_shape]
    ldr w4, [x3, #ARM_OFF_JSShape_prop_hash_mask]
    and w4, w8, w4
    neg x4, x4
    add x4, x3, x4, lsl #2
    ldur w4, [x4, #-4]
    add x5, x3, #ARM_OFF_JSShape_prop
.Lproperty_live_bucket:
    cbz w4, .Lproperty_live_absent
    sub w6, w4, #1
    add x6, x5, x6, lsl #3
    ldr w7, [x6, #ARM_OFF_JSShapeProperty_atom]
    cmp w7, w8
    b.eq .Lproperty_live_found
    ldr w4, [x6]
    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lproperty_live_bucket
.Lproperty_live_found:
    cmp w16, #4
    b.ne .Lproperty_live_descriptor
    cmp w15, #32
    b.eq .Lproperty_proto_persistent
.Lproperty_live_descriptor:
    ldr w7, [x6]
    tst w7, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lproperty_live_miss
    cmp w16, #4
    b.ne .Lproperty_live_value
    mov w16, #1
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    ldr x13, [x12, #80]
    add x13, x13, #1
    str x13, [x12, #80]
#endif
.Lproperty_live_value:
    sub w4, w4, #1
    ldr x3, [x2, #ARM_OFF_JSObject_prop]
    add x3, x3, x4, lsl #4
    ldp x10, x11, [x3, #ARM_OFF_JSProperty_u_value]
    tbz x11, #63, .Lproperty_live_commit
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
.Lproperty_live_commit:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    cmp w16, #1
    b.ne .Lproperty_counter_primitive
    cmp x2, x0
    cset w13, ne
    b .Lproperty_counter_method
.Lproperty_counter_primitive:
    mov w13, w16
.Lproperty_counter_method:
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_primitive_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_primitive_counters
    add x12, x12, x13, lsl #3
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
#endif
    stp x10, x11, [x21], #16
    add x20, x20, #5
    ARM_DISPATCH_NEXT 1
.Lproperty_live_absent:
    cmp w16, #4
    b.eq .Lproperty_live_absent_object
    cmp w16, #1
    b.ne .Lproperty_live_miss
.Lproperty_live_absent_object:
    cmp x2, x0
    b.ne .Lproperty_live_proto_absent
    ldrh w9, [x2, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.eq .Lproperty_live_next
.Lproperty_live_proto_absent:
    ldrb w9, [x2, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lproperty_live_miss
.Lproperty_live_next:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_primitive_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_primitive_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    subs w15, w15, #1
    b.eq .Lproperty_live_miss
    ldr x2, [x3, #ARM_OFF_JSShape_proto]
    cbz x2, .Lproperty_live_miss
    b .Lproperty_live_lookup
.Lproperty_live_miss:
    cmp w16, #4
    b.eq .Lproperty_proto_persistent
    b .Lslow
.Lproperty_number_cold:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_primitive_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_primitive_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
// Pure immutable policy initialization;no runtime/JS/GC access. All VM
// cached registers are callee-saved. Restart to reload all volatile inputs.
    add x27, x27, #1
    bl JS_FrameNumberPropertyConfigure
    b .Lproperty_method_live
.Lget_length:
#if ARM_HAS_ARGUMENTS
    b .Larguments_length
.Lget_length_original:
#endif
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #13, .Lslow
    adrp x9, JS_FrameLengthData
    add x9, x9, :lo12:JS_FrameLengthData
    ldarb w9, [x9]
    cmp w9, #1
    b.ne .Lslow
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_STRING
    b.eq .Lproperty_string_length
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lslow
    ldrb w9, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w9, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lslow
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lslow
    ldr x2, [x0, #ARM_OFF_JSObject_prop]
    ldp x10, x11, [x2, #ARM_OFF_JSProperty_u_value]
    cmp x11, #ARM_CONST_JS_TAG_INT
    b.eq .Lproperty_array_length
    cmp x11, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
.Lproperty_array_length:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_primitive_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_primitive_counters
    ldr x13, [x12, #40]
    add x13, x13, #1
    str x13, [x12, #40]
#endif
    sub w9, w9, #1
    str w9, [x0, #ARM_REF_COUNT_OFFSET]
    stp x10, x11, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lproperty_string_length:
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lslow
    ldr w10, [x0, #ARM_BIT_JSString_len_BYTE]
    and w10, w10, #0x7fffffff
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_primitive_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_primitive_counters
    ldr x13, [x12, #32]
    add x13, x13, #1
    str x13, [x12, #32]
#endif
    sub w9, w9, #1
    str w9, [x0, #ARM_REF_COUNT_OFFSET]
    mov x11, #ARM_CONST_JS_TAG_INT
    stp x10, x11, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
