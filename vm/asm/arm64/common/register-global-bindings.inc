/* Complete accepted GNU global cells,activation hints,undefined arithmetic
* and resolved-cell Symbol continuation over measured ARM types. MIT. */
#if ARM_HAS_GLOBAL_BINDING
.macro ARM_GLOBAL_EVENT offset
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_global_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_global_counters
    ldr x15, [x14, #\offset]
    add x15, x15, #1
    str x15, [x14, #\offset]
#endif
.endm
.Lget_var:
    adrp x9, JS_FrameGlobalBindingControl
    add x9, x9, :lo12:JS_FrameGlobalBindingControl
    ldarb w9, [x9]
    cmp w9, #1
    b.eq .Lglobal_enabled
    cbz w9, .Lglobal_cold
    mov w16, #0
    b .Lglobal_cell_probe
.Lglobal_enabled:
    mov w16, #1
.Lglobal_cell_probe:
    ldr x11, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x0, [x11, #ARM_OFF_JSFunctionBytecode_realm]
#if ARM_HAS_PROPERTY_IC
    ldr x2, [x11, #ARM_OFF_JSFunctionBytecode_property_ic]
    cmp x2, #4095
    b.hi .Lglobal_cell_metadata
    cmp x2, #1
    b.eq .Lglobal_after_cell
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr w9, [x9, #ARM_OFF_JSRuntime_property_ic_mode]
    cmp w9, #1
    b.eq .Lglobal_cell_relink
    b .Lglobal_after_cell
.Lglobal_cell_metadata:
    ldr x3, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    sub x3, x20, x3
    lsr x3, x3, #2
    add x2, x2, #ARM_OFF_JSPropertyIC_map
    ldr x3, [x2, x3, lsl #3]
    tbnz x3, #0, .Lglobal_cell_hit
    cbz x3, .Lglobal_cell_relink
    b .Lglobal_after_cell
.Lglobal_cell_hit:
    and x4, x3, #0xfffffffffffffffc
    ldp x12, x13, [x4]
    cmp x13, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.ne .Lglobal_cell_ready
    tbz x3, #1, .Lglobal_after_cell
.Lglobal_cell_ready:
    ARM_GLOBAL_EVENT 0
    cbnz w16, .Lglobal_symbol_condition
    b .Lglobal_ready
.Lglobal_cell_relink:
    ARM_GLOBAL_EVENT 8
    b .Lglobal_fallback
#endif
.Lglobal_after_cell:
    cbz w16, .Lglobal_resolve
    ldr w9, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w9, #4096
    b.ls .Lglobal_activation
    adrp x9, JS_FrameLargeGlobalMode
    add x9, x9, :lo12:JS_FrameLargeGlobalMode
    ldar w9, [x9]
    cmp w9, #1
    b.ne .Lglobal_activation
    ARM_GLOBAL_EVENT 80
    mov w16, #0
    b .Lglobal_resolve
.Lglobal_activation:
    ldur w8, [x20, #1]
    tbnz w8, #31, .Lglobal_fallback
    ldr x3, [x19, #ARM_OFF_JSFrameRegisterState_sites]
    cbz x3, .Lglobal_fallback
    lsr x4, x20, #6
    eor x4, x4, x20
    eor x4, x4, x20, lsr #12
    and x4, x4, #7
    add x3, x3, x4, lsl #6
    mov w17, #2
.Lglobal_activation_way:
    ldr x9, [x3, #ARM_OFF_JSFrameGlobalHint_pc]
    cmp x9, x20
    b.ne .Lglobal_activation_next
    ldr x4, [x3, #ARM_OFF_JSFrameGlobalHint_atom_slot]
    lsr x9, x4, #32
    cmp w9, w8
    b.ne .Lglobal_activation_next
    ldr w7, [x3, #ARM_OFF_JSFrameGlobalHint_marker]
    cmp w7, #-2
    b.eq .Lglobal_global_guard
    cmp w7, #-3
    b.eq .Lglobal_lexical_guard
.Lglobal_activation_next:
    subs w17, w17, #1
    b.eq .Lglobal_miss
    add x3, x3, #ARM_SIZE_JSFrameGlobalHint
    b .Lglobal_activation_way
.Lglobal_global_guard:
    ldr x6, [x3, #ARM_OFF_JSFrameGlobalHint_arithmetic]
    ldr x1, [x0, #ARM_OFF_JSContext_global_var_obj]
    ldr x2, [x1, #ARM_OFF_JSObject_shape]
    ldr w9, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    cmp w9, w6
    b.ne .Lglobal_miss
    add x9, x2, w9, uxtw #2
    add x9, x9, #(ARM_OFF_JSShape_hash_table + 4)
    lsr x10, x6, #32
    sub x9, x9, x10, lsl #2
    ldur w9, [x9, #-4]
    cbnz w9, .Lglobal_miss
    ldr x1, [x0, #ARM_OFF_JSContext_global_obj]
    b .Lglobal_hint_guard
.Lglobal_lexical_guard:
    ldr x1, [x0, #ARM_OFF_JSContext_global_var_obj]
.Lglobal_hint_guard:
    ldr x2, [x1, #ARM_OFF_JSObject_shape]
    ldr w9, [x2, #ARM_OFF_JSShape_prop_count]
    cmp w4, w9
    b.hs .Lglobal_miss
    ldr w9, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x2, w9, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    add x5, x5, w4, uxtw #3
    ldr w9, [x5, #ARM_OFF_JSShapeProperty_atom]
    cmp w9, w8
    b.ne .Lglobal_miss
    ldr w9, [x5]
    tst w9, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lglobal_fallback
    cmp w7, #-3
    b.eq .Lglobal_lexical_hit
    ARM_GLOBAL_EVENT 16
    b .Lglobal_load
.Lglobal_lexical_hit:
    ARM_GLOBAL_EVENT 24
    b .Lglobal_load
.Lglobal_miss:
    ARM_GLOBAL_EVENT 48
    cmp w8, #ARM_CONST_JS_ATOM_undefined
    b.ne .Lglobal_resolve
    adrp x9, JS_FrameGlobalUndefinedControl
    add x9, x9, :lo12:JS_FrameGlobalUndefinedControl
    ldarb w9, [x9]
    cmp w9, #1
    b.ne .Lglobal_resolve
    ldr x1, [x0, #ARM_OFF_JSContext_global_var_obj]
    ldr x2, [x1, #ARM_OFF_JSObject_shape]
    ldr w4, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    tbnz w4, #31, .Lglobal_fallback
    adrp x5, JS_FrameGlobalUndefinedArithmetic
    add x5, x5, :lo12:JS_FrameGlobalUndefinedArithmetic
    ldar x6, [x5]
    cmp w6, w4
    b.eq .Lglobal_undefined_bucket
    movz x10, #0x83eb
    movk x10, #0x80b5, lsl #16
    movk x10, #0x8646, lsl #32
    movk x10, #0x61c8, lsl #48
    mov w9, #ARM_CONST_JS_ATOM_undefined
    mul x9, x9, x10
    lsr x9, x9, #32
    add x11, x4, #1
    mul x9, x9, x11
    lsr x9, x9, #32
    orr x6, x4, x9, lsl #32
    stlr x6, [x5]
    ARM_GLOBAL_EVENT 72
.Lglobal_undefined_bucket:
    add x10, x2, w4, uxtw #2
    add x10, x10, #(ARM_OFF_JSShape_hash_table + 4)
    lsr x9, x6, #32
    sub x10, x10, x9, lsl #2
    ldur w9, [x10, #-4]
    cbz w9, .Lglobal_undefined_empty
    ARM_GLOBAL_EVENT 64
    mov w16, #0
    b .Lglobal_resolve
.Lglobal_undefined_empty:
    ARM_GLOBAL_EVENT 56
.Lglobal_resolve:
    ldur w8, [x20, #1]
    tbnz w8, #31, .Lglobal_fallback
    ldr x1, [x0, #ARM_OFF_JSContext_global_var_obj]
    mov w7, #-3
    ldrb w9, [x1, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lglobal_fallback
    ldr x2, [x1, #ARM_OFF_JSObject_shape]
    ldr w4, [x2, #ARM_OFF_JSShape_prop_hash_mask]
    tbnz w4, #31, .Lglobal_fallback
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
    orr x6, x4, x9, lsl #32
    add x5, x2, w4, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    sub x9, x5, x9, lsl #2
    ldur w4, [x9, #-4]
    cbnz w4, .Lglobal_hash_probe
.Lglobal_hash_object:
    ldp x1, x9, [x0, #ARM_OFF_JSContext_global_obj]
    cmp x9, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lglobal_fallback
    ldrb w9, [x1, #ARM_BIT_JSObject_is_exotic_BYTE]
    tst w9, #ARM_BIT_JSObject_is_exotic_MASK
    b.ne .Lglobal_fallback
    mov w7, #-2
    ldr x2, [x1, #ARM_OFF_JSObject_shape]
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
.Lglobal_hash_probe:
    cbz w4, .Lglobal_hash_absent
    sub w9, w4, #1
    add x9, x5, x9, lsl #3
    ldr w10, [x9, #ARM_OFF_JSShapeProperty_atom]
    cmp w10, w8
    b.eq .Lglobal_hash_found
    ldr w4, [x9]
    and w4, w4, #ARM_PROPERTY_DESC_NEXT_MASK
    b .Lglobal_hash_probe
.Lglobal_hash_absent:
    cmp w7, #-3
    b.ne .Lglobal_fallback
    cbz w16, .Lglobal_hash_object
// A nonempty lexical bucket cannot supply an absence hint. Preserve
// the accepted base resolver,including its complete global lookup.
    mov w16, #0
    b .Lglobal_resolve
.Lglobal_hash_found:
    ldr w9, [x9]
    tst w9, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lglobal_fallback
    sub w4, w4, #1
    cbz w16, .Lglobal_base_load
// Fill CURRENT PC and arithmetic/slot hints. No pointer is retained.
    ldr x3, [x19, #ARM_OFF_JSFrameRegisterState_sites]
    cbz x3, .Lglobal_fallback
    lsr x9, x20, #6
    eor x9, x9, x20
    eor x9, x9, x20, lsr #12
    and x9, x9, #7
    add x3, x3, x9, lsl #6
    ldr x10, [x3]
    cmp x10, x20
    b.eq .Lglobal_fill
    ldr x11, [x3, #32]
    cmp x11, x20
    b.eq .Lglobal_fill_second
    ldr x5, [x19, #ARM_OFF_JSFrameRegisterState_cache_next]
    cbz x10, .Lglobal_fill_empty_first
    cbz x11, .Lglobal_fill_empty_second
    cbz x5, .Lglobal_fallback
    ldrb w10, [x5, x9]
    eor w11, w10, #1
    strb w11, [x5, x9]
    and x10, x10, #1
    add x3, x3, x10, lsl #5
    b .Lglobal_fill
.Lglobal_fill_empty_first:
    cbz x5, .Lglobal_fallback
    mov w10, #1
    strb w10, [x5, x9]
    b .Lglobal_fill
.Lglobal_fill_empty_second:
    cbz x5, .Lglobal_fallback
    strb wzr, [x5, x9]
.Lglobal_fill_second:
    add x3, x3, #ARM_SIZE_JSFrameGlobalHint
.Lglobal_fill:
    orr x9, x4, x8, lsl #32
    str x6, [x3, #ARM_OFF_JSFrameGlobalHint_arithmetic]
    str x9, [x3, #ARM_OFF_JSFrameGlobalHint_atom_slot]
    str x7, [x3, #ARM_OFF_JSFrameGlobalHint_marker]
    str x20, [x3, #ARM_OFF_JSFrameGlobalHint_pc]
    cmp w7, #-3
    b.eq .Lglobal_fill_lexical
    ARM_GLOBAL_EVENT 32
    b .Lglobal_load
.Lglobal_fill_lexical:
    ARM_GLOBAL_EVENT 40
    b .Lglobal_load
.Lglobal_base_load:
    ARM_GLOBAL_EVENT 88
.Lglobal_load:
    mov w4, w4
    ldr x5, [x1, #ARM_OFF_JSObject_prop]
    add x5, x5, x4, lsl #4
    ldp x12, x13, [x5, #ARM_OFF_JSProperty_u_value]
    cmp w7, #-3
    b.ne .Lglobal_ready
    cmp x13, #ARM_CONST_JS_TAG_UNINITIALIZED
    b.eq .Lglobal_fallback
.Lglobal_ready:
    add x20, x20, #5
    str x20, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    tbz x13, #63, .Lglobal_push
    ldur w9, [x12, #ARM_REF_COUNT_OFFSET]
    add w9, w9, #1
    stur w9, [x12, #ARM_REF_COUNT_OFFSET]
.Lglobal_push:
    stp x12, x13, [x21], #16
    ARM_DISPATCH_NEXT 1
.Lglobal_symbol_condition:
    cmp x13, #ARM_CONST_JS_TAG_SYMBOL
    b.ne .Lglobal_ready
    adrp x9, JS_FrameOwnBytecodeData
    add x9, x9, :lo12:JS_FrameOwnBytecodeData
    ldrb w9, [x9, #ARM_OFF_JSFrameOwnBytecodeControl_symbol_case]
    cmp w9, #1
    b.ne .Lglobal_ready
    ldp x1, x2, [x21, #-16]
    cmp x2, #ARM_CONST_JS_TAG_SYMBOL
    b.ne .Lglobal_ready
    ldur w3, [x1, #ARM_REF_COUNT_OFFSET]
    cmp w3, #1
    b.le .Lglobal_ready
    ldr w4, [x0, #ARM_OFF_JSContext_interrupt_counter]
    cmp w4, #1
    b.le .Lglobal_ready
    ldr x11, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x5, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr w6, [x11, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    add x6, x5, x6
    sub x7, x6, #11
    cmp x20, x7
    b.hi .Lglobal_ready
    cmp x20, x5
    b.lo .Lglobal_ready
    ldrb w7, [x20, #5]
    cmp w7, #ARM_OP_strict_eq
    b.ne .Lglobal_ready
    add x9, x20, #6
    ldrb w7, [x9]
    cmp x12, x1
    cset w10, eq
    cmp w7, #ARM_OP_if_true8
    b.eq .Lglobal_symbol_true8
    cmp w7, #ARM_OP_if_false8
    b.eq .Lglobal_symbol_false8
    cmp w7, #ARM_OP_if_true
    b.eq .Lglobal_symbol_true32
    cmp w7, #ARM_OP_if_false
    b.ne .Lglobal_ready
    cbz w10, .Lglobal_symbol_take32
    b .Lglobal_symbol_fall32
.Lglobal_symbol_true32:
    cbz w10, .Lglobal_symbol_fall32
.Lglobal_symbol_take32:
    ldursw x7, [x9, #1]
    add x9, x9, x7
    add x9, x9, #1
    b .Lglobal_symbol_target
.Lglobal_symbol_fall32:
    add x9, x9, #5
    b .Lglobal_symbol_target
.Lglobal_symbol_true8:
    cbz w10, .Lglobal_symbol_fall8
    b .Lglobal_symbol_take8
.Lglobal_symbol_false8:
    cbnz w10, .Lglobal_symbol_fall8
.Lglobal_symbol_take8:
    ldrsb x7, [x9, #1]
    add x9, x9, x7
    add x9, x9, #1
    b .Lglobal_symbol_target
.Lglobal_symbol_fall8:
    add x9, x9, #2
.Lglobal_symbol_target:
    cmp x9, x5
    b.lo .Lglobal_ready
    cmp x9, x6
    b.hs .Lglobal_ready
    sub w3, w3, #1
    stur w3, [x1, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #16
    sub w4, w4, #1
    str w4, [x0, #ARM_OFF_JSContext_interrupt_counter]
    mov x20, x9
    ARM_GLOBAL_EVENT 96
    ARM_DISPATCH_NEXT 1
.Lglobal_cold:
    ARM_GLOBAL_EVENT 104
    mov x0, x19
    add x27, x27, #1
    bl JS_LinuxGlobalBindingInit
    b .Lget_var
.Lglobal_fallback:
    ARM_GLOBAL_EVENT 120
    b .Lslow
.purgem ARM_GLOBAL_EVENT
#endif
