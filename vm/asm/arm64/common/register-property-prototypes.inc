/* Original two-way weak activation/persistent/direct prototype mechanisms.
* Only CURRENT live holders are dereferenced. x5 is one packed atom+slot.
* Fixed VM CFA;the one C fill is proven nonobserving/no-allocation. MIT. */
.Lproperty_proto_object_absent:
    ldr w9, [sp, #ARM_VM_POLICY_OFF]
    tbz w9, #14, .Lproperty_method_live
    ldp x0, x1, [x21, #-16]
    ldur w8, [x20, #1]
    tbnz w8, #31, .Lproperty_proto_fallback
    adrp x9, JS_FrameProtoLoadControl
    add x9, x9, :lo12:JS_FrameProtoLoadControl
    ldarb w9, [x9]
    cbz w9, .Lproperty_proto_miss
    cmp w9, #1
    b.ne .Lproperty_proto_fallback
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.eq .Lproperty_proto_object_holder
    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lproperty_proto_fallback
.Lproperty_proto_object_holder:
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldr x2, [x2, #ARM_OFF_JSShape_proto]
    cbz x2, .Lproperty_proto_fallback
    b .Lproperty_proto_activation
.Lproperty_proto_string:
    ldp x0, x1, [x21, #-16]
    ldur w8, [x20, #1]
    adrp x9, JS_FrameProtoLoadControl
    add x9, x9, :lo12:JS_FrameProtoLoadControl
    ldarb w9, [x9]
    cbz w9, .Lproperty_proto_fill
    cmp w9, #1
    b.ne .Lproperty_proto_fallback
    ldr x2, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x2, [x2, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x2, [x2, #ARM_OFF_JSContext_class_proto]
    add x2, x2, #(ARM_CONST_JS_CLASS_STRING*16)
    ldp x2, x9, [x2]
    cmp x9, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lproperty_proto_fallback
.Lproperty_proto_activation:
    ldr x3, [x19, #ARM_OFF_JSFrameRegisterState_sites]
    cbz x3, .Lproperty_proto_fallback
    lsr x6, x20, #6
    eor x6, x6, x20
    eor x6, x6, x20, lsr #12
    and x6, x6, #7
    add x3, x3, x6, lsl #6
    mov x7, x3
    mov w15, #2
.Lproperty_proto_activation_way:
    ldr x9, [x7, #ARM_OFF_JSFrameProtoHint_pc]
    cmp x9, x20
    b.ne .Lproperty_proto_activation_next
    ldr w9, [x7, #ARM_OFF_JSFrameProtoHint_marker]
    cmp w9, #-1
    b.ne .Lproperty_proto_activation_next
    ldr x9, [x7, #ARM_OFF_JSFrameProtoHint_holder]
    cmp x9, x2
    b.ne .Lproperty_proto_activation_next
    ldr x5, [x7, #ARM_OFF_JSFrameProtoHint_atom_slot]
    lsr x9, x5, #32
    cmp w9, w8
    b.eq .Lproperty_proto_activation_guard
.Lproperty_proto_activation_next:
    subs w15, w15, #1
    b.eq .Lproperty_proto_miss
    add x7, x7, #ARM_SIZE_JSFrameProtoHint
    b .Lproperty_proto_activation_way
.Lproperty_proto_activation_guard:
    cmp w5, #-1
    b.eq .Lproperty_proto_negative
    ldr x4, [x2, #ARM_OFF_JSObject_shape]
    ldr w9, [x4, #ARM_OFF_JSShape_prop_count]
    cmp w5, w9
    b.hs .Lproperty_proto_miss
    mov w10, w5
    add x9, x4, #ARM_OFF_JSShape_prop
    add x9, x9, x10, lsl #3
    ldr w10, [x9, #ARM_OFF_JSShapeProperty_atom]
    cmp w10, w8
    b.ne .Lproperty_proto_miss
    ldr w10, [x9]
    tst w10, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lproperty_proto_fallback
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    mov w14, #2
    sub w14, w14, w15
    add x12, x12, x14, lsl #3
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
#endif
    b .Lproperty_proto_value
.Lproperty_proto_negative:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    b .Lproperty_proto_fallback
.Lproperty_proto_miss:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    ldr x13, [x12, #64]
    add x13, x13, #1
    str x13, [x12, #64]
#endif
// The accepted deep-only probe skips a direct hit so its original
// cache-fill policy remains. Exotics and every miss go to the old try.
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lproperty_proto_persistent
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lproperty_proto_persistent
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldr x2, [x2, #ARM_OFF_JSShape_proto]
    cbz x2, .Lproperty_proto_persistent
    mov w16, #4
    mov w15, #32
    b .Lproperty_live_lookup
.Lproperty_proto_persistent:
    adrp x9, JS_FrameProtoLoadControl
    add x9, x9, :lo12:JS_FrameProtoLoadControl
    ldarb w9, [x9]
    cmp w9, #1
    b.ne .Lproperty_proto_fill
    adrp x9, JS_FrameProtoPersistControl
    add x9, x9, :lo12:JS_FrameProtoPersistControl
    ldarb w9, [x9]
    cmp w9, #1
    b.ne .Lproperty_proto_fill
// Re-derive CURRENT identities;no incoming scratch/cached holder trusted.
    ldp x0, x1, [x21, #-16]
    ldur w8, [x20, #1]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lproperty_proto_persist_object
    cmp x1, #ARM_CONST_JS_TAG_STRING
    b.ne .Lproperty_proto_fill
    ldr x2, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x2, [x2, #ARM_OFF_JSFunctionBytecode_realm]
    ldr x2, [x2, #ARM_OFF_JSContext_class_proto]
    add x2, x2, #(ARM_CONST_JS_CLASS_STRING*16)
    ldp x2, x9, [x2]
    cmp x9, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lproperty_proto_fill
    b .Lproperty_proto_persist_holder
.Lproperty_proto_persist_object:
    ldrb w9, [x0, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.eq .Lproperty_proto_persist_ordinary
    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lproperty_proto_fill
.Lproperty_proto_persist_ordinary:
    ldr x2, [x0, #ARM_OFF_JSObject_shape]
    ldr x2, [x2, #ARM_OFF_JSShape_proto]
.Lproperty_proto_persist_holder:
    cbz x2, .Lproperty_proto_fill
    lsr x6, x20, #6
    eor x6, x6, x20
    eor x6, x6, x20, lsr #12
    and x6, x6, #63
    adrp x7, JS_FrameProtoPersistentHints
    add x7, x7, :lo12:JS_FrameProtoPersistentHints
    add x7, x7, x6, lsl #6
    mov w15, #2
.Lproperty_proto_persist_way:
    add x10, x7, #ARM_OFF_JSFrameProtoPersistentHint_pc
    ldar x9, [x10]
    cmp x9, x20
    b.ne .Lproperty_proto_persist_next
    add x10, x7, #ARM_OFF_JSFrameProtoPersistentHint_marker
    ldar w9, [x10]
    cmp w9, #-1
    b.ne .Lproperty_proto_persist_next
    add x10, x7, #ARM_OFF_JSFrameProtoPersistentHint_holder
    ldar x9, [x10]
    cmp x9, x2
    b.ne .Lproperty_proto_persist_next
    add x10, x7, #ARM_OFF_JSFrameProtoPersistentHint_atom_slot
    ldar x5, [x10]
    lsr x9, x5, #32
    cmp w9, w8
    b.eq .Lproperty_proto_persist_guard
.Lproperty_proto_persist_next:
    subs w15, w15, #1
    b.eq .Lproperty_proto_fill
    add x7, x7, #ARM_SIZE_JSFrameProtoPersistentHint
    b .Lproperty_proto_persist_way
.Lproperty_proto_persist_guard:
// Validate this SAME packed snapshot against the CURRENT live holder.
    ldr x4, [x2, #ARM_OFF_JSObject_shape]
    ldr w9, [x4, #ARM_OFF_JSShape_prop_count]
    cmp w5, w9
    b.hs .Lproperty_proto_fill
    mov w10, w5
    add x9, x4, #ARM_OFF_JSShape_prop
    add x9, x9, x10, lsl #3
    ldr w10, [x9, #ARM_OFF_JSShapeProperty_atom]
    cmp w10, w8
    b.ne .Lproperty_proto_fill
    ldr w10, [x9]
    tst w10, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lproperty_proto_fill
    ldr x3, [x19, #ARM_OFF_JSFrameRegisterState_sites]
    cbz x3, .Lproperty_proto_fill
    ldr x4, [x19, #ARM_OFF_JSFrameRegisterState_cache_next]
    cbz x4, .Lproperty_proto_fill
    lsr x6, x20, #6
    eor x6, x6, x20
    eor x6, x6, x20, lsr #12
    and x6, x6, #7
    add x3, x3, x6, lsl #6
    ldr x9, [x3]
    cbz x9, .Lproperty_proto_promote_first
    add x7, x3, #ARM_SIZE_JSFrameProtoHint
    ldr x9, [x7]
    cbz x9, .Lproperty_proto_promote_second
// Only the fully validated snapshot plus FULL private bucket may bypass
// the original returning try in direct mode. No second descriptor lookup.
    adrp x9, JS_FrameProtoDirectData
    add x9, x9, :lo12:JS_FrameProtoDirectData
    ldrb w9, [x9, #ARM_OFF_JSFrameProtoDirectData_mode]
    cmp w9, #1
    b.ne .Lproperty_proto_fill
    cmp w8, #ARM_CONST_JS_ATOM_length
    b.ne .Lproperty_proto_direct_ready
    cmp x1, #ARM_CONST_JS_TAG_STRING
    b.eq .Lproperty_proto_fill
    ldrh w9, [x0, #ARM_OFF_JSObject_class_id]
    cmp w9, #ARM_CONST_JS_CLASS_ARRAY
    b.eq .Lproperty_proto_fill
.Lproperty_proto_direct_ready:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    cmp x1, #ARM_CONST_JS_TAG_STRING
    cset w14, eq
    add w14, w14, #3
    add x12, x12, x14, lsl #3
    ldr x13, [x12]
    add x13, x13, #1
    str x13, [x12]
#endif
    b .Lproperty_proto_value
.Lproperty_proto_promote_first:
    mov x7, x3
    mov w9, #1
    b .Lproperty_proto_promote
.Lproperty_proto_promote_second:
    mov w9, #0
.Lproperty_proto_promote:
    strb w9, [x4, x6]
    stp x20, x2, [x7, #ARM_OFF_JSFrameProtoHint_pc]
    str x5, [x7, #ARM_OFF_JSFrameProtoHint_atom_slot]
    mov w9, #-1
    str x9, [x7, #ARM_OFF_JSFrameProtoHint_marker]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    ldr x13, [x12, #16]
    add x13, x13, #1
    str x13, [x12, #16]
#endif
    b .Lproperty_proto_retry
.Lproperty_proto_fill:
    str x22, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameAArch64ProtoFill
    cbz w0, .Lproperty_proto_fallback
.Lproperty_proto_retry:
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lproperty_proto_object_absent
    b .Lproperty_proto_string
.Lproperty_proto_fallback:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_proto_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_proto_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lproperty_method_live
    b .Lslow
.Lproperty_proto_value:
    mov w9, w5
    ldr x4, [x2, #ARM_OFF_JSObject_prop]
    add x4, x4, x9, lsl #4
    ldp x10, x11, [x4, #ARM_OFF_JSProperty_u_value]
    cmp x1, #ARM_CONST_JS_TAG_STRING
    cset w16, eq
    add w16, w16, #1
    tbz x11, #63, .Lproperty_proto_commit
    ldr w9, [x10, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    str w9, [x10, #ARM_REF_COUNT_OFFSET]
.Lproperty_proto_commit:
    b .Lproperty_live_commit
