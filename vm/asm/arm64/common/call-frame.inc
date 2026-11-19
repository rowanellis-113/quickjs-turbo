/* GAS AAPCS64 frame instructions. The platform supplies unwind hooks. */
.macro QJS_AARCH64_FRAME_ENTER
    stp x29, x30, [sp, #-16]!
    QJS_AARCH64_FRAME_SAVED
    mov x29, sp
    QJS_AARCH64_FRAME_ESTABLISHED
.endm

.macro QJS_AARCH64_FRAME_LEAVE
    ldp x29, x30, [sp], #16
    QJS_AARCH64_FRAME_RESTORED
    ret
.endm
