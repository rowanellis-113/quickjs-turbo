/* Original intrinsic apply guard/return protocol,actual AAPCS64 state owner. */
#if ARM_HAS_VARARGS
.Lapply_forward_guard:
    adrp x15, qjs_linux_core_js_function_apply
    add x15, x15, :lo12:qjs_linux_core_js_function_apply
    cmp x14, x15
    b.ne .Lcall_host_original
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_cproto]
    cmp w14, #ARM_CONST_JS_CFUNC_generic_magic
    b.ne .Lcall_host_original
    ldrh w14, [x3, #ARM_OFF_JSObject_u_cfunc_magic]
    cbnz w14, .Lcall_host_original
    ldrb w14, [x3, #ARM_OFF_JSObject_u_cfunc_length]
    cmp w14, #2
    b.ne .Lcall_host_original
    mov w28, w0
    orr w28, w28, w17, lsl #16
    sub x14, x1, x20
    orr w28, w28, w14, lsl #24
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    bl JS_FrameApplyForwardCall
    add x27, x27, #1
    cbz w0, .Lcall_forward_original
    add x26, x26, #1
    cmp w0, #2
    b.eq .Lapply_forward_exit
    ldr x9, [x19, #ARM_OFF_JSFrameRegisterState_frame]
    str xzr, [x9, #ARM_OFF_JSStackFrame_cur_sp]
    b .Lreload
.Lapply_forward_exit:
    mov w0, #1
    b .Ldone
#endif
