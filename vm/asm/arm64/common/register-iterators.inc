/* Accepted typed synchronous iterator/checkpoint boundaries. MIT. */
#if ARM_HAS_ITERATORS
.Literator_for_of_start:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_for_of_start
    cbz w0, .Lreload
    b .Ldone
.Literator_for_of_next:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_for_of_next
    cbz w0, .Lreload
    b .Ldone
.Literator_iterator_close:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_iterator_close
    cbz w0, .Lreload
    b .Ldone
.Literator_catch:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_catch
    cbz w0, .Lreload
    b .Ldone
.Literator_gosub:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_gosub
    cbz w0, .Lreload
    b .Ldone
.Literator_ret:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_ret
    cbz w0, .Lreload
    b .Ldone
.Literator_nip_catch:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_nip_catch
    cbz w0, .Lreload
    b .Ldone
.Literator_check_object:
    str x20, [x19, #ARM_OFF_JSFrameRegisterState_pc]
    str x21, [x19, #ARM_OFF_JSFrameRegisterState_sp]
    mov x0, x19
    add x26, x26, #1
    add x27, x27, #1
    bl JS_LinuxIterator_check_object
    cbz w0, .Lreload
    b .Ldone
#endif
