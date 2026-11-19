/* Original guarded string add/local and integer-receiver entries. MIT. */
#if ARM_HAS_STRING_WORKERS
.Lstring_binary:
    cbnz w17, .Lslow
#if ARM_HAS_NATIVE_STRING_APPEND
    b .Lstring_native_append
#endif
.Lstring_binary_c:
// Original C owner retains conversion, Symbol exceptions and fallback.
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12,tpidr_el0
    add x12,x12,:tprel_hi12:qjs_aarch64_string_counters
    add x12,x12,:tprel_lo12_nc:qjs_aarch64_string_counters
    ldr x13,[x12,#16]
    add x13,x13,#1
    str x13,[x12,#16]
#endif
    bl JS_FrameLinuxStringAdd
    cbz w0, .Lreload
    b .Ldone
.Lstring_add_local:
    ldrb w4, [x20, #1]
    add x4, x23, x4, lsl #4
    ldr x6, [x4, #8]
    add x6, x6, #7
    cmp x6, #1
    b.hi .Lslow
    ldr x8, [x21, #-8]
    add x8, x8, #7
    cmp x8, #1
    b.hi .Lslow
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12,tpidr_el0
    add x12,x12,:tprel_hi12:qjs_aarch64_string_counters
    add x12,x12,:tprel_lo12_nc:qjs_aarch64_string_counters
    ldr x13,[x12,#8]
    add x13,x13,#1
    str x13,[x12,#8]
#endif
    bl JS_FrameAddLocalString
    cmp w0, #2
    b.eq .Lreload
    cbz w0, .Lreload
    b .Ldone
.Lstring_index:
// The integer-index guard precedes every receiver/string access.
    ldp x2, x3, [x21, #-16]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lslow
    ldp x0, x1, [x21, #-32]
    mov x4, #ARM_CONST_JS_TAG_STRING
    cmp x1, x4
    b.ne .Lslow
    adrp x4, JS_FrameStringIndexMode
    ldrb w4, [x4, :lo12:JS_FrameStringIndexMode]
    tbnz w4, #1, .Lslow
    ldr w5, [x0, #ARM_BIT_JSString_len_BYTE]
    and w5, w5, #ARM_STRING_LEN_MASK
    cmp w2, w5
    b.hs .Lslow
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12,tpidr_el0
    add x12,x12,:tprel_hi12:qjs_aarch64_string_counters
    add x12,x12,:tprel_lo12_nc:qjs_aarch64_string_counters
    ldr x13,[x12,#0]
    add x13,x13,#1
    str x13,[x12,#0]
#endif
    bl JS_FrameStringIndexStep
    cbz w0, .Lreload
    b .Ldone
#endif
