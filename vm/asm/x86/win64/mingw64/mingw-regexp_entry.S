.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameRegexpEntry, JS_FrameRegexpEntry_end
.def JS_FrameRegexpEntry; .scl 2; .type 32; .endef
JS_FrameRegexpEntry:
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameRegexpStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameRegexpEntry_end:
.p2align 2
JS_FrameRegexpEntry_unwind:
.byte 33,0,0,0
.rva JS_FrameInterpUnscoped, JS_FrameInterp_end, JS_FrameInterp_unwind
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameRegexpEntry, JS_FrameRegexpEntry_end, JS_FrameRegexpEntry_unwind
