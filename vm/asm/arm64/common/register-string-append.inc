/* Complete accepted GNU one-byte append and following local-store fusion.
* Source algorithm: tools/generate/add-boundary.py:native_append_body.
* Actual target fields/pool header are measured by the build compiler. MIT. */
#if ARM_HAS_STRING_WORKERS && ARM_HAS_NATIVE_STRING_APPEND
.Lstring_native_append:
    ldp x0, x4, [x21, #-32]
    mov x5, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x4, x5
    b.ne .Lstring_binary_c
    ldp x1, x4, [x21, #-16]
    mov x5, #ARM_CONST_JS_TAG_STRING
    cmp x4, x5
    b.ne .Lstring_binary_c
    adrp x4, JS_FrameLocalRopeMode
    ldrb w4, [x4, :lo12:JS_FrameLocalRopeMode]
    cmp w4, #17
    b.ne .Lstring_binary_c
    adrp x4, qjs_linux_string_add_mode
    ldrb w4, [x4, :lo12:qjs_linux_string_add_mode]
    cmp w4, #1
    b.ne .Lstring_binary_c
    ldr x4, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x4, [x4, #(ARM_OFF_JSRuntime_mf+ARM_OFF_JSMallocFunctions_js_malloc_usable_size)]
    adrp x16, FramePoolFunctions
    add x16, x16, :lo12:FramePoolFunctions
    ldr x16, [x16, #ARM_OFF_JSMallocFunctions_js_malloc_usable_size]
    cmp x4, x16
    b.ne .Lstring_binary_c
    ldur w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #2
    b.ne .Lstring_binary_c
    ldr w4, [x1, #ARM_BIT_JSString_len_BYTE]
    cmp w4, #1
    b.ne .Lstring_binary_c
    ldr w4, [x1, #ARM_STRING_FLAGS_OFFSET]
    tst w4, #ARM_STRING_KIND_MASK
    b.ne .Lstring_binary_c
    ldur w4, [x1, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lstring_binary_c
    ldr x4, [x0, #(ARM_OFF_JSStringRope_right+8)]
    cmp x4, x5
    b.ne .Lstring_binary_c
    ldr x2, [x0, #ARM_OFF_JSStringRope_right]
    ldur w4, [x2, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.ne .Lstring_binary_c
    ldr w4, [x2, #ARM_STRING_FLAGS_OFFSET]
    tst w4, #ARM_STRING_NONNORMAL_MASK
    b.ne .Lstring_binary_c
    ldr w3, [x2, #ARM_BIT_JSString_len_BYTE]
    cmp w3, #512
    b.hi .Lstring_binary_c
    add w4, w3, #(ARM_SIZE_JSString+2)
    ldur x12, [x2, #(ARM_OFF_FramePoolHeader_capacity-ARM_SIZE_FramePoolHeader)]
    cmp x12, x4
    b.lo .Lstring_binary_c
    ldr x6, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x7, [x6, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldrsw x4, [x6, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    add x7, x7, x4
    add x4, x20, #1
    cmp x4, x7
    b.hs .Lstring_binary_c
    ldrb w9, [x20, #1]
    cmp w9, #ARM_OP_put_loc8
    b.eq .Lstring_append_put8
    cmp w9, #ARM_OP_set_loc8
    b.eq .Lstring_append_set8
    cmp w9, #ARM_OP_put_loc
    b.eq .Lstring_append_put16
    cmp w9, #ARM_OP_set_loc
    b.eq .Lstring_append_set16
    mov w8, #2
    sub w9, w9, #ARM_OP_put_loc0
    cmp w9, #3
    b.ls .Lstring_append_index
    add w9, w9, #(ARM_OP_put_loc0-ARM_OP_set_loc0)
    cmp w9, #3
    b.hi .Lstring_binary_c
    mov w8, #258
    b .Lstring_append_index
.Lstring_append_put8:
    mov w8, #3
    b .Lstring_append_index8
.Lstring_append_set8:
    mov w8, #259
.Lstring_append_index8:
    add x4, x20, #2
    cmp x4, x7
    b.hs .Lstring_binary_c
    ldrb w9, [x20, #2]
    b .Lstring_append_index
.Lstring_append_put16:
    mov w8, #4
    b .Lstring_append_index16
.Lstring_append_set16:
    mov w8, #260
.Lstring_append_index16:
    add x4, x20, #3
    cmp x4, x7
    b.hs .Lstring_binary_c
    ldrh w9, [x20, #2]
.Lstring_append_index:
    ldrh w4, [x6, #ARM_OFF_JSFunctionBytecode_var_count]
    cmp w9, w4
    b.hs .Lstring_binary_c
    ldr x10, [x22, #ARM_OFF_JSStackFrame_var_buf]
    cbz x10, .Lstring_binary_c
    add x10, x10, w9, uxtw #4
    ldp x4, x5, [x10]
    mov x12, #ARM_CONST_JS_TAG_STRING_ROPE
    cmp x5, x12
    b.ne .Lstring_binary_c
    cmp x4, x0
    b.ne .Lstring_binary_c
    mov w11, #1
    ldr x4, [x0, #(ARM_OFF_JSStringRope_left+8)]
    cmp x4, x12
    b.ne .Lstring_append_depth
    ldr x4, [x0, #ARM_OFF_JSStringRope_left]
    ldrb w11, [x4, #ARM_OFF_JSStringRope_depth]
    add w11, w11, #1
.Lstring_append_depth:
    cmp w11, #60
    b.hi .Lstring_binary_c
    ldr w5, [x0, #ARM_OFF_JSStringRope_len]
    mov w4, #1073741823
    cmp w5, w4
    b.hs .Lstring_binary_c
// Commit: no allocation, callbacks or last-reference release remains.
    ldrb w14, [x1, #ARM_SIZE_JSString]
    add x15, x2, w3, uxtw
    strb w14, [x15, #ARM_SIZE_JSString]
    strb wzr, [x15, #(ARM_SIZE_JSString+1)]
    add w3, w3, #1
    str w3, [x2, #ARM_BIT_JSString_len_BYTE]
    add w5, w5, #1
    str w5, [x0, #ARM_OFF_JSStringRope_len]
    strb w11, [x0, #ARM_OFF_JSStringRope_depth]
    ldur w4, [x1, #ARM_REF_COUNT_OFFSET]
    sub w4, w4, #1
    stur w4, [x1, #ARM_REF_COUNT_OFFSET]
    mov x4, #ARM_CONST_JS_TAG_UNDEFINED
    stp xzr, x4, [x21, #-16]
    tbnz w8, #8, .Lstring_append_keep
    ldur w5, [x0, #ARM_REF_COUNT_OFFSET]
    sub w5, w5, #1
    stur w5, [x0, #ARM_REF_COUNT_OFFSET]
    stp xzr, x4, [x21, #-32]
    sub x21, x21, #16
.Lstring_append_keep:
    sub x21, x21, #16
    and w8, w8, #255
    add x20, x20, x8
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12,tpidr_el0
    add x12,x12,:tprel_hi12:qjs_aarch64_string_counters
    add x12,x12,:tprel_lo12_nc:qjs_aarch64_string_counters
    ldr x13,[x12,#56]
    add x13,x13,#1
    str x13,[x12,#56]
#endif
    ARM_DISPATCH_NEXT 1
#endif
