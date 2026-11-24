/* AArch64 register instruction semantics. Linux/AAPCS64 CFI and entry live
* in the platform wrapper; generated values and register contract are required. */
.Lpush_i8:
    ldrsb w10, [x20, #1]
    add x20, x20, #2
    b .Lpush_int
.Lpush_i16:
// Bytecode operands are unaligned; Linux AArch64 permits these loads.
    ldursh w10, [x20, #1]
    add x20, x20, #3
    b .Lpush_int
.Lpush_i32:
    ldur w10, [x20, #1]
    add x20, x20, #5
    b .Lpush_int
.Lpush_small:
    sub w10, w9, #ARM_OP_push_0
    add x20, x20, #1
.Lpush_int:
    mov x11, #ARM_CONST_JS_TAG_INT
    b .Lpush_value
.Lundefined:
    mov x10, #0
    mov x11, #ARM_CONST_JS_TAG_UNDEFINED
    b .Lliteral
.Lnull:
    mov x10, #0
    mov x11, #ARM_CONST_JS_TAG_NULL
    b .Lliteral
.Lbool:
    cmp w9, #ARM_OP_push_true
    cset w10, eq
    mov x11, #ARM_CONST_JS_TAG_BOOL
.Lliteral:
    add x20, x20, #1
.Lpush_value:
    stp x10, x11, [x21], #16
    ARM_DISPATCH_NEXT 1
.Lnop:
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1

// Inline-header duplication cannot allocate or invoke a destructor.
.Lget_loc_short:
    sub w10, w9, #ARM_OP_get_loc0
    add x12, x23, x10, lsl #4
    mov x13, #1
    b .Lget_slot
.Lget_arg_short:
    sub w10, w9, #ARM_OP_get_arg0
    add x12, x24, x10, lsl #4
    mov x13, #1
    b .Lget_slot
.Lget_loc8:
    ldrb w10, [x20, #1]
    add x12, x23, x10, lsl #4
    mov x13, #2
    b .Lget_slot
.Lget_loc:
    ldurh w10, [x20, #1]
    add x12, x23, x10, lsl #4
    mov x13, #3
    b .Lget_slot
.Lget_arg:
    ldurh w10, [x20, #1]
    add x12, x24, x10, lsl #4
    mov x13, #3
.Lget_slot:
    ldp x10, x11, [x12]
#if ARM_HAS_PROPERTY_IC
// The live local/argument/capture owns the receiver until a safepoint.
// Every failed borrowed PIC reconstructs the original owning operand.
    cmp x11, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lcopy_value
    add x14, x20, x13
    ldrb w14, [x14]
    cmp w14, #ARM_OP_get_field
    b.ne .Lcopy_value
    add x20, x20, x13
    add x26, x26, #1
    mov x0, x10
    mov x1, x11
    b .Lproperty_borrow_entry
#endif
.Lcopy_value:
    tbz x11, #63, .Lcopy_commit
    ldur w14, [x10, #ARM_REF_COUNT_OFFSET]
    add w14, w14, #1
    stur w14, [x10, #ARM_REF_COUNT_OFFSET]
.Lcopy_commit:
    add x20, x20, x13
    b .Lpush_value
.Ldup:
    ldp x10, x11, [x21, #-16]
    mov x13, #1
    b .Lcopy_value
.Ldrop:
    ldp x10, x11, [x21, #-16]
    tbz x11, #63, .Ldrop_commit
    ldur w14, [x10, #ARM_REF_COUNT_OFFSET]
    cmp w14, #1
    b.le .Lslow
    sub w14, w14, #1
    stur w14, [x10, #ARM_REF_COUNT_OFFSET]
.Ldrop_commit:
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lcurrent_function:
#if ARM_HAS_ARGUMENTS
    ldr x12, [x22, #ARM_OFF_JSFrame_bytecode]
    ldrb w13, [x12, #ARM_FRAME_KIND_OFFSET]
    cmp w13, #2
    b.ne .Larguments_not_object
    ldrb w13, [x12, #(ARM_OFF_JSFunctionBytecode_pc2line_len+4)]
    cmp w13, #128
    b.eq .Larguments_object
.Larguments_not_object:
#endif
    ldrb w12, [x20, #1]
    cmp w12, #ARM_CONST_OP_SPECIAL_OBJECT_THIS_FUNC
#if ARM_HAS_NULL_PROTO
    b.ne .Lnull_proto
#else
    b.ne .Lslow
#endif
    add x12, x22, #ARM_OFF_JSStackFrame_cur_func
    ldp x10, x11, [x12]
    mov x13, #2
    b .Lcopy_value

.Lbitand:
    ldp x10, x11, [x21, #-32]
    ldp x12, x13, [x21, #-16]
    orr x14, x11, x13
    cbnz x14, .Lslow
    and w10, w10, w12
    stp x10, x11, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
