/* Original indexed-storage algorithms; actual measured AAPCS64 VM. MIT. */
#if ARM_HAS_INDEXED
.Lindexed_get_array_el:
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
#if ARM_HAS_STRING_WORKERS
    b.ne .Lstring_index
#else
    b.ne .Lindexed_get_array_el_fallback
#endif
    ldp x2, x3, [x21, #-16]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_get_array_el_fallback
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w8, #1
    b.le .Lindexed_get_array_el_fallback
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lindexed_get_array_el_typed
    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lindexed_get_array_el_own
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_own
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lindexed_get_array_el_dense
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lindexed_get_array_el_dense:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #0]
    add x13, x13, #1
    str x13, [x12, #0]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_own:
    adrp x12, JS_FrameSlowDirectData
    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]
    tbnz w16, #4, .Lindexed_get_array_el_fallback
    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.ne .Lindexed_get_array_el_fallback
    tbnz w2, #31, .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_shape]
    ldr w8, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x5, w8, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    orr w9, w2, #0x80000000
    movz x11, #0x83eb
    movk x11, #0x80b5, lsl #16
    movk x11, #0x8646, lsl #32
    movk x11, #0x61c8, lsl #48
    mul x10, x9, x11
    lsr x10, x10, #32
    add x12, x8, #1
    mul x10, x10, x12
    lsr x10, x10, #32
    sub x11, x5, x10, lsl #2
    ldur w8, [x11, #-4]
.Lindexed_get_array_el_probe:
    cbz w8, .Lindexed_get_array_el_fallback
    add x10, x5, w8, uxtw #3
    ldur w11, [x10, #-4]
    cmp w11, w9
    b.ne .Lindexed_get_array_el_probe_next
.Lindexed_get_array_el_found:
    ldur w11, [x10, #-8]
    tst w11, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lindexed_get_array_el_fallback
    sub w8, w8, #1
    ldr x5, [x0, #ARM_OFF_JSObject_prop]
    add x5, x5, w8, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lindexed_get_array_el_own_value
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lindexed_get_array_el_own_value:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #24]
    add x13, x13, #1
    str x13, [x12, #24]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_probe_next:
    ldur w8, [x10, #-8]
    and w8, w8, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lindexed_get_array_el_probe
.Lindexed_get_array_el_typed:
    cmp w4, #ARM_CONST_JS_CLASS_INT32_ARRAY
    b.eq .Lindexed_get_array_el_i32
    cmp w4, #ARM_CONST_JS_CLASS_UINT8_ARRAY
    b.eq .Lindexed_get_array_el_u8
    cmp w4, #ARM_CONST_JS_CLASS_UINT32_ARRAY
    b.eq .Lindexed_get_array_el_u32
    cmp w4, #ARM_CONST_JS_CLASS_INT8_ARRAY
    b.eq .Lindexed_get_array_el_i8
    cmp w4, #ARM_CONST_JS_CLASS_INT16_ARRAY
    b.eq .Lindexed_get_array_el_i16
    cmp w4, #ARM_CONST_JS_CLASS_UINT16_ARRAY
    b.eq .Lindexed_get_array_el_u16
    cmp w4, #ARM_CONST_JS_CLASS_UINT8C_ARRAY
    b.eq .Lindexed_get_array_el_u8
    b .Lindexed_get_array_el_fallback
.Lindexed_get_array_el_i32:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x5, w2, uxtw #2]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_u8:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrb w6, [x5, w2, uxtw]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_u32:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x5, w2, uxtw #2]
    mov x7, #ARM_CONST_JS_TAG_INT
    tbz w6, #31, .Lindexed_get_array_el_u32_boxed
    ucvtf d0, w6
    fmov x6, d0
    mov x7, #ARM_CONST_JS_TAG_FLOAT64
.Lindexed_get_array_el_u32_boxed:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_i8:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrsb w6, [x5, w2, uxtw]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_i16:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrsh w6, [x5, w2, uxtw #1]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_u16:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrh w6, [x5, w2, uxtw #1]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el_fallback:
#if ARM_HAS_ARGUMENTS
    b .Lget_array_el
#else
    b .Lslow
#endif
.Lindexed_get_array_el2:
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
#if ARM_HAS_STRING_WORKERS
    b.ne .Lstring_index
#else
    b.ne .Lindexed_get_array_el2_fallback
#endif
    ldp x2, x3, [x21, #-16]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_get_array_el2_fallback
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lindexed_get_array_el2_typed
    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lindexed_get_array_el2_own
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_own
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lindexed_get_array_el2_dense
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lindexed_get_array_el2_dense:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #8]
    add x13, x13, #1
    str x13, [x12, #8]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_own:
    adrp x12, JS_FrameSlowDirectData
    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]
    tbnz w16, #4, .Lindexed_get_array_el2_fallback
    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.ne .Lindexed_get_array_el2_fallback
    tbnz w2, #31, .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_shape]
    ldr w8, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x5, w8, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    orr w9, w2, #0x80000000
    movz x11, #0x83eb
    movk x11, #0x80b5, lsl #16
    movk x11, #0x8646, lsl #32
    movk x11, #0x61c8, lsl #48
    mul x10, x9, x11
    lsr x10, x10, #32
    add x12, x8, #1
    mul x10, x10, x12
    lsr x10, x10, #32
    sub x11, x5, x10, lsl #2
    ldur w8, [x11, #-4]
.Lindexed_get_array_el2_probe:
    cbz w8, .Lindexed_get_array_el2_fallback
    add x10, x5, w8, uxtw #3
    ldur w11, [x10, #-4]
    cmp w11, w9
    b.ne .Lindexed_get_array_el2_probe_next
.Lindexed_get_array_el2_found:
    ldur w11, [x10, #-8]
    tst w11, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lindexed_get_array_el2_fallback
    sub w8, w8, #1
    ldr x5, [x0, #ARM_OFF_JSObject_prop]
    add x5, x5, w8, uxtw #4
    ldp x6, x7, [x5]
    tbz x7, #63, .Lindexed_get_array_el2_own_value
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lindexed_get_array_el2_own_value:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #32]
    add x13, x13, #1
    str x13, [x12, #32]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_probe_next:
    ldur w8, [x10, #-8]
    and w8, w8, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lindexed_get_array_el2_probe
.Lindexed_get_array_el2_typed:
    cmp w4, #ARM_CONST_JS_CLASS_INT32_ARRAY
    b.eq .Lindexed_get_array_el2_i32
    cmp w4, #ARM_CONST_JS_CLASS_UINT8_ARRAY
    b.eq .Lindexed_get_array_el2_u8
    cmp w4, #ARM_CONST_JS_CLASS_UINT32_ARRAY
    b.eq .Lindexed_get_array_el2_u32
    cmp w4, #ARM_CONST_JS_CLASS_INT8_ARRAY
    b.eq .Lindexed_get_array_el2_i8
    cmp w4, #ARM_CONST_JS_CLASS_INT16_ARRAY
    b.eq .Lindexed_get_array_el2_i16
    cmp w4, #ARM_CONST_JS_CLASS_UINT16_ARRAY
    b.eq .Lindexed_get_array_el2_u16
    cmp w4, #ARM_CONST_JS_CLASS_UINT8C_ARRAY
    b.eq .Lindexed_get_array_el2_u8
    b .Lindexed_get_array_el2_fallback
.Lindexed_get_array_el2_i32:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x5, w2, uxtw #2]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_u8:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrb w6, [x5, w2, uxtw]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_u32:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x5, w2, uxtw #2]
    mov x7, #ARM_CONST_JS_TAG_INT
    tbz w6, #31, .Lindexed_get_array_el2_u32_boxed
    ucvtf d0, w6
    fmov x6, d0
    mov x7, #ARM_CONST_JS_TAG_FLOAT64
.Lindexed_get_array_el2_u32_boxed:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_i8:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrsb w6, [x5, w2, uxtw]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_i16:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrsh w6, [x5, w2, uxtw #1]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_u16:
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_get_array_el2_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldrh w6, [x5, w2, uxtw #1]
    mov x7, #ARM_CONST_JS_TAG_INT
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #48]
    add x13, x13, #1
    str x13, [x12, #48]
#endif
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_get_array_el2_fallback:
#if ARM_HAS_ARGUMENTS
    b .Lget_array_el2
#else
    b .Lslow
#endif
.Lindexed_put_array_el:
    ldp x0, x1, [x21, #-48]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lindexed_put_array_el_fallback
    ldp x2, x3, [x21, #-32]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w8, #1
    b.le .Lindexed_put_array_el_fallback
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARRAY
    b.ne .Lindexed_put_array_el_typed
    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lindexed_put_array_el_own
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_append
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
    ldp x6, x7, [x5]
    tbnz x7, #63, .Lindexed_put_array_el_fallback
    ldp x6, x7, [x21, #-16]
    stp x6, x7, [x5]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #16]
    add x13, x13, #1
    str x13, [x12, #16]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_own:
    adrp x12, JS_FrameSlowDirectData
    ldrb w16, [x12, :lo12:JS_FrameSlowDirectData]
    tbnz w16, #4, .Lindexed_put_array_el_fallback
    ldrb w5, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w5, #ARM_BIT_JSObject_fast_array_MASK
    b.ne .Lindexed_put_array_el_fallback
    tbnz w2, #31, .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_shape]
    ldr w8, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x5, w8, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    orr w9, w2, #0x80000000
    movz x11, #0x83eb
    movk x11, #0x80b5, lsl #16
    movk x11, #0x8646, lsl #32
    movk x11, #0x61c8, lsl #48
    mul x10, x9, x11
    lsr x10, x10, #32
    add x12, x8, #1
    mul x10, x10, x12
    lsr x10, x10, #32
    sub x11, x5, x10, lsl #2
    ldur w8, [x11, #-4]
.Lindexed_put_array_el_probe:
    cbz w8, .Lindexed_put_array_el_fallback
    add x10, x5, w8, uxtw #3
    ldur w11, [x10, #-4]
    cmp w11, w9
    b.ne .Lindexed_put_array_el_probe_next
.Lindexed_put_array_el_found:
    ldur w11, [x10, #-8]
    mov w10, #ARM_PROPERTY_DESC_WRITE_MASK
    and w11, w11, w10
    mov w10, #ARM_PROPERTY_DESC_WRITABLE
    cmp w11, w10
    b.ne .Lindexed_put_array_el_fallback
    sub w8, w8, #1
    ldr x5, [x0, #ARM_OFF_JSObject_prop]
    add x5, x5, w8, uxtw #4
    ldp x6, x7, [x5]
    tbnz x7, #63, .Lindexed_put_array_el_fallback
    ldp x6, x7, [x21, #-16]
    stp x6, x7, [x5]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #40]
    add x13, x13, #1
    str x13, [x12, #40]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_probe_next:
    ldur w8, [x10, #-8]
    and w8, w8, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lindexed_put_array_el_probe
.Lindexed_put_array_el_typed:
    cmp w4, #ARM_CONST_JS_CLASS_INT32_ARRAY
    b.eq .Lindexed_put_array_el_i32
    cmp w4, #ARM_CONST_JS_CLASS_UINT8_ARRAY
    b.eq .Lindexed_put_array_el_u8
    cmp w4, #ARM_CONST_JS_CLASS_UINT32_ARRAY
    b.eq .Lindexed_put_array_el_u32
    cmp w4, #ARM_CONST_JS_CLASS_INT8_ARRAY
    b.eq .Lindexed_put_array_el_i8
    cmp w4, #ARM_CONST_JS_CLASS_INT16_ARRAY
    b.eq .Lindexed_put_array_el_i16
    cmp w4, #ARM_CONST_JS_CLASS_UINT16_ARRAY
    b.eq .Lindexed_put_array_el_u16
    b .Lindexed_put_array_el_fallback
.Lindexed_put_array_el_i32:
    ldr x7, [x21, #-8]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lindexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x21, #-16]
    str w6, [x5, w2, uxtw #2]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_u8:
    ldr x7, [x21, #-8]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lindexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x21, #-16]
    strb w6, [x5, w2, uxtw]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_u32:
    ldr x7, [x21, #-8]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lindexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x21, #-16]
    str w6, [x5, w2, uxtw #2]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_i8:
    ldr x7, [x21, #-8]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lindexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x21, #-16]
    strb w6, [x5, w2, uxtw]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_i16:
    ldr x7, [x21, #-8]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lindexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x21, #-16]
    strh w6, [x5, w2, uxtw #1]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_u16:
    ldr x7, [x21, #-8]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.ne .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_typed_array]
    ldr x5, [x5, #ARM_OFF_JSTypedArray_buffer]
    ldr x5, [x5, #ARM_OFF_JSObject_u_array_buffer]
    ldrb w5, [x5, #ARM_OFF_JSArrayBuffer_immutable]
    cbnz w5, .Lindexed_put_array_el_fallback
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.hs .Lindexed_put_array_el_fallback
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr w6, [x21, #-16]
    strh w6, [x5, w2, uxtw #1]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #56]
    add x13, x13, #1
    str x13, [x12, #56]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lindexed_put_array_el_fallback:
#if ARM_HAS_ARGUMENTS
    b .Lput_array_el
#else
    b .Lslow
#endif
// Incoming object/index passed dense-array/nonlast-receiver guards.
.Lindexed_append:
    adrp x12, JS_FrameVarargsArrayAppendData
    ldrb w16, [x12, :lo12:JS_FrameVarargsArrayAppendData]
    and w5, w16, #3
    cmp w5, #1
    b.ne .Lput_array_el_fallback_indexed
    ldr w5, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w5
    b.ne .Lput_array_el_fallback_indexed
    tbnz w2, #31, .Lput_array_el_fallback_indexed
    ldrb w5, [x0, #ARM_BIT_JSObject_extensible_BYTE]
    tst w5, #ARM_BIT_JSObject_extensible_MASK
    b.eq .Lput_array_el_fallback_indexed
    ldr x8, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x8, [x8, #ARM_OFF_JSFunctionBytecode_realm]
    ldrb w5, [x8, #ARM_BIT_JSContext_std_array_prototype_BYTE]
    tst w5, #ARM_BIT_JSContext_std_array_prototype_MASK
    b.eq .Lput_array_el_fallback_indexed
    ldr x5, [x0, #ARM_OFF_JSObject_shape]
    ldr x6, [x5, #ARM_OFF_JSShape_proto]
    ldr x7, [x8, #ARM_OFF_JSContext_class_proto]
    ldr x7, [x7, #(ARM_CONST_JS_CLASS_ARRAY*16)]
    cmp x6, x7
    b.ne .Lput_array_el_fallback_indexed
    ldr x5, [x0, #ARM_OFF_JSObject_prop]
    ldr x6, [x5, #8]
    cmp x6, #ARM_CONST_JS_TAG_INT
    b.ne .Lput_array_el_fallback_indexed
    add w4, w2, #1
    ldr w6, [x0, #ARM_OFF_JSObject_u_array_u1_size]
    cmp w4, w6
    b.hi .Lput_array_el_fallback_indexed
    ldr w6, [x5]
    cmp w4, w6
    b.ls .Lindexed_append_allowed
    ldr x7, [x0, #ARM_OFF_JSObject_shape]
    ldr w10, [x7, #ARM_OFF_JSShape_prop_hash_mask]
    add x7, x7, w10, uxtw #2
    ldr w7, [x7, #(ARM_OFF_JSShape_hash_table + 4)]
    tst w7, #ARM_PROPERTY_DESC_WRITABLE
    b.eq .Lput_array_el_fallback_indexed
.Lindexed_append_allowed:
    tbz w16, #2, .Lindexed_append_commit
    adrp x12, JS_FrameVarargsArrayAppendData
    add x12, x12, :lo12:JS_FrameVarargsArrayAppendData
    add x12, x12, #ARM_OFF_JSFrameArrayAppendData_hits
.Lindexed_append_observe:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lindexed_append_observe
.Lindexed_append_commit:
    ldr x7, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x7, x7, w2, uxtw #4
    ldp x10, x11, [x21, #-16]
    stp x10, x11, [x7]
    str w4, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w4, w6
    b.ls .Lindexed_append_stored
    mov w4, w4
    stp x4, xzr, [x5]
.Lindexed_append_stored:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #64]
    add x13, x13, #1
    str x13, [x12, #64]
#endif
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lput_array_el_fallback_indexed:
    b .Lslow

// Source-owned pure proof; no allocator,user call,poll failure or last release.
.Lindexed_instanceof:
    ldr x0, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x0, [x0, #ARM_OFF_JSFunctionBytecode_realm]
    mov x1, x21
    bl JS_FrameSlowDirectTryInstanceOfLeaf
    cbz w0, .Lslow
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_indexed_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_indexed_counters
    ldr x13, [x12, #72]
    add x13, x13, #1
    str x13, [x12, #72]
#endif
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
#endif
