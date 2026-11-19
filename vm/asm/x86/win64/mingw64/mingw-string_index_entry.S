.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjzzpc,"xr"
.p2align 4
.globl JS_FrameStringIndexClean, JS_FrameStringIndexClean_end
.def JS_FrameStringIndexClean; .scl 2; .type 32; .endef
JS_FrameStringIndexClean:
    cmp QWORD PTR [r13-24], -7
    jne interp_slow
    test BYTE PTR [rip+JS_FrameStringIndexMode], 2
    jnz interp_slow
    mov r10, QWORD PTR [r13-32]
    mov eax, DWORD PTR [r10+QJS_ABI_BIT_JSString_len_BYTE]
    and eax, 0x7fffffff
    cmp DWORD PTR [r13-16], eax
    jae interp_slow
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameStringIndexStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameStringIndexClean_end:
.p2align 4
.globl JS_FrameStringIndexDirty, JS_FrameStringIndexDirty_end
.def JS_FrameStringIndexDirty; .scl 2; .type 32; .endef
JS_FrameStringIndexDirty:
    cmp QWORD PTR [r13-24], -7
    jne dirty_interp_slow
    test BYTE PTR [rip+JS_FrameStringIndexMode], 2
    jnz dirty_interp_slow
    mov r10, QWORD PTR [r13-32]
    mov eax, DWORD PTR [r10+QJS_ABI_BIT_JSString_len_BYTE]
    and eax, 0x7fffffff
    cmp DWORD PTR [r13-16], eax
    jae dirty_interp_slow
    mov QWORD PTR [rbx], rbp
    mov QWORD PTR [rbx+16], r12
    mov QWORD PTR [rbx+24], r13
    mov r10, QWORD PTR [rbx+56]
    mov QWORD PTR [r10+QJS_ABI_OFF_JSRuntime_current_stack_frame], rbp
    mov rcx, rbx
    call JS_FrameStringIndexStep
    test eax, eax
    jz JS_FrameNativeLifetimeResume
    mov rbp, QWORD PTR [rbx]
    mov r12, QWORD PTR [rbx+16]
    mov r13, QWORD PTR [rbx+24]
    jmp interp_exit
JS_FrameStringIndexDirty_end:
.p2align 2
JS_FrameStringIndexEntry_unwind:
.byte 33,0,0,0
.rva JS_FrameInterpUnscoped, JS_FrameInterp_end, JS_FrameInterp_unwind
.section .pdata$zzzzzznullfast,"dr"
.p2align 2
.rva JS_FrameStringIndexClean, JS_FrameStringIndexClean_end, JS_FrameStringIndexEntry_unwind
.rva JS_FrameStringIndexDirty, JS_FrameStringIndexDirty_end, JS_FrameStringIndexEntry_unwind
