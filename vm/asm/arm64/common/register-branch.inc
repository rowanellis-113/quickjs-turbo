/* Pure int32 comparisons and immediate truth. Every branch retains the exact
* current-realm interrupt decrement; the reset/observing case replays C before
* touching its counter, PC or operand owners. */
.macro ARM_INT_COMPARE name, condition
.L\name:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lfloat_\name
    cmp w10, w12
    cset w10, \condition
    mov x11, #ARM_CONST_JS_TAG_BOOL
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.endm
    ARM_INT_COMPARE lt, lt
    ARM_INT_COMPARE lte, le
    ARM_INT_COMPARE gt, gt
    ARM_INT_COMPARE gte, ge
    ARM_INT_COMPARE eq, eq
    ARM_INT_COMPARE neq, ne
.purgem ARM_INT_COMPARE
.macro ARM_GOTO name, width
.L\name:
.if \width == 1
    ldrsb x10, [x20, #1]
.elseif \width == 2
    ldursh x10, [x20, #1]
.else
    ldursw x10, [x20, #1]
.endif
    add x10, x10, #1
    add x10, x20, x10
    mov w17, #0
    b .Lbranch_poll
.endm
    ARM_GOTO goto8, 1
    ARM_GOTO goto16, 2
    ARM_GOTO goto, 4
.purgem ARM_GOTO
.macro ARM_IF name, width, want
.L\name:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #1, .Lslow
    ldp x12, x13, [x21, #-16]
    cmp x13, #ARM_CONST_JS_TAG_UNDEFINED
    b.hi .Lfloat_\name
    cmp w12, #0
    cset w12, ne
    cmp w12, #\want
.if \width == 1
    ldrsb x10, [x20, #1]
.else
    ldursw x10, [x20, #1]
.endif
    mov x11, #(\width+1)
    add x10, x10, #1
    csel x10, x10, x11, eq
    add x10, x20, x10
    mov w17, #1
    b .Lbranch_poll
.Lfloat_\name:
#if ARM_HAS_LITERALS
    b .Lliteral_truth_\name
#else
    cmp x13, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
    tbz w14, #2, .Lslow
    fmov d0, x12
    fcmp d0, #0.0
    cset w12, ne
    csel w12, wzr, w12, vs
    cmp w12, #\want
.if \width == 1
    ldrsb x10, [x20, #1]
.else
    ldursw x10, [x20, #1]
.endif
    mov x11, #(\width+1)
    add x10, x10, #1
    csel x10, x10, x11, eq
    add x10, x20, x10
    mov w17, #1
    b .Lbranch_poll
#endif
.endm
    ARM_IF if_true8, 1, 1
    ARM_IF if_false8, 1, 0
    ARM_IF if_true, 4, 1
    ARM_IF if_false, 4, 0
.purgem ARM_IF
.Lbranch_poll:
    ldr x11, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x11, [x11, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w12, [x11, #ARM_OFF_JSContext_interrupt_counter]
    subs w12, w12, #1
    b.le .Lslow
    str w12, [x11, #ARM_OFF_JSContext_interrupt_counter]
    cbz w17, .Lbranch_pc_ready
    sub x21, x21, #16
.Lbranch_pc_ready:
    mov x20, x10
    ARM_DISPATCH_NEXT 1
