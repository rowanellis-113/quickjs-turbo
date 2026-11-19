.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjscold$zzzztruthmsvc,"xr"
.p2align 4
.globl JS_FrameTruthLnotClean, JS_FrameTruthLnotClean_end
.def JS_FrameTruthLnotClean; .scl 2; .type 32; .endef
JS_FrameTruthLnotClean:
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthLnotClean_object
    cmp eax, -7
    je JS_FrameTruthLnotClean_string
    cmp eax, -6
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthLnotClean_release
JS_FrameTruthLnotClean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthLnotClean_release
JS_FrameTruthLnotClean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthLnotClean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameTruthLnotClean_commit:
    xor eax, 1
    mov QWORD PTR [r13-16], rax
    mov QWORD PTR [r13-8], 1
    inc r12
JS_FrameTruthLnotClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthLnotClean_end:
.p2align 4
.globl JS_FrameTruthIfTrueClean, JS_FrameTruthIfTrueClean_end
.def JS_FrameTruthIfTrueClean; .scl 2; .type 32; .endef
JS_FrameTruthIfTrueClean:
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfTrueClean_object
    cmp eax, -7
    je JS_FrameTruthIfTrueClean_string
    cmp eax, -6
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfTrueClean_release
JS_FrameTruthIfTrueClean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfTrueClean_release
JS_FrameTruthIfTrueClean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfTrueClean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameTruthIfTrueClean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jz JS_FrameTruthIfTrueClean_untaken
    movsxd rax, DWORD PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfTrueClean_dispatch
JS_FrameTruthIfTrueClean_untaken:
    add r12, 5
JS_FrameTruthIfTrueClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfTrueClean_end:
.p2align 4
.globl JS_FrameTruthIfFalseClean, JS_FrameTruthIfFalseClean_end
.def JS_FrameTruthIfFalseClean; .scl 2; .type 32; .endef
JS_FrameTruthIfFalseClean:
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfFalseClean_object
    cmp eax, -7
    je JS_FrameTruthIfFalseClean_string
    cmp eax, -6
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfFalseClean_release
JS_FrameTruthIfFalseClean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfFalseClean_release
JS_FrameTruthIfFalseClean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfFalseClean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameTruthIfFalseClean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jnz JS_FrameTruthIfFalseClean_untaken
    movsxd rax, DWORD PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfFalseClean_dispatch
JS_FrameTruthIfFalseClean_untaken:
    add r12, 5
JS_FrameTruthIfFalseClean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfFalseClean_end:
.p2align 4
.globl JS_FrameTruthIfTrue8Clean, JS_FrameTruthIfTrue8Clean_end
.def JS_FrameTruthIfTrue8Clean; .scl 2; .type 32; .endef
JS_FrameTruthIfTrue8Clean:
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfTrue8Clean_object
    cmp eax, -7
    je JS_FrameTruthIfTrue8Clean_string
    cmp eax, -6
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfTrue8Clean_release
JS_FrameTruthIfTrue8Clean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfTrue8Clean_release
JS_FrameTruthIfTrue8Clean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfTrue8Clean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameTruthIfTrue8Clean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jz JS_FrameTruthIfTrue8Clean_untaken
    movsx rax, BYTE PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfTrue8Clean_dispatch
JS_FrameTruthIfTrue8Clean_untaken:
    add r12, 2
JS_FrameTruthIfTrue8Clean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfTrue8Clean_end:
.p2align 4
.globl JS_FrameTruthIfFalse8Clean, JS_FrameTruthIfFalse8Clean_end
.def JS_FrameTruthIfFalse8Clean; .scl 2; .type 32; .endef
JS_FrameTruthIfFalse8Clean:
    mov eax, DWORD PTR [r13-8]
    cmp eax, -1
    je JS_FrameTruthIfFalse8Clean_object
    cmp eax, -7
    je JS_FrameTruthIfFalse8Clean_string
    cmp eax, -6
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    cmp DWORD PTR [r8+QJS_ABI_OFF_JSStringRope_len], 0
    setne al
    jmp JS_FrameTruthIfFalse8Clean_release
JS_FrameTruthIfFalse8Clean_string:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE], 2147483647
    setne al
    jmp JS_FrameTruthIfFalse8Clean_release
JS_FrameTruthIfFalse8Clean_object:
    mov r8, QWORD PTR [r13-16]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    xor eax, eax
    test BYTE PTR [r8+QJS_ABI_BIT_JSObject_is_HTMLDDA_BYTE], QJS_ABI_BIT_JSObject_is_HTMLDDA_MASK
    sete al
JS_FrameTruthIfFalse8Clean_release:
    sub DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
JS_FrameTruthIfFalse8Clean_commit:
    sub r13, 16
    dec DWORD PTR [rsi+QJS_ABI_OFF_JSContext_interrupt_counter]
    test eax, eax
    jnz JS_FrameTruthIfFalse8Clean_untaken
    movsx rax, BYTE PTR [r12+1]
    lea r12, [r12+rax+1]
    jmp JS_FrameTruthIfFalse8Clean_dispatch
JS_FrameTruthIfFalse8Clean_untaken:
    add r12, 2
JS_FrameTruthIfFalse8Clean_dispatch:
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameTruthIfFalse8Clean_end:
.p2align 4
.globl JS_FrameTruthMSVCOff, JS_FrameTruthMSVCOff_end
.def JS_FrameTruthMSVCOff; .scl 2; .type 32; .endef
JS_FrameTruthMSVCOff:
    jmp JS_FrameTruthMSVCOldSlow
JS_FrameTruthMSVCOff_end:
.section .pdata$zztruthmsvc,"dr"
.p2align 2
.rva JS_FrameTruthLnotClean, JS_FrameTruthLnotClean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTruthIfTrueClean, JS_FrameTruthIfTrueClean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTruthIfFalseClean, JS_FrameTruthIfFalseClean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTruthIfTrue8Clean, JS_FrameTruthIfTrue8Clean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTruthIfFalse8Clean, JS_FrameTruthIfFalse8Clean_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameTruthMSVCOff, JS_FrameTruthMSVCOff_end, JS_FrameInterpPropertyCold_unwind
