/* Original arguments prefix admission and typed same-activation builder. MIT. */
#if ARM_HAS_ARGUMENTS
.Larguments_guard:
// Called with the ordinary decoded argc/next-PC/argv/callee/bytecode.
    mov w12, #32765
    cmp w0, w12
    b.hi .Larguments_decline
    adrp x12, JS_FrameArgumentsMode
    ldr w12, [x12, :lo12:JS_FrameArgumentsMode]
    tbnz w12, #1, .Larguments_decline
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    tbnz w12, #0, .Larguments_decline
    cmp w12, #2
    b.ne .Larguments_unknown
    ldrb w12, [x7, #(ARM_OFF_JSFunctionBytecode_pc2line_len+4)]
    cmp w12, #128
    b.eq .Larguments_ready
    cmp w12, #64
    b.eq .Larguments_decline
.Larguments_unknown:
    ldr w12, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_len]
    cmp w12, #2
    b.lo .Larguments_negative
    cmp w12, #2048
    b.hi .Larguments_negative
    cmp w12, #17
    mov w14, #17
    csel w12, w12, w14, ls
    ldr x13, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    add x14, x13, x12
.Larguments_prefix:
    cmp x13, x14
    b.hs .Larguments_negative
    ldrb w12, [x13], #1
    cmp w12, #ARM_OP_push_this
    b.eq .Larguments_store
    cmp w12, #ARM_OP_special_object
    b.ne .Larguments_negative
    cmp x13, x14
    b.hs .Larguments_negative
    ldrb w12, [x13], #1
    cmp w12, #1
    b.ls .Larguments_cold
    cmp w12, #4
    b.hi .Larguments_negative
.Larguments_store:
    cmp x13, x14
    b.hs .Larguments_negative
    ldrb w12, [x13], #1
    cmp w12, #ARM_OP_put_loc8
    b.eq .Larguments_local8
    sub w12, w12, #ARM_OP_put_loc0
    cmp w12, #3
    b.hi .Larguments_negative
    b .Larguments_prefix
.Larguments_local8:
    add x13, x13, #1
    b .Larguments_prefix
