/* Complete source-owned regexp opcode bridge;MIT. No immediate operands. */
.Lregexp:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    bl JS_FrameInterpRegExp
    cbz w0, .Lreload
    b .Ldone
