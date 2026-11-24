/* Complete accepted base scalar/stack/atom/predicate opcode family. MIT.
* Noncalling hits retain the incoming publication token and allocate nothing.
* All declines precede PC/SP/ownership mutation;last releases stay with C. */
#if ARM_HAS_SCALAR_OPS
.macro ARM_SCALAR_EVENT index
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_scalar_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_scalar_counters
    ldr x13, [x12, #(8*\index)]
    add x13, x13, #1
    str x13, [x12, #(8*\index)]
#endif
.endm
.Lscalar_or:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .Lslow
    orr w0, w0, w2
    ARM_SCALAR_EVENT 0
    b .Lscalar_binary_commit
.Lscalar_xor:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .Lslow
    eor w0, w0, w2
    ARM_SCALAR_EVENT 1
    b .Lscalar_binary_commit
.Lscalar_shl:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .Lslow
    lsl w0, w0, w2
    ARM_SCALAR_EVENT 2
    b .Lscalar_binary_commit
.Lscalar_sar:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .Lslow
    asr w0, w0, w2
    ARM_SCALAR_EVENT 3
    b .Lscalar_binary_commit
.Lscalar_shr:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .Lslow
    lsr w0, w0, w2
    tbnz w0, #31, .Lslow
    ARM_SCALAR_EVENT 4
    b .Lscalar_binary_commit
.Lscalar_mod:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    orr x4, x1, x3
    cbnz x4, .Lslow
    cbz w2, .Lslow
    mov w4, #0x80000000
    cmp w0, w4
    b.eq .Lslow
    sdiv w4, w0, w2
    msub w4, w4, w2, w0
    cbnz w4, .Lscalar_mod_ready
    tbnz w0, #31, .Lslow
.Lscalar_mod_ready:
    mov w0, w4
    ARM_SCALAR_EVENT 5
.Lscalar_binary_commit:
    str x0, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_inc:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .Lslow
    adds w0, w0, #1
    b.vs .Lslow
    ARM_SCALAR_EVENT 6
    b .Lscalar_unary_commit
.Lscalar_dec:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .Lslow
    subs w0, w0, #1
    b.vs .Lslow
    ARM_SCALAR_EVENT 7
    b .Lscalar_unary_commit
.Lscalar_not:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .Lslow
    mvn w0, w0
    ARM_SCALAR_EVENT 8
    b .Lscalar_unary_commit
.Lscalar_neg:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .Lslow
    cbz w0, .Lslow
    negs w0, w0
    b.vs .Lslow
    ARM_SCALAR_EVENT 9
.Lscalar_unary_commit:
    str x0, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_post_inc:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .Lslow
    adds w0, w0, #1
    b.vs .Lslow
    ARM_SCALAR_EVENT 10
    b .Lscalar_post_commit
.Lscalar_post_dec:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-16]
    cbnz x1, .Lslow
    subs w0, w0, #1
    b.vs .Lslow
    ARM_SCALAR_EVENT 11
.Lscalar_post_commit:
    stp x0, x1, [x21], #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_swap:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x21, #-32]
    ldp x2, x3, [x21, #-16]
    stp x0, x1, [x21, #-16]
    stp x2, x3, [x21, #-32]
    ARM_SCALAR_EVENT 12
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_get_loc0_loc1:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldp x0, x1, [x23]
    tbz x1, #63, .Lscalar_pair_first_ready
    ldur w2, [x0, #ARM_REF_COUNT_OFFSET]
    add w2, w2, #1
    stur w2, [x0, #ARM_REF_COUNT_OFFSET]
.Lscalar_pair_first_ready:
    stp x0, x1, [x21], #16
    ldp x0, x1, [x23, #16]
    tbz x1, #63, .Lscalar_pair_second_ready
    ldur w2, [x0, #ARM_REF_COUNT_OFFSET]
    add w2, w2, #1
    stur w2, [x0, #ARM_REF_COUNT_OFFSET]
.Lscalar_pair_second_ready:
    stp x0, x1, [x21], #16
    ARM_SCALAR_EVENT 13
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_push_empty_string:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldr x0, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x0, [x0, #ARM_OFF_JSRuntime_atom_array]
    ldr x0, [x0, #(8*ARM_CONST_JS_ATOM_empty_string)]
    mov x1, #ARM_CONST_JS_TAG_STRING
    ARM_SCALAR_EVENT 14
    add x20, x20, #1
    b .Lscalar_atom_commit
.Lscalar_push_atom_value:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldur w2, [x20, #1]
    tbnz w2, #31, .Lslow
    ldr x0, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    ldr x0, [x0, #ARM_OFF_JSRuntime_atom_array]
    ldr x0, [x0, x2, lsl #3]
    ldrb w2, [x0, #ARM_SCALAR_ATOM_TYPE_BYTE]
    and w2, w2, #ARM_SCALAR_ATOM_TYPE_MASK
    cmp w2, #(ARM_CONST_JS_ATOM_TYPE_STRING << ARM_SCALAR_ATOM_TYPE_SHIFT)
    mov x1, #ARM_CONST_JS_TAG_STRING
    mov x3, #ARM_CONST_JS_TAG_SYMBOL
    csel x1, x1, x3, eq
    ARM_SCALAR_EVENT 15
    add x20, x20, #5
.Lscalar_atom_commit:
    ldur w2, [x0, #ARM_REF_COUNT_OFFSET]
    add w2, w2, #1
    stur w2, [x0, #ARM_REF_COUNT_OFFSET]
    stp x0, x1, [x21], #16
    ARM_DISPATCH_NEXT 1
.Lscalar_is_undefined:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    mov w8, #16
    mov w7, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lscalar_predicate
.Lscalar_is_null:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    mov w8, #17
    mov w7, #ARM_CONST_JS_TAG_NULL
    b .Lscalar_predicate
.Lscalar_is_undefined_or_null:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    mov w8, #18
    mov w7, #0
.Lscalar_predicate:
    ldp x0, x1, [x21, #-16]
    tbz x1, #63, .Lscalar_predicate_value
    ldur w2, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w2, #1
    b.le .Lslow
    sub w2, w2, #1
    stur w2, [x0, #ARM_REF_COUNT_OFFSET]
.Lscalar_predicate_value:
    cmp w8, #18
    b.eq .Lscalar_predicate_both
    cmp x1, x7
    cset w0, eq
    b .Lscalar_predicate_commit
.Lscalar_predicate_both:
    sub x2, x1, #ARM_CONST_JS_TAG_NULL
    cmp x2, #(ARM_CONST_JS_TAG_UNDEFINED-ARM_CONST_JS_TAG_NULL)
    cset w0, ls
.Lscalar_predicate_commit:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_scalar_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_scalar_counters
    ldr x13, [x12, x8, lsl #3]
    add x13, x13, #1
    str x13, [x12, x8, lsl #3]
#endif
    mov x1, #ARM_CONST_JS_TAG_BOOL
    stp x0, x1, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_to_propkey:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    mov w8, #19
    b .Lscalar_propkey_guard
.Lscalar_to_propkey2:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldur x0, [x21, #-24]
    sub x0, x0, #ARM_CONST_JS_TAG_NULL
    cmp x0, #(ARM_CONST_JS_TAG_UNDEFINED-ARM_CONST_JS_TAG_NULL)
    b.ls .Lslow
    mov w8, #20
.Lscalar_propkey_guard:
    ldur x0, [x21, #-8]
    cbz x0, .Lscalar_propkey_ready
    cmp x0, #ARM_CONST_JS_TAG_STRING
    b.eq .Lscalar_propkey_ready
    cmp x0, #ARM_CONST_JS_TAG_SYMBOL
    b.ne .Lslow
.Lscalar_propkey_ready:
#ifdef QJS_AARCH64_VM_INSTRUMENT
    mrs x12, tpidr_el0
    add x12, x12, :tprel_hi12:qjs_aarch64_scalar_counters
    add x12, x12, :tprel_lo12_nc:qjs_aarch64_scalar_counters
    ldr x13, [x12, x8, lsl #3]
    add x13, x13, #1
    str x13, [x12, x8, lsl #3]
#endif
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lscalar_check_ctor:
    ldr w12, [sp, #ARM_VM_POLICY_OFF]
    tbz w12, #16, .Lslow
    ldrb w0, [x22, #ARM_FRAME_ROOT_OFFSET]
    cmp w0, #3
    b.ne .Lslow
    ARM_SCALAR_EVENT 21
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
#endif