.Larguments_negative:
    ldrb w12, [x7, #ARM_FRAME_KIND_OFFSET]
    cmp w12, #2
    b.ne .Larguments_decline
    mov w12, #64
    strb w12, [x7, #(ARM_OFF_JSFunctionBytecode_pc2line_len+4)]
.Larguments_decline:
    b .Lcall_original_kind
.Larguments_cold:
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x12, .Larguments_cold_ready
    ldr x13, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x12, x12, x13
    b.cs .Larguments_decline
    adds x12, x12, #8192
    b.cs .Larguments_decline
    mov x13, sp
    cmp x13, x12
    b.lo .Larguments_decline
.Larguments_cold_ready:
    str x1, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    str x21, [x22, #ARM_OFF_JSStackFrame_cur_sp]
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    bl JS_FrameArgumentsTry
    cmp w0, #0
    b.ge .Lreload
    mov x0, x19
    bl JS_FrameInterpSlow
    cbz w0, .Lreload
    b .Ldone
.Larguments_object:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    bl JS_FrameArgumentsStep
    cbz w0, .Lreload
    b .Ldone

// Complete provided-window argument child: source GNU Ready semantics.
.Larguments_ready:
    adrp x12, JS_FrameArgumentsMode
    ldr w16, [x12, :lo12:JS_FrameArgumentsMode]
    tst w16, #24
    b.ne .Larguments_cold
    ldrb w12, [x7, #ARM_FRAME_CALL_FORMALS_OFFSET]
    cmp w0, w12
    b.lo .Larguments_cold
    ldrh w9, [x7, #ARM_FRAME_CALL_META_OFFSET]
    ldr x8, [x19, #ARM_OFF_JSFrameRegisterState_segment]
    ldr x10, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_capacity]
    subs x12, x12, x10
    b.lo .Larguments_cold
    cmp x12, x9
    b.lo .Larguments_cold
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_native_stack_limit]
    cbz x12, .Larguments_ready_quota
    ldr x13, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    adds x12, x12, x13
    b.cs .Larguments_cold
    adds x12, x12, x9
    b.cs .Larguments_cold
    adds x12, x12, #4096
    b.cs .Larguments_cold
    mov x13, sp
    cmp x13, x12
    b.lo .Larguments_cold
.Larguments_ready_quota:
    ldr x12, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x15, [x12, #ARM_OFF_JSFunctionBytecode_realm]
    ldr w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    subs w12, w12, #1
    b.le .Larguments_cold
// Commit only after every guard. No call or failing operation follows.
    str w12, [x15, #ARM_OFF_JSContext_interrupt_counter]
    tbz w16, #2, .Larguments_ready_counted
    adrp x12, JS_FrameArgumentsStats
    add x12, x12, :lo12:JS_FrameArgumentsStats
    add x12, x12, #16
.Larguments_ready_count_child:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Larguments_ready_count_child
    add x12, x12, #32
.Larguments_ready_count_native:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Larguments_ready_count_native
.Larguments_ready_counted:
    str x1, [x22, #ARM_OFF_JSStackFrame_cur_pc]
    str x21, [x22, #ARM_OFF_JSFrame_saved_sp]
    and w12, w17, #1
    add w12, w12, w0
    add w12, w12, #1
    tbz w17, #1, .Larguments_ready_pending
    orr w12, w12, #0x8000
.Larguments_ready_pending:
    strh w12, [x22, #ARM_OFF_JSFrame_pending]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_data]
    add x10, x10, x12
    str x22, [x10, #ARM_OFF_JSStackFrame_prev_frame]
    add x12, x10, #ARM_OFF_JSStackFrame_cur_func
    stp x3, x4, [x12]
    str x2, [x10, #ARM_OFF_JSStackFrame_arg_buf]
    str xzr, [x10, #ARM_OFF_JSStackFrame_var_refs]
    str xzr, [x10, #ARM_OFF_JSStackFrame_cur_pc]
    stp xzr, xzr, [x10, #ARM_OFF_JSStackFrame_cur_sp]
    strh wzr, [x10, #ARM_OFF_JSStackFrame_var_ref_count]
    strh w0, [x10, #ARM_OFF_JSStackFrame_arg_count]
    ldrb w12, [x7, #ARM_STRICT_BYTE]
    and w12, w12, #ARM_STRICT_MASK
    lsr w12, w12, #ARM_STRICT_SHIFT
    str w12, [x10, #ARM_OFF_JSStackFrame_is_strict_mode]
    str x7, [x10, #ARM_OFF_JSFrame_bytecode]
    mov x5, #0
    mov x6, #ARM_CONST_JS_TAG_UNDEFINED
    tbz w17, #0, .Larguments_ready_this
    ldp x5, x6, [x2, #-32]
.Larguments_ready_this:
    add x12, x10, #ARM_OFF_JSFrame_this_value
    stp x5, x6, [x12]
    str xzr, [x10, #ARM_OFF_JSFrame_saved_sp]
    str x8, [x10, #ARM_OFF_JSFrame_segment]
    str w9, [x10, #ARM_OFF_JSFrame_frame_bytes]
    strh wzr, [x10, #ARM_OFF_JSFrame_owned_args]
    strh wzr, [x10, #ARM_OFF_JSFrame_pending]
    add x12, x10, #ARM_FRAME_HEADER_BYTES
    str x2, [x12, #ARM_OFF_JSFrameArgumentsRecord_argv]
    str w0, [x12, #ARM_OFF_JSFrameArgumentsRecord_argc]
    movz w13, #(ARM_CONST_ARGUMENTS_SIGNATURE & 65535)
    movk w13, #(ARM_CONST_ARGUMENTS_SIGNATURE >> 16), lsl #16
    str w13, [x12, #ARM_OFF_JSFrameArgumentsRecord_signature]
    add x23, x12, #ARM_SIZE_JSFrameArgumentsRecord
    str x23, [x10, #ARM_OFF_JSStackFrame_var_buf]
    mov x24, x2
    mov x21, x23
    ldrb w13, [x7, #ARM_FRAME_CALL_LOCALS_OFFSET]
    mov x14, #ARM_CONST_JS_TAG_UNDEFINED
    cbz w13, .Larguments_ready_locals_done
.Larguments_ready_locals:
    stp xzr, x14, [x21], #16
    subs w13, w13, #1
    b.ne .Larguments_ready_locals
.Larguments_ready_locals_done:
    ldrh w13, [x7, #ARM_OFF_JSFunctionBytecode_var_ref_count]
    strh w13, [x10, #ARM_OFF_JSStackFrame_var_ref_count]
    cbz w13, .Larguments_ready_captures_done
    ldrh w14, [x7, #ARM_OFF_JSFunctionBytecode_stack_size]
    add x14, x21, x14, lsl #4
    str x14, [x10, #ARM_OFF_JSStackFrame_var_refs]
.Larguments_ready_captures:
    str xzr, [x14], #ARM_VAR_REF_POINTER_BYTES
    subs w13, w13, #1
    b.ne .Larguments_ready_captures
.Larguments_ready_captures_done:
    ldr x20, [x7, #ARM_OFF_JSFunctionBytecode_byte_code_buf]
    ldr x12, [x8, #ARM_OFF_JSFrameSegment_used]
    add x12, x12, x9
    str x12, [x8, #ARM_OFF_JSFrameSegment_used]
    ldr x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    add x12, x12, x9
    str x12, [x19, #ARM_OFF_JSFrameRegisterState_used_bytes]
    str x10, [x19, #ARM_OFF_JSFrameRegisterState_frame]
// Dedicated commit marker for the shared publication factory.
    mov x22, x10
    ldr x11, [x19, #ARM_OFF_JSFrameRegisterState_rt]
    str x22, [x11, #ARM_OFF_JSRuntime_current_stack_frame]
#ifdef QJS_AARCH64_VM_INSTRUMENT
    ldr x12, [sp, #96]
    add x12, x12, #1
    str x12, [sp, #96]
    tbz w17, #1, .Larguments_ready_observed
    ldr x12, [sp, #112]
    add x12, x12, #1
    str x12, [sp, #112]
.Larguments_ready_observed:
#endif
    ARM_DISPATCH_NEXT 1

// Complete original argument access leaves. All misses precede mutation.
.Lget_array_el:
    adrp x12, JS_FrameArgumentsMode
    ldr w16, [x12, :lo12:JS_FrameArgumentsMode]
    tbz w16, #0, .Lslow
    tst w16, #96
    b.ne .Lslow
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldp x2, x3, [x21, #-16]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lslow
    ldr w4, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w4
    b.hs .Lslow
    ldrb w4, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w4, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lslow
    ldur w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARGUMENTS
    b.eq .Lget_array_el_plain
    cmp w4, #ARM_CONST_JS_CLASS_MAPPED_ARGUMENTS
    b.ne .Lslow
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr x5, [x5, w2, uxtw #3]
    cbz x5, .Lslow
    ldr x5, [x5, #ARM_OFF_JSVarRef_pvalue]
    cbz x5, .Lslow
    b .Lget_array_el_slot
.Lget_array_el_plain:
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
.Lget_array_el_slot:
    ldp x6, x7, [x5]
    tbz x7, #63, .Lget_array_el_value
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lget_array_el_value:
    tbz w16, #2, .Lget_array_el_counted
    adrp x12, JS_FrameArgumentsAccessStats
    add x12, x12, :lo12:JS_FrameArgumentsAccessStats
    add x12, x12, #0
.Lget_array_el_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lget_array_el_count
.Lget_array_el_counted:
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-32]
    sub x21, x21, #16
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lget_array_el2:
    adrp x12, JS_FrameArgumentsMode
    ldr w16, [x12, :lo12:JS_FrameArgumentsMode]
    tbz w16, #0, .Lslow
    tst w16, #96
    b.ne .Lslow
    ldp x0, x1, [x21, #-32]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldp x2, x3, [x21, #-16]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lslow
    ldr w4, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w4
    b.hs .Lslow
    ldrb w4, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w4, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lslow
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARGUMENTS
    b.eq .Lget_array_el2_plain
    cmp w4, #ARM_CONST_JS_CLASS_MAPPED_ARGUMENTS
    b.ne .Lslow
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr x5, [x5, w2, uxtw #3]
    cbz x5, .Lslow
    ldr x5, [x5, #ARM_OFF_JSVarRef_pvalue]
    cbz x5, .Lslow
    b .Lget_array_el2_slot
.Lget_array_el2_plain:
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
.Lget_array_el2_slot:
    ldp x6, x7, [x5]
    tbz x7, #63, .Lget_array_el2_value
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    add w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lget_array_el2_value:
    tbz w16, #2, .Lget_array_el2_counted
    adrp x12, JS_FrameArgumentsAccessStats
    add x12, x12, :lo12:JS_FrameArgumentsAccessStats
    add x12, x12, #8
.Lget_array_el2_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lget_array_el2_count
.Lget_array_el2_counted:
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Lput_array_el:
    adrp x12, JS_FrameArgumentsMode
    ldr w16, [x12, :lo12:JS_FrameArgumentsMode]
    tbz w16, #0, .Lslow
    tst w16, #96
    b.ne .Lslow
    ldp x0, x1, [x21, #-48]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lslow
    ldp x2, x3, [x21, #-32]
    cmp x3, #ARM_CONST_JS_TAG_INT
    b.ne .Lslow
    ldr w4, [x0, #ARM_OFF_JSObject_u_array_count]
    cmp w2, w4
    b.hs .Lslow
    ldrb w4, [x0, #ARM_BIT_JSObject_fast_array_BYTE]
    tst w4, #ARM_BIT_JSObject_fast_array_MASK
    b.eq .Lslow
    ldur w4, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w4, #1
    b.le .Lslow
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARGUMENTS
    b.eq .Lput_array_el_plain
    cmp w4, #ARM_CONST_JS_CLASS_MAPPED_ARGUMENTS
    b.ne .Lslow
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    ldr x5, [x5, w2, uxtw #3]
    cbz x5, .Lslow
    ldr x5, [x5, #ARM_OFF_JSVarRef_pvalue]
    cbz x5, .Lslow
    b .Lput_array_el_slot
.Lput_array_el_plain:
    ldr x5, [x0, #ARM_OFF_JSObject_u_array_u_values]
    add x5, x5, w2, uxtw #4
.Lput_array_el_slot:
    ldp x6, x7, [x5]
    tbz x7, #63, .Lput_array_el_store
    cmp x6, x0
    b.eq .Lslow
    ldur w8, [x6, #ARM_REF_COUNT_OFFSET]
    cmp w8, #1
    b.le .Lslow
    sub w8, w8, #1
    stur w8, [x6, #ARM_REF_COUNT_OFFSET]
.Lput_array_el_store:
    ldp x6, x7, [x21, #-16]
    stp x6, x7, [x5]
    tbz w16, #2, .Lput_array_el_counted
    adrp x12, JS_FrameArgumentsAccessStats
    add x12, x12, :lo12:JS_FrameArgumentsAccessStats
    add x12, x12, #16
.Lput_array_el_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Lput_array_el_count
.Lput_array_el_counted:
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    sub x21, x21, #48
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
.Larguments_length:
    adrp x12, JS_FrameArgumentsMode
    ldr w16, [x12, :lo12:JS_FrameArgumentsMode]
    tbz w16, #0, .Lget_length_original
    tbnz w16, #5, .Lget_length_original
    tbnz w16, #7, .Lget_length_original
    adrp x12, JS_LinuxArgumentsLengthControl
    add x12, x12, :lo12:JS_LinuxArgumentsLengthControl
    ldarb w12, [x12]
    cmp w12, #1
    b.ne .Lget_length_original
    ldp x0, x1, [x21, #-16]
    cmp x1, #ARM_CONST_JS_TAG_OBJECT
    b.ne .Lget_length_original
    ldrh w4, [x0, #ARM_OFF_JSObject_class_id]
    cmp w4, #ARM_CONST_JS_CLASS_ARGUMENTS
    b.eq .Larguments_length_class
    cmp w4, #ARM_CONST_JS_CLASS_MAPPED_ARGUMENTS
    b.ne .Lget_length_original
.Larguments_length_class:
    ldur w8, [x0, #ARM_REF_COUNT_OFFSET]
    cmp w8, #1
    b.le .Lslow
    ldr x5, [x0, #ARM_OFF_JSObject_shape]
    ldr w4, [x5, #ARM_OFF_JSShape_prop_count]
    cbz w4, .Lslow
    ldr w4, [x5, #ARM_OFF_JSShape_prop_hash_mask]
    add x5, x5, w4, uxtw #2
    add x5, x5, #(ARM_OFF_JSShape_hash_table + 4)
    ldr w4, [x5, #ARM_OFF_JSShapeProperty_atom]
    cmp w4, #ARM_CONST_JS_ATOM_length
    b.ne .Lslow
    ldr w4, [x5]
    tst w4, #ARM_PROPERTY_DESC_TMASK
    b.ne .Lslow
    ldr x5, [x0, #ARM_OFF_JSObject_prop]
    ldp x6, x7, [x5, #ARM_OFF_JSProperty_u_value]
    cmp x7, #ARM_CONST_JS_TAG_INT
    b.eq .Larguments_length_value
    cmp x7, #ARM_CONST_JS_TAG_FLOAT64
    b.ne .Lslow
.Larguments_length_value:
    tbz w16, #2, .Larguments_length_counted
    adrp x12, JS_FrameArgumentsAccessStats
    add x12, x12, :lo12:JS_FrameArgumentsAccessStats
    add x12, x12, #24
.Larguments_length_count:
    ldxr x13, [x12]
    add x13, x13, #1
    stxr w14, x13, [x12]
    cbnz w14, .Larguments_length_count
.Larguments_length_counted:
    sub w8, w8, #1
    stur w8, [x0, #ARM_REF_COUNT_OFFSET]
    stp x6, x7, [x21, #-16]
    add x20, x20, #1
    ARM_DISPATCH_NEXT 1
#endif
