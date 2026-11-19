/* Callee-saved corruption sentinel; tests only, never linked into qjs. */
.text
.p2align 2
.global qjs_aarch64_test_saved
.type qjs_aarch64_test_saved, %function
qjs_aarch64_test_saved:
.cfi_startproc
    stp x29, x30, [sp, #-96]!
.cfi_def_cfa_offset 96
.cfi_offset 29, -96
.cfi_offset 30, -88
    stp x19, x20, [sp, #16]
.cfi_offset 19, -80
.cfi_offset 20, -72
    stp x21, x22, [sp, #32]
.cfi_offset 21, -64
.cfi_offset 22, -56
    stp x23, x24, [sp, #48]
.cfi_offset 23, -48
.cfi_offset 24, -40
    stp x25, x26, [sp, #64]
.cfi_offset 25, -32
.cfi_offset 26, -24
    stp x27, x28, [sp, #80]
.cfi_offset 27, -16
.cfi_offset 28, -8
    mov x29, sp
.cfi_def_cfa_register 29
    mov x19, #0x1919
    mov x20, #0x2020
    mov x21, #0x2121
    mov x22, #0x2222
    mov x23, #0x2323
    mov x24, #0x2424
    mov x25, #0x2525
    mov x26, #0x2626
    mov x27, #0x2727
    mov x28, #0x2828
    bl qjs_aarch64_call_generic
/* The fixture callback returns only a primitive; no owning result is dropped. */
#ifdef PROBE_BAD_SAVED
    mov x19, #0
#endif
    mov w0, #1
.macro check_saved reg, value
    mov x10, #\value
    cmp \reg, x10
    b.ne 1f
.endm
    check_saved x19, 0x1919
    check_saved x20, 0x2020
    check_saved x21, 0x2121
    check_saved x22, 0x2222
    check_saved x23, 0x2323
    check_saved x24, 0x2424
    check_saved x25, 0x2525
    check_saved x26, 0x2626
    check_saved x27, 0x2727
    check_saved x28, 0x2828
    mov w0, #0
1:
    ldp x19, x20, [sp, #16]
.cfi_restore 19
.cfi_restore 20
    ldp x21, x22, [sp, #32]
.cfi_restore 21
.cfi_restore 22
    ldp x23, x24, [sp, #48]
.cfi_restore 23
.cfi_restore 24
    ldp x25, x26, [sp, #64]
.cfi_restore 25
.cfi_restore 26
    ldp x27, x28, [sp, #80]
.cfi_restore 27
.cfi_restore 28
    ldp x29, x30, [sp], #96
.cfi_restore 29
.cfi_restore 30
.cfi_def_cfa sp, 0
    ret
.cfi_endproc
.global qjs_aarch64_test_saved_end
qjs_aarch64_test_saved_end:
.size qjs_aarch64_test_saved, .-qjs_aarch64_test_saved
.section .note.GNU-stack,"",%progbits
