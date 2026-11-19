/* Genuine original Function.prototype.call gate. MIT.
* The temporary32-byte private probe lease never aliases the live VM save
* area or policy. x28 retains only scalar original argc/flags/PC size.
*/
#if ARM_HAS_FORWARDING
.Lcall_forward_guard:
    cmp w12, #ARM_CONST_JS_CLASS_C_FUNCTION
    b.ne .Lcall_host_original
    ldr x14, [x3, #ARM_OFF_JSObject_u_cfunc_c_function]
    adrp x15, qjs_aarch64_core_js_function_call
    add x15, x15, :lo12:qjs_aarch64_core_js_function_call
    cmp x14, x15
#if ARM_HAS_VARARGS
    b.ne .Lapply_forward_guard
#else
    b.ne .Lcall_host_original
#endif
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_cproto]
    cbnz w14, .Lcall_host_original
    ldrh w14, [x3, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w14, .Lcall_host_original
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #1
    b.ne .Lcall_host_original
    mov w28, w0
    orr w28, w28, w17, lsl #16
    sub x14, x1, x20
    orr w28, w28, w14, lsl #24
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    sub sp, sp, #32
.cfi_adjust_cfa_offset 32
    bl JS_AArch64ForwardProbe
    add sp, sp, #32
.cfi_adjust_cfa_offset -32
    add x27, x27, #1
    cbz w0, .Lcall_forward_original
    add x26, x26, #1
    cmp w0, #2
    b.eq .Lcall_forward_leaf
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str xzr, [x9, #ARM_OFF_JSStackFrame_cur_sp]
    b .Lreload
.Lcall_forward_leaf:
    str xzr, [x22, #ARM_OFF_JSStackFrame_cur_sp]
    add x9, x19, #ARM_OFF_JSFrameRegisterState_result
    ldp x0, x1, [x9]
    b .Lhost_return
.Lcall_forward_original:
    uxth w0, w28
    ubfx w17, w28, #16, #2
    lsr w14, w28, #24
    add x1, x20, x14
    sub x2, x21, x0, lsl #4
    ldr x3, [x2, #-16]
    ldrh w12, [x3, #ARM_OFF_JSObject_class_id]
    b .Lcall_host_original
#endif
