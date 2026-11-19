.include "interpreter-private-abi-gas.inc"
.intel_syntax noprefix
.section .qjscold$zzzzzzzzzzzzzzzzzzzzlatinindex,"xr"
.p2align 4
.globl JS_FrameLatinIndexConsume, JS_FrameLatinIndexConsume_end
.def JS_FrameLatinIndexConsume; .scl 2; .type 32; .endef
JS_FrameLatinIndexConsume:
    cmp DWORD PTR [r13-24], -7
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-32]
    cmp DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET], 1
    jle JS_FrameTruthMSVCOldSlow
    mov eax, DWORD PTR [rip+JS_FrameSmallCharMode]
    and eax, 3
    cmp eax, 1
    jne JS_FrameTruthMSVCOldSlow
    mov ecx, DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE]
    and ecx, 0x7fffffff
    mov edx, DWORD PTR [r13-16]
    cmp edx, ecx
    jae JS_FrameTruthMSVCOldSlow
    mov r9d, DWORD PTR [r8+QJS_ABI_BIT_JSString_hash_BYTE]
    shr r9d, 28
    and r9d, 3
    lea r10, [r8+24]
    test r9d, r9d
    jz JS_FrameLatinIndexConsume_data
    cmp r9d, 1
    je JS_FrameLatinIndexConsume_slice
    cmp r9d, 2
    jne JS_FrameTruthMSVCOldSlow
    mov r10, QWORD PTR [r8+24]
    jmp JS_FrameLatinIndexConsume_data
JS_FrameLatinIndexConsume_slice:
    mov r10, QWORD PTR [r8+24]
    mov ecx, DWORD PTR [r8+32]
    lea r10, [r10+rcx+24]
JS_FrameLatinIndexConsume_data:
    test BYTE PTR [r8+QJS_ABI_BIT_JSString_is_wide_char_BYTE], QJS_ABI_BIT_JSString_is_wide_char_MASK
    jnz JS_FrameLatinIndexConsume_wide
    movzx eax, BYTE PTR [r10+rdx]
    jmp JS_FrameLatinIndexConsume_unit
JS_FrameLatinIndexConsume_wide:
    movzx eax, WORD PTR [r10+rdx*2]
JS_FrameLatinIndexConsume_unit:
    cmp eax, 256
    jae JS_FrameTruthMSVCOldSlow
    mov r11, QWORD PTR [rbx+56]
    lea r9, [rip+JS_FrameSmallCharOwners]
    xor ecx, ecx
JS_FrameLatinIndexConsume_owner:
    cmp QWORD PTR [r9+rcx*8], r11
    je JS_FrameLatinIndexConsume_owned
    inc ecx
    cmp ecx, 16
    jb JS_FrameLatinIndexConsume_owner
    jmp JS_FrameTruthMSVCOldSlow
JS_FrameLatinIndexConsume_owned:
    shl ecx, 8
    add ecx, eax
    lea r9, [rip+JS_FrameSmallCharValues]
    mov r10, QWORD PTR [r9+rcx*8]
    test r10, r10
    jz JS_FrameTruthMSVCOldSlow
    inc DWORD PTR [r10+QJS_ABI_REF_COUNT_OFFSET]
    dec DWORD PTR [r8+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r13-32], r10
    mov QWORD PTR [r13-24], -7
    sub r13, 16
    add r12, 1
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameLatinIndexConsume_end:
.p2align 4
.globl JS_FrameLatinIndexKeep, JS_FrameLatinIndexKeep_end
.def JS_FrameLatinIndexKeep; .scl 2; .type 32; .endef
JS_FrameLatinIndexKeep:
    cmp DWORD PTR [r13-24], -7
    jne JS_FrameTruthMSVCOldSlow
    mov r8, QWORD PTR [r13-32]
    mov eax, DWORD PTR [rip+JS_FrameSmallCharMode]
    and eax, 3
    cmp eax, 1
    jne JS_FrameTruthMSVCOldSlow
    mov ecx, DWORD PTR [r8+QJS_ABI_BIT_JSString_len_BYTE]
    and ecx, 0x7fffffff
    mov edx, DWORD PTR [r13-16]
    cmp edx, ecx
    jae JS_FrameTruthMSVCOldSlow
    mov r9d, DWORD PTR [r8+QJS_ABI_BIT_JSString_hash_BYTE]
    shr r9d, 28
    and r9d, 3
    lea r10, [r8+24]
    test r9d, r9d
    jz JS_FrameLatinIndexKeep_data
    cmp r9d, 1
    je JS_FrameLatinIndexKeep_slice
    cmp r9d, 2
    jne JS_FrameTruthMSVCOldSlow
    mov r10, QWORD PTR [r8+24]
    jmp JS_FrameLatinIndexKeep_data
JS_FrameLatinIndexKeep_slice:
    mov r10, QWORD PTR [r8+24]
    mov ecx, DWORD PTR [r8+32]
    lea r10, [r10+rcx+24]
JS_FrameLatinIndexKeep_data:
    test BYTE PTR [r8+QJS_ABI_BIT_JSString_is_wide_char_BYTE], QJS_ABI_BIT_JSString_is_wide_char_MASK
    jnz JS_FrameLatinIndexKeep_wide
    movzx eax, BYTE PTR [r10+rdx]
    jmp JS_FrameLatinIndexKeep_unit
JS_FrameLatinIndexKeep_wide:
    movzx eax, WORD PTR [r10+rdx*2]
JS_FrameLatinIndexKeep_unit:
    cmp eax, 256
    jae JS_FrameTruthMSVCOldSlow
    mov r11, QWORD PTR [rbx+56]
    lea r9, [rip+JS_FrameSmallCharOwners]
    xor ecx, ecx
JS_FrameLatinIndexKeep_owner:
    cmp QWORD PTR [r9+rcx*8], r11
    je JS_FrameLatinIndexKeep_owned
    inc ecx
    cmp ecx, 16
    jb JS_FrameLatinIndexKeep_owner
    jmp JS_FrameTruthMSVCOldSlow
JS_FrameLatinIndexKeep_owned:
    shl ecx, 8
    add ecx, eax
    lea r9, [rip+JS_FrameSmallCharValues]
    mov r10, QWORD PTR [r9+rcx*8]
    test r10, r10
    jz JS_FrameTruthMSVCOldSlow
    inc DWORD PTR [r10+QJS_ABI_REF_COUNT_OFFSET]
    mov QWORD PTR [r13-16], r10
    mov QWORD PTR [r13-8], -7
    add r12, 1
    movzx eax, BYTE PTR [r12]
    jmp QWORD PTR [rdi+rax*8]
JS_FrameLatinIndexKeep_end:
.p2align 4
.globl JS_FrameLatinIndexOff, JS_FrameLatinIndexOff_end
.def JS_FrameLatinIndexOff; .scl 2; .type 32; .endef
JS_FrameLatinIndexOff:
    jmp JS_FrameTruthMSVCOldSlow
JS_FrameLatinIndexOff_end:
.section .pdata$zzlatinindex,"dr"
.p2align 2
.rva JS_FrameLatinIndexConsume, JS_FrameLatinIndexConsume_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameLatinIndexKeep, JS_FrameLatinIndexKeep_end, JS_FrameInterpPropertyCold_unwind
.rva JS_FrameLatinIndexOff, JS_FrameLatinIndexOff_end, JS_FrameInterpPropertyCold_unwind
