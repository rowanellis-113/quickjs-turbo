.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qztpd$typeof,"dw"
.p2align 3
.globl JS_FrameTypeofNativeStats
JS_FrameTypeofNativeStats:
.zero 24
.section .qztpc$typeof,"xr"
.p2align 4
.globl JS_FrameTypeofValueClean, JS_FrameTypeofValueClean_end
.def JS_FrameTypeofValueClean; .scl 2; .type 32; .endef
JS_FrameTypeofValueClean:
    mov edx, DWORD PTR [rip+JS_FrameTypeofNativeMode]
    test edx, edx
    jz JS_FrameTypeofValueClean_configure
    test edx, 2
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofValueClean_immediate
    cmp eax, -9
    jl interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofValueClean_classified
JS_FrameTypeofValueClean_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofValueClean_classified
    cmp eax, 7
    je JS_FrameTypeofValueClean_classified
    cmp eax, 8
    jne interp_slow
JS_FrameTypeofValueClean_classified:
    cmp eax, -7
    je JS_FrameTypeofValueClean_atom76
    cmp eax, -6
    je JS_FrameTypeofValueClean_atom76
    cmp eax, -9
    je JS_FrameTypeofValueClean_atom150
    cmp eax, -8
    je JS_FrameTypeofValueClean_atom78
    cmp eax, 0
    je JS_FrameTypeofValueClean_atom74
    cmp eax, 8
    je JS_FrameTypeofValueClean_atom74
    cmp eax, 1
    je JS_FrameTypeofValueClean_atom75
    cmp eax, 2
    je JS_FrameTypeofValueClean_atom77
    cmp eax, 3
    je JS_FrameTypeofValueClean_atom73
    cmp eax, 7
    je JS_FrameTypeofValueClean_atom150
    ud2
JS_FrameTypeofValueClean_atom76:
    mov ecx, 76
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom150:
    mov ecx, 150
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom78:
    mov ecx, 78
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom74:
    mov ecx, 74
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom75:
    mov ecx, 75
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom77:
    mov ecx, 77
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_atom73:
    mov ecx, 73
    jmp JS_FrameTypeofValueClean_result
JS_FrameTypeofValueClean_result:
    mov r8, QWORD PTR [rbx+56]
    mov r8, QWORD PTR [r8+QJS_ABI_OFF_JSRuntime_atom_array]
    mov r8, QWORD PTR [r8+rcx*8]
    add DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    mov QWORD PTR [r13-16], r8
    mov QWORD PTR [r13-8], -7
    inc r12
    test edx, 4
    jz JS_FrameTypeofValueClean_dispatch
    lock inc QWORD PTR [rip+JS_FrameTypeofNativeStats+0]
JS_FrameTypeofValueClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofValueClean_configure:
    call JS_FrameTypeofNativeConfigure
    jmp JS_FrameTypeofValueClean
JS_FrameTypeofValueClean_end:
.p2align 4
.globl JS_FrameTypeofFunctionClean, JS_FrameTypeofFunctionClean_end
.def JS_FrameTypeofFunctionClean; .scl 2; .type 32; .endef
JS_FrameTypeofFunctionClean:
    mov edx, DWORD PTR [rip+JS_FrameTypeofNativeMode]
    test edx, edx
    jz JS_FrameTypeofFunctionClean_configure
    test edx, 2
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofFunctionClean_immediate
    cmp eax, -9
    jl interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofFunctionClean_classified
JS_FrameTypeofFunctionClean_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofFunctionClean_classified
    cmp eax, 7
    je JS_FrameTypeofFunctionClean_classified
    cmp eax, 8
    jne interp_slow
JS_FrameTypeofFunctionClean_classified:
    xor ecx, ecx
    mov QWORD PTR [r13-16], rcx
    mov QWORD PTR [r13-8], 1
    inc r12
    test edx, 4
    jz JS_FrameTypeofFunctionClean_dispatch
    lock inc QWORD PTR [rip+JS_FrameTypeofNativeStats+8]
JS_FrameTypeofFunctionClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofFunctionClean_configure:
    call JS_FrameTypeofNativeConfigure
    jmp JS_FrameTypeofFunctionClean
JS_FrameTypeofFunctionClean_end:
.p2align 4
.globl JS_FrameTypeofUndefinedClean, JS_FrameTypeofUndefinedClean_end
.def JS_FrameTypeofUndefinedClean; .scl 2; .type 32; .endef
JS_FrameTypeofUndefinedClean:
    mov edx, DWORD PTR [rip+JS_FrameTypeofNativeMode]
    test edx, edx
    jz JS_FrameTypeofUndefinedClean_configure
    test edx, 2
    jnz interp_slow
    mov eax, DWORD PTR [r13-8]
    cmp eax, -6
    jg JS_FrameTypeofUndefinedClean_immediate
    cmp eax, -9
    jl interp_slow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle interp_slow
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jmp JS_FrameTypeofUndefinedClean_classified
JS_FrameTypeofUndefinedClean_immediate:
    cmp eax, 3
    jbe JS_FrameTypeofUndefinedClean_classified
    cmp eax, 7
    je JS_FrameTypeofUndefinedClean_classified
    cmp eax, 8
    jne interp_slow
JS_FrameTypeofUndefinedClean_classified:
    cmp eax, 3
    sete cl
    movzx ecx, cl
    mov QWORD PTR [r13-16], rcx
    mov QWORD PTR [r13-8], 1
    inc r12
    test edx, 4
    jz JS_FrameTypeofUndefinedClean_dispatch
    lock inc QWORD PTR [rip+JS_FrameTypeofNativeStats+16]
JS_FrameTypeofUndefinedClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTypeofUndefinedClean_configure:
    call JS_FrameTypeofNativeConfigure
    jmp JS_FrameTypeofUndefinedClean
JS_FrameTypeofUndefinedClean_end:
.section .pdata$zzzztypeof,"dr"
.p2align 2
.rva JS_FrameTypeofValueClean, JS_FrameTypeofValueClean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTypeofFunctionClean, JS_FrameTypeofFunctionClean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTypeofUndefinedClean, JS_FrameTypeofUndefinedClean_end, JS_FrameInterpPropertyCold_unwind
