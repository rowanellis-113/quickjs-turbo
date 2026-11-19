/* Complete source-owned ordinary null object opcode; MIT. */
#if ARM_HAS_NULL_PROTO
.Lnull_proto:
    cmp w12, #ARM_CONST_OP_SPECIAL_OBJECT_NULL_PROTO
    b.ne .Lslow
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    bl JS_FrameLinuxNullProtoStep
    cbz w0, .Lreload
    b .Ldone
#endif
