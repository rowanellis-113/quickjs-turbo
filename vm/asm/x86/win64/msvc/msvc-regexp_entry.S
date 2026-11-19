.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjscold$zzzzzzzzzzzzzzzzzzzzzzzzzzzzregexpop,"xr"
.p2align 4
.globl JS_FrameRegExpOpcode, JS_FrameRegExpOpcode_end
.def JS_FrameRegExpOpcode; .scl 2; .type 32; .endef
JS_FrameRegExpOpcode:
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov rcx, rbx
    call JS_FrameRegExpStep
    test eax, eax
    jz interp_reload
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameRegExpOpcode_end:
.section .pdata$zzregexpop,"dr"
.p2align 2
.rva JS_FrameRegExpOpcode, JS_FrameRegExpOpcode_end, JS_FrameInterpPropertyCold_unwind
