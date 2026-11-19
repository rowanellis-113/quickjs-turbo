/* Capture slots are followed from the current live function on every opcode.
* Attached and detached JSVarRef cells share the original pvalue owner. No
* pointer is cached across a C boundary, close_loc or a reentrant callback. */
.macro ARM_REF_SLOT name, first, width, store, keep, check
.L\name:
    ldr w14, [sp, #ARM_VM_POLICY_OFF]
    tbz w14, #3, .Lslow
.if \width == 0
    sub w10, w9, #\first
    mov x13, #1
.else
    ldurh w10, [x20, #1]
    mov x13, #3
.endif
    ldr x12, [x22, #ARM_OFF_JSStackFrame_cur_func]
    ldr x12, [x12, #ARM_OFF_JSObject_u_func_var_refs]
    ldr x12, [x12, x10, lsl #3]
    ldr x12, [x12, #ARM_OFF_JSVarRef_pvalue]
.if \check != 0
    ldr x15, [x12, #8]
    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED
.if \check == 1
    b.eq .Lslow
.else
    b.ne .Lslow
.endif
.endif
.if \store
    mov w17, #\keep
    b .Lslot_store
.else
    b .Lget_slot
.endif
.endm
    ARM_REF_SLOT get_var_ref_short, ARM_OP_get_var_ref0, 0, 0, 0, 0
    ARM_REF_SLOT put_var_ref_short, ARM_OP_put_var_ref0, 0, 1, 0, 0
    ARM_REF_SLOT set_var_ref_short, ARM_OP_set_var_ref0, 0, 1, 1, 0
    ARM_REF_SLOT get_var_ref, 0, 2, 0, 0, 0
    ARM_REF_SLOT put_var_ref, 0, 2, 1, 0, 0
    ARM_REF_SLOT set_var_ref, 0, 2, 1, 1, 0
    ARM_REF_SLOT get_var_ref_check, 0, 2, 0, 0, 1
    ARM_REF_SLOT put_var_ref_check, 0, 2, 1, 0, 1
    ARM_REF_SLOT put_var_ref_check_init, 0, 2, 1, 0, 2
.purgem ARM_REF_SLOT

.macro ARM_CHECKED_LOCAL name, store, check
.L\name:
    ldurh w10, [x20, #1]
    add x12, x23, x10, lsl #4
    mov x13, #3
    ldr x15, [x12, #8]
    cmp x15, #ARM_CONST_JS_TAG_UNINITIALIZED
.if \check == 1
    b.eq .Lslow
.else
    b.ne .Lslow
.endif
.if \store
    mov w17, #0
    b .Lslot_store
.else
    b .Lget_slot
.endif
.endm
    ARM_CHECKED_LOCAL get_loc_check, 0, 1
    ARM_CHECKED_LOCAL put_loc_check, 1, 1
    ARM_CHECKED_LOCAL put_loc_check_init, 1, 2
.purgem ARM_CHECKED_LOCAL
.Lset_loc_uninitialized:
    ldurh w10, [x20, #1]
    add x12, x23, x10, lsl #4
    mov x13, #3
    mov x10, #0
    mov x11, #ARM_CONST_JS_TAG_UNINITIALIZED
    mov w17, #1
    b .Lslot_store_value

.Lpush_const8:
    ldrb w10, [x20, #1]
    mov x13, #2
    b .Lconstant_slot
.Lpush_const:
    ldur w10, [x20, #1]
    mov x13, #5
.Lconstant_slot:
    ldr x12, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x12, [x12, #ARM_OFF_JSFunctionBytecode_cpool]
    add x12, x12, x10, lsl #4
    b .Lget_slot
.Lpush_this:
    add x12, x22, #ARM_OFF_JSFrame_this_value
    ldp x10, x11, [x12]
    ldrb w14, [x22, #ARM_OFF_JSStackFrame_is_strict_mode]
    cbnz w14, .Lthis_copy
    cmn x11, #1
    b.eq .Lthis_copy
    cmp x11, #ARM_CONST_JS_TAG_NULL
    b.eq .Lthis_global
    cmp x11, #ARM_CONST_JS_TAG_UNDEFINED
    b.ne .Lslow
.Lthis_global:
    ldr x12, [x22, #ARM_OFF_JSFrame_bytecode]
    ldr x12, [x12, #ARM_OFF_JSFunctionBytecode_realm]
    add x12, x12, #ARM_OFF_JSContext_global_obj
    ldp x10, x11, [x12]
.Lthis_copy:
    mov x13, #1
    b .Lcopy_value
