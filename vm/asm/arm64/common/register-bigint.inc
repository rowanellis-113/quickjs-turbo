/* Original numeric misses retain both tags/owners until full BigInt proof. MIT. */
#if ARM_HAS_NUMERIC_WORKERS
.Lnumeric_binary:
    cmp w17, #0
    b.eq .Lnumeric_binary_tags
    cmp w17, #2
    b.ne .Lslow
.Lnumeric_binary_tags:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    cmp x11, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lnumeric_binary_rhs
    mov x14, #ARM_CONST_JS_TAG_BIG_INT
    cmp x11, x14
#if ARM_HAS_STRING_WORKERS
    b.ne .Lstring_binary
#else
    b.ne .Lslow
#endif
.Lnumeric_binary_rhs:
    cmp x13, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lnumeric_binary_call
    mov x14, #ARM_CONST_JS_TAG_BIG_INT
    cmp x13, x14
#if ARM_HAS_STRING_WORKERS
    b.ne .Lstring_binary
#else
    b.ne .Lslow
#endif
.Lnumeric_binary_call:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
    cbnz w17, .Lnumeric_mul_call
    bl JS_FrameInterpPrimitive_add
    b .Lnumeric_binary_done
.Lnumeric_mul_call:
    bl JS_FrameInterpPrimitive_mul
.Lnumeric_binary_done:
    cbz w0, .Lreload
    b .Ldone

.Lnumeric_add_local:
    ldrb w4, [x20, #1]
    add x4, x23, x4, lsl #4
    ldp x5, x6, [x4]
    cmp x6, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lnumeric_local_rhs
    mov x7, #ARM_CONST_JS_TAG_BIG_INT
    cmp x6, x7
#if ARM_HAS_STRING_WORKERS
    b.ne .Lstring_add_local
#else
    b.ne .Lslow
#endif
.Lnumeric_local_rhs:
    ldp x7, x8, [x21, #-16]
    cmp x8, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lnumeric_local_mode
    mov x9, #ARM_CONST_JS_TAG_BIG_INT
    cmp x8, x9
#if ARM_HAS_STRING_WORKERS
    b.ne .Lstring_add_local
#else
    b.ne .Lslow
#endif
.Lnumeric_local_mode:
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldrb w10, [x9, #ARM_NUMERIC_LOCAL_MODE_OFFSET]
    cmp w10, #2
    b.eq .Lslow
    cbz w10, .Lnumeric_local_c
    cmp x6, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.ne .Lnumeric_local_c
    cmp x8, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.ne .Lnumeric_local_c
    adds w5, w5, w7
    b.vs .Lnumeric_local_c
    str x5, [x4]
    sub x21, x21, #16
    add x20, x20, #2
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_numeric_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_numeric_counters
    ldr x13, [x12, #32]
    add x13, x13, #1
    str x13, [x12, #32]
#endif
    ARM_DISPATCH_NEXT 1
.Lnumeric_local_c:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x27, x27, #1
    bl JS_FrameAddLocalBig
    cmp w0, #2
    b.eq .Lreload
    cbz w0, .Lreload
    b .Ldone
#endif
