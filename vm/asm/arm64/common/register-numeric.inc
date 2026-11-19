/* Number-only AArch64 arithmetic. Match js_float64 versus js_number exactly:
* add/sub/mul keep float results boxed; div uses the original bit classifier.
* No coercion/owner is consumed before both operand tags have been checked. */
.macro ARM_NUMBER payload, narrow, tag, fp, fallback
    cbz \tag, .Lnumber_int\@
    cmp \tag, #ARM_CONST_JS_TAG_FLOAT64
    b.ne \fallback
    fmov \fp, \payload
    b .Lnumber_ready\@
.Lnumber_int\@:
    scvtf \fp, \narrow
.Lnumber_ready\@:
.endm
.Ladd:
    mov w17, #0
    b .Lbinary_number
.Lsub:
    mov w17, #1
    b .Lbinary_number
.Lmul:
    mov w17, #2
    b .Lbinary_number
.Ldiv:
    mov w17, #3
.Lbinary_number:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lbinary_float
    cmp w17, #3
    b.eq .Lbinary_float
    cmp w17, #2
    b.eq .Lnumber_int_mul
    cmp w17, #1
    b.eq .Lnumber_int_sub
    adds w14, w10, w12
    b.vs .Lbinary_float
    b .Lnumber_int_result
.Lnumber_int_sub:
    subs w14, w10, w12
    b.vs .Lbinary_float
    b .Lnumber_int_result
.Lnumber_int_mul:
    smull x14, w10, w12
    cmp x14, w14, sxtw
    b.ne .Lbinary_float
    cbnz x14, .Lnumber_int_result
    orr w15, w10, w12
    tbnz w15, #31, .Lbinary_float
.Lnumber_int_result:
    mov w10, w14
    mov x11, #ARM_CONST_JS_TAG_INT
    b .Lnumber_store
.Lbinary_float:
#if ARM_HAS_NUMERIC_WORKERS
    ARM_NUMBER x10, w10, x11, d0, .Lnumeric_binary
    ARM_NUMBER x12, w12, x13, d1, .Lnumeric_binary
#elif ARM_HAS_STRING_WORKERS
    ARM_NUMBER x10, w10, x11, d0, .Lstring_binary
    ARM_NUMBER x12, w12, x13, d1, .Lstring_binary
#else
    ARM_NUMBER x10, w10, x11, d0, .Lslow
    ARM_NUMBER x12, w12, x13, d1, .Lslow
#endif
    cmp w17, #0
    b.eq .Lnumber_add
    cmp w17, #1
    b.eq .Lnumber_sub
    cmp w17, #2
    b.eq .Lnumber_mul
    fdiv d0, d0, d1
    b .Lnumber_canonical
.Lnumber_add:
    fadd d0, d0, d1
    b .Lnumber_float_result
.Lnumber_sub:
    fsub d0, d0, d1
    b .Lnumber_float_result
.Lnumber_mul:
    fmul d0, d0, d1
    b .Lnumber_float_result
.Lnumber_canonical:
// double_is_int32 from the actual core. Check bits before FCVTZS, so
// NaN/Inf/out-of-range conversions do not add invalid FP exceptions.
    fmov x10, d0
    ubfx x14, x10, #52, #11
    sub x14, x14, #1023
    cmp x14, #30
    b.hi .Lnumber_canonical_special
    lsl x15, x10, #12
    lslv x15, x15, x14
    cbnz x15, .Lnumber_float_result
    fcvtzs w10, d0
    mov x11, #ARM_CONST_JS_TAG_INT
    b .Lnumber_store
.Lnumber_canonical_special:
    cbz x10, .Lnumber_zero
    mov x15, #0xc1e0000000000000
    cmp x10, x15
    b.ne .Lnumber_float_result
    mov w10, #0x80000000
    mov x11, #ARM_CONST_JS_TAG_INT
    b .Lnumber_store
.Lnumber_zero:
    mov x10, #0
    mov x11, #ARM_CONST_JS_TAG_INT
    b .Lnumber_store
.Lnumber_float_result:
    fmov x10, d0
    mov x11, #ARM_CONST_JS_TAG_FLOAT64
.Lnumber_store:
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

.macro ARM_FLOAT_COMPARE name, condition, unordered_false, fallback
.Lfloat_\name:
    ARM_NUMBER x10, w10, x11, d0, \fallback
    ARM_NUMBER x12, w12, x13, d1, \fallback
.if \unordered_false
    fcmpe d0, d1
.else
    fcmp d0, d1
.endif
    cset w10, \condition
.if \unordered_false
    csel w10, wzr, w10, vs
.endif
    mov x11, #ARM_CONST_JS_TAG_BOOL
    b .Lnumber_store
.endm
    ARM_FLOAT_COMPARE lt, lt, 1, .Lslow
    ARM_FLOAT_COMPARE lte, le, 1, .Lslow
    ARM_FLOAT_COMPARE gt, gt, 1, .Lslow
    ARM_FLOAT_COMPARE gte, ge, 1, .Lslow
#if ARM_HAS_COMPARISONS
    ARM_FLOAT_COMPARE eq, eq, 0, .Lcomparison
    ARM_FLOAT_COMPARE neq, ne, 0, .Lcomparison
#else
    ARM_FLOAT_COMPARE eq, eq, 0, .Lslow
    ARM_FLOAT_COMPARE neq, ne, 0, .Lslow
#endif
.purgem ARM_FLOAT_COMPARE
.purgem ARM_NUMBER
