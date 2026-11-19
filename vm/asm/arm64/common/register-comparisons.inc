/* Complete accepted GNU equality lanes over measured AAPCS64 types. MIT. */
#if ARM_HAS_COMPARISONS
.macro ARM_COMPARE_EVENT offset
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x14, tpidr_el0
    add x14, x14, :tprel_hi12:qjs_aarch64_compare_counters
    add x14, x14, :tprel_lo12_nc:qjs_aarch64_compare_counters
    ldr x15, [x14, #\offset]
    add x15, x15, #1
    str x15, [x14, #\offset]
#endif
.endm
// Preserve the original optional process observation bank. Only x9,x14,x15
// are scratch; all operands and the original policy/operator remain live.
.macro ARM_COMPARE_STAT symbol, index, bit
    tbz w16, #\bit, .Lcmp_stat_done\@
    adrp x14, \symbol
    add x14, x14, :lo12:\symbol
    add x14, x14, #(\index*8)
    adrp x15, qjs_aarch64_publish_dirty
    add x15, x15, :lo12:qjs_aarch64_publish_dirty
    cmp x25, x15
    b.ne .Lcmp_stat_retry\@
    add x14, x14, #64
.Lcmp_stat_retry\@:
    ldaxr x15, [x14]
    add x15, x15, #1
    stlxr w9, x15, [x14]
    cbnz w9, .Lcmp_stat_retry\@
.Lcmp_stat_done\@:
.endm
.Lcomparison:
    adrp x9, JS_LinuxComparisonControl
    add x9, x9, :lo12:JS_LinuxComparisonControl
    ldarb w9, [x9]
    cbz w9, .Lcomparison_init
    tbnz w9, #1, .Lcomparison_fallback
    ldrb w17, [x20]
    cmp w17, #ARM_OP_strict_eq
    b.eq .Lcomparison_strict_eq
    cmp w17, #ARM_OP_strict_neq
    b.eq .Lcomparison_strict_neq
    tbnz w9, #3, .Lcomparison_fallback
    cmp w17, #ARM_OP_neq
    cset w17, eq
    adrp x9, JS_FrameLooseEqMode
    add x9, x9, :lo12:JS_FrameLooseEqMode
    ldar w16, [x9]
    cbz w16, .Lcomparison_loose_init
    cbnz w17, .Lcomparison_loose_neq_stat
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 0, 5
    b .Lcomparison_loose
.Lcomparison_loose_neq_stat:
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 1, 5
.Lcomparison_loose:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    tbz w16, #0, .Lcomparison_null
    cmp x11, #ARM_CONST_JS_TAG_STRING
    b.ne .Lcomparison_null
    cmp x13, #ARM_CONST_JS_TAG_STRING
    b.ne .Lcomparison_null
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 2, 5
    ARM_COMPARE_EVENT 88
// Loose string delegation retains the independently disabled strict tier.
    adrp x9, JS_LinuxComparisonControl
    add x9, x9, :lo12:JS_LinuxComparisonControl
    ldarb w9, [x9]
    tbnz w9, #2, .Lcomparison_loose_strict_disabled
    b .Lcomparison_strict_policy
.Lcomparison_loose_strict_disabled:
// The accepted GNU delegation enters the strict selector,whose disabled
// path reaches the original strict C opcode instead of coercion.
    b .Lcomparison_fallback
.Lcomparison_null:
    tbz w16, #1, .Lcomparison_loose_miss
    cmp x11, #ARM_CONST_JS_TAG_NULL
    b.eq .Lcomparison_left_null
    cmp x11, #ARM_CONST_JS_TAG_UNDEFINED
    b.eq .Lcomparison_left_null
    cmp x13, #ARM_CONST_JS_TAG_NULL
    b.eq .Lcomparison_right_null
    cmp x13, #ARM_CONST_JS_TAG_UNDEFINED
    b.ne .Lcomparison_loose_miss
.Lcomparison_right_null:
    mov x0, x10
    mov x1, x11
    b .Lcomparison_null_other
.Lcomparison_left_null:
    mov x0, x12
    mov x1, x13
.Lcomparison_null_other:
    cmp x1, #ARM_CONST_JS_TAG_UNDEFINED
    b.ls .Lcomparison_null_immediate
    cmp x1, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lcomparison_null_immediate
    cmp x1, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .Lcomparison_null_immediate
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.eq .Lcomparison_null_object
    cmp x1, #ARM_CONST_JS_TAG_BIG_INT
    b.lt .Lcomparison_loose_miss
    cmp x1, #-6
    b.gt .Lcomparison_loose_miss
    b .Lcomparison_null_release_guard
.Lcomparison_null_object:
    tbz w16, #2, .Lcomparison_loose_miss
    ldrb w9, [x0, #ARM_BIT_JSObject_is_HTMLDDA_BYTE]
    tst w9, #ARM_BIT_JSObject_is_HTMLDDA_MASK
    b.ne .Lcomparison_loose_miss
    ldr w9, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w9, #1
    b.le .Lcomparison_loose_last
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 7, 5
.Lcomparison_null_release_guard:
    ldr w2, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w2, #1
    b.le .Lcomparison_loose_last
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 4, 5
    sub w2, w2, #1
    str w2, [x0, #ARM_REF_COUNT_OFFSET]
    mov w10, #0
    ARM_COMPARE_EVENT 80
    b .Lcomparison_commit
.Lcomparison_null_immediate:
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 3, 5
    sub x1, x1, #ARM_CONST_JS_TAG_NULL
    cmp x1, #1
    cset w10, ls
    ARM_COMPARE_EVENT 72
    b .Lcomparison_commit
.Lcomparison_loose_last:
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 6, 5
.Lcomparison_loose_miss:
    ARM_COMPARE_STAT JS_FrameLooseEqStats, 5, 5
    b .Lcomparison_fallback
.Lcomparison_strict_eq:
    tbnz w9, #2, .Lcomparison_fallback
    mov w17, #0
    b .Lcomparison_strict_policy
.Lcomparison_strict_neq:
    tbnz w9, #2, .Lcomparison_fallback
    mov w17, #1
.Lcomparison_strict_policy:
    adrp x9, JS_FrameStrictEqMode
    add x9, x9, :lo12:JS_FrameStrictEqMode
    ldr w16, [x9]
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    cmp x11, #ARM_CONST_JS_TAG_STRING
    b.ne .Lcomparison_strict_number
    cmp x13, #ARM_CONST_JS_TAG_STRING
    b.ne .Lcomparison_strict_number
    tbz w16, #0, .Lcomparison_strict_miss
    cmp x10, x12
    b.ne .Lcomparison_string_distinct
    ldr w0, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w0, #2
    b.le .Lcomparison_strict_last
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 0, 3
    mov w0, #1
    ARM_COMPARE_EVENT 0
    b .Lcomparison_pair_release
.Lcomparison_string_distinct:
    ldr w0, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w0, #1
    b.le .Lcomparison_strict_last
    ldr w0, [x12, #ARM_REF_COUNT_OFFSET]
    cmp w0, #1
    b.le .Lcomparison_strict_last
    ldr w2, [x10, #ARM_BIT_JSString_len_BYTE]
    ldr w3, [x12, #ARM_BIT_JSString_len_BYTE]
    and w8, w2, #0x7fffffff
    and w9, w3, #0x7fffffff
    cmp w8, w9
    b.ne .Lcomparison_string_length
    cmp w8, #8
    b.hi .Lcomparison_strict_miss
    cbz w8, .Lcomparison_string_equal
    ldr w4, [x10, #ARM_BIT_JSString_hash_BYTE]
    ubfx w4, w4, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cmp w4, #1
    b.eq .Lcomparison_string_left_slice
    cmp w4, #2
    b.eq .Lcomparison_string_left_indirect
    cbnz w4, .Lcomparison_strict_miss
    add x0, x10, #ARM_SIZE_JSString
    b .Lcomparison_string_left_ready
.Lcomparison_string_left_slice:
    ldr x0, [x10, #ARM_SIZE_JSString]
    ldr w4, [x10, #(ARM_SIZE_JSString+ARM_COMPARE_SLICE_START)]
    add x0, x0, x4
    add x0, x0, #ARM_SIZE_JSString
    b .Lcomparison_string_left_ready
.Lcomparison_string_left_indirect:
    ldr x0, [x10, #ARM_SIZE_JSString]
.Lcomparison_string_left_ready:
    ldr w4, [x12, #ARM_BIT_JSString_hash_BYTE]
    ubfx w4, w4, #ARM_COMPARE_STRING_KIND_SHIFT, #2
    cmp w4, #1
    b.eq .Lcomparison_string_right_slice
    cmp w4, #2
    b.eq .Lcomparison_string_right_indirect
    cbnz w4, .Lcomparison_strict_miss
    add x1, x12, #ARM_SIZE_JSString
    b .Lcomparison_string_right_ready
.Lcomparison_string_right_slice:
    ldr x1, [x12, #ARM_SIZE_JSString]
    ldr w4, [x12, #(ARM_SIZE_JSString+ARM_COMPARE_SLICE_START)]
    add x1, x1, x4
    add x1, x1, #ARM_SIZE_JSString
    b .Lcomparison_string_right_ready
.Lcomparison_string_right_indirect:
    ldr x1, [x12, #ARM_SIZE_JSString]
.Lcomparison_string_right_ready:
    eor w4, w2, w3
    tbnz w4, #31, .Lcomparison_string_mixed
    tbz w2, #31, .Lcomparison_string_same_width
    lsl w8, w8, #1
.Lcomparison_string_same_width:
    cmp w8, #8
    b.lo .Lcomparison_string_four
    ldr x4, [x0]
    ldr x5, [x1]
    cmp x4, x5
    b.ne .Lcomparison_string_different
    sub w8, w8, #8
    ldr x4, [x0, x8]
    ldr x5, [x1, x8]
    cmp x4, x5
    b.ne .Lcomparison_string_different
    b .Lcomparison_string_equal
.Lcomparison_string_four:
    cmp w8, #4
    b.lo .Lcomparison_string_two
    ldr w4, [x0]
    ldr w5, [x1]
    cmp w4, w5
    b.ne .Lcomparison_string_different
    sub w8, w8, #4
    ldr w4, [x0, x8]
    ldr w5, [x1, x8]
    cmp w4, w5
    b.ne .Lcomparison_string_different
    b .Lcomparison_string_equal
.Lcomparison_string_two:
    cmp w8, #2
    b.lo .Lcomparison_string_one
    ldrh w4, [x0]
    ldrh w5, [x1]
    cmp w4, w5
    b.ne .Lcomparison_string_different
    sub w8, w8, #2
    ldrh w4, [x0, x8]
    ldrh w5, [x1, x8]
    cmp w4, w5
    b.ne .Lcomparison_string_different
    b .Lcomparison_string_equal
.Lcomparison_string_one:
    ldrb w4, [x0]
    ldrb w5, [x1]
    cmp w4, w5
    b.ne .Lcomparison_string_different
    b .Lcomparison_string_equal
.Lcomparison_string_mixed:
    tbnz w2, #31, .Lcomparison_string_left_wide
    mov x4, x0
    mov x0, x1
    mov x1, x4
.Lcomparison_string_left_wide:
    ldrh w4, [x0], #2
    ldrb w5, [x1], #1
    cmp w4, w5
    b.ne .Lcomparison_string_mixed_different
    subs w8, w8, #1
    b.ne .Lcomparison_string_left_wide
    mov w0, #1
    b .Lcomparison_string_mixed_commit
.Lcomparison_string_mixed_different:
    mov w0, #0
.Lcomparison_string_mixed_commit:
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 3, 3
    ARM_COMPARE_EVENT 24
    b .Lcomparison_pair_release
.Lcomparison_string_equal:
    mov w0, #1
    b .Lcomparison_string_short_commit
.Lcomparison_string_different:
    mov w0, #0
.Lcomparison_string_short_commit:
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 2, 3
    ARM_COMPARE_EVENT 16
    b .Lcomparison_pair_release
.Lcomparison_string_length:
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 1, 3
    ARM_COMPARE_EVENT 8
    mov w0, #0
    b .Lcomparison_pair_release
.Lcomparison_strict_number:
    tbz w16, #1, .Lcomparison_strict_miss
    cmp x11, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .Lcomparison_strict_left_float
    cmp x13, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lcomparison_strict_miss
    cbz x11, .Lcomparison_strict_left_int
    cmp x11, #ARM_CONST_JS_TAG_UNDEFINED
    b.ls .Lcomparison_strict_mixed_false
    cmp x11, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lcomparison_strict_mixed_false
    b .Lcomparison_strict_miss
.Lcomparison_strict_left_int:
    scvtf d0, w10
    fmov d1, x12
    b .Lcomparison_strict_float_result
.Lcomparison_strict_left_float:
    fmov d0, x10
    cmp x13, #ARM_CONST_JS_TAG_FLOAT64
    b.eq .Lcomparison_strict_right_float
    cbz x13, .Lcomparison_strict_right_int
    cmp x13, #ARM_CONST_JS_TAG_UNDEFINED
    b.ls .Lcomparison_strict_mixed_false
    cmp x13, #ARM_CONST_JS_TAG_SHORT_BIG_INT
    b.eq .Lcomparison_strict_mixed_false
    b .Lcomparison_strict_miss
.Lcomparison_strict_right_int:
    scvtf d1, w12
    b .Lcomparison_strict_float_result
.Lcomparison_strict_right_float:
    fmov d1, x12
.Lcomparison_strict_float_result:
    fcmp d0, d1
    cset w10, eq
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 4, 3
    ARM_COMPARE_EVENT 32
    b .Lcomparison_commit
.Lcomparison_strict_mixed_false:
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 5, 3
    ARM_COMPARE_EVENT 40
    mov w10, #0
    b .Lcomparison_commit
.Lcomparison_strict_last:
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 7, 3
    ARM_COMPARE_EVENT 56
.Lcomparison_strict_miss:
    adrp x9, JS_FrameReferenceMode
    add x9, x9, :lo12:JS_FrameReferenceMode
    ldar w9, [x9]
    cmp w9, #1
    b.ne .Lcomparison_strict_reference_miss
    cmp x11, x13
    b.ne .Lcomparison_strict_reference_miss
    cmp x11, #ARM_CONST_JS_TAG_SYMBOL
    b.eq .Lcomparison_reference_tag
    cmp x11, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lcomparison_strict_reference_miss
.Lcomparison_reference_tag:
    ldr w0, [x10, #ARM_REF_COUNT_OFFSET]
    cmp x10, x12
    b.ne .Lcomparison_reference_distinct
    cmp w0, #2
    b.le .Lcomparison_strict_reference_miss
    mov w0, #1
    b .Lcomparison_reference_release
.Lcomparison_reference_distinct:
    cmp w0, #1
    b.le .Lcomparison_strict_reference_miss
    ldr w0, [x12, #ARM_REF_COUNT_OFFSET]
    cmp w0, #1
    b.le .Lcomparison_strict_reference_miss
    mov w0, #0
.Lcomparison_reference_release:
    ARM_COMPARE_EVENT 64
.Lcomparison_pair_release:
    ldr w1, [x10, #ARM_REF_COUNT_OFFSET]
    sub w1, w1, #1
    str w1, [x10, #ARM_REF_COUNT_OFFSET]
    ldr w1, [x12, #ARM_REF_COUNT_OFFSET]
    sub w1, w1, #1
    str w1, [x12, #ARM_REF_COUNT_OFFSET]
    mov w10, w0
.Lcomparison_commit:
    eor w10, w10, w17
    mov x11, #ARM_CONST_JS_TAG_BOOL
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lcomparison_strict_reference_miss:
    ARM_COMPARE_STAT JS_FrameStrictEqStats, 6, 3
.Lcomparison_fallback:
    ARM_COMPARE_EVENT 96
    b .Lslow
.Lcomparison_init:
    ARM_COMPARE_EVENT 104
    mov x0, x19
    add x27, x27, #1
    bl JS_LinuxComparisonInit
    b .Lcomparison
.Lcomparison_loose_init:
    mov x0, x19
    add x27, x27, #1
    bl JS_LinuxLooseEqInit
    b .Lcomparison
.purgem ARM_COMPARE_EVENT
.purgem ARM_COMPARE_STAT
#endif
